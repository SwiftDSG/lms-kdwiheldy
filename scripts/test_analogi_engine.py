#!/usr/bin/env python3
"""
test_analogi_engine.py — local render test (no server, no DB, no Ollama).

Exercises:
  - validate_spec       (both modes)
  - difficulty_score    (new from paper)
  - _check_rule_compatibility (new from paper)
  - auto_distractors_scd      (new SCD logic)
  - auto_distractors_explicit (explicit mode)
  - render_cell / render_analogy_composite

Saves all rendered images to /tmp/analogi_test/<spec_name>/ and then
opens the folder so you can inspect them.

Usage:
  python3 test_analogi_engine.py           # run all specs
  python3 test_analogi_engine.py legacy    # only legacy specs
  python3 test_analogi_engine.py explicit  # only explicit-mode specs
"""

import os
import random
import sys
import subprocess

from analogi_engine import (
    validate_spec,
    apply_rules,
    auto_distractors_scd,
    auto_distractors_explicit,
    difficulty_score,
    _check_rule_compatibility,
    _auto_explanation,
    render_cell,
    render_analogy_composite,
    _cell_key,
)

OUT_ROOT = "/tmp/analogi_test"

# ── Test specs ────────────────────────────────────────────────────────────────

LEGACY_SPECS = [
    {
        "_name": "legacy_easy_invert",
        "format": "analogy",
        "title": "TIU - Analogi Gambar",
        "content": "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?",
        "cell_a": [
            {"shape": "circle",   "size": "large",  "filled": True,  "pos": "TL"},
            {"shape": "square",   "size": "small",  "filled": False, "pos": "BR"},
            {"shape": "triangle", "size": "medium", "filled": True,  "pos": "C"},
        ],
        "cell_c": [
            {"shape": "hexagon",  "size": "medium", "filled": False, "pos": "TC"},
            {"shape": "diamond",  "size": "large",  "filled": True,  "pos": "ML"},
            {"shape": "star",     "size": "small",  "filled": False, "pos": "BR"},
        ],
        "rules": [
            {"op": "invert_fills"},
        ],
    },
    {
        "_name": "legacy_medium_reflect_invert",
        "format": "analogy",
        "title": "TIU - Analogi Gambar",
        "content": "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?",
        "cell_a": [
            {"shape": "circle",   "size": "large",  "filled": True,  "pos": "TL"},
            {"shape": "arrow",    "size": "small",  "filled": False, "pos": "C",  "rotation": 0},
            {"shape": "triangle", "size": "medium", "filled": True,  "pos": "BR"},
        ],
        "cell_c": [
            {"shape": "pentagon", "size": "small",  "filled": True,  "pos": "TC"},
            {"shape": "star",     "size": "large",  "filled": False, "pos": "MR"},
            {"shape": "hexagon",  "size": "medium", "filled": True,  "pos": "BC"},
        ],
        "rules": [
            {"op": "reflect_h"},
            {"op": "invert_fills"},
        ],
    },
    {
        "_name": "legacy_hard_rotate_reflect_swap",
        "format": "analogy",
        "title": "TIU - Analogi Gambar",
        "content": "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?",
        "cell_a": [
            {"shape": "circle",   "size": "large",  "filled": True,  "pos": "TL"},
            {"shape": "triangle", "size": "small",  "filled": False, "pos": "C",  "rotation": 45},
            {"shape": "square",   "size": "medium", "filled": True,  "pos": "BR"},
        ],
        "cell_c": [
            {"shape": "hexagon",  "size": "small",  "filled": False, "pos": "TR"},
            {"shape": "diamond",  "size": "large",  "filled": True,  "pos": "ML"},
            {"shape": "cross",    "size": "medium", "filled": False, "pos": "BC"},
        ],
        "rules": [
            {"op": "rotate_shapes", "step": 90, "direction": "cw"},
            {"op": "reflect_v"},
            {"op": "swap_sizes"},
        ],
    },
    {
        "_name": "legacy_compatibility_warning",
        "format": "analogy",
        "title": "TIU - Analogi Gambar",
        "content": "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?",
        "cell_a": [
            {"shape": "circle", "size": "large", "filled": True,  "pos": "TL"},
            {"shape": "square", "size": "small", "filled": False, "pos": "BR"},
        ],
        "cell_c": [
            {"shape": "star",   "size": "medium", "filled": False, "pos": "C"},
            {"shape": "cross",  "size": "small",  "filled": True,  "pos": "TR"},
        ],
        # reflect_h + reflect_v = 180° rotation (should trigger warning)
        "rules": [
            {"op": "reflect_h"},
            {"op": "reflect_v"},
        ],
    },
]

