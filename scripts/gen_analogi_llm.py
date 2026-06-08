#!/usr/bin/env python3
"""
gen_analogi_llm.py — LLM-driven analogi gambar question generator.

Uses Ollama to generate a question spec (all 4 cells explicitly defined)
in JSON, then passes it to analogi_engine.py for rendering and DB insertion.

Usage:
  python3 gen_analogi_llm.py                    # generate one random question
  python3 gen_analogi_llm.py --model llama3.2   # specify Ollama model
  python3 gen_analogi_llm.py --dry-run          # print spec only, don't upload
  python3 gen_analogi_llm.py --retries 5        # max LLM retry attempts
"""

import argparse
import json
import re
import sys
import requests

from analogi_engine import validate_spec, process

OLLAMA_URL    = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:7b"

# ── Prompt ────────────────────────────────────────────────────────────────────

SCHEMA_DOC = """
You generate analogi gambar (picture analogy) question specs for Indonesian CPNS exams.

OUTPUT: A single JSON object — no markdown, no explanation text outside the JSON.

APPROACH:
  1. Choose a visual transformation rule (e.g. "mirror left-right then invert fills").
  2. Write a clear Indonesian explanation of that rule.
  3. Design cell_a (the first image).
  4. Mentally apply the rule → write cell_b (what cell_a becomes).
  5. Design cell_c (a different-looking image with different shapes/positions).
  6. Mentally apply the same rule → write cell_d (the correct answer).
  The question asks: "A : B = C : ?" and the answer is cell_d.

SCHEMA:
{
  "format": "analogy",
  "title": "<string>",
  "content": "<string — Indonesian question text>",
  "explanation": "<string — Indonesian description of the rule, REQUIRED>",
  "category": "TIU",
  "time_limit": 30,
  "cell_a": [ <shape objects> ],
  "cell_b": [ <shape objects — result of rule applied to cell_a> ],
  "cell_c": [ <shape objects — different from cell_a> ],
  "cell_d": [ <shape objects — result of rule applied to cell_c, this is the ANSWER> ]
}

SHAPE OBJECT:
{
  "shape":    <shape>,
  "size":     <size>,
  "filled":   <bool>,
  "pos":      <pos>,
  "rotation": <rotation>   ← optional, default 0
}

  shape    : "circle" | "square" | "triangle" | "diamond" | "pentagon"
             "hexagon" | "star" | "cross" | "semicircle" | "arrow" | "line" | "wave"
  size     : "small" | "medium" | "large"
  filled   : true (solid black) | false (outline only)
  pos      : 3×3 named grid — TL TC TR / ML C MR / BL BC BR
             (aliases: T=TC, B=BC, L=ML, R=MR)
             Each position may appear at most ONCE per cell.
  rotation : 0 | 30 | 45 | 60 | 90 | 120 | 135 | 150 | 180  (degrees)
             Especially useful for "line", "arrow", "triangle", "semicircle".

TRANSFORMATION RULE IDEAS (pick ONE or COMBINE two):
  • Mirror left-right: TL↔TR, ML↔MR, BL↔BR (TC, BC, C stay)
  • Mirror top-bottom: TL↔BL, TC↔BC, TR↔BR (ML, MR, C stay)
  • Invert fills: filled↔outline for every shape
  • Rotate positions clockwise (corners: TL→TR→BR→BL→TL)
  • Rotate positions clockwise (edges: TC→MR→BC→ML→TC)
  • Rotate every shape's orientation by 90° (changes rotation field)
  • Swap sizes: small→medium→large→small cycle
  • Shift all shapes one step right/left/up/down
  • Mix of any two of the above

CONSTRAINTS:
  • No two shapes in the same cell may share a position slot.
  • cell_a and cell_c must look visually different (different shapes, fills, or positions).
  • cell_b must be the exact result of applying your chosen rule to cell_a.
  • cell_d must be the exact result of applying the same rule to cell_c.
  • Use 2–5 shapes per cell.
  • Rules applied to cell_b and cell_d must be CONSISTENT — same rule, same result.

DIFFICULTY TARGET: Medium-hard. Combine 2 transformations for a harder question.
"""

