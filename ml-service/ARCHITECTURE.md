# ML Service Architecture

## Overview

The ML service generates explanations and tips for CPNS quiz questions using two
cooperating systems: a **RAG pipeline** that retrieves similar worked examples to
guide the LLM, and a **math post-processor** that deterministically converts
plain-text math into LaTeX and evaluates numeric expressions.

---

## Part 1 — RAG Pipeline

### Phase 0 — Offline Indexing (`embed_questions.py`)

Run once before the server starts, and re-run whenever questions are added or
updated in the database.

**Input:** All quiz sets from the `quizzes` MongoDB collection. Connection is
configured via two environment variables:

| Variable      | Default                     | Description               |
| ------------- | --------------------------- | ------------------------- |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB`  | `lms`                       | Database name             |

Each quiz set document contains an embedded `questions` array. Only questions
that have at least one option are indexed (ESSAY questions without options are
skipped). The `explanation` field is included when present; `tip` is not stored
in the DB schema (it is LLM-generated at explain time) and defaults to `""`.

**Pre-processing:** For each question, `question_to_embed_text()` builds a single
string combining the question content and all answer options:

```
"35% dari 240 adalah... A. 72 | B. 84 | C. 96 | D. 108 | E. 120"
```

LaTeX is stripped first via `clean_latex()` so the embedding model sees plain text
rather than `\frac{\text{35}}{\text{100}}`.

**Embedding:** Each string is encoded with `intfloat/multilingual-e5-small`, a
117M-parameter sentence transformer trained on 100+ languages including Indonesian.
The e5 family uses asymmetric task prefixes — documents being indexed get
`"passage: ..."` prepended. This is a training-time convention that measurably
improves retrieval accuracy compared to encoding both sides identically.

The model outputs a 384-dimensional float vector per question.

**L2 normalization:** `normalize_embeddings=True` divides each vector by its
magnitude, placing all vectors on the surface of the unit hypersphere. This
converts the cosine similarity formula (dot product divided by both magnitudes)
into a plain dot product at query time, since both magnitudes are already 1.

**Storage:** Saved as two files:

| File                       | Contents                                                                                                              |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `data/embeddings.npy`      | `(N, 384)` float32 NumPy matrix                                                                                       |
| `data/questions_meta.json` | Human-readable metadata per question (content, options, correct answer, explanation, tip, quiz set title as `source`) |

**Why NumPy instead of a vector database (Pinecone, Qdrant, etc.):**
At 400 questions, a full dot-product scan over the entire matrix takes under 1ms
on CPU with NumPy — there is no retrieval bottleneck to solve. Vector databases
add network latency, operational complexity, and cost. The threshold where a
dedicated vector DB becomes worthwhile is typically around 100,000+ vectors. The
approach here is the standard "flat index" strategy, the same primitive that
FAISS's `IndexFlatIP` uses internally.

---

### Phase 1 — Server Startup (`serve.py`)

When `uvicorn serve:app` starts, the `@app.on_event("startup")` handler runs:

1. `Embedder()` is instantiated — loads the embedding model into memory and reads
   `embeddings.npy` and `questions_meta.json` from disk into a module-level global.
2. An `httpx.Client` is created for synchronous HTTP calls to Ollama (180s timeout,
   since LLM inference on CPU is slow, and `/generate` makes two sequential calls).

Both stay alive for the lifetime of the process.

---

### Phase 2 — Per-Request RAG (`/explain` endpoint)

When a request arrives with a question, its options, and the correct answer label:

#### Step 1 — Embed the query

`embedder.search(req.question, top_k=3)` calls `embed_query()`, which encodes the
incoming question text with the `"query: "` prefix — asymmetric from the
`"passage: "` used at index time. The e5 model was fine-tuned so that `query:`
vectors align well against `passage:` vectors.

#### Step 2 — Cosine similarity search

```python
scores = self.embeddings @ query_vec   # (N, 384) @ (384,) → (N,)
top_indices = np.argsort(scores)[-top_k:][::-1]
```

`self.embeddings @ query_vec` is a single matrix–vector multiply: every row is
dot-producted with the query vector simultaneously. Because both are L2-normalized,
each result is the cosine similarity between that question and the query (0 =
unrelated, 1 = identical). `np.argsort` returns all N indices sorted ascending;
`[-top_k:]` slices the top 3; `[::-1]` reverses to descending. No loop, no
database, no network call.

#### Step 3 — Build the few-shot prompt

`build_prompt()` injects the 3 retrieved examples as context shots:

```
=== Contoh 1 ===
Soal: Jika 30% dari suatu bilangan adalah 18...
Pilihan: A. 50 | B. 60 | C. 70 ...
Jawaban benar: B. 60
Output: {"explanation": "...", "tip": "..."}

