"""
math_parser.py — Plain-text math → LaTeX converter for CPNS explanations.

Detects mathematical expressions written in natural notation and wraps them in
$...$ with proper LaTeX commands.  The LLM is never asked to output LaTeX;
this module handles the conversion deterministically.

Supported input patterns
------------------------
  Fractions:      3/4   35/100   9/12
  Powers:         2^5   x^2   2^(5+3-4)
  Square roots:   √169   √(a+b)
  Arithmetic:     3 × 4   60 ÷ 5
  Equations:      3/4 + 5/6 = 19/12   2^5 × 2^3 = 256
  Mixed numbers:  1 7/12  (space-separated whole + fraction)

Prose numbers are left untouched:
  "Ada 3 orang dan 5 soal."  →  unchanged
  "Diskon 25% dari 200"      →  unchanged
"""
from __future__ import annotations

import math
import re
from fractions import Fraction


# ── Unicode superscript normalizer ─────────────────────────────────────────────

_SUPERSCRIPT_CHARS = frozenset("⁰¹²³⁴⁵⁶⁷⁸⁹")
_SUPERSCRIPT_MAP   = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def _normalize_superscripts(text: str) -> str:
    """
    Convert Unicode superscript digits to caret notation.

    Examples:  5²  →  5^2
               5²³ →  5^23   (consecutive superscripts become one exponent)
               5²×5³÷5⁴ →  5^2×5^3÷5^4
    """
    if not any(c in _SUPERSCRIPT_CHARS for c in text):
        return text          # fast-path: most text has no superscripts
    parts: list[str] = []
    i = 0
    while i < len(text):
        if text[i] in _SUPERSCRIPT_CHARS:
            j = i
            while j < len(text) and text[j] in _SUPERSCRIPT_CHARS:
                j += 1
            parts.append("^" + text[i:j].translate(_SUPERSCRIPT_MAP))
            i = j
        else:
            parts.append(text[i])
            i += 1
    return "".join(parts)


# ── Math evaluator ────────────────────────────────────────────────────────────
# Converts a plain-text expression to Python and evaluates it with exact
# fraction arithmetic.  Used to fill in "expr =" spans so the model never
# has to produce numerical results.

def _to_python(expr: str) -> str | None:
    """
    Convert a plain-text math expression to an evaluable Python string.
    Returns None if the expression contains non-numeric variables.
    """
    e = _normalize_superscripts(expr.strip())
    # Single-letter variables → can't evaluate algebraically
    if re.search(r"(?<![a-zA-Z])[a-zA-Z](?![a-zA-Z])", e):
        return None

    # √(expr) — recursive
    def _sqrt_paren(m: re.Match) -> str:
        inner = _to_python(m.group(1))
        return f"math.sqrt({inner})" if inner else m.group(0)

    e = re.sub(r"√\(([^)]+)\)", _sqrt_paren, e)

    # √n — substitute perfect square directly, else keep as float
    def _sqrt_n(m: re.Match) -> str:
        n = int(m.group(1))
        sq = math.isqrt(n)
        return str(sq) if sq * sq == n else f"math.sqrt({n})"

    e = re.sub(r"√(\d+)", _sqrt_n, e)

    # a^(expr) → a**(expr),  a^b → a**b
    e = re.sub(r"(\d+)\^\(([^)]+)\)", r"\1**(\2)", e)
    e = re.sub(r"(\d+)\^(\d+)",       r"\1**\2",    e)

    # a/b or a / b → Fraction(a, b) for exact arithmetic
    e = re.sub(r"(\d+)\s*/\s*(\d+)", r"Fraction(\1,\2)", e)

    # Unicode operators
    e = e.replace("×", "*").replace("÷", "/")

    return e


def _format_result(v: object) -> str:
    """Format a computed value as a plain-text string."""
    if isinstance(v, Fraction):
        if v.denominator == 1:
            return str(v.numerator)
        # Mixed number when |numerator| > denominator
        if abs(v.numerator) > v.denominator:
            whole = v.numerator // v.denominator
            rem   = abs(v.numerator % v.denominator)
            return f"{whole} {rem}/{v.denominator}" if rem else str(whole)
        return f"{v.numerator}/{v.denominator}"
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(round(v, 4))
    return str(v)