EXPLICIT_SPECS = [
    {
        "_name": "explicit_reflect_invert",
        "format": "analogy",
        "title": "TIU - Analogi Gambar",
        "content": "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?",
        "explanation": (
            "Pola: posisi bentuk dicerminkan horizontal (kiri↔kanan), "
            "kemudian isian dibalik (padat↔kosong)."
        ),
        "cell_a": [
            {"shape": "circle",   "size": "large",  "filled": True,  "pos": "TL"},
            {"shape": "arrow",    "size": "small",  "filled": False, "pos": "C"},
            {"shape": "triangle", "size": "medium", "filled": True,  "pos": "BR"},
        ],
        "cell_b": [
            {"shape": "circle",   "size": "large",  "filled": False, "pos": "TR"},
            {"shape": "arrow",    "size": "small",  "filled": True,  "pos": "C"},
            {"shape": "triangle", "size": "medium", "filled": False, "pos": "BL"},
        ],
        "cell_c": [
            {"shape": "pentagon", "size": "small",  "filled": True,  "pos": "TC"},
            {"shape": "star",     "size": "large",  "filled": False, "pos": "MR"},
            {"shape": "hexagon",  "size": "medium", "filled": True,  "pos": "BC"},
        ],
        "cell_d": [
            {"shape": "pentagon", "size": "small",  "filled": False, "pos": "TC"},
            {"shape": "star",     "size": "large",  "filled": True,  "pos": "ML"},
            {"shape": "hexagon",  "size": "medium", "filled": False, "pos": "BC"},
        ],
    },
]

# ── Render helper ─────────────────────────────────────────────────────────────

def run_spec(spec: dict, out_dir: str):
    name = spec.get("_name", "unnamed")
    print(f"\n{'─'*60}")
    print(f"Spec: {name}")
    print(f"{'─'*60}")

    # Strip private keys before validation
    clean = {k: v for k, v in spec.items() if not k.startswith("_")}

    errors = validate_spec(clean)
    if errors:
        print("  VALIDATION FAILED:")
        for e in errors:
            print(f"    • {e}")
        return False

    explicit = "cell_b" in clean and "cell_d" in clean
    rules    = clean.get("rules") or []
    cell_a   = clean["cell_a"]
    cell_c   = clean["cell_c"]

    if explicit:
        cell_b      = clean["cell_b"]
        correct     = clean["cell_d"]
        explanation = clean.get("explanation", "")
        distractors = auto_distractors_explicit(cell_c, cell_b, correct)
        print(f"  Mode:        explicit (4 cells authored)")
        print(f"  Explanation: {explanation}")
    else:
        cell_b      = apply_rules(cell_a, rules)
        correct     = apply_rules(cell_c, rules)
        explanation = clean.get("explanation") or _auto_explanation(rules)

        compat = _check_rule_compatibility(rules)
        for w in compat:
            print(f"  ⚠ [compatibility] {w}")

        diff = difficulty_score(rules)
        print(f"  Mode:        legacy ({len(rules)} rule(s))")
        print(f"  Difficulty:  {diff['level']} (score={diff['score']})")
        print(f"  Explanation: {explanation}")

        distractors = auto_distractors_scd(cell_c, rules, correct)

    # Shuffle options
    all_opts = [correct] + distractors
    order    = list(range(len(all_opts)))
    random.shuffle(order)
    correct_idx = order.index(0)
    shuffled    = [all_opts[i] for i in order]
    labels      = "ABCDE"

    # Verify no distractor matches the answer
    correct_key = _cell_key(correct)
    for i, d in enumerate(distractors):
        if _cell_key(d) == correct_key:
            print(f"  ⚠ distractor {i} is identical to correct answer!")

    os.makedirs(out_dir, exist_ok=True)

    # Render composite question image
    composite = render_analogy_composite(cell_a, cell_b, cell_c)
    composite.save(os.path.join(out_dir, "question.png"))
    print(f"  Question:    {out_dir}/question.png")

    # Render option cells
    for i, shapes in enumerate(shuffled):
        label  = labels[i]
        marker = " ✓" if i == correct_idx else ""
        img    = render_cell(shapes)
        fname  = f"option_{label}.png"
        img.save(os.path.join(out_dir, fname))
        print(f"  Option {label}{marker}:   {out_dir}/{fname}")

    print(f"  Correct answer: {labels[correct_idx]}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    mode_filter = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    specs_to_run = []
    if mode_filter in ("all", "legacy"):
        specs_to_run += [(s, "legacy") for s in LEGACY_SPECS]
    if mode_filter in ("all", "explicit"):
        specs_to_run += [(s, "explicit") for s in EXPLICIT_SPECS]

    if not specs_to_run:
        print(f"Unknown filter {mode_filter!r}. Use: all | legacy | explicit")
        sys.exit(1)

    passed = 0
    failed = 0
    for spec, kind in specs_to_run:
        name    = spec.get("_name", "unnamed")
        out_dir = os.path.join(OUT_ROOT, name)
        ok = run_spec(spec, out_dir)
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{'═'*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"Images:  {OUT_ROOT}/")

    # Open the output folder on macOS
    if sys.platform == "darwin":
        subprocess.run(["open", OUT_ROOT])


if __name__ == "__main__":
    random.seed(42)  # reproducible option ordering for easier comparison
    main()
