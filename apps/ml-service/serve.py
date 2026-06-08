"""
serve.py — RAG + Ollama inference server.

Architecture:
  1. On startup: load embedding model + pre-computed question vectors
  2. On each request:
       a. Embed the incoming question
       b. Cosine-search the 400-question store → top 3 similar examples
       c. Build a few-shot prompt: "here are 3 examples, now do this one"
       d. Call local Ollama (qwen2.5) to generate {explanation, tip}
       e. Post-process both fields through math_parser.plain_to_latex()
       f. Return the result

COMMUNICATION:
  Rust backend → [Unix Domain Socket] → this service
  this service → [localhost:11434]    → Ollama

RUN (development, TCP):
  uvicorn serve:app --host 0.0.0.0 --port 8001 --reload

RUN (production, UDS — Rust connects via /run/lms/ml.sock):
  uvicorn serve:app --uds /run/lms/ml.sock

PREREQUISITES:
  1. ollama pull qwen2.5:7b   (or qwen2.5:3b for smaller VPS)
  2. python embed_questions.py
"""

from __future__ import annotations

import json
import re

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from embedder import Embedder
from math_parser import plain_to_latex, _compute, _find_spans, _normalize_superscripts
from analogi_engine import validate_spec as _validate_analogi_spec, process_no_db as _process_analogi_no_db

# ── Configuration ─────────────────────────────────────────────────────────────

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3:8b"

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="CPNS ML Service — RAG + Ollama")

embedder: Embedder | None = None
http_client: httpx.Client | None = None


@app.on_event("startup")
def startup():
    global embedder, http_client
    embedder    = Embedder()
    http_client = httpx.Client(timeout=180.0)  # qwen3 can be slow on CPU; 2 LLM calls per generate


@app.on_event("shutdown")
def shutdown():
    if http_client:
        http_client.close()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ExplanationRequest(BaseModel):
    question:      str         # question content (plain text, LaTeX stripped)
    options:       list[dict]  # [{"label": "A", "content": "..."}, ...]
    correct_label: str         # "B"
    subtype:       str = ""    # e.g. "ARITMATIKA", "SINONIM", "ANALOGI_GAMBAR"


class ExplanationResponse(BaseModel):
    explanation: str
    tip:         str


class GenerationRequest(BaseModel):
    source_question:      str        # content of the source question
    source_options:       list[dict] # [{"label": "A", "content": "...", "score": int}, ...]
    source_correct_label: str        # best label (score=5 for TKP, correct label for MCQ/TWK)
    category:             str        # "TIU", "TWK", "TKP"
    subtype:              str = ""   # e.g. "ARITMATIKA", "SINONIM"


class GeneratedOption(BaseModel):
    label:   str
    content: str
    score:   int  # MCQ/TF: 0=wrong, 5=correct; TKP: 1-5 weighted


class GeneratedQuestion(BaseModel):
    content:     str
    options:     list[GeneratedOption]
    explanation: str
    tip:         str


# ── Prompt builder ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\Kamu adalah tutor CPNS (Calon Pegawai Negeri Sipil) yang berpengalaman. Gunakan Bahasa Indonesia sepenuhnya — jangan gunakan kata bahasa Inggris kecuali istilah teknis yang tidak ada padanannya.
Untuk setiap soal berikan dua hal:
1. "explanation" — jelaskan METODE dan LANGKAH penyelesaiannya (2-4 kalimat, fokus pada cara berpikir). Jika ada perhitungan numerik, tulis ekspresinya dan akhiri dengan "=". JANGAN tulis hasilnya — sistem akan menghitung otomatis. Contoh: "Sehingga 3/4 + 5/6 =" atau "Maka 35/100 × 240 ="
2. "tip" — strategi cepat untuk menyelesaikan soal serupa saat ujian (1-2 kalimat)

Tulis matematika sebagai teks biasa menggunakan notasi alami:
- Pecahan: 3/4, 35/100
- Pangkat: 2^5, 2^(5+3-4)
- Akar: √169, √(a+b)
- Perkalian: × (atau *), Pembagian: ÷ (atau /)
- Persentase tulis di luar pecahan: "25% dari 200" atau "35/100 × 200"