_EVAL_NS = {"__builtins__": {}, "Fraction": Fraction, "math": math}


def _compute(expr: str) -> str | None:
    """
    Evaluate a plain-text math expression.

    Only evaluates expressions that contain an arithmetic operator (×, ÷, ^, √,
    +, -) so bare fractions like "3/4" are left untouched.

    Returns the formatted result string, or None if not evaluable.
    """
    if not re.search(r"[+\-×÷*/^√]", expr):
        return None  # bare number or fraction — don't evaluate

    py = _to_python(expr)
    if py is None:
        return None
    try:
        result = eval(py, _EVAL_NS)           # noqa: S307 — restricted namespace
        return _format_result(result)
    except Exception:
        return None


# ── Internal: digit wrapper ────────────────────────────────────────────────────

def _wrap_digits(s: str) -> str:
    """Wrap bare digit sequences in \\text{} inside a LaTeX fragment."""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i : i + 6] == "\\text{":
            # Already wrapped — copy until matching closing brace
            depth, j = 1, i + 6
            while j < len(s) and depth > 0:
                depth += (s[j] == "{") - (s[j] == "}")
                j += 1
            out.append(s[i:j]); i = j
        elif s[i] == "\\":
            # LaTeX command — copy as-is
            j = i + 1
            while j < len(s) and (s[j].isalpha() or s[j] == "*"):
                j += 1
            out.append(s[i:j]); i = j
        elif s[i].isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append(f"\\text{{{s[i:j]}}}"); i = j
        else:
            out.append(s[i]); i += 1
    return "".join(out)


def _tw(s: str) -> str:
    """Wrap number in \\text{}; leave single-letter variable as-is."""
    return f"\\text{{{s}}}" if re.fullmatch(r"\d+", s) else s


# ── Internal: span converter ───────────────────────────────────────────────────

def _conv(s: str) -> str:
    """
    Convert a plain-text math span to LaTeX (no surrounding $...$).

    Applied in precedence order so complex patterns are handled first.
    """
    # 1. √(expr) — recursive
    s = re.sub(
        r"√\(([^)]*)\)",
        lambda m: f"\\sqrt{{{_conv(m.group(1))}}}",
        s,
    )
    # 2. √n
    s = re.sub(
        r"√(\d+)",
        lambda m: f"\\sqrt{{\\text{{{m.group(1)}}}}}",
        s,
    )
    # 3. base^(expr) — power with parenthesised exponent
    s = re.sub(
        r"(\d+|(?<![a-zA-Z])[a-zA-Z](?![a-zA-Z]))\^\(([^)]*)\)",
        lambda m: f"{_tw(m.group(1))}^{{({_conv(m.group(2))})}}" ,
        s,
    )
    # 4. base^n — simple power
    s = re.sub(
        r"(\d+|(?<![a-zA-Z])[a-zA-Z](?![a-zA-Z]))\^(\d+)",
        lambda m: f"{_tw(m.group(1))}^{{\\text{{{m.group(2)}}}}}",
        s,
    )
    # 5. a/b — fraction
    # 5-pre. (expr)/(expr) — parenthesized fraction, e.g. (4×15)/(5×8)
    s = re.sub(
        r"\(([^()]+)\)/\(([^()]+)\)",
        lambda m: f"\\frac{{{m.group(1)}}}{{{m.group(2)}}}",
        s,
    )
    # 5a. digit/digit (guard against URLs/dates with :/\d lookbehind/lookahead)
    s = re.sub(
        r"(?<![:/\d])(\d+)/(\d+)(?![:/\d])",
        lambda m: f"\\frac{{\\text{{{m.group(1)}}}}}{{\\text{{{m.group(2)}}}}}",
        s,
    )
    # 5b. single-letter variable / (digit+ or single letter): x/4, x/n, y/7, n/k
    s = re.sub(
        r"(?<![a-zA-Z\d:/])([a-zA-Z])/(\d+|[a-zA-Z](?![a-zA-Z]))(?![a-zA-Z\d:/])",
        lambda m: f"\\frac{{{m.group(1)}}}{{{_tw(m.group(2))}}}",
        s,
    )
    # 6. Operators
    s = s.replace("×", "\\times").replace("÷", "\\div").replace("*", "\\cdot")
    s = s.replace(" / ", " \\div ")  # spaced division not caught by step 5
    s = s.replace("%", "\\%")
    # 7. Wrap remaining bare digit sequences
    s = _wrap_digits(s)
    # 8. Normalise whitespace
    return re.sub(r" {2,}", " ", s).strip()


