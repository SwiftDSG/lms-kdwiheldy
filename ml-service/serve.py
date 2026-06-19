"""
serve.py — RAG + llama-cpp-python inference server over Unix Domain Socket.

Protocol (length-prefix, newline-terminated header):
  Request:  "<verb> <byte_length>\\n<json_bytes>"
  Response: "ok <byte_length>\\n<json_bytes>"
         or "error <byte_length>\\n<message>"

Verbs:
  explain   — generate explanation + tip for a question
  generate  — generate a new question similar to a source
  analogi   — generate an analogi gambar question (no input needed)

RUN:
  python serve.py

PREREQUISITES:
  1. Download a GGUF model and set LLM_MODEL_PATH (or place at ../models/model.gguf)
  2. python embed_questions.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading

from llama_cpp import Llama

from embedder import Embedder
from math_parser import plain_to_latex, _compute, _find_spans, _normalize_superscripts
from analogi_engine import validate_spec as _validate_analogi_spec, process_no_db as _process_analogi_no_db

# ── Configuration ─────────────────────────────────────────────────────────────

SOCKET_PATH  = os.environ.get("ML_SOCKET_PATH", "/tmp/lms-ml.sock")
MODEL_PATH   = os.environ.get("LLM_MODEL_PATH", "../models/model.gguf")

# ── Globals (initialised once at startup) ─────────────────────────────────────

embedder: Embedder | None = None
llm:      Llama   | None  = None


def _init():
    global embedder, llm
    embedder = Embedder()
    print(f"Loading LLM from {MODEL_PATH} …")
    llm = Llama(
        model_path=MODEL_PATH,
        n_gpu_layers=-1,   # offload all layers to GPU/Metal; 0 = CPU only
        n_ctx=8192,        # context window — large enough for RAG + generation prompts
        verbose=False,     # suppress llama.cpp's per-token logging
    )
    print("LLM ready.")


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


# ── System prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Kamu adalah tutor CPNS (Calon Pegawai Negeri Sipil) yang berpengalaman. Gunakan Bahasa Indonesia sepenuhnya — jangan gunakan kata bahasa Inggris kecuali istilah teknis yang tidak ada padanannya.
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
    if subtype in _LANGUAGE_SUBTYPES:   return SYSTEM_PROMPT_LANGUAGE
    if subtype in _CIVIC_SUBTYPES:      return SYSTEM_PROMPT_CIVIC
    if subtype in _SITUATIONAL_SUBTYPES: return SYSTEM_PROMPT_SITUATIONAL
    return SYSTEM_PROMPT


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
    if subtype in _LANGUAGE_SUBTYPES:    return GENERATION_SYSTEM_PROMPT_LANGUAGE
    if subtype in _CIVIC_SUBTYPES:       return GENERATION_SYSTEM_PROMPT_CIVIC
    if subtype in _SITUATIONAL_SUBTYPES: return GENERATION_SYSTEM_PROMPT_SITUATIONAL
    return GENERATION_SYSTEM_PROMPT


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


# ── LaTeX helpers ─────────────────────────────────────────────────────────────

def _strip_latex(text: str) -> str:
    text = text.replace('\text',  '\\text')
    text = text.replace('\times', '\\times')
    text = text.replace('\frac',  '\\frac')
    text = text.replace('\\Rightarrow', '→').replace('\\rightarrow', '→')
    text = text.replace('\\Leftrightarrow', '↔').replace('\\leftrightarrow', '↔')
    text = text.replace('\\implies', '→').replace('\\iff', '↔')
    text = re.sub(r'\\text\{([^{}]+)\}', r'\1', text)
    text = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'\1/\2', text)
    text = text.replace('\\times', '×').replace('\\div', '÷').replace('\\cdot', '×')
    text = text.replace('\\sqrt', '√')
    text = re.sub(r'\^\{([^{}]+)\}', r'^(\1)', text)
    text = re.sub(r'[{}]', '', text)
    text = text.replace('$$', '').replace('$', '')
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_prompt(question: str, options: list, correct_label: str, examples: list) -> str:
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
    options_str  = " | ".join(f"{o['label']}. {o['content']}" for o in options)
    correct_text = next((o["content"] for o in options if o["label"] == correct_label), "")
    parts.append("=== Soal Baru (buat penjelasan BARU — jangan salin dari contoh di atas) ===")
    parts.append(f"Soal: {question}")
    parts.append(f"Pilihan: {options_str}")
    parts.append(f"Jawaban benar: {correct_label}. {correct_text}")
    parts.append("Output:")
    return "\n".join(parts)


def _parse_options_from_meta(ex: dict) -> list[dict]:
    correct_label = ex.get("correct_label", "")
    opts = []
    for part in ex.get("options_str", "").split(" | "):
        part = part.strip()
        if not part:
            continue
        label   = part[0]
        content = part[3:].strip()
        opts.append({"label": label, "content": content, "score": 5 if label == correct_label else 0})
    return opts


def build_generation_prompt(source_question: str, source_options: list, source_correct_label: str,
                             category: str, subtype: str, examples: list) -> str:
    parts: list[str] = []
    shown = 0
    for ex in examples:
        if ex.get("content", "").strip() == source_question.strip():
            continue
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

    is_tkp = subtype in _SITUATIONAL_SUBTYPES
    parts.append("=== Soal Referensi ===")
    parts.append(f"Kategori: {category}")
    parts.append(f"Soal: {_strip_latex(source_question)}")
    if is_tkp:
        opts_str = " | ".join(
            f"{o['label']}. {_strip_latex(o['content'])} [skor={o.get('score', '?')}]"
            for o in source_options
        )
        parts.append(f"Pilihan (dengan skor): {opts_str}")
    else:
        opts_str = " | ".join(f"{o['label']}. {_strip_latex(o['content'])}" for o in source_options)
        parts.append(f"Pilihan: {opts_str}")
        parts.append(f"Jawaban benar: {source_correct_label}")
    parts.append("")
    parts.append("Buat SATU soal BARU yang mirip (topik dan kesulitan sama, konten berbeda).")
    parts.append("Output:")
    return "\n".join(parts)


# ── LLM call ─────────────────────────────────────────────────────────────────

def call_llm(user_message: str, system_prompt: str = SYSTEM_PROMPT,
             cancel_event: "threading.Event | None" = None) -> dict:
    stream = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
        stream=True,
    )
    chunks: list[str] = []
    for chunk in stream:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Cancelled: client disconnected")
        delta = chunk["choices"][0]["delta"].get("content", "")
        if delta:
            chunks.append(delta)

    content = "".join(chunks)
    try:
        return json.loads(content)
    except Exception:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise RuntimeError(f"Could not parse model output: {content}")


# ── Answer inference ──────────────────────────────────────────────────────────

_NO_MATH   = object()
_NOT_FOUND = object()


def _compute_from_content(question_content: str, options: list) -> "tuple[str | object | None, str | None]":
    """
    Returns (result, computed_value) where:
      - (label_str, None)        — found the answer and it matches an existing option
      - (_NOT_FOUND, value_str)  — computed an answer but it is not in any option
      - (None, None)             — no computable math expression found
    """
    clean_content      = _strip_latex(question_content)
    normalized_content = _normalize_superscripts(clean_content)
    spans = _find_spans(normalized_content)

    print(f"  [compute_from_content] normalized: {normalized_content!r}")
    if not spans:
        print(f"  [compute_from_content] no math spans detected")
        return None, None

    option_map: dict[str, str] = {
        o.get("content", "").strip(): o.get("label", "").strip().upper()
        for o in options
    }

    def _try_match(computed: str) -> "str | None":
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

    sorted_by_pos = sorted(spans, key=lambda s: s[0])
    if len(sorted_by_pos) > 1:
        joined = normalized_content[sorted_by_pos[0][0]:sorted_by_pos[-1][1]].strip()
        joined_computed = _compute(joined)
        print(f"  [compute_from_content] joined {joined!r} → {joined_computed!r}")
        if joined_computed is not None:
            label = _try_match(joined_computed)
            if label:
                print(f"  [compute_from_content] matched option {label} ({joined_computed})")
                return label, None
            print(f"  [compute_from_content] joined answer {joined_computed!r} not in options → will replace")
            return _NOT_FOUND, joined_computed

    last_computed: "str | None" = None
    for start, end in sorted(spans, key=lambda s: s[1] - s[0], reverse=True):
        expr = normalized_content[start:end].strip()
        computed = _compute(expr)
        print(f"  [compute_from_content] span {expr!r} → {computed!r}")
        if computed is None:
            continue
        last_computed = computed
        label = _try_match(computed)
        if label:
            print(f"  [compute_from_content] matched option {label} ({computed})")
            return label, None

    if last_computed is not None:
        print(f"  [compute_from_content] answer {last_computed!r} not in options → will replace")
        return _NOT_FOUND, last_computed

    print(f"  [compute_from_content] no span was computable (verbal/sequence question)")
    return None, None


def _fix_arithmetic_in_explanation(text: str) -> str:
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
            raw, re.DOTALL,
        )
        if m:
            expr_part = m.group(1).strip()
            stated    = m.group(2).strip()
            last_eq   = expr_part.rfind("=")
            sub       = expr_part[last_eq + 1:].strip() if last_eq >= 0 else expr_part
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


def _infer_correct_label(explanation: str, options: list) -> "str | object":
    explanation = _strip_latex(explanation)
    explanation = _fix_arithmetic_in_explanation(explanation)
    hits = re.findall(r'=\s*([^\s=.,;!?()\n]+(?:\s+\d+/\d+)?)', explanation)
    if not hits:
        return _NO_MATH
    answer = hits[-1].strip().rstrip('.,;!?')
    option_map: dict[str, str] = {
        o.get("content", "").strip(): o.get("label", "").strip().upper()
        for o in options
    }
    if answer in option_map:
        return option_map[answer]
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
    return _NOT_FOUND


# ── Build response dict ───────────────────────────────────────────────────────

def _build_result(result: dict, options_raw: list, correct_label: str,
                  apply_math: bool = True, tkp_scores: "dict[str, int] | None" = None) -> dict:
    def _latex(raw: str, label: str) -> str:
        if not apply_math:
            print(f"  [math_parser] {label}: (skipped)")
            return raw
        stripped = _strip_latex(raw)
        out = plain_to_latex(stripped)
        if out != raw:
            print(f"  [math_parser] {label}:\n    raw: {raw!r}\n    out: {out!r}")
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
        label = o["label"]
        if tkp_scores is not None:
            score = tkp_scores.get(label.strip().upper(), 1)
        else:
            score = 5 if label.strip().upper() == correct_label else 0
        options_out.append({"label": label, "content": opt_out, "score": score})
    print("────────────────────────────────────────────────────────────────────────\n")

    return {
        "content":     content_out,
        "options":     options_out,
        "explanation": explanation_out,
        "tip":         tip_out,
    }


# ── Analogi spec helpers ──────────────────────────────────────────────────────

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


# ── Handlers ──────────────────────────────────────────────────────────────────

def handle_explain(payload: dict, cancel_event: "threading.Event | None" = None) -> dict:
    question      = payload["question"]
    options       = payload["options"]
    correct_label = max(options, key=lambda o: o.get("score", 0))["label"]
    subtype       = payload.get("subtype", "")

    print("\n══ [explain] RAW PAYLOAD FROM AXUM ════════════════════════════════════")
    print(f"  subtype       : {subtype}")
    print(f"  question      : {question}")
    print(f"  correct_label : {correct_label} (derived from max score)")
    for o in options:
        marker = " ← correct" if o.get("label") == correct_label else ""
        print(f"    {o['label']}. {o['content']}  [score={o.get('score', '?')}]{marker}")
    print("════════════════════════════════════════════════════════════════════════\n")

    system_prompt = _explain_system_prompt(subtype)
    examples      = embedder.search(question, top_k=3)

    print("── [explain] RAG examples retrieved ───────────────────────────────────")
    for i, ex in enumerate(examples, 1):
        print(f"  [{i}] score={ex.get('score', '?'):.4f}  {ex.get('content', '')[:100]}")
        if ex.get("explanation"):
            print(f"       explanation: {ex['explanation'][:80]}...")
    print("────────────────────────────────────────────────────────────────────────\n")

    user_message  = build_prompt(question, options, correct_label, examples)

    print("── [explain] FULL PROMPT SENT TO OLLAMA ───────────────────────────────")
    print(f"[SYSTEM]\n{system_prompt}")
    print(f"\n[USER]\n{user_message}")
    print("────────────────────────────────────────────────────────────────────────\n")

    result = call_llm(user_message, system_prompt=system_prompt, cancel_event=cancel_event)

    print("── [explain] OLLAMA OUTPUT ─────────────────────────────────────────────")
    print(result)
    print("────────────────────────────────────────────────────────────────────────\n")

    if _needs_math(subtype):
        return {
            "explanation": plain_to_latex(result.get("explanation", "")),
            "tip":         plain_to_latex(result.get("tip", "")),
        }
    return {
        "explanation": result.get("explanation", ""),
        "tip":         result.get("tip", ""),
    }


def handle_generate(payload: dict, cancel_event: "threading.Event | None" = None) -> dict:
    source_question      = payload["source_question"]
    source_options       = payload["source_options"]
    source_correct_label = next((o["label"] for o in source_options if o.get("score", 0) == 5), "")
    category             = payload["category"]
    subtype              = payload.get("subtype", "")

    print("\n══ [generate] INCOMING REQUEST ═════════════════════════════════════════")
    print(f"  category       : {category}")
    print(f"  source_question: {source_question}")
    for o in source_options:
        print(f"    {o['label']}. {o['content']} (score={o.get('score', '?')})")
    print("════════════════════════════════════════════════════════════════════════\n")

    examples = embedder.search(source_question, top_k=5)
    examples = [ex for ex in examples if ex.get("content", "").strip() != source_question.strip()]

    print(f"── [generate] RAG retrieved {len(examples)} examples ──────────────────────────────")
    for i, ex in enumerate(examples, 1):
        has_exp = bool(ex.get("explanation"))
        print(f"  [{i}] {'✓' if has_exp else '✗'} {ex.get('content', '')[:80]}")
    print("────────────────────────────────────────────────────────────────────────\n")

    user_message  = build_generation_prompt(source_question, source_options, source_correct_label,
                                             category, subtype, examples)
    system_prompt = _generate_system_prompt(subtype)
    apply_math    = _needs_math(subtype)

    print("── [generate] PROMPT sent to Ollama ────────────────────────────────────")
    print(user_message)
    print("────────────────────────────────────────────────────────────────────────\n")

    result = call_llm(user_message, system_prompt=system_prompt, cancel_event=cancel_event)

    print("── [generate] LLM raw output ───────────────────────────────────────────")
    print(result)
    print("────────────────────────────────────────────────────────────────────────\n")

    options_raw   = result.get("options", [])
    correct_label = result.get("correct_label", "").strip().upper()

    if len(options_raw) != 5:
        raise RuntimeError(f"Model returned {len(options_raw)} options (expected 5)")

    # ── TKP path ─────────────────────────────────────────────────────────────
    if subtype in _SITUATIONAL_SUBTYPES:
        tkp_scores: dict[str, int] = {}
        for o in options_raw:
            label = o.get("label", "").strip().upper()
            try:
                tkp_scores[label] = max(1, min(5, int(o.get("score", 1))))
            except (TypeError, ValueError):
                tkp_scores[label] = 1
        if len(set(tkp_scores.values())) < 3:
            raise RuntimeError(f"TKP scores not sufficiently varied: {tkp_scores}")
        best_label = max(tkp_scores, key=lambda k: tkp_scores[k])
        print(f"✓ [generate] TKP scores={tkp_scores} best_label={best_label}\n")
        return _build_result(result, options_raw, best_label, apply_math=False, tkp_scores=tkp_scores)

    valid_labels = {o.get("label", "").strip().upper() for o in options_raw}
    if correct_label not in valid_labels:
        raise RuntimeError(f"Model returned invalid correct_label '{correct_label}'")

    if not apply_math:
        print(f"✓ [generate] non-math — correct_label={correct_label}\n")
        return _build_result(result, options_raw, correct_label, apply_math=False)

    # ── Direct computation ────────────────────────────────────────────────────
    content_label, computed_value = _compute_from_content(result.get("content", ""), options_raw)
    if content_label is _NOT_FOUND:
        if computed_value:
            for o in options_raw:
                if o.get("label", "").strip().upper() == correct_label:
                    print(f"ℹ [generate] patching option {correct_label}: {o['content']!r} → {computed_value!r}")
                    o["content"] = computed_value
                    break
            print(f"✓ [generate] option patched — correct_label={correct_label}\n")
            return _build_result(result, options_raw, correct_label, apply_math=True)
        raise RuntimeError("Computed answer unavailable and no matching option found")
    elif content_label is not None:
        if content_label != correct_label:
            print(f"ℹ [generate] correct_label override: {correct_label} → {content_label}")
        correct_label = content_label
        print(f"✓ [generate] confirmed by direct computation ({content_label})\n")
        return _build_result(result, options_raw, correct_label, apply_math=True)

    # ── LLM correction pass ───────────────────────────────────────────────────
    correction_input = json.dumps({
        "content":       result.get("content", ""),
        "options":       options_raw,
        "correct_label": correct_label,
        "explanation":   result.get("explanation", ""),
        "tip":           result.get("tip", ""),
    }, ensure_ascii=False)

    print("── [generate] LLM correction pass ─────────────────────────────────────")
    corrected = call_llm(correction_input, system_prompt=CORRECTION_SYSTEM_PROMPT, cancel_event=cancel_event)
    print(corrected)
    print("────────────────────────────────────────────────────────────────────────\n")

    corrected_options = corrected.get("options", options_raw)
    corrected_label   = corrected.get("correct_label", correct_label).strip().upper()
    corrected_labels  = {o.get("label", "").strip().upper() for o in corrected_options}

    if len(corrected_options) == 5 and corrected_label in corrected_labels:
        if corrected_options != options_raw or corrected_label != correct_label:
            print(f"ℹ [generate] correction applied: {correct_label} → {corrected_label}")
        options_raw   = corrected_options
        correct_label = corrected_label
        result["content"]     = corrected.get("content",     result.get("content", ""))
        result["explanation"] = corrected.get("explanation", result.get("explanation", ""))
        result["tip"]         = corrected.get("tip",         result.get("tip", ""))
    else:
        print("⚠ [generate] correction output invalid — keeping original")

    # ── Python deterministic inference ────────────────────────────────────────
    inferred = _infer_correct_label(result.get("explanation", ""), options_raw)
    if inferred is _NOT_FOUND:
        raise RuntimeError("No option matches the correct answer in the explanation")
    elif inferred is not _NO_MATH:
        if inferred != correct_label:
            print(f"ℹ [generate] Python inference override: {correct_label} → {inferred}")
        correct_label = inferred

    print(f"✓ [generate] validation passed — correct_label={correct_label}\n")
    return _build_result(result, options_raw, correct_label, apply_math=True)


def handle_analogi(cancel_event: "threading.Event | None" = None) -> dict:
    max_attempts = 3
    last_error   = "Unknown error"

    for attempt in range(1, max_attempts + 1):
        print(f"\n══ [analogi/generate] attempt {attempt}/{max_attempts} ══════════════════════")
        try:
            result   = call_llm("Generate a new analogi gambar question spec now.",
                                   system_prompt=ANALOGI_SPEC_SYSTEM_PROMPT,
                                   cancel_event=cancel_event)
            raw_text = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
            spec     = _extract_spec_json(raw_text)
            spec     = _normalise_analogi_spec(spec)
            print(f"  spec cells: a={len(spec.get('cell_a', []))} b={len(spec.get('cell_b', []))} "
                  f"c={len(spec.get('cell_c', []))} d={len(spec.get('cell_d', []))}")

            errors = _validate_analogi_spec(spec)
            if errors:
                last_error = "; ".join(errors)
                print(f"  spec invalid: {last_error}")
                continue

            data = _process_analogi_no_db(spec)
            print(f"  ✓ rendered: {data['image_url']}")

            return {
                "content":     data["content"],
                "image_url":   data["image_url"],
                "explanation": data["explanation"],
                "options":     data["options"],
            }
        except Exception as e:
            last_error = str(e)
            print(f"  error: {e}")
            continue

    raise RuntimeError(f"Failed to generate analogi question after {max_attempts} attempts: {last_error}")


# ── Socket server ─────────────────────────────────────────────────────────────

HANDLERS = {
    "explain":  lambda p, c: handle_explain(p, c),
    "generate": lambda p, c: handle_generate(p, c),
    "analogi":  lambda _, c: handle_analogi(c),
}


async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    cancel_event = threading.Event()

    async def _monitor_disconnect():
        try:
            data = await reader.read(1)
            if not data:  # EOF — Rust side dropped the UDS socket
                cancel_event.set()
                print("[serve] client disconnected — cancel_event set")
        except Exception:
            cancel_event.set()

    monitor_task = None
    try:
        header_line = (await reader.readline()).decode().strip()
        if not header_line:
            return

        parts  = header_line.split(" ", 1)
        verb   = parts[0]
        length = int(parts[1]) if len(parts) > 1 else 0

        body_bytes = await reader.readexactly(length) if length > 0 else b"{}"
        payload    = json.loads(body_bytes)

        # Start the monitor only after the request is fully read.
        # At this point the Rust write half is still open (no early drop), so
        # reader.read(1) will block until the Rust task is cancelled — which is
        # exactly when we want to set the cancel event.
        monitor_task = asyncio.create_task(_monitor_disconnect())

        handler = HANDLERS.get(verb)
        if handler is None:
            raise ValueError(f"Unknown verb: {verb!r}")

        result   = await asyncio.to_thread(handler, payload, cancel_event)
        resp     = json.dumps(result, ensure_ascii=False).encode()
        writer.write(f"ok {len(resp)}\n".encode())
        writer.write(resp)

    except Exception as e:
        msg = str(e).encode()
        writer.write(f"error {len(msg)}\n".encode())
        writer.write(msg)
    finally:
        if monitor_task is not None:
            monitor_task.cancel()
        await writer.drain()
        writer.close()
        await writer.wait_closed()


async def main():
    _init()

    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    server = await asyncio.start_unix_server(handle_connection, SOCKET_PATH)
    print(f"ML service listening on {SOCKET_PATH}", flush=True)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
