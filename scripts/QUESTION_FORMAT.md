# Question JSON Format & LaTeX Writing Rules

## JSON Structure

```json
{
  "quiz": {
    "title": "...",
    "description": "...",
    "category": "TWK" | "TIU" | "TKP",
    "time_limit": 25
  },
  "questions": [
    {
      "type": "MCQ" | "TRUE_FALSE" | "ESSAY",
      "content": "Question text, may include $math$",
      "position": 1,
      "explanation": "Shown after answering. May include $math$.",
      "options": [
        { "label": "A", "content": "...", "score": 0, "is_correct": false },
        { "label": "B", "content": "...", "score": 5, "is_correct": true }
      ]
    }
  ]
}
```

**Scoring:**
- MCQ / TRUE_FALSE: correct option gets `"score": 5`, all others `"score": 0`
- TKP: no `is_correct` option; each option gets a weighted `"score"` from 1–5

---

## LaTeX Rules (LaTeXSwiftUI / KaTeX)

### 1. Delimiters

| Mode    | Delimiter        | Use for                        |
|---------|------------------|--------------------------------|
| Inline  | `$...$`          | Math within a sentence         |
| Display | `$$...$$`        | Standalone equations (centered)|

```
Good:  "Jika $x + 2 = 5$, maka $x$ adalah:"
Good:  "Rumus luas: $$L = \frac{1}{2} \times a \times t$$"
```

### 2. Fractions — always use `\frac`, never `\dfrac`

`\dfrac` causes a rendering artifact (black block) in certain inline contexts.

```
Good:  $\frac{3}{4}$
Bad:   $\dfrac{3}{4}$
```

### 3. Every digit in math mode — wrap with `\text{}`

LaTeXSwiftUI renders bare digits in math mode with rendering artifacts.
**Every digit sequence anywhere inside `$...$` must be wrapped in `\text{}`.**
This includes digits in bases, exponents, fractions, square roots, and results.

```
Good:  $\text{1}\frac{\text{1}}{\text{4}}$   ← JSON: $\\text{1}\\frac{\\text{1}}{\\text{4}}$
Bad:   $1\frac{1}{4}$                         ← rendering artifact

Good:  $\text{2}^{\text{5}}$                  ← JSON: $\\text{2}^{\\text{5}}$
Bad:   $2^5$                                   ← broken rendering

Good:  $\text{2}^{\text{5}+\text{3}-\text{4}}$   ← digits inside ^{...} also wrapped
Bad:   $\text{2}^{5+3-4}$                          ← digits inside exponent still break

Good:  $\frac{\text{22}}{\text{7}} \times \text{7}^{\text{2}} = \text{154}$
```

**Rule:** if it's a digit and it's inside `$...$`, it needs `\text{}`. No exceptions.

### 4. Percentages — write as plain text, not inside `$...$`

`%` is a comment character in LaTeX, so avoid it inside math delimiters.

```
Good:  "Berapakah 25% dari 200?"
Good:  "Perhitungan: $\frac{25}{100} \times 200 = 50$"
Bad:   "Berapakah $25\%$ dari 200?"
```

### 5. Common math symbols

| Symbol        | LaTeX         | JSON (escaped) |
|---------------|---------------|----------------|
| ×             | `\times`      | `\\times`      |
| ÷             | `\div`        | `\\div`        |
| ±             | `\pm`         | `\\pm`         |
| √x            | `\sqrt{x}`    | `\\sqrt{x}`    |
| xⁿ            | `x^n`         | `x^n`          |
| xₙ            | `x_n`         | `x_n`          |
| ≤             | `\leq`        | `\\leq`        |
| ≥             | `\geq`        | `\\geq`        |
| ≠             | `\neq`        | `\\neq`        |

### 6. JSON escaping

Every backslash in LaTeX must be doubled in JSON:

| In LaTeX string | In JSON file   |
|-----------------|----------------|
| `\frac{1}{2}`   | `\\frac{1}{2}` |
| `\times`        | `\\times`      |
| `\sqrt{x}`      | `\\sqrt{x}`    |
| `x^2`           | `x^2`          |

Newlines in `content` use `\n`:
```json
"content": "1, 2, 3, ...\n\nAngka selanjutnya adalah:"
```

### 7. Keep plain text outside `$...$`

Only put actual math expressions inside math delimiters. Units, labels, and
punctuation belong outside.

```
Good:  "$L = 9 \\times 6 = 54$ cm²"
Good:  "Kecepatan $= \\frac{120}{2} = 60$ km/jam"
Bad:   "$L = 9 \\times 6 = 54 \\text{ cm}^2$"
```

---

## Quick Checklist Before Submitting

- [ ] No `\dfrac` anywhere — replaced with `\frac`
- [ ] Every digit inside `$...$` is wrapped in `\text{}`: bases, exponents, fractions, results — e.g. `$\text{2}^{\text{5}}$`, `$\frac{\text{3}}{\text{4}}$`, `$= \text{16}$` → JSON doubles backslashes
- [ ] Percentages are plain text, not inside `$...$`
- [ ] All LaTeX backslashes are doubled in JSON (`\frac` → `\\frac`)
- [ ] Each question has exactly one option with `"is_correct": true` and `"score": 5`
- [ ] Positions are sequential starting from 1