# ── Internal: span detection ───────────────────────────────────────────────────

# Characters that may appear inside a math span (non-space, non-letter)
_HARD_MATH = frozenset("0123456789+-*/^√×÷=≤≥≠<>()")

# Anchors: fraction slash (digit/digit or digit / digit), power caret, root, unicode arithmetic,
# single-letter variable before slash: x/4, y/7, x/n etc.
_ANCHOR_RE = re.compile(r"(?<=\d)/(?=\d)|(?<=\d) / (?=\d)|(?<=[\da-zA-Z])\^|[√×÷]|(?<![a-zA-Z])[a-zA-Z]/(?=[\da-zA-Z])")

# Explicit arithmetic equations: 13 + 3 = 16, 20 - 5 = 15 (not caught by anchors above)
_ARITH_EQ_RE = re.compile(r"\d+\s*[+\-]\s*\d+\s*=\s*\d+")

# Variable arithmetic: single-letter ± number — e.g. "x + 10", "y - 5"
# Used to seed hot regions so the connection phase links them to adjacent spans.
_VAR_ARITH_RE = re.compile(r"(?<![a-zA-Z])([a-zA-Z])\s*[+\-]\s*(\d+)")


def _math_char(c: str) -> bool:
    return c in _HARD_MATH


def _find_spans(text: str) -> list[tuple[int, int]]:
    """
    Return (start, end) pairs for detected math spans.

    Strategy:
      1. Seed from anchors (/^√×÷).
      2. Expand left/right consuming math chars and context-aware spaces.
      3. Connect adjacent spans through = signs (both sides must be hot).
    """
    n = len(text)
    hot = bytearray(n)

    for m in _ANCHOR_RE.finditer(text):
        for k in range(m.start(), m.end()):
            hot[k] = 1

        # ── Expand LEFT ───────────────────────────────────────────────────────
        j = m.start() - 1
        while j >= 0:
            c = text[j]
            if _math_char(c):
                hot[j] = 1; j -= 1
            elif c == " " and j > 0 and (
                text[j - 1].isdigit()
                # also bridge through space when preceding char is an isolated letter (variable)
                or (text[j - 1].isalpha() and not (j > 1 and text[j - 2].isalpha()))
            ):
                hot[j] = 1; j -= 1
            elif (
                c.isalpha()
                and not (j > 0 and text[j - 1].isalpha())
                and (j + 1 >= n or not text[j + 1].isalpha())
            ):
                hot[j] = 1; j -= 1
            else:
                break

        # ── Expand RIGHT ─────────────────────────────────────────────────────
        j = m.end()
        while j < n:
            c = text[j]
            if _math_char(c):
                hot[j] = 1; j += 1
            elif c == " " and j + 1 < n and (
                text[j + 1].isdigit() or text[j + 1] in "(√" or text[j + 1] in "/*"
                # also bridge through space when next char is an isolated letter (variable)
                or (text[j + 1].isalpha() and (j + 2 >= n or not text[j + 2].isalpha()))
            ):
                hot[j] = 1; j += 1
            elif (
                c.isalpha()
                and (j == 0 or not text[j - 1].isalpha())
                and (j + 1 >= n or not text[j + 1].isalpha())
            ):
                hot[j] = 1; j += 1
            else:
                break

    # ── Mark explicit arithmetic equations: a + b = c, a - b = c ────────────
    # These have no ×/÷/^/√ anchor but are clearly calculations.
    for m in _ARITH_EQ_RE.finditer(text):
        for k in range(m.start(), m.end()):
            hot[k] = 1

    # ── Mark variable arithmetic: single-letter ± number ─────────────────────
    # e.g. "x + 10", "y - 5" — seeds hot region so the connection phase can
    # link it to an adjacent "= result" or digit-only expression.
    for m in _VAR_ARITH_RE.finditer(text):
        for k in range(m.start(), m.end()):
            hot[k] = 1

    # ── Connect adjacent hot spans through arithmetic operators ─────────────
    # Run multiple passes so chains like A + B = C + D all merge.
    for op_pattern in [r"[=+\-]", r"\*"]:
        changed = True
        while changed:
            changed = False
            for m in re.finditer(op_pattern, text):
                pos = m.start()
                if hot[pos]:
                    continue
                left_hot  = pos > 0   and any(hot[max(0, pos - 14) : pos])
                right_hot = pos < n-1 and any(hot[pos + 1 : min(n, pos + 15)])
                if left_hot and right_hot:
                    hot[pos] = 1
                    j = pos - 1
                    while j >= 0 and text[j] == " ":
                        hot[j] = 1; j -= 1
                    j = pos + 1
                    while j < n and text[j] == " ":
                        hot[j] = 1; j += 1
                    changed = True

    # ── Extend hot spans to include trailing "= number/letter" result ──────────
    # e.g. "√169 = 13" — 13 has no anchor; "x/n = k" — k is a single-letter result.
    for m in re.finditer(r"=\s*(\d+|[a-zA-Z](?![a-zA-Z]))", text):
        eq_pos = m.start()
        if not any(hot[max(0, eq_pos - 14) : eq_pos + 1]):
            continue
        # Bridge any whitespace gap back to the hot span
        j = eq_pos - 1
        while j >= 0 and text[j] == " ":
            hot[j] = 1; j -= 1
        # Also consume a preceding isolated single-letter variable, e.g. "x = 12 × 4"
        if (j >= 0 and text[j].isalpha()
                and not (j > 0 and text[j - 1].isalpha())
                and (j + 1 >= n or not text[j + 1].isalpha())):
            hot[j] = 1; j -= 1
            while j >= 0 and text[j] == " ":
                hot[j] = 1; j -= 1
        for k in range(eq_pos, m.end()):
            hot[k] = 1

    # ── Extend hot spans BACKWARD to include "number% =" label prefix ────────
    # e.g. "30% = 3 × 24 = 72" — 30% has no anchor but labels the hot span.
    for m in re.finditer(r"\d+%\s*=\s*", text):
        eq_end = m.end()
        if not any(hot[eq_end : min(n, eq_end + 14)]):
            continue
        for k in range(m.start(), m.end()):
            hot[k] = 1

    # ── Collect contiguous hot regions (trim whitespace boundaries) ──────────
    spans: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if hot[i]:
            j = i
            while j < n and hot[j]:
                j += 1
            s, e = i, j
            while s < e and text[s] == " ":  s += 1
            while e > s and text[e - 1] == " ": e -= 1
            if s < e:
                spans.append((s, e))
            i = j
        else:
            i += 1

    return spans