Jawab HANYA dalam format JSON berikut, tanpa teks lain:
{"explanation": "...", "tip": "..."}"""


# ── Subtype classification ────────────────────────────────────────────────────

_MATH_SUBTYPES        = {"ARITMATIKA", "DERET_ANGKA", "PERBANDINGAN_KUANTITATIF", "SOAL_CERITA"}
_LANGUAGE_SUBTYPES    = {"SINONIM", "ANTONIM", "ANALOGI_VERBAL", "SILOGISME"}
_CIVIC_SUBTYPES       = {"PANCASILA", "UUD_1945", "BHINNEKA", "NKRI", "SEJARAH_NASIONAL",
                         "SISTEM_PEMERINTAHAN", "BELA_NEGARA", "BAHASA_INDONESIA"}
_SITUATIONAL_SUBTYPES = {"PELAYANAN_PUBLIK", "PROFESIONALISME", "JEJARING_KERJA", "SOSIAL_BUDAYA",
                         "TEKNOLOGI_INFORMASI", "ORIENTASI_BELAJAR", "MENGENDALIKAN_DIRI",
                         "BERADAPTASI", "KREATIVITAS_INOVASI"}


def _needs_math(subtype: str) -> bool:
    return subtype in _MATH_SUBTYPES


SYSTEM_PROMPT_LANGUAGE = """\
Kamu adalah tutor CPNS yang berpengalaman dalam soal kemampuan verbal. Gunakan Bahasa Indonesia sepenuhnya.
Untuk setiap soal berikan dua hal:
1. "explanation" — jelaskan hubungan makna kata atau pola logis yang menentukan jawaban (2-4 kalimat).
2. "tip" — strategi cepat untuk menemukan jawaban serupa saat ujian (1-2 kalimat).
Jawab HANYA dalam format JSON berikut, tanpa teks lain:
{"explanation": "...", "tip": "..."}"""

SYSTEM_PROMPT_CIVIC = """\
Kamu adalah tutor CPNS yang berpengalaman dalam materi Wawasan Kebangsaan (TWK). Gunakan Bahasa Indonesia sepenuhnya.
Untuk setiap soal berikan dua hal:
1. "explanation" — jelaskan dasar hukum, pasal, atau fakta sejarah yang relevan (2-4 kalimat). Sebutkan sumber spesifik (misalnya "Pasal 28B UUD 1945" atau "Sila ke-3 Pancasila").
2. "tip" — kata kunci atau cara cepat mengingat materi ini untuk ujian (1-2 kalimat).
Jawab HANYA dalam format JSON berikut, tanpa teks lain:
{"explanation": "...", "tip": "..."}"""

SYSTEM_PROMPT_SITUATIONAL = """\
Kamu adalah tutor CPNS yang berpengalaman dalam soal Karakteristik Pribadi (TKP). Gunakan Bahasa Indonesia sepenuhnya.
Soal TKP menggunakan skor bobot 1-5 untuk setiap pilihan — tidak ada jawaban benar/salah mutlak.
Untuk setiap soal berikan dua hal:
1. "explanation" — jelaskan mengapa pilihan dengan skor tertinggi paling sesuai nilai ASN (profesionalisme, orientasi pelayanan, dll), dan mengapa pilihan lain skornya lebih rendah (2-4 kalimat).
2. "tip" — prinsip nilai ASN yang menjadi kunci untuk soal sejenis (1-2 kalimat).
Jawab HANYA dalam format JSON berikut, tanpa teks lain:
{"explanation": "...", "tip": "..."}"""


def _explain_system_prompt(subtype: str) -> str:
    if subtype in _LANGUAGE_SUBTYPES:
        return SYSTEM_PROMPT_LANGUAGE
    if subtype in _CIVIC_SUBTYPES:
        return SYSTEM_PROMPT_CIVIC
    if subtype in _SITUATIONAL_SUBTYPES:
        return SYSTEM_PROMPT_SITUATIONAL
    return SYSTEM_PROMPT  # math subtypes + default


GENERATION_SYSTEM_PROMPT_LANGUAGE = """\
Kamu adalah pembuat soal CPNS kemampuan verbal yang berpengalaman. Gunakan Bahasa Indonesia sepenuhnya.
Buat SATU soal pilihan ganda BARU yang mirip gaya dengan soal referensi tapi konten berbeda.
Soal harus memiliki TEPAT 5 pilihan (A-E). Sertakan "correct_label" berisi huruf jawaban yang benar.
Untuk explanation: jelaskan pola hubungan kata atau logis (2-4 kalimat).
Untuk tip: strategi cepat untuk soal serupa (1-2 kalimat).
Jawab HANYA dalam format JSON:
{"content": "...", "options": [{"label": "A", "content": "..."}, ...], "correct_label": "B", "explanation": "...", "tip": "..."}"""

GENERATION_SYSTEM_PROMPT_CIVIC = """\
Kamu adalah pembuat soal CPNS Wawasan Kebangsaan (TWK) yang berpengalaman. Gunakan Bahasa Indonesia sepenuhnya.
Buat SATU soal pilihan ganda BARU yang mirip gaya dengan soal referensi tapi konten berbeda.
Soal harus memiliki TEPAT 5 pilihan (A-E). Sertakan "correct_label" berisi huruf jawaban yang benar.
Untuk explanation: sebutkan pasal, sila, atau fakta historis yang relevan (2-4 kalimat).
Untuk tip: kata kunci untuk mengingat materi ini (1-2 kalimat).
Jawab HANYA dalam format JSON:
{"content": "...", "options": [{"label": "A", "content": "..."}, ...], "correct_label": "C", "explanation": "...", "tip": "..."}"""

GENERATION_SYSTEM_PROMPT_SITUATIONAL = """\
Kamu adalah pembuat soal CPNS Karakteristik Pribadi (TKP) yang berpengalaman. Gunakan Bahasa Indonesia sepenuhnya.
Buat SATU soal situasional BARU yang mirip gaya dengan soal referensi tapi skenario berbeda.
Soal harus memiliki TEPAT 5 pilihan (A-E). Berikan skor bobot 1-5 pada SETIAP pilihan — tidak boleh ada skor yang sama. Skor 5 = paling sesuai nilai ASN; skor 1 = paling tidak sesuai.
Untuk explanation: jelaskan mengapa setiap pilihan mendapat skornya berdasarkan nilai ASN (2-4 kalimat).
Untuk tip: nilai ASN kunci untuk soal sejenis (1-2 kalimat).
Jawab HANYA dalam format JSON:
{"content": "...", "options": [{"label": "A", "content": "...", "score": 3}, {"label": "B", "content": "...", "score": 5}, {"label": "C", "content": "...", "score": 1}, {"label": "D", "content": "...", "score": 4}, {"label": "E", "content": "...", "score": 2}], "explanation": "...", "tip": "..."}"""


def _generate_system_prompt(subtype: str) -> str:
    if subtype in _LANGUAGE_SUBTYPES:
        return GENERATION_SYSTEM_PROMPT_LANGUAGE
    if subtype in _CIVIC_SUBTYPES:
        return GENERATION_SYSTEM_PROMPT_CIVIC
    if subtype in _SITUATIONAL_SUBTYPES:
        return GENERATION_SYSTEM_PROMPT_SITUATIONAL
    return GENERATION_SYSTEM_PROMPT  # math + default


# ── LaTeX post-processing ─────────────────────────────────────────────────────

def _strip_latex(text: str) -> str:
    """Convert LaTeX back to plain-text math for computation and few-shot examples."""
    # JSON silently decodes some LaTeX command prefixes as escape sequences:
    #   \t (tab, ASCII 9)        → \times becomes TAB+"imes", \text becomes TAB+"ext"
    #   \f (form feed, ASCII 12) → \frac  becomes FF+"rac"
    # Restore these to literal backslash so the processing below works correctly.
    text = text.replace('\text',  '\\text')   # TAB+ext  → \text
    text = text.replace('\times', '\\times')  # TAB+imes → \times
    text = text.replace('\frac',  '\\frac')   # FF+rac   → \frac

    # Arrow / logical symbols (common in algebra explanations)
    text = text.replace('\\Rightarrow', '→').replace('\\rightarrow', '→')
    text = text.replace('\\Leftrightarrow', '↔').replace('\\leftrightarrow', '↔')
    text = text.replace('\\implies', '→').replace('\\iff', '↔')

    text = re.sub(r'\\text\{([^{}]+)\}', r'\1', text)
    text = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'\1/\2', text)
    text = text.replace('\\times', '×').replace('\\div', '÷').replace('\\cdot', '×')
    text = text.replace('\\sqrt', '√')
    # ^{expr} → ^(expr)  so _compute can evaluate e.g. 3^{4+2-5} → 3^(4+2-5)
    text = re.sub(r'\^\{([^{}]+)\}', r'^(\1)', text)
    text = re.sub(r'[{}]', '', text)   # strip any remaining braces
    text = text.replace('$$', '').replace('$', '')
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def build_prompt(req: ExplanationRequest, examples: list[dict]) -> str:
    parts: list[str] = []

    for i, ex in enumerate(examples, 1):
        if not ex.get("explanation"):
            continue
        parts.append(f"=== Contoh {i} ===")
        parts.append(f"Soal: {ex['content']}")
        parts.append(f"Pilihan: {ex['options_str']}")
        parts.append(f"Jawaban benar: {ex['correct_label']}. {ex['correct_text']}")
        parts.append(
            f'Output: {{"explanation": "{_strip_latex(ex["explanation"])}", '
            f'"tip": "{_strip_latex(ex.get("tip", ""))}"}}\n'
        )

    options_str  = " | ".join(f"{o['label']}. {o['content']}" for o in req.options)
    correct_text = next(
        (o["content"] for o in req.options if o["label"] == req.correct_label), ""
    )

    parts.append("=== Soal Baru ===")
    parts.append(f"Soal: {req.question}")
    parts.append(f"Pilihan: {options_str}")
    parts.append(f"Jawaban benar: {req.correct_label}. {correct_text}")
    parts.append("Output:")

    return "\n".join(parts)


GENERATION_SYSTEM_PROMPT = """\
Kamu adalah pembuat soal CPNS (Calon Pegawai Negeri Sipil) yang berpengalaman. Gunakan Bahasa Indonesia sepenuhnya.

