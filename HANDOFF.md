# Session Handoff

## 1. Ultimate Goal

An iPad-first LMS for Indonesian CPNS (Civil Servant) exam preparation.

The full system has three layers:
- **Rust backend** (`server/`) — Axum + MongoDB, REST API for quiz sets, questions, sessions
- **Next.js admin web** (`admin-web/`) — dashboard for managing quiz sets, questions, bulk import
- **SwiftUI iPad app** (`client-ios/`) — offline-first quiz experience with PencilKit handwriting canvas

The actively developed fourth layer is the **ML service** (`apps/ml-service/`) — a
Python FastAPI server that generates LaTeX-formatted explanations and study tips for
quiz questions using a RAG pipeline (retrieval-augmented generation) backed by
a local Ollama LLM.

The next major feature on the backlog is **AI question generation for the admin**
— allowing the admin web to request new questions from the ML service rather than
writing them manually.

---

## 2. Files Altered This Session

All changes this session are confined to `apps/ml-service/`.

### `apps/ml-service/serve.py` — Modified

- **Removed** the `code` field from the JSON output schema and the entire
  `execute_code_safely()` sandbox machinery (~80 lines). The inline math evaluator
  in `math_parser.py` replaces this.
- **Updated `SYSTEM_PROMPT`** — three key changes:
  1. Added `"Gunakan Bahasa Indonesia sepenuhnya"` to prevent English bleed-through
  2. Reduced fields from `{explanation, code, tip}` to `{explanation, tip}`
  3. Instructs the model to write expressions ending with `=` and leave results
     blank (e.g. `"Maka 35/100 × 240 ="`) — the evaluator fills them in
- **Updated `build_prompt()`** — removed `"code": null` from few-shot example
  output format to match the new schema
- **Updated `explain()` endpoint** — removed code execution block; now just calls
  `plain_to_latex()` on both fields

### `apps/ml-service/math_parser.py` — Created (new file)

Full deterministic plain-text math → LaTeX converter and evaluator. Replaces the
old `_latex_postprocess` approach of asking the LLM to output LaTeX directly.

Key components (in order of execution):

**Evaluator (`_to_python`, `_format_result`, `_compute`)**
- Translates plain-text math to Python: `3/4` or `3 / 4` → `Fraction(3,4)`,
  `2^5` → `2**5`, `√169` → `13`, `×` → `*`, `÷` → `/`
- Evaluates in a restricted namespace `{"__builtins__": {}, "Fraction": ..., "math": ...}`
- Formats results as integers, proper fractions, or mixed numbers (`1 7/12`)
- Only evaluates expressions that contain an arithmetic operator — bare `3/4`
  is left unevaluated

**Span detector (`_find_spans`)**
Uses a `bytearray` hot-array bitmask. Five-pass strategy:
1. Seed from anchors: `(?<=\d)/(?=\d)`, `(?<=\d) / (?=\d)`, `\^`, `[√×÷]`
2. Expand left/right consuming `_HARD_MATH` chars and context-aware spaces
   (right expansion also crosses space before `/` and `*`)
3. Seed explicit arithmetic equations via `_ARITH_EQ_RE` (`\d+\s*[+\-]\s*\d+\s*=\s*\d+`)
4. Connect adjacent hot spans through `=`, `+`, `-`, `*` operators
   (both sides must already be hot — guards against prose like `"nilai A = baik"`)
5. Extend hot spans to include trailing `= number` results and leading `number% =` labels

**Converter (`_conv`)**
Converts a raw plain-text math span to LaTeX in fixed precedence order:
`√(expr)` → `\sqrt{}`, `√n`, `base^(expr)`, `base^n`, `a/b` → `\frac{}{}`,
operator replacements (`×`→`\times`, ` / `→`\div`, `%`→`\%`),
`_wrap_digits()` wraps remaining bare digit sequences in `\text{}`
(required by LaTeXSwiftUI renderer)

**Public API (`plain_to_latex`)**
- Guards existing `$...$` blocks from modification
- Finds spans, converts each to LaTeX
- For spans followed by a bare `=`: evaluates the LHS via `_compute`; on failure
  (multi-step chain), falls back to evaluating only the last sub-expression
- After assembly, calls `_wrap_numbers_in_prose()` if any math was detected

**Prose number wrapper (`_wrap_numbers_in_prose`)**
- Only fires if at least one math span was detected in the text
- Protects existing `$...$` blocks using letter-indexed placeholders
  (`\x01A\x01`, `\x01B\x01`, …) — letter-based to prevent the digit-wrapping
  regex from corrupting numeric placeholder indices
- Single-pass alternation regex (`\d+%` before `\d+`) prevents double-wrapping
- Wraps `35%` → `$\text{35}\%$`, `240` → `$\text{240}$`

### `apps/ml-service/ARCHITECTURE.md` — Created (new file)

Comprehensive documentation of both the RAG pipeline and the math post-processor.
Covers methodology, design decisions, and the reasoning behind each choice
(e.g. NumPy flat matrix vs. vector database, few-shot vs. fine-tuning,
plain-text math vs. LLM-generated LaTeX).

---

## 3. Next Logical Steps

### Immediate — AI Question Generation for Admin

The last discussed feature. Architectural decision already made: **shared vector
store, separate prompt logic**.

Concretely:

1. **Add `/generate` endpoint to `serve.py`**
   - Request schema: `{category, question_type, topic_hint, count}`
   - Calls `embedder.search(topic_hint, top_k=5)` — reuses existing `Embedder`
     instance, same embeddings, no new infrastructure
   - Builds a generation-specific few-shot prompt via a new `build_generation_prompt()`
     that shows retrieved questions as style examples
   - New system prompt instructs the model to output an array of questions
     matching `[{content, options: [{label, content, is_correct}], explanation, tip}]`
   - Post-processes each generated question's `explanation` and `tip` through
     `plain_to_latex()`

2. **Add generation UI to admin web**
   - A "Generate Questions" button/panel on the quiz set detail page
   - Inputs: category (TWK/TIU/TKP), question type, topic hint (free text), count
   - Displays generated questions in a review table — admin can accept, edit, or
     discard each one before saving to the database

3. **Wire admin web → Rust backend → ML service**
   - The admin web calls the Rust backend, which proxies to the ML service
     via Unix socket (same pattern as the existing explanation endpoint in
     `server/src/ml_client.rs`)
   - Rust validates and saves accepted questions to MongoDB

### Also Pending (pre-existing, not touched this session)

- **`server/src/service_manager.rs`** (untracked) — auto-start Ollama + ML service
  from Rust on server startup. Plan exists at
  `.claude/plans/valiant-snuggling-willow.md`. Not yet implemented.
- **`apps/ml-service/embed_questions.py`** — needs to be re-run whenever new
  `tiu_*.json` files are added to `scripts/`. Currently 14 new JSON files are
  untracked (`scripts/tiu_analogi.json` through `scripts/tiu_soal_cerita_2.json`)
  that have NOT been embedded yet. Run `python embed_questions.py` inside
  `apps/ml-service/` after any environment setup to pick them up.
- **iOS client** — `client-ios/lms/Views/MathTextView.swift` was modified
  (likely to handle the new `$\text{N}$` LaTeX format). Verify rendering of
  the updated output format on device/simulator.