# ── Public API ─────────────────────────────────────────────────────────────────

def _wrap_numbers_in_prose(s: str) -> str:
    """
    Wrap bare numbers and number% in prose regions as $\\text{N}$ / $\\text{N}\\%$.
    Existing $...$ blocks are left untouched.
    """
    protected: list[str] = []

    def _protect(m: re.Match) -> str:
        protected.append(m.group(0))
        # Letter-based index (A, B, C, ...) — avoids digit-wrapping of the index
        return f"\x01{chr(len(protected) - 1 + 65)}\x01"

    s = re.sub(r"\$\$[\s\S]+?\$\$", _protect, s)
    s = re.sub(r"\$[^\$\n]+?\$",    _protect, s)

    # Single pass — \d+% checked before \d+ to avoid double-wrapping
    def _replace(m: re.Match) -> str:
        t = m.group(0)
        if t.endswith("%"):
            return f"$\\text{{{t[:-1]}}}\\%$"
        return f"$\\text{{{t}}}$"

    s = re.sub(r"(?<!\d)\d+%(?!\d)|(?<!\d)\d+(?!\d)", _replace, s)

    for i, p in enumerate(protected):
        s = s.replace(f"\x01{chr(i + 65)}\x01", p)
    return s

def _verify_computed_results(raw: str) -> str:
    """
    If a span already contains a result (e.g. '3^5 = 81'), verify it by
    re-computing the preceding expression and replacing any wrong value.

    Handles chains: '3^(4-2+3) = 3^5 = 81' → '3^(4-2+3) = 3^5 = 243'.
    Correct spans are returned unchanged.
    """
    m = re.match(
        r"^(.*)\s*=\s*(-?\d+(?:\.\d+)?(?:\s+\d+/\d+)?|-?\d+/\d+)\s*$",
        raw,
        re.DOTALL,
    )
    if not m:
        return raw

    expr_part = m.group(1).strip()
    stated = m.group(2).strip()

    # In a chain like 'a = b = c', compute just the last sub-expression (b)
    last_eq = expr_part.rfind("=")
    sub = expr_part[last_eq + 1 :].strip() if last_eq >= 0 else expr_part

    computed = _compute(sub)
    if computed is None:
        return raw

    def _num(s: str) -> float | None:
        try:
            parts = s.strip().split()
            if len(parts) == 2 and "/" in parts[1]:
                w, frac = parts
                n, d = frac.split("/")
                return int(w) + int(n) / int(d)
            if "/" in s:
                n, d = s.strip().split("/")
                return int(n) / int(d)
            return float(s.strip())
        except Exception:
            return None

    stated_num = _num(stated)
    computed_num = _num(computed)

    if stated_num is None or computed_num is None:
        return raw
    if abs(stated_num - computed_num) < 1e-9:
        return raw  # already correct

    print(f"  [verify] correcting '{raw}' → '{expr_part} = {computed}'")
    return f"{expr_part} = {computed}"