Tugasmu: buat SATU soal pilihan ganda BARU yang mirip gaya dan tingkat kesulitannya dengan soal referensi, tapi dengan konten yang berbeda.

Soal harus memiliki TEPAT 5 pilihan (A, B, C, D, E). Sertakan field "correct_label" berisi SATU huruf jawaban yang benar.

Untuk explanation: jelaskan metode penyelesaian (2-4 kalimat). Jika ada perhitungan numerik, tulis ekspresinya dan akhiri dengan "=". JANGAN tulis hasilnya — sistem akan menghitung otomatis.
Untuk tip: strategi cepat untuk soal serupa (1-2 kalimat).

Tulis matematika sebagai teks biasa:
- Pecahan: 3/4, 35/100
- Pangkat: 2^5
- Akar: √169
- Perkalian: ×, Pembagian: ÷

Jawab HANYA dalam format JSON berikut, tanpa teks lain:
{"content": "...", "options": [{"label": "A", "content": "..."}, {"label": "B", "content": "..."}, {"label": "C", "content": "..."}, {"label": "D", "content": "..."}, {"label": "E", "content": "..."}], "correct_label": "C", "explanation": "...", "tip": "..."}"""


def _parse_options_from_meta(ex: dict) -> list[dict]:
    """Reconstruct option objects from options_str and correct_label."""
    correct_label = ex.get("correct_label", "")
    opts = []
    for part in ex.get("options_str", "").split(" | "):
        part = part.strip()
        if not part:
            continue
        label   = part[0]
        content = part[3:].strip()  # skip "A. "
        opts.append({"label": label, "content": content, "score": 5 if label == correct_label else 0})
    return opts


def build_generation_prompt(req: GenerationRequest, examples: list[dict]) -> str:
    parts: list[str] = []

    shown = 0
    for ex in examples:
        if ex.get("content", "").strip() == req.source_question.strip():
            continue  # don't show the source question as its own example
        if not ex.get("explanation"):
            continue
        shown += 1
        if shown > 3:
            break
        opts = _parse_options_from_meta(ex)
        parts.append(f"=== Contoh {shown} ===")
        parts.append(json.dumps({
            "content":       ex["content"],
            "options":       [{"label": o["label"], "content": o["content"]} for o in opts],
            "correct_label": ex.get("correct_label", ""),
            "explanation":   _strip_latex(ex["explanation"]),
            "tip":           _strip_latex(ex.get("tip", "")),
        }, ensure_ascii=False))
        parts.append("")

    is_tkp = req.subtype in _SITUATIONAL_SUBTYPES
    parts.append("=== Soal Referensi ===")
    parts.append(f"Kategori: {req.category}")
    parts.append(f"Soal: {_strip_latex(req.source_question)}")
    if is_tkp:
        source_opts_str = " | ".join(
            f"{o['label']}. {_strip_latex(o['content'])} [skor={o.get('score', '?')}]"
            for o in req.source_options
        )
        parts.append(f"Pilihan (dengan skor): {source_opts_str}")
    else:
        source_opts_str = " | ".join(
            f"{o['label']}. {_strip_latex(o['content'])}" for o in req.source_options
        )
        parts.append(f"Pilihan: {source_opts_str}")
        parts.append(f"Jawaban benar: {req.source_correct_label}")
    parts.append("")
    parts.append("Buat SATU soal BARU yang mirip (topik dan kesulitan sama, konten berbeda).")
    parts.append("Output:")

    return "\n".join(parts)


# ── Answer inference ──────────────────────────────────────────────────────────

def _compute_from_content(question_content: str, options: list[dict]) -> "str | object":
    """
    Directly evaluate the mathematical expression embedded in the question text.

    Returns:
      str        — matching option label (e.g. 'B') — use as correct_label
      None       — no computable expression found (non-arithmetic question, fall through)
      _NOT_FOUND — answer computed but not present in any option → reject the question
    """
    clean_content      = _strip_latex(question_content)
    normalized_content = _normalize_superscripts(clean_content)
    spans = _find_spans(normalized_content)

    print(f"  [compute_from_content] normalized: {normalized_content!r}")
    if not spans:
        print(f"  [compute_from_content] no math spans detected")
        return None

    option_map: dict[str, str] = {
        o.get("content", "").strip(): o.get("label", "").strip().upper()
        for o in options
    }

    found_computable = False  # tracks whether any span evaluated to a number

    def _try_match(computed: str) -> "str | None":
        """Return the option label whose content equals computed, or None."""
        if computed in option_map:
            return option_map[computed]
        try:
            cf = float(computed.replace(",", "."))
            for content, label in option_map.items():
                try:
                    if float(content.replace(",", ".")) == cf:
                        return label
                except ValueError:
                    pass
        except ValueError:
            pass
        return None

    # Try 1: join ALL spans from first-start to last-end.
    # Handles fragmented detection like "3^(4)" + "× 3^(2)" + "÷ 3^(5)" which
    # should be one expression "3^(4) × 3^(2) ÷ 3^(5)".
    sorted_by_pos = sorted(spans, key=lambda s: s[0])
    if len(sorted_by_pos) > 1:
        joined = normalized_content[sorted_by_pos[0][0]:sorted_by_pos[-1][1]].strip()
        joined_computed = _compute(joined)
        print(f"  [compute_from_content] joined {joined!r} → {joined_computed!r}")
        if joined_computed is not None:
            found_computable = True
            label = _try_match(joined_computed)
            if label:
                print(f"  [compute_from_content] matched option {label} ({joined_computed})")
                return label
            print(f"  [compute_from_content] joined answer not in options → reject")
            return _NOT_FOUND

    # Try 2: individual spans, longest first (catches single-term like "√169")
    for start, end in sorted(spans, key=lambda s: s[1] - s[0], reverse=True):
        expr = normalized_content[start:end].strip()
        computed = _compute(expr)
        print(f"  [compute_from_content] span {expr!r} → {computed!r}")
        if computed is None:
            continue

        found_computable = True
        label = _try_match(computed)
        if label:
            print(f"  [compute_from_content] matched option {label} ({computed})")
            return label

    if found_computable:
        print(f"  [compute_from_content] answer computed but not in options → reject")
        return _NOT_FOUND

    print(f"  [compute_from_content] no span was computable (verbal/sequence question)")
    return None


_NO_MATH   = object()   # sentinel: explanation had no computable answer
_NOT_FOUND = object()   # sentinel: answer inferred but no option matches it


def _fix_arithmetic_in_explanation(text: str) -> str:
    """
    Find arithmetic spans in plain text that already have a pre-filled result
    and correct any wrong values.  E.g. '98 + 15 = 103' → '98 + 15 = 113'.

    Called inside _infer_correct_label so that the label is inferred from a
    mathematically-correct explanation rather than a hallucinated one.
    """
    spans = _find_spans(text)
    if not spans:
        return text

    result: list[str] = []
    prev = 0
    for start, end in spans:
        result.append(text[prev:start])
        raw = text[start:end].strip()

        m = re.match(
            r"^(.*)\s*=\s*(-?\d+(?:\.\d+)?(?:\s+\d+/\d+)?|-?\d+/\d+)\s*$",
            raw,
            re.DOTALL,
        )
        if m:
            expr_part = m.group(1).strip()
            stated    = m.group(2).strip()
            last_eq   = expr_part.rfind("=")
            sub       = expr_part[last_eq + 1 :].strip() if last_eq >= 0 else expr_part
            computed  = _compute(sub)
            if computed is not None:
                try:
                    if abs(float(computed) - float(stated)) > 1e-9:
                        raw = f"{expr_part} = {computed}"
                except Exception:
                    pass

        result.append(raw)
        prev = end

    result.append(text[prev:])
    return "".join(result)


def _infer_correct_label(explanation: str, options: list[dict]) -> str | object:
    """
    Parse the computed result from the explanation and find which option matches.

    Returns:
      str        — the matching option label (e.g. 'B')
      _NO_MATH   — no arithmetic answer found in the explanation (safe to use model's label)
      _NOT_FOUND — answer extracted but no option contains it (invalid question, reject)
    """
    # Strip any LaTeX before parsing (model sometimes outputs $...$ despite instructions)
    explanation = _strip_latex(explanation)
    # Fix any arithmetically wrong values in the explanation so the label we
    # infer is based on the correct answer, not a hallucinated one.
    explanation = _fix_arithmetic_in_explanation(explanation)

    # Collect every "= <token>" in the explanation; last one is the final answer
    hits = re.findall(r'=\s*([^\s=.,;!?()\n]+(?:\s+\d+/\d+)?)', explanation)
    if not hits:
        return _NO_MATH

    answer = hits[-1].strip().rstrip('.,;!?')

    # Build lookup: normalised content → label
    option_map: dict[str, str] = {
        o.get("content", "").strip(): o.get("label", "").strip().upper()
        for o in options
    }

    # 1. Exact string match
    if answer in option_map:
        return option_map[answer]

    # 2. Numeric float comparison ("25" == "25.0")
    try:
        answer_f = float(answer.replace(',', '.'))
        for content, label in option_map.items():
            try:
                if float(content.replace(',', '.')) == answer_f:
                    return label
            except ValueError:
                pass
    except ValueError:
        pass

    # 3. Expression evaluation via _compute ("5^1" → "5", "19/12" → "19/12")
    computed = _compute(answer)
    if computed:
        if computed in option_map:
            return option_map[computed]
        try:
            computed_f = float(computed.replace(',', '.'))
            for content, label in option_map.items():
                try:
                    if float(content.replace(',', '.')) == computed_f:
                        return label
                except ValueError:
                    pass
        except ValueError:
            pass

    # Answer found in explanation but does not match any option
    return _NOT_FOUND


# ── Build + log response ──────────────────────────────────────────────────────

def _build_and_log(
    result: dict,
    options_raw: list[dict],
    correct_label: str,
    apply_math: bool = True,
    tkp_scores: "dict[str, int] | None" = None,
) -> "GeneratedQuestion":
    """
    Optionally apply plain_to_latex to all text fields, log every transformation,
    and return the final GeneratedQuestion.

    tkp_scores: when set, each option gets its score from this dict (TKP weighted scoring).
    Otherwise score=5 for correct_label, score=0 for all others (MCQ/TF/TWK).
    """
    def _latex(raw: str, label: str) -> str:
        if not apply_math:
            print(f"  [math_parser] {label}: (skipped — non-math subtype)")
            return raw
        # Strip any LLM-output LaTeX first so plain_to_latex can re-process it cleanly.
        stripped = _strip_latex(raw)
        out = plain_to_latex(stripped)
        if out != raw:
            print(f"  [math_parser] {label}:")
            print(f"    raw: {raw!r}")
            print(f"    out: {out!r}")
        else:
            print(f"  [math_parser] {label}: (no change)")
        return out

    print("── [generate] math_parser transformations ──────────────────────────────")
    content_out     = _latex(result.get("content",     ""), "content")
    explanation_out = _latex(result.get("explanation", ""), "explanation")
    tip_out         = _latex(result.get("tip",         ""), "tip")
    options_out = []
    for o in options_raw:
        opt_out = _latex(o.get("content", ""), f"option {o.get('label', '?')}")
        options_out.append((o["label"], opt_out))
    print("────────────────────────────────────────────────────────────────────────\n")

    options_list = []
    for label, content in options_out:
        if tkp_scores is not None:
            score = tkp_scores.get(label.strip().upper(), 1)
        else:
            score = 5 if label.strip().upper() == correct_label else 0
        options_list.append(GeneratedOption(label=label, content=content, score=score))

    return GeneratedQuestion(
        content=content_out,
        options=options_list,
        explanation=explanation_out,
        tip=tip_out,
    )


# ── Correction prompt ─────────────────────────────────────────────────────────

CORRECTION_SYSTEM_PROMPT = """\
Kamu adalah validator soal pilihan ganda CPNS. Tugasmu HANYA memeriksa dan memperbaiki inkonsistensi — jangan buat soal baru.

Langkah:
1. Hitung sendiri jawaban yang benar berdasarkan konten soal dan explanation
2. Periksa apakah opsi yang ditunjuk correct_label berisi nilai yang benar
3. Periksa apakah nilai yang benar sudah ada di salah satu opsi

Aturan perbaikan (pilih SATU yang paling minimal):
- Jika correct_label salah tapi nilai benar sudah ada di opsi lain → perbaiki correct_label saja
- Jika nilai yang benar tidak ada di opsi mana pun → ganti konten opsi correct_label dengan nilai yang benar
- Jika sudah benar → kembalikan tanpa perubahan

JANGAN ubah: content soal, opsi yang bukan correct_label, explanation, tip.

Kembalikan HANYA JSON dengan format sama persis, tanpa teks lain:
{"content": "...", "options": [{"label": "A", "content": "..."}, ...], "correct_label": "...", "explanation": "...", "tip": "..."}"""


# ── Ollama call ───────────────────────────────────────────────────────────────

def call_ollama(user_message: str, system_prompt: str = SYSTEM_PROMPT) -> dict:
    """
    Calls the local Ollama /api/chat endpoint.
    Returns parsed JSON from the model output.
    """
    payload = {
        "model":  OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "format": "json",
    }

    try:
        resp = http_client.post(OLLAMA_URL, json=payload)
        resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama is not running. Start it with: ollama serve"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}")

    content = resp.json()["message"]["content"]

    try:
        return json.loads(content)
    except Exception:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise HTTPException(status_code=500, detail=f"Could not parse model output: {content}")


# ── Analogi Gambar generation ─────────────────────────────────────────────────

class AnalogiGenerateResponse(BaseModel):
    content:     str
    image_url:   str
    explanation: str
    options:     list[GeneratedOption]  # content field holds the image URL


ANALOGI_SPEC_SYSTEM_PROMPT = """\
You generate analogi gambar (picture analogy) question specs for Indonesian CPNS exams.
Output ONLY a single JSON object — no markdown, no explanation text outside the JSON.

APPROACH:
  1. Choose a visual transformation rule (e.g. "mirror left-right then invert fills").
  2. Write a clear Indonesian explanation of that rule.
  3. Design cell_a (the first image).
  4. Mentally apply the rule → write cell_b (what cell_a becomes).
  5. Design cell_c (a different-looking image with different shapes/positions).
  6. Mentally apply the same rule → write cell_d (the correct answer).

SCHEMA:
{"format":"analogy","title":"<string>","content":"<Indonesian question text>","explanation":"<Indonesian rule description, REQUIRED>","category":"TIU","time_limit":30,"cell_a":[<shapes>],"cell_b":[<shapes>],"cell_c":[<shapes>],"cell_d":[<shapes>]}

SHAPE: {"shape":<name>,"size":<size>,"filled":<bool>,"pos":<pos>,"rotation":<deg>}
  shape : circle|square|triangle|diamond|pentagon|hexagon|star|cross|semicircle|arrow|line|wave
  size  : small|medium|large
  filled: true (solid) | false (outline)
  pos   : TL TC TR / ML C MR / BL BC BR  (each position at most ONCE per cell)
  rotation: 0|30|45|60|90|120|135|150|180

TRANSFORMATION IDEAS (pick ONE or combine TWO):
  • Mirror left-right: TL↔TR, ML↔MR, BL↔BR
  • Mirror top-bottom: TL↔BL, TC↔BC, TR↔BR
  • Invert fills: filled↔outline for every shape
  • Rotate positions clockwise (corners: TL→TR→BR→BL→TL)
  • Rotate positions clockwise (edges: TC→MR→BC→ML→TC)
  • Rotate shape orientations by 90°
  • Swap sizes: small→medium→large→small

CONSTRAINTS:
  • cell_a and cell_c must look visually different.
  • cell_b = rule(cell_a) exactly. cell_d = rule(cell_c) exactly.
  • Use 2–5 shapes per cell. No duplicate positions within a cell."""


def _extract_spec_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = re.sub(r"```\s*$", "", text).strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object in LLM response")
    depth, end = 0, -1
    for i, ch in enumerate(text[start:], start):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("Unterminated JSON object")
    return json.loads(text[start:end])


def _normalise_analogi_spec(spec: dict) -> dict:
    for cell_key in ("cell_a", "cell_b", "cell_c", "cell_d"):
        for s in spec.get(cell_key, []):
            if isinstance(s.get("filled"), int):
                s["filled"] = bool(s["filled"])
            s.setdefault("rotation", 0)
    spec.setdefault("format", "analogy")
    spec.setdefault("category", "TIU")
    spec.setdefault("time_limit", 30)
    spec.setdefault("content", "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?")
    return spec


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/explain", response_model=ExplanationResponse)
def explain(req: ExplanationRequest):
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedder not loaded")

    system_prompt = _explain_system_prompt(req.subtype)

    # 1. Find similar questions from our store
    examples = embedder.search(req.question, top_k=3)

    # 2. Build the few-shot prompt
    user_message = build_prompt(req, examples)

    print("\n── [explain] RAG-augmented prompt ─────────────────────────────────────")
    print(f"[SYSTEM]\n{system_prompt}")
    print(f"\n[USER]\n{user_message}")
    print("───────────────────────────────────────────────────────────────────────\n")

    # 3. Generate via Ollama
    result = call_ollama(user_message, system_prompt=system_prompt)

    print("\n── [explain] LLM output ───────────────────────────────────────────────")
    print(result)
    print("───────────────────────────────────────────────────────────────────────\n")

    if _needs_math(req.subtype):
        explanation = plain_to_latex(result.get("explanation", ""))
        tip         = plain_to_latex(result.get("tip", ""))
    else:
        explanation = result.get("explanation", "")
        tip         = result.get("tip", "")

    return ExplanationResponse(explanation=explanation, tip=tip)


@app.post("/generate", response_model=GeneratedQuestion)
def generate(req: GenerationRequest):
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedder not loaded")

    print("\n══ [generate] INCOMING REQUEST ═════════════════════════════════════════")
    print(f"  category       : {req.category}")
    print(f"  source_question: {req.source_question}")
    print(f"  source_options :")
    for o in req.source_options:
        score_str = f" (score={o.get('score', '?')})"
        print(f"    {o['label']}. {o['content']}{score_str}")
    print(f"  correct_label  : {req.source_correct_label}")
    print("════════════════════════════════════════════════════════════════════════\n")

    examples = embedder.search(req.source_question, top_k=5)
    # Exclude the source question itself if it appears in the store
    examples = [ex for ex in examples
                if ex.get("content", "").strip() != req.source_question.strip()]

    print(f"── [generate] RAG retrieved {len(examples)} examples ──────────────────────────────")
    for i, ex in enumerate(examples, 1):
        has_exp = bool(ex.get("explanation"))
        print(f"  [{i}] {'✓' if has_exp else '✗ (no explanation)'} {ex.get('content', '')[:80]}")
    print("────────────────────────────────────────────────────────────────────────\n")

    user_message  = build_generation_prompt(req, examples)
    system_prompt = _generate_system_prompt(req.subtype)
    apply_math    = _needs_math(req.subtype)

    print("── [generate] PROMPT sent to Ollama ────────────────────────────────────")
    print(user_message)
    print("────────────────────────────────────────────────────────────────────────\n")

    result = call_ollama(user_message, system_prompt=system_prompt)

    print("── [generate] LLM raw output ───────────────────────────────────────────")
    print(result)
    print("────────────────────────────────────────────────────────────────────────\n")

    options_raw   = result.get("options", [])
    correct_label = result.get("correct_label", "").strip().upper()

    if len(options_raw) != 5:
        print(f"✗ [generate] VALIDATION FAIL: got {len(options_raw)} options (expected 5)")
        print(f"  options were: {options_raw}")
        raise HTTPException(
            status_code=500,
            detail=f"Model returned {len(options_raw)} options (expected 5)",
        )

    # ── TKP path: weighted scores 1-5 per option, no single correct_label ────
    if req.subtype in _SITUATIONAL_SUBTYPES:
        tkp_scores: dict[str, int] = {}
        for o in options_raw:
            label = o.get("label", "").strip().upper()
            raw_score = o.get("score", None)
            try:
                s = int(raw_score)
                tkp_scores[label] = max(1, min(5, s))  # clamp to 1-5
            except (TypeError, ValueError):
                tkp_scores[label] = 1  # fallback for missing/invalid score
        scores_set = set(tkp_scores.values())
        if len(scores_set) < 3:
            print(f"✗ [generate] TKP VALIDATION FAIL: scores not sufficiently varied {tkp_scores}")
            raise HTTPException(
                status_code=500,
                detail=f"TKP model returned insufficiently varied scores: {tkp_scores}",
            )
        best_label = max(tkp_scores, key=lambda k: tkp_scores[k])
        print(f"✓ [generate] TKP scores={tkp_scores} best_label={best_label}\n")
        return _build_and_log(result, options_raw, best_label, apply_math=False, tkp_scores=tkp_scores)
    # ─────────────────────────────────────────────────────────────────────────

    valid_labels = {o.get("label", "").strip().upper() for o in options_raw}
    if correct_label not in valid_labels:
        print(f"✗ [generate] VALIDATION FAIL: correct_label '{correct_label}' not in option labels {valid_labels}")
        raise HTTPException(
            status_code=500,
            detail=f"Model returned invalid correct_label '{correct_label}'",
        )

    if not apply_math:
        # Non-math subtypes: trust the LLM's correct_label directly — no arithmetic to verify
        print(f"✓ [generate] non-math subtype — skipping arithmetic verification, correct_label={correct_label}\n")
        return _build_and_log(result, options_raw, correct_label, apply_math=False)

    # ── Direct computation from question content ──────────────────────────────
    # Most reliable for arithmetic/algebra questions: evaluate the expression in
    # the question itself — independent of what the model wrote in the explanation.
    content_label = _compute_from_content(result.get("content", ""), options_raw)
    if content_label is _NOT_FOUND:
        print(f"✗ [generate] REJECT: computed answer not present in any option")
        raise HTTPException(
            status_code=500,
            detail="Generated options don't include the mathematically correct answer",
        )
    elif content_label is not None:
        # It's a label string — direct computation succeeded
        if content_label != correct_label:
            print(f"ℹ [generate] correct_label override from content: model={correct_label} → computed={content_label}")
        correct_label = content_label
        print(f"✓ [generate] answer confirmed by direct computation ({content_label}) — skipping LLM correction\n")
        return _build_and_log(result, options_raw, correct_label, apply_math=True)
    # else: None → non-arithmetic question, fall through to LLM correction

    # ── LLM correction pass ───────────────────────────────────────────────────
    # Send the generated question back to the model for self-correction.
    # It sees the full content + options + explanation and is asked to fix any
    # mismatch between the correct_label and the explanation's answer.
    correction_input = json.dumps({
        "content":       result.get("content", ""),
        "options":       options_raw,
        "correct_label": correct_label,
        "explanation":   result.get("explanation", ""),
        "tip":           result.get("tip", ""),
    }, ensure_ascii=False)

    print("── [generate] sending to LLM for correction ────────────────────────────")
    corrected = call_ollama(correction_input, system_prompt=CORRECTION_SYSTEM_PROMPT)
    print("── [generate] corrected output ─────────────────────────────────────────")
    print(corrected)
    print("────────────────────────────────────────────────────────────────────────\n")

    # Accept the corrected values if the structure is still valid
    corrected_options = corrected.get("options", options_raw)
    corrected_label   = corrected.get("correct_label", correct_label).strip().upper()
    corrected_labels  = {o.get("label", "").strip().upper() for o in corrected_options}

    if (len(corrected_options) == 5
            and corrected_label in corrected_labels):
        if corrected_options != options_raw or corrected_label != correct_label:
            print(f"ℹ [generate] correction applied: correct_label {correct_label} → {corrected_label}")
        options_raw   = corrected_options
        correct_label = corrected_label
        valid_labels  = corrected_labels
        result["content"]     = corrected.get("content",     result.get("content", ""))
        result["explanation"] = corrected.get("explanation", result.get("explanation", ""))
        result["tip"]         = corrected.get("tip",         result.get("tip", ""))
    else:
        print(f"⚠ [generate] correction output invalid — keeping original")

    # ── Python deterministic inference (final override for arithmetic) ─────────
    inferred = _infer_correct_label(result.get("explanation", ""), options_raw)
    if inferred is _NOT_FOUND:
        print(f"✗ [generate] VALIDATION FAIL: explanation answer not present in any option")
        raise HTTPException(
            status_code=500,
            detail="Generated question has no option matching the correct answer in the explanation",
        )
    elif inferred is _NO_MATH:
        print(f"ℹ [generate] no arithmetic answer in explanation — keeping correct_label={correct_label}")
    else:
        if inferred != correct_label:
            print(f"ℹ [generate] Python inference override: {correct_label} → {inferred}")
        correct_label = inferred

    print(f"✓ [generate] validation passed — correct_label={correct_label}\n")
    return _build_and_log(result, options_raw, correct_label, apply_math=True)


@app.post("/analogi/generate", response_model=AnalogiGenerateResponse)
def analogi_generate():
    """
    Generate a new analogi gambar question using the full pipeline:
    LLM → spec → render → upload images → return question data (no DB save).
    """
    max_attempts = 3
    last_error: str = "Unknown error"

    for attempt in range(1, max_attempts + 1):
        print(f"\n══ [analogi/generate] attempt {attempt}/{max_attempts} ══════════════════════")
        try:
            # 1. Generate spec from LLM
            result = call_ollama(
                "Generate a new analogi gambar question spec now.",
                system_prompt=ANALOGI_SPEC_SYSTEM_PROMPT,
            )
            raw_text = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            spec = _extract_spec_json(raw_text)
            spec = _normalise_analogi_spec(spec)
            print(f"  spec cells: a={len(spec.get('cell_a',[]))} b={len(spec.get('cell_b',[]))} "
                  f"c={len(spec.get('cell_c',[]))} d={len(spec.get('cell_d',[]))}")

            # 2. Validate spec
            errors = _validate_analogi_spec(spec)
            if errors:
                last_error = "; ".join(errors)
                print(f"  spec invalid: {last_error}")
                continue

            # 3. Render + upload (no DB save)
            data = _process_analogi_no_db(spec)
            print(f"  ✓ rendered: {data['image_url']}")

            return AnalogiGenerateResponse(
                content=data["content"],
                image_url=data["image_url"],
                explanation=data["explanation"],
                options=[
                    GeneratedOption(
                        label=o["label"],
                        content=o["content"],
                        score=o["score"],
                    )
                    for o in data["options"]
                ],
            )
        except Exception as e:
            last_error = str(e)
            print(f"  error: {e}")
            continue

    raise HTTPException(status_code=500, detail=f"Failed to generate analogi question after {max_attempts} attempts: {last_error}")


@app.get("/health")
def health():
    return {
        "status":          "ok",
        "embedder_loaded": embedder is not None,
        "ollama_model":    OLLAMA_MODEL,
        "questions_count": len(embedder.questions) if embedder else 0,
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Development: TCP on port 8001
    # Production: pass --uds /run/lms/ml.sock to uvicorn CLI instead
    uvicorn.run(app, host="127.0.0.1", port=8001)