=== Contoh 2 ===
...

=== Soal Baru ===
Soal: 35% dari 240 adalah...
Output:
```

The retrieved examples' explanations are stripped of LaTeX via `_strip_latex()`
before injection. Since the system prompt instructs the model to write plain-text
math, showing it `\frac{}{}` in examples would contradict that instruction. The
examples teach reasoning style and format, not notation.

#### Step 4 — LLM generation via Ollama

The prompt is sent to a local `gemma4:e4b` instance over `localhost:11434` with
`"format": "json"` to constrain the output to a valid JSON object. The model
produces `{"explanation": "...", "tip": "..."}`.

**Why few-shot over fine-tuning:** The dataset is too small to fine-tune reliably.
RAG injects domain knowledge at inference time instead, with zero training cost and
instant updates when new questions are added.

#### Step 5 — Math post-processing

Both fields go through `plain_to_latex()` (described in Part 2 below).

---

### Design Choices Summary

| Decision                            | Reason                                                                             |
| ----------------------------------- | ---------------------------------------------------------------------------------- |
| `multilingual-e5-small`             | Natively supports Indonesian; ~120 MB, runs on a cheap VPS alongside the LLM       |
| L2 normalization at index time      | Reduces cosine similarity to a dot product at query time — no division per request |
| NumPy flat matrix                   | 400 questions × 384 dims ≈ 600 KB; full scan < 1ms; zero operational overhead      |
| `"passage:"` / `"query:"` asymmetry | e5 training convention that improves retrieval over symmetric encoding             |
| Few-shot over fine-tuning           | Dataset too small for reliable fine-tuning; RAG gives instant updates              |
| LaTeX stripped from examples        | Keeps few-shot examples consistent with the plain-text math instruction            |

---

## Part 2 — Math Post-Processor (`math_parser.py`)

The model is instructed to write math in plain text (`3/4 + 5/6 =`). The
post-processor converts this deterministically to LaTeX and evaluates any
expressions the model left blank.

### Why plain text instead of asking the LLM to output LaTeX directly

LLMs are probabilistic. Asking the model to output LaTeX directly causes two
classes of failure:

1. **Corruption** — `\frac` in JSON becomes a form-feed character (`\f` + `rac`),
   breaking JSON parsing.
2. **Inconsistency** — the model sometimes writes `\frac{3}{4}`, sometimes `3/4`,
   sometimes `\dfrac` (which causes rendering artifacts in LaTeXSwiftUI).

The math post-processor eliminates both problems by separating concerns: the LLM
reasons and plans, the parser formats.

### Why the model doesn't compute results

LLMs are also unreliable at arithmetic. `35/100 × 240` might produce `84` or `82`
or `8.4` depending on the run. The system prompt instructs the model to write
expressions ending with `=` and leave the result blank — e.g. `"Maka 35/100 × 240 ="`.
The evaluator fills in the correct answer using exact `fractions.Fraction`
arithmetic.

---

### Span Detection (`_find_spans`)

The core question the post-processor must answer is: **which characters in this
string are part of a math expression?** It uses a **hot-array bitmask** — a
`bytearray` of length `n` where each position is `1` if it belongs to a math span.

#### Step 1 — Seed from anchors

Rather than describing what math _is_, the algorithm looks for characters that
almost never appear outside of math:

```python
_ANCHOR_RE = re.compile(
    r"(?<=\d)/(?=\d)|(?<=\d) / (?=\d)|(?<=[\da-zA-Z])\^|[√×÷]"
    r"|(?<![a-zA-Z])[a-zA-Z]/(?=[\da-zA-Z])"
)
```

| Pattern                                | Matches                       | Example             |
| -------------------------------------- | ----------------------------- | ------------------- |
| `(?<=\d)/(?=\d)`                       | Fraction slash between digits | `3/4`               |
| `(?<=\d) / (?=\d)`                     | Division with spaces          | `240 / 100`         |
| `(?<=[\da-zA-Z])\^`                    | Exponentiation caret          | `2^5`, `x^2`        |
| `[√×÷]`                                | Unicode math symbols          | `√169`, `3 × 4`     |
| `(?<![a-zA-Z])[a-zA-Z]/(?=[\da-zA-Z])` | Variable fraction slash       | `x/4`, `x/n`, `n/k` |

When any anchor is found, its positions are marked hot in the bytearray.

#### Step 2 — Expand outward from each anchor

From each anchor, the algorithm walks left and right, marking positions hot as
long as they look like part of the same expression. The allowed character set is:

```python
_HARD_MATH = frozenset("0123456789+-*/^√×÷=≤≥≠<>()")
```

Spaces are crossed context-awarely:

- **Going right:** continue through a space if the next character is a digit,
  `(`, `√`, `/`, `*`, or an isolated single letter (not immediately preceded or
  followed by another letter)
- **Going left:** continue through a space if the previous character is a digit,
  or an isolated single letter

Single isolated letters (`x`, `n`, `k`) are included as potential variables, but
only if not surrounded by other letters — so `x` in `x/4` and `n` in `x/n` are
included, but `d` in `dari` is not. This allows expressions like `k × n` or the
full `x = k × n` to be captured as a single span.

#### Step 3 — Mark explicit arithmetic equations

`a + b = c` and `a - b = c` patterns have no `×÷^√` anchors, so they get a
dedicated pass:

```python
_ARITH_EQ_RE = re.compile(r"\d+\s*[+\-]\s*\d+\s*=\s*\d+")
```

#### Step 3b — Mark variable arithmetic

Expressions like `x + 10` or `y - 5` have neither a fraction/power anchor nor a
trailing `= c` result that would make `_ARITH_EQ_RE` fire. A dedicated pattern
seeds them explicitly:

```python
_VAR_ARITH_RE = re.compile(r"(?<![a-zA-Z])([a-zA-Z])\s*[+\-]\s*(\d+)")
```

Every position in the match range is marked hot. This makes `x + 10` a hot region
that the connection phase can then link to an adjacent `= result` span.

#### Step 4 — Connect adjacent hot spans through operators

After the seeding phase, `3/4` and `5/6` in `3/4 + 5/6 = 19/12` are two separate
hot regions with a cold `+` between them. A multi-pass bridge loop connects them:

```
If an operator (=, +, -, *) has hot regions within 14 chars on BOTH sides → mark it hot
```

The "both sides must already be hot" guard prevents prose like `"nilai A = baik"`
from being absorbed, because neither `A` nor `baik` are hot.

#### Step 5 — Extend to adjacent results and labels

Two final passes extend hot spans outward:

- **Trailing `= number`:** if `= 13` follows a hot span (`√169 = 13`), include it
  even though `13` alone has no anchor
- **Leading `number% =` label:** if `30% =` precedes a hot span
  (`30% = 3 × 24 = 72`), extend backward to include the percentage label

#### What stays cold (untouched)

The design is intentionally conservative:

| Input                   | Why it stays prose                      |
| ----------------------- | --------------------------------------- |
| `"Ada 3 orang"`         | `3` has no nearby anchor                |
| `"Diskon 25% dari 200"` | No `×÷^√/` anchor                       |
| `"Nilai A = baik"`      | `=` flanked by two cold regions         |
| `"10% dari 240 = 24"`   | No anchor; `_ARITH_EQ_RE` doesn't match |

---

### LaTeX Conversion (`_conv`)

Once a span is identified, `_conv()` converts the raw plain-text math to LaTeX in
a fixed precedence order:

1. `√(expr)` → `\sqrt{...}` (recursive)
2. `√n` → `\sqrt{\text{n}}`
3. `base^(expr)` → `base^{(...)}` with recursive inner conversion
4. `base^n` → `base^{\text{n}}`
   5-pre. `(expr)/(expr)` → `\frac{expr}{expr}` — parenthesized groups like `(4×15)/(5×8)`, processed before digit fractions so the inner content (already converted by steps 1–4) is preserved intact
   5a. `digit/digit` → `\frac{\text{a}}{\text{b}}` (guarded against URLs and dates with `:/` lookbehind)
   5b. `letter/digit` or `letter/letter` → `\frac{letter}{\text{b}}` — variable fractions like `x/4`, `x/n`, `n/k`
5. Operator replacements: `×` → `\times`, `÷` → `\div`, `/` → `\div`, `%` → `\%`
6. Remaining bare digit sequences wrapped in `\text{}` (required by LaTeXSwiftUI)
7. Whitespace normalized

---

### Expression Evaluator (`_compute`)

When a span ends with a bare `=` (model left the result blank), `_compute()`
evaluates the left-hand side:

```python
_EVAL_NS = {"__builtins__": {}, "Fraction": Fraction, "math": math}
```

The expression is first translated to Python (`_to_python()`):

- `3/4` or `3 / 4` → `Fraction(3, 4)` — exact rational arithmetic
- `2^5` → `2**5`
- `√169` → `13` (perfect square) or `math.sqrt(169)`
- `×` → `*`, `÷` → `/`

Then `eval()` runs in a **restricted namespace** with no builtins — no file I/O,
no imports, no access to anything outside `Fraction` and `math`. The result is
formatted back to plain text:

| Result type                   | Example output |
| ----------------------------- | -------------- |
| `Fraction` with denominator 1 | `84`           |
| Proper fraction               | `3/4`          |
| Mixed number                  | `1 7/12`       |
| Float (irrational)            | `1.4142`       |

For multi-step chains (`35/100 × 240 = 35 × 240 / 100 = 8400 / 100 =`), evaluating
the whole expression fails (multiple `=` signs). The evaluator falls back to the
last sub-expression after the final `=`, computing just `8400 / 100 = 84`.

---

### Prose Number Wrapping (`_wrap_numbers_in_prose`)

If `_find_spans()` detected **any** math span in the text, the whole response is
treated as a mathematical context. All remaining bare numbers in prose are then
wrapped:

- `240` → `$\text{240}$`
- `35%` → `$\text{35}\%$`

**Trigger:** Only fires when at least one math span was found. A response with no
detected math (pure prose) is left completely untouched.

**Implementation:** Existing `$...$` blocks are protected with letter-indexed
placeholders (`\x01A\x01`, `\x01B\x01`, …) before the number-wrapping regex runs,
then restored afterward. Letter-based (not digit-based) placeholders are used
specifically to prevent the digit-wrapping regex from corrupting the placeholder
indices themselves. A single-pass alternation regex (`\d+%` before `\d+`) prevents
double-wrapping of `35%` as `$\text{$\text{35}$}\%$`.

---

## Part 3 — Question Generation Pipeline (`/generate` endpoint)

### Overview

Unlike `/explain` (which is given the correct answer and asked to justify it),
`/generate` must invent a new question from scratch — content, five options, and
the correct answer label — then verify the answer is actually right. It uses two
LLM calls plus a Python arithmetic layer.

---

### Phase 1 — RAG Retrieval

```python
examples = embedder.search(req.source_question, top_k=5)
```

Same embedding + dot-product search as `/explain`, but `top_k=5` (vs. 3) to
capture more style diversity. The source question is filtered out if it appears
in the store.

---

### Phase 2 — Prompt Construction (`build_generation_prompt`)

Up to 3 retrieved examples (those that have an `explanation`) are serialised as
full JSON objects — `content`, `options`, `correct_label`, `explanation`, `tip`
— rather than the key-value text format used by `/explain`. All explanations pass
through `_strip_latex()` first so the LLM sees plain-text math.

After the examples, the reference question appears as `=== Soal Referensi ===`
with its category, options, and correct label.

The `GENERATION_SYSTEM_PROMPT` extends the explain system prompt with two extra
requirements: produce exactly 5 options (A–E) and include a `correct_label` field.
The "end arithmetic with `=`" convention still applies.

---

### Phase 3 — First LLM Call (Generation)

`call_ollama(user_message, GENERATION_SYSTEM_PROMPT)` returns a JSON object with
`content`, `options` (array of 5 objects), `correct_label`, `explanation`, and `tip`.

**Structural validation** runs immediately before any math logic:

| Check                                                | Failure action                  |
| ---------------------------------------------------- | ------------------------------- |
| `len(options) == 5`                                  | HTTP 500 — Rust backend retries |
| `correct_label` is one of the returned option labels | HTTP 500 — Rust backend retries |

---

### Phase 4 — Answer Verification (Three-Layer System)

The core reliability problem: LLMs frequently pick the wrong option as `correct_label`,
or generate options that don't contain the mathematically correct answer at all.
Three layers catch these failures in order of confidence.

#### Layer 1 — Direct Computation from Question Content (`_compute_from_content`)

For arithmetic questions the question text itself contains the expression to evaluate
(e.g. `"Berapakah hasil dari 72 ÷ 8 × 3?"`). This layer:

1. Strips LaTeX from the generated content; normalises superscripts
2. Runs `_find_spans()` to locate math expressions
3. If multiple spans exist, joins from first-start to last-end and evaluates the whole
4. Falls back to individual spans evaluated longest-first (catches `√169`, single-term questions)
5. Compares the computed result against every option via exact string match, then float comparison

Returns:

- **A label string** — computed answer matches an option → use as `correct_label`, skip layers 2 & 3
- **`_NOT_FOUND`** — answer computed but not present in any option → HTTP 500, reject immediately
- **`None`** — no computable expression found (verbal, analogy, sequence question) → fall through to layer 2

#### Layer 2 — LLM Self-Correction (conditional on Layer 1 returning `None`)

The generated question is sent back to Ollama under `CORRECTION_SYSTEM_PROMPT`,
which instructs the model to:

- Compute the correct answer itself from `content` + `explanation`
- Apply the minimum fix: change `correct_label` if the right value is already in another
  option, or overwrite the option content if no option contains the right answer
- Return the same JSON structure completely unchanged if already consistent

The corrected output replaces the original if it still passes structural validation
(5 options, valid label). A failed correction is silently ignored and the original kept.

#### Layer 3 — Python Deterministic Inference (`_infer_correct_label`)

Always runs after layer 2. Operates on the explanation text:

1. `_strip_latex()` — reverts any LaTeX the model produced despite instructions
2. `_fix_arithmetic_in_explanation()` — finds all math spans that already contain a
   stated result (`98 + 15 = 103`), recomputes the correct value via `_compute()`,
   and silently corrects wrong values before inference runs. This prevents a
   hallucinated intermediate result from producing a wrong final label.
3. Extracts every `= <token>` from the corrected explanation via regex; the **last**
   token is treated as the final answer
4. Matches against options: exact string → float comparison → `_compute()` evaluation

Returns:

- **A label string** → override `correct_label` (even if layers 1 and 2 agreed)
- **`_NOT_FOUND`** → explanation has an answer but no option matches → HTTP 500
- **`_NO_MATH`** → purely verbal explanation, no `=` tokens → keep current `correct_label`

---

### Phase 5 — Math Formatting (`_build_and_log`)

`_strip_latex()` then `plain_to_latex()` is applied to all six text fields: `content`,
`explanation`, `tip`, and the content of all five options. The strip-then-reparse
pattern ensures consistent output even if the model produced partial LaTeX despite
instructions.

All transformations are printed to stdout for debugging.

---

### `/generate` vs `/explain` at a Glance

| Aspect                                    | `/explain`                         | `/generate`                                                   |
| ----------------------------------------- | ---------------------------------- | ------------------------------------------------------------- |
| LLM receives                              | Existing question + correct answer | Source question + style examples                              |
| LLM produces                              | `{explanation, tip}`               | `{content, options[5], correct_label, explanation, tip}`      |
| RAG `top_k`                               | 3                                  | 5                                                             |
| LLM calls                                 | 1                                  | 1 generation + 1 correction (conditional)                     |
| Answer verification                       | None — answer given as input       | 3-layer: direct math eval → LLM correction → Python inference |
| Fields post-processed by `plain_to_latex` | 2                                  | 6                                                             |
| Can reject with HTTP 500                  | No                                 | Yes — invalid structure or unverifiable answer                |