def plain_to_latex(text: str) -> str:
    """
    Detect mathematical expressions in plain text and wrap in LaTeX $...$.

    Already-formatted $...$ blocks (if any) are left untouched.
    """
    # Guard existing $...$ blocks so they survive unmodified
    guarded: list[str] = []

    def _guard(m: re.Match) -> str:
        guarded.append(m.group(0))
        return f"\x00G{len(guarded) - 1}\x00"

    work = re.sub(r"\$\$[\s\S]+?\$\$", _guard, text)
    work = re.sub(r"\$[^\$\n]+?\$",    _guard, work)
    work = _normalize_superscripts(work)

    spans = _find_spans(work)

    if not spans:
        def _unguard(m: re.Match) -> str:
            return guarded[int(m.group(1))]
        return re.sub(r"\x00G(\d+)\x00", _unguard, work)

    parts: list[str] = []
    prev = 0
    for start, end in spans:
        parts.append(work[prev:start])
        raw = work[start:end].strip()

        # Check for a bare "=" immediately after this span (model left result blank)
        after = end
        while after < len(work) and work[after] == " ":
            after += 1
        # Look past spaces after "=" to determine what follows
        _look = after + 1
        while _look < len(work) and work[_look] == " ":
            _look += 1
        trailing_eq = (
            after < len(work)
            and work[after] == "="
            # A "bare" = has nothing (or only punctuation) after it, not a digit or letter
            and (_look >= len(work) or (not work[_look].isdigit() and not work[_look].isalpha()))
        )

        if trailing_eq:
            result = _compute(raw)
            if result is None and "=" in raw:
                # Multi-step chain: evaluate just the last sub-expression
                result = _compute(raw.rsplit("=", 1)[1].strip())
            if result is not None:
                raw = f"{raw} = {result}"
                prev = after + 1  # consume the bare "=" only when we filled it in
            else:
                prev = end        # can't compute; leave the "=" in the output
        elif raw.endswith("="):
            lhs = raw[:-1].strip()
            result = _compute(lhs)
            if result is not None:
                raw = f"{lhs} = {result}"
            prev = end
        else:
            # Verify any pre-filled result — LLM may have hallucinated the value
            raw = _verify_computed_results(raw)
            prev = end

        parts.append(f"${_conv(raw)}$")
    parts.append(work[prev:])

    result = "".join(parts)

    def _unguard(m: re.Match) -> str:
        return guarded[int(m.group(1))]
    result = re.sub(r"\x00G(\d+)\x00", _unguard, result)

    return _wrap_numbers_in_prose(result)