EXAMPLE_SPEC = {
    "format": "analogy",
    "title": "TIU - Analogi Gambar",
    "content": "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?",
    "explanation": (
        "Pola yang berlaku: posisi bentuk dicerminkan secara horizontal (kiri↔kanan), "
        "kemudian isian setiap bentuk dibalik (padat↔kosong)."
    ),
    "category": "TIU",
    "time_limit": 30,
    "cell_a": [
        {"shape": "circle",   "size": "large",  "filled": True,  "pos": "TL", "rotation": 0},
        {"shape": "arrow",    "size": "small",  "filled": False, "pos": "C",  "rotation": 0},
        {"shape": "triangle", "size": "medium", "filled": True,  "pos": "BR", "rotation": 0},
    ],
    "cell_b": [
        {"shape": "circle",   "size": "large",  "filled": False, "pos": "TR", "rotation": 0},
        {"shape": "arrow",    "size": "small",  "filled": True,  "pos": "C",  "rotation": 0},
        {"shape": "triangle", "size": "medium", "filled": False, "pos": "BL", "rotation": 0},
    ],
    "cell_c": [
        {"shape": "pentagon", "size": "small",  "filled": True,  "pos": "TC", "rotation": 0},
        {"shape": "star",     "size": "large",  "filled": False, "pos": "MR", "rotation": 0},
        {"shape": "hexagon",  "size": "medium", "filled": True,  "pos": "BC", "rotation": 0},
    ],
    "cell_d": [
        {"shape": "pentagon", "size": "small",  "filled": False, "pos": "TC", "rotation": 0},
        {"shape": "star",     "size": "large",  "filled": True,  "pos": "ML", "rotation": 0},
        {"shape": "hexagon",  "size": "medium", "filled": False, "pos": "BC", "rotation": 0},
    ],
}


def build_prompt() -> str:
    return (
        SCHEMA_DOC
        + "\n\nEXAMPLE (for reference, do NOT copy — generate a NEW one with different shapes and a different rule):\n"
        + json.dumps(EXAMPLE_SPEC, indent=2, ensure_ascii=False)
        + "\n\nNow generate a new, creative analogi gambar question spec. "
          "Use different shapes, a different rule combination, and different cell arrangements "
          "from the example. Remember: cell_b = rule(cell_a) and cell_d = rule(cell_c). "
          "Output ONLY the JSON object."
    )


# ── LLM call ──────────────────────────────────────────────────────────────────

def call_ollama(prompt: str, model: str) -> str:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["response"]


# ── Response parsing ──────────────────────────────────────────────────────────

def extract_json(text: str) -> dict:
    """
    Extract and parse the first JSON object from the LLM response.
    Handles responses that wrap JSON in markdown code fences.
    """
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = re.sub(r"```\s*$", "", text).strip()

    # Find the outermost {...}
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")

    # Walk to find matching closing brace
    depth = 0
    end   = -1
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("Unterminated JSON object in LLM response")

    raw = text[start:end]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse error: {e}\nRaw: {raw[:300]}")


def normalise_spec(spec: dict) -> dict:
    """Coerce common LLM mistakes to the expected types."""
    for cell_key in ("cell_a", "cell_b", "cell_c", "cell_d"):
        for s in spec.get(cell_key, []):
            if isinstance(s.get("filled"), int):
                s["filled"] = bool(s["filled"])
            s.setdefault("rotation", 0)
    for rule in spec.get("rules", []):
        if rule.get("op") == "rotate_positions":
            rule.setdefault("ring", "corners")
            rule.setdefault("direction", "cw")
            rule.setdefault("amount", 1)
        if rule.get("op") == "rotate_shapes":
            rule.setdefault("direction", "cw")
            rule.setdefault("step", 45)
        if rule.get("op") == "shift_positions":
            rule.setdefault("wrap", False)
    spec.setdefault("format", "analogy")
    spec.setdefault("category", "TIU")
    spec.setdefault("time_limit", 30)
    return spec


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate analogi gambar questions via LLM")
    parser.add_argument("--model",   default=DEFAULT_MODEL, help="Ollama model name")
    parser.add_argument("--retries", type=int, default=3,   help="Max LLM retry attempts")
    parser.add_argument("--dry-run", action="store_true",   help="Print spec only, skip upload")
    args = parser.parse_args()

    prompt  = build_prompt()
    spec    = None
    errors  = []

    for attempt in range(1, args.retries + 1):
        print(f"[Attempt {attempt}/{args.retries}] Calling Ollama ({args.model})…")
        try:
            raw  = call_ollama(prompt, args.model)
            spec = normalise_spec(extract_json(raw))
        except Exception as e:
            print(f"  Parse error: {e}")
            continue

        errors = validate_spec(spec)
        if not errors:
            print("  Spec valid ✓")
            break
        else:
            print(f"  Validation failed ({len(errors)} error(s)):")
            for err in errors:
                print(f"    • {err}")
            spec = None

    if spec is None:
        print("All attempts failed. Last errors:")
        for err in errors:
            print(f"  • {err}")
        sys.exit(1)

    print("\nGenerated spec:")
    print(json.dumps(spec, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("\n[dry-run] Skipping upload and DB insert.")
        return

    print()
    try:
        result = process(spec, verbose=True)
        print(f"\nquiz_id: {result.get('quiz_id')}")
    except Exception as e:
        print(f"Engine error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
