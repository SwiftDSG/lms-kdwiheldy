#!/usr/bin/env python3
"""
analogi_engine.py — rendering engine for CPNS analogi gambar questions.

Accepts a question spec dict and:
  1. Validates it.
  2. Derives cell_b and the correct answer (cell_d).
  3. Auto-generates 4 plausible distractors.
  4. Renders images with Pillow.
  5. Uploads images to the server.
  6. Inserts the question into MongoDB via /api/v1/admin/questions/bulk.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXPLICIT MODE (preferred) — all 4 cells defined by the author:
  cell_a, cell_b, cell_c, cell_d are all provided.
  The rule is expressed as a natural-language "explanation" (required).
  "rules" may optionally be included for a soft consistency check,
  but the explicit cells take precedence.
  Supports any visual transformation, even those the rule DSL can't express.

LEGACY MODE — derive cells from rules:
  Only cell_a and cell_c are provided; cell_b and cell_d are computed.
  "rules" is required. "explanation" is auto-generated if omitted.
  Guarantees A→B and C→D follow the exact same formal rule.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPEC FORMAT (explicit mode)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "format":      "analogy",
  "title":       "TIU - Analogi Gambar",
  "content":     "Tentukan gambar yang tepat untuk melengkapi A : B = C : ?",
  "explanation": "<Indonesian description of the rule — required>",
  "cell_a": [ <shape>, ... ],
  "cell_b": [ <shape>, ... ],   ← result of rule applied to cell_a
  "cell_c": [ <shape>, ... ],
  "cell_d": [ <shape>, ... ]    ← correct answer (rule applied to cell_c)
}

SPEC FORMAT (legacy mode)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "format":      "analogy",
  "title":       "TIU - Analogi Gambar",
  "content":     "...",
  "explanation": "...",   # auto-generated from rules if omitted
  "cell_a": [ <shape>, ... ],
  "cell_c": [ <shape>, ... ],
  "rules":  [ <rule>,  ... ]
}

Shape:
  {
    "shape":    <name>,   # see SHAPES below
    "size":     <size>,   # see SIZES  below
    "filled":   true|false,
    "pos":      <pos>,    # see POSITIONS below
    "rotation": 0         # optional, degrees — see ROTATIONS below
  }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POSITIONS   3×3 named grid:
               TL  TC  TR
               ML   C  MR
               BL  BC  BR
            Aliases: T=TC, B=BC, L=ML, R=MR

SHAPES      circle | square | triangle | diamond | pentagon
            hexagon | star | cross | semicircle | arrow | line | wave

SIZES       small | medium | large

ROTATIONS   0 | 30 | 45 | 60 | 90 | 120 | 135 | 150 | 180  (degrees, default 0)

RULES (legacy mode):
  rotate_positions  direction:"cw"|"ccw"  amount:1-7  ring:"corners"|"outer"|"edges"
  rotate_shapes     step:30|45|60|90      direction:"cw"|"ccw"
  invert_fills      (no params)
  swap_sizes        (no params)
  reflect_h         (no params)
  reflect_v         (no params)
  shift_positions   direction:"right"|"left"|"up"|"down"  wrap:true|false
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import io
import math
import random
import requests
from PIL import Image, ImageDraw, ImageFont

API    = "http://localhost:3000"
CELL   = 240   # standalone option cell (px)
QCELL  = 160   # cell inside A:B=C:? composite
BORDER = 8

SIZE_R = {"small": 14, "medium": 22, "large": 30}   # radii at CELL scale

# ── Position grid ─────────────────────────────────────────────────────────────

POS_ALIASES = {"T": "TC", "B": "BC", "L": "ML", "R": "MR"}

VALID_POS_CANONICAL = {"TL", "TC", "TR", "ML", "C", "MR", "BL", "BC", "BR"}
VALID_POS = VALID_POS_CANONICAL | set(POS_ALIASES)

POS_GRID = {
    "TL": (0, 0), "TC": (0, 1), "TR": (0, 2),
    "ML": (1, 0), "C":  (1, 1), "MR": (1, 2),
    "BL": (2, 0), "BC": (2, 1), "BR": (2, 2),
}
GRID_POS = {v: k for k, v in POS_GRID.items()}

# Rotation rings (clockwise order)
POS_CORNERS_CW = ["TL", "TR", "BR", "BL"]
POS_OUTER_CW   = ["TL", "TC", "TR", "MR", "BR", "BC", "BL", "ML"]
POS_EDGES_CW   = ["TC", "MR", "BC", "ML"]
RINGS = {"corners": POS_CORNERS_CW, "outer": POS_OUTER_CW, "edges": POS_EDGES_CW}

VALID_SHAPES = {
    "circle", "square", "triangle", "diamond", "pentagon",
    "hexagon", "star", "cross", "semicircle", "arrow", "line", "wave",
}
VALID_SIZES      = {"small", "medium", "large"}
VALID_ROTATIONS  = {0, 30, 45, 60, 90, 120, 135, 150, 180}
VALID_OPS        = {
    "rotate_positions", "rotate_shapes", "invert_fills",
    "swap_sizes", "reflect_h", "reflect_v", "shift_positions",
}
VALID_DIRS       = {"cw", "ccw"}
VALID_SHIFT_DIRS = {"right", "left", "up", "down"}
VALID_RINGS      = set(RINGS)

# Difficulty weights from Blum & Holling (2018) LLTM basic parameters.
# Reflects each rule's empirical contribution to item difficulty (β).
RULE_DIFFICULTY_WEIGHTS: dict[str, int] = {
    "rotate_shapes":    3,  # hardest to mentally track
    "reflect_h":        2,
    "reflect_v":        2,
    "rotate_positions": 2,
    "shift_positions":  1,
    "invert_fills":     1,
    "swap_sizes":       1,
}


def _canonical(pos: str) -> str:
    return POS_ALIASES.get(pos, pos)


def _pos_center(pos: str, size: int) -> tuple[int, int]:
    row, col = POS_GRID[_canonical(pos)]
    step = size // 3
    half = step // 2
    return (col * step + half, row * step + half)


# ── Font helper ───────────────────────────────────────────────────────────────

def _font(size: int):
    for path in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ── Shape drawing ─────────────────────────────────────────────────────────────

def _poly_pts(cx: int, cy: int, r: int, n: int, start_deg: float = 0) -> list:
    return [
        (cx + r * math.cos(math.radians(start_deg + i * 360 / n)),
         cy + r * math.sin(math.radians(start_deg + i * 360 / n)))
        for i in range(n)
    ]


def _outline(draw, pts, color, lw: int):
    for i in range(len(pts)):
        draw.line([pts[i], pts[(i + 1) % len(pts)]], fill=color, width=lw)


def _shape_canvas(name: str, r: int, filled: bool, lw: int) -> Image.Image:
    """Render a single shape centered in a transparent RGBA canvas (no rotation)."""
    pad = lw + 4
    sz  = 2 * (r + pad)
    img  = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = sz // 2

    BLACK = (0, 0, 0, 255)
    fc    = BLACK if filled else (255, 255, 255, 255)

    if name == "circle":
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=fc, outline=BLACK, width=lw)

    elif name == "square":
        draw.rectangle([cx-r, cy-r, cx+r, cy+r], fill=fc, outline=BLACK, width=lw)

    elif name == "triangle":
        pts = [(cx, cy-r), (cx+r, cy+r), (cx-r, cy+r)]
        if filled:
            draw.polygon(pts, fill=BLACK)
        _outline(draw, pts, BLACK, lw)

    elif name == "diamond":
        pts = [(cx, cy-r), (cx+r, cy), (cx, cy+r), (cx-r, cy)]
        if filled:
            draw.polygon(pts, fill=BLACK)
        _outline(draw, pts, BLACK, lw)

    elif name == "pentagon":
        pts = _poly_pts(cx, cy, r, 5, start_deg=-90)
        if filled:
            draw.polygon(pts, fill=BLACK)
        _outline(draw, pts, BLACK, lw)

    elif name == "hexagon":
        pts = _poly_pts(cx, cy, r, 6, start_deg=0)
        if filled:
            draw.polygon(pts, fill=BLACK)
        _outline(draw, pts, BLACK, lw)

    elif name == "star":
        inner = max(4, int(r * 0.4))
        pts = []
        for i in range(10):
            rad = r if i % 2 == 0 else inner
            angle = math.radians(-90 + i * 36)
            pts.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
        if filled:
            draw.polygon(pts, fill=BLACK)
        _outline(draw, pts, BLACK, lw)

    elif name == "cross":
        arm = max(3, r // 3)
        draw.rectangle([cx-r, cy-arm, cx+r, cy+arm], fill=fc, outline=BLACK, width=lw)
        draw.rectangle([cx-arm, cy-r, cx+arm, cy+r], fill=fc, outline=BLACK, width=lw)

    elif name == "semicircle":
        draw.pieslice([cx-r, cy-r, cx+r, cy+r], start=180, end=360, fill=fc, outline=BLACK, width=lw)
        draw.line([(cx-r, cy), (cx+r, cy)], fill=BLACK, width=lw)

    elif name == "arrow":
        body_h = max(3, r // 3)
        head_w = r // 2
        draw.rectangle([cx-r, cy-body_h, cx, cy+body_h], fill=fc, outline=BLACK, width=lw)
        pts = [(cx, cy - r//2), (cx + head_w, cy), (cx, cy + r//2)]
        if filled:
            draw.polygon(pts, fill=BLACK)
        _outline(draw, pts, BLACK, lw)

    elif name == "line":
        draw.line([(cx-r, cy), (cx+r, cy)], fill=BLACK, width=lw)

    elif name == "wave":
        n_pts = 24
        amp = max(4, r // 3)
        pts = [
            (cx - r + (2 * r * i // n_pts),
             cy + int(amp * math.sin(2 * math.pi * 1.5 * i / n_pts)))
            for i in range(n_pts + 1)
        ]
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i + 1]], fill=BLACK, width=lw)

    return img


def _render_shape(name: str, r: int, filled: bool, rotation: int, lw: int) -> Image.Image:
    img = _shape_canvas(name, r, filled, lw)
    if rotation != 0:
        img = img.rotate(-rotation, resample=Image.BICUBIC, expand=False)
    return img


# ── Cell renderer ─────────────────────────────────────────────────────────────

def render_cell(shapes: list[dict], size: int = CELL, qmark: bool = False) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    b = max(4, BORDER * size // CELL)
    for i in range(b):
        draw.rectangle([i, i, size-1-i, size-1-i], outline=(0, 0, 0, 255))

    if qmark:
        draw.text(
            (size // 2, size // 2), "?",
            fill=(170, 170, 170, 255), font=_font(size // 2), anchor="mm",
        )
        return img.convert("RGB")

    # Subtle 3×3 grid guide
    step = size // 3
    for i in [1, 2]:
        draw.line([(b + 2, i * step), (size - b - 2, i * step)], fill=(220, 220, 220, 255), width=1)
        draw.line([(i * step, b + 2), (i * step, size - b - 2)], fill=(220, 220, 220, 255), width=1)

    scale = size / CELL
    lw    = max(3, int(5 * scale))

    for s in shapes:
        cx, cy  = _pos_center(s.get("pos", "C"), size)
        r       = max(6, int(SIZE_R[s["size"]] * scale))
        simg    = _render_shape(s["shape"], r, s["filled"], s.get("rotation", 0), lw)

        # Paste centered at (cx, cy), clipped to cell boundary
        ox = cx - simg.width  // 2
        oy = cy - simg.height // 2
        sx1 = max(0, -ox);      sy1 = max(0, -oy)
        dx1 = max(0, ox);       dy1 = max(0, oy)
        w   = min(simg.width  - sx1, size - dx1)
        h   = min(simg.height - sy1, size - dy1)
        if w > 0 and h > 0:
            region = simg.crop((sx1, sy1, sx1 + w, sy1 + h))
            img.paste(region, (dx1, dy1), region)

    return img.convert("RGB")


# ── Analogy composite (A : B = C : ?) ────────────────────────────────────────

def render_analogy_composite(
    cell_a: list[dict],
    cell_b: list[dict],
    cell_c: list[dict],
) -> Image.Image:
    sep_w   = 30
    pad     = 16
    q       = QCELL
    total_w = 4 * q + 3 * sep_w + 2 * pad
    total_h = q + 2 * pad

    img  = Image.new("RGB", (total_w, total_h), "white")
    draw = ImageDraw.Draw(img)
    fnt  = _font(28)

    x = pad
    for kind, data in [
        ("cell",  cell_a), ("sep", ":"),
        ("cell",  cell_b), ("sep", "="),
        ("cell",  cell_c), ("sep", ":"),
        ("qmark", None),
    ]:
        if kind == "cell":
            img.paste(render_cell(data, q), (x, pad))
            x += q
        elif kind == "qmark":
            img.paste(render_cell([], q, qmark=True), (x, pad))
            x += q
        else:
            draw.text((x + sep_w // 2, total_h // 2), data,
                      fill="black", font=fnt, anchor="mm")
            x += sep_w
    return img


# ── Upload helper ─────────────────────────────────────────────────────────────

def upload_image(img: Image.Image, filename: str) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    resp = requests.post(
        f"{API}/api/v1/admin/upload/image",
        files={"file": (filename, buf, "image/png")},
    )
    resp.raise_for_status()
    return resp.json()["url"]


# ── Rule engine ───────────────────────────────────────────────────────────────

def _rotate_positions(shapes: list[dict], direction: str = "cw", amount: int = 1, ring: str = "corners") -> list[dict]:
    order    = RINGS.get(ring, POS_CORNERS_CW)
    n        = len(order)
    step     = amount % n if direction == "cw" else (n - amount % n) % n
    ring_set = set(order)
    pmap     = {order[i]: order[(i + step) % n] for i in range(n)}
    return [
        {**s, "pos": pmap.get(_canonical(s["pos"]), _canonical(s["pos"]))}
        if _canonical(s["pos"]) in ring_set else dict(s)
        for s in shapes
    ]


def _rotate_shapes(shapes: list[dict], step: int = 45, direction: str = "cw") -> list[dict]:
    delta = step if direction == "cw" else -step
    return [{**s, "rotation": (s.get("rotation", 0) + delta) % 360} for s in shapes]


def _invert_fills(shapes: list[dict], **_) -> list[dict]:
    return [{**s, "filled": not s["filled"]} for s in shapes]


def _swap_sizes(shapes: list[dict], **_) -> list[dict]:
    cycle = {"small": "medium", "medium": "large", "large": "small"}
    return [{**s, "size": cycle.get(s["size"], s["size"])} for s in shapes]


def _reflect_h(shapes: list[dict], **_) -> list[dict]:
    m = {"TL": "TR", "TR": "TL", "ML": "MR", "MR": "ML",
         "BL": "BR", "BR": "BL", "TC": "TC", "BC": "BC", "C": "C"}
    return [{**s, "pos": m.get(_canonical(s["pos"]), _canonical(s["pos"]))} for s in shapes]


def _reflect_v(shapes: list[dict], **_) -> list[dict]:
    m = {"TL": "BL", "BL": "TL", "TC": "BC", "BC": "TC",
         "TR": "BR", "BR": "TR", "ML": "ML", "MR": "MR", "C": "C"}
    return [{**s, "pos": m.get(_canonical(s["pos"]), _canonical(s["pos"]))} for s in shapes]


def _shift_positions(shapes: list[dict], direction: str = "right", wrap: bool = False) -> list[dict]:
    dr, dc = {"right": (0, 1), "left": (0, -1), "down": (1, 0), "up": (-1, 0)}[direction]
    result = []
    for s in shapes:
        r, c = POS_GRID[_canonical(s["pos"])]
        nr, nc = r + dr, c + dc
        if wrap:
            nr, nc = nr % 3, nc % 3
        if 0 <= nr < 3 and 0 <= nc < 3:
            result.append({**s, "pos": GRID_POS[(nr, nc)]})
        # else: shape falls off edge — dropped intentionally
    return result


_OPS = {
    "rotate_positions": _rotate_positions,
    "rotate_shapes":    _rotate_shapes,
    "invert_fills":     _invert_fills,
    "swap_sizes":       _swap_sizes,
    "reflect_h":        _reflect_h,
    "reflect_v":        _reflect_v,
    "shift_positions":  _shift_positions,
}


def apply_rules(shapes: list[dict], rules: list[dict]) -> list[dict]:
    result = [dict(s) for s in shapes]
    for rule in rules:
        fn     = _OPS[rule["op"]]
        kwargs = {k: v for k, v in rule.items() if k != "op"}
        result = fn(result, **kwargs)
    return result


# ── Distractor generation (legacy mode) ──────────────────────────────────────

def _cell_key(shapes: list[dict]) -> frozenset:
    return frozenset(
        (_canonical(s.get("pos", "C")), s["shape"], s["size"], s["filled"], s.get("rotation", 0))
        for s in shapes
    )


def auto_distractors(
    cell_c: list[dict],
    rules: list[dict],
    correct: list[dict],
    count: int = 4,
) -> list[list[dict]]:
    correct_key = _cell_key(correct)
    seen        = {correct_key}
    candidates  = []

    def _add(shapes):
        if not shapes:
            return
        k = _cell_key(shapes)
        if k not in seen:
            seen.add(k)
            candidates.append([dict(s) for s in shapes])

    # Strategy 1: each rule applied alone
    for rule in rules:
        _add(apply_rules(cell_c, [rule]))

    # Strategy 2: per-rule modifications
    for i, rule in enumerate(rules):
        op   = rule["op"]
        rest = rules[:i] + rules[i + 1:]

        if op == "rotate_positions":
            flipped = {**rule, "direction": "ccw" if rule.get("direction") == "cw" else "cw"}
            _add(apply_rules(cell_c, rest + [flipped]))
            if rule.get("amount", 1) < 6:
                _add(apply_rules(cell_c, rest + [{**rule, "amount": rule.get("amount", 1) + 1}]))
            for ring in VALID_RINGS - {rule.get("ring", "corners")}:
                _add(apply_rules(cell_c, rest + [{**rule, "ring": ring}]))

        elif op == "rotate_shapes":
            flipped = {**rule, "direction": "ccw" if rule.get("direction", "cw") == "cw" else "cw"}
            _add(apply_rules(cell_c, rest + [flipped]))
            doubled = {**rule, "step": (rule.get("step", 45) * 2) % 360 or 90}
            _add(apply_rules(cell_c, rest + [doubled]))

        elif op == "shift_positions":
            opposites = {"right": "left", "left": "right", "up": "down", "down": "up"}
            _add(apply_rules(cell_c, rest + [{**rule, "direction": opposites[rule.get("direction", "right")]}]))

    # Strategy 3: no transformation
    _add([dict(s) for s in cell_c])

    # Strategy 4: skip last rule
    if len(rules) > 1:
        _add(apply_rules(cell_c, rules[:-1]))

    # Strategy 5: only last rule
    if len(rules) > 1:
        _add(apply_rules(cell_c, [rules[-1]]))

    # Fallback: perturb one property of the correct answer
    attempts = 0
    while len(candidates) < count and attempts < 40:
        attempts += 1
        perturbed = [dict(s) for s in correct]
        idx = random.randrange(len(perturbed))
        choice = random.choice(["fill", "size", "rotation", "shape"])
        if choice == "fill":
            perturbed[idx] = {**perturbed[idx], "filled": not perturbed[idx]["filled"]}
        elif choice == "size":
            others = [s for s in VALID_SIZES if s != perturbed[idx]["size"]]
            perturbed[idx] = {**perturbed[idx], "size": random.choice(others)}
        elif choice == "rotation":
            others = [r for r in VALID_ROTATIONS if r != perturbed[idx].get("rotation", 0)]
            perturbed[idx] = {**perturbed[idx], "rotation": random.choice(others)}
        elif choice == "shape":
            others = [sh for sh in VALID_SHAPES if sh != perturbed[idx]["shape"]]
            perturbed[idx] = {**perturbed[idx], "shape": random.choice(others)}
        _add(perturbed)

    return candidates[:count]


# ── Distractor generation (explicit mode) ────────────────────────────────────

def auto_distractors_explicit(
    cell_c: list[dict],
    cell_b: list[dict],
    correct: list[dict],
    count: int = 4,
) -> list[list[dict]]:
    """
    Generate distractors without formal rules.

    Strategy 1 — cell_c unchanged: the test-taker picks C itself (no transform).
    Strategy 2 — cell_b: wrong pairing (A's output, not C's).
    Strategy 3 — perturb one attribute of correct per axis (fill, size, shape, rotation).
    Strategy 4 — random perturbation fallback.
    """
    correct_key = _cell_key(correct)
    seen        = {correct_key}
    candidates  = []

    def _add(shapes):
        if not shapes:
            return
        k = _cell_key(shapes)
        if k not in seen:
            seen.add(k)
            candidates.append([dict(s) for s in shapes])

    # Strategy 1: no transformation (cell_c as-is)
    _add([dict(s) for s in cell_c])

    # Strategy 2: cell_b (wrong pairing)
    _add([dict(s) for s in cell_b])

    # Strategy 3: single-attribute perturbations of correct
    for attr in ("filled", "size", "shape", "rotation"):
        if len(candidates) >= count:
            break
        perturbed = [dict(s) for s in correct]
        changed = False
        for idx in range(len(perturbed)):
            s = perturbed[idx]
            if attr == "filled":
                perturbed[idx] = {**s, "filled": not s["filled"]}
                changed = True
                break
            elif attr == "size":
                others = [sz for sz in VALID_SIZES if sz != s["size"]]
                if others:
                    perturbed[idx] = {**s, "size": random.choice(others)}
                    changed = True
                    break
            elif attr == "shape":
                others = [sh for sh in VALID_SHAPES if sh != s["shape"]]
                if others:
                    perturbed[idx] = {**s, "shape": random.choice(others)}
                    changed = True
                    break
            elif attr == "rotation":
                others = [r for r in VALID_ROTATIONS if r != s.get("rotation", 0)]
                if others:
                    perturbed[idx] = {**s, "rotation": random.choice(others)}
                    changed = True
                    break
        if changed:
            _add(perturbed)

    # Strategy 4: random perturbation fallback
    attempts = 0
    while len(candidates) < count and attempts < 40:
        attempts += 1
        if not correct:
            break
        perturbed = [dict(s) for s in correct]
        idx    = random.randrange(len(perturbed))
        choice = random.choice(["fill", "size", "rotation", "shape"])
        s      = perturbed[idx]
        if choice == "fill":
            perturbed[idx] = {**s, "filled": not s["filled"]}
        elif choice == "size":
            others = [sz for sz in VALID_SIZES if sz != s["size"]]
            if others:
                perturbed[idx] = {**s, "size": random.choice(others)}
        elif choice == "rotation":
            others = [r for r in VALID_ROTATIONS if r != s.get("rotation", 0)]
            if others:
                perturbed[idx] = {**s, "rotation": random.choice(others)}
        elif choice == "shape":
            others = [sh for sh in VALID_SHAPES if sh != s["shape"]]
            if others:
                perturbed[idx] = {**s, "shape": random.choice(others)}
        _add(perturbed)

    return candidates[:count]


# ── SCD distractor generation (legacy mode) ───────────────────────────────────

def _wrong_rule_variants(rule: dict) -> list[list[dict]]:
    """
    Return alternative rule-lists that produce wrong results for this rule.
    Each element is a list of rules to apply in place of the correct rule.
    The identity (empty list = don't apply this rule) is always the first variant.
    """
    op       = rule["op"]
    variants: list[list[dict]] = [[]]  # identity = skip this rule

    if op == "rotate_positions":
        direction = rule.get("direction", "cw")
        flipped   = {**rule, "direction": "ccw" if direction == "cw" else "cw"}
        variants.append([flipped])
        for ring in sorted(VALID_RINGS - {rule.get("ring", "corners")}):
            variants.append([{**rule, "ring": ring}])

    elif op == "rotate_shapes":
        direction = rule.get("direction", "cw")
        flipped   = {**rule, "direction": "ccw" if direction == "cw" else "cw"}
        variants.append([flipped])

    elif op == "invert_fills":
        pass  # identity is the only meaningful wrong variant

    elif op == "swap_sizes":
        variants.append([rule, rule])  # apply twice → different cycle position

    elif op == "reflect_h":
        variants.append([{"op": "reflect_v"}])

    elif op == "reflect_v":
        variants.append([{"op": "reflect_h"}])

    elif op == "shift_positions":
        opposites = {"right": "left", "left": "right", "up": "down", "down": "up"}
        opp       = opposites.get(rule.get("direction", "right"), "right")
        variants.append([{**rule, "direction": opp}])

    return variants


def auto_distractors_scd(
    cell_c: list[dict],
    rules:  list[dict],
    correct: list[dict],
    count:  int = 4,
) -> list[list[dict]]:
    """
    Solutions Combination Design (SCD) distractor generation.
    Reference: Blum & Holling (2018), Frontiers in Psychology.

    For each rule R_i, define:
      - correct variant  : apply R_i normally
      - wrong variant(s) : apply R_i differently (flipped dir, wrong ring, etc.)
                           or skip it entirely (identity)

    Distractors are formed by taking every cross-product combination of
    correct/wrong choices per rule, excluding the all-correct combination
    (which is the right answer). This means every distractor is wrong for
    a specific, explainable reason — matching how real CPNS exam distractors
    are constructed.

    Combinations are enumerated so that single-rule deviations (one rule
    wrong, the rest correct) come before multi-rule deviations, making the
    most plausible distractors surface first.

    Falls back to random perturbation of the correct answer if the SCD pool
    is exhausted.
    """
    import itertools

    correct_key = _cell_key(correct)
    seen        = {correct_key}
    candidates  = []

    def _add(shapes):
        if not shapes:
            return
        k = _cell_key(shapes)
        if k not in seen:
            seen.add(k)
            candidates.append([dict(s) for s in shapes])

    # alts_per_rule[i] = [ [correct_rule], [wrong_rules_1], [wrong_rules_2], ... ]
    alts_per_rule = [[[rule]] + _wrong_rule_variants(rule) for rule in rules]

    for combo in itertools.product(*[range(len(a)) for a in alts_per_rule]):
        if all(i == 0 for i in combo):
            continue  # all-correct = the right answer
        combined: list[dict] = []
        for rule_idx, alt_idx in enumerate(combo):
            combined.extend(alts_per_rule[rule_idx][alt_idx])
        _add(apply_rules(cell_c, combined))
        if len(candidates) >= count:
            return candidates[:count]

    # Fallback: random perturbation if SCD pool was too small
    attempts = 0
    while len(candidates) < count and attempts < 40:
        attempts += 1
        if not correct:
            break
        perturbed = [dict(s) for s in correct]
        idx    = random.randrange(len(perturbed))
        choice = random.choice(["fill", "size", "rotation", "shape"])
        s      = perturbed[idx]
        if choice == "fill":
            perturbed[idx] = {**s, "filled": not s["filled"]}
        elif choice == "size":
            others = [sz for sz in VALID_SIZES if sz != s["size"]]
            if others:
                perturbed[idx] = {**s, "size": random.choice(others)}
        elif choice == "rotation":
            others = [r for r in VALID_ROTATIONS if r != s.get("rotation", 0)]
            if others:
                perturbed[idx] = {**s, "rotation": random.choice(others)}
        elif choice == "shape":
            others = [sh for sh in VALID_SHAPES if sh != s["shape"]]
            if others:
                perturbed[idx] = {**s, "shape": random.choice(others)}
        _add(perturbed)

    return candidates[:count]


# ── Explanation auto-generation (legacy mode) ─────────────────────────────────

def _rule_description(rule: dict) -> str:
    op = rule["op"]
    if op == "rotate_positions":
        dir_name  = "searah jarum jam" if rule.get("direction", "cw") == "cw" else "berlawanan jarum jam"
        amount    = rule.get("amount", 1)
        ring_name = {"corners": "sudut", "outer": "tepi luar", "edges": "sisi tengah"}.get(
            rule.get("ring", "corners"), rule.get("ring", "corners")
        )
        return f"posisi bentuk di {ring_name} diputar {amount * 90}° {dir_name}"
    if op == "rotate_shapes":
        dir_name = "searah jarum jam" if rule.get("direction", "cw") == "cw" else "berlawanan jarum jam"
        return f"setiap bentuk diputar {rule.get('step', 45)}° {dir_name}"
    if op == "invert_fills":
        return "isian dibalik (padat↔kosong)"
    if op == "swap_sizes":
        return "ukuran digeser satu langkah (kecil→sedang→besar)"
    if op == "reflect_h":
        return "posisi dicerminkan horizontal (kiri↔kanan)"
    if op == "reflect_v":
        return "posisi dicerminkan vertikal (atas↔bawah)"
    if op == "shift_positions":
        dirs = {"right": "kanan", "left": "kiri", "up": "atas", "down": "bawah"}
        return f"semua bentuk digeser satu langkah ke {dirs.get(rule.get('direction','right'), rule.get('direction','right'))}"
    return op


def _auto_explanation(rules: list[dict]) -> str:
    descs = [f"({i+1}) {_rule_description(r)}" for i, r in enumerate(rules)]
    return "Pola yang berlaku: " + "; ".join(descs) + "."


# ── Difficulty scoring ────────────────────────────────────────────────────────

def difficulty_score(rules: list[dict]) -> dict:
    """
    Estimate item difficulty from the rule set.

    Based on Blum & Holling (2018): rule count and type predict empirical
    difficulty (β) via LLTM. More rules and cognitively demanding rules
    (rotation > reflection > positional) increase difficulty.

    Returns {"score": int, "level": "easy"|"medium"|"hard", "rule_count": int}.
    """
    score = sum(RULE_DIFFICULTY_WEIGHTS.get(r["op"], 1) for r in rules)
    if score <= 2:
        level = "easy"
    elif score <= 5:
        level = "medium"
    else:
        level = "hard"
    return {"score": score, "level": level, "rule_count": len(rules)}


def _check_rule_compatibility(rules: list[dict]) -> list[str]:
    """
    Detect rule combinations that cancel each other out or produce
    unintended results. Returns warning strings (non-blocking).

    Based on Blum & Holling (2018): e.g. reflect_x + rotate_180° = reflect_y,
    and two identical self-inverse rules cancel completely.
    """
    warnings: list[str] = []
    ops = [r["op"] for r in rules]

    # Self-inverse rules cancel when applied an even number of times
    for op in ("reflect_h", "reflect_v", "invert_fills"):
        n = ops.count(op)
        if n >= 2 and n % 2 == 0:
            warnings.append(
                f"'{op}' appears {n}× — even repetitions cancel out (net effect = identity)"
            )
        elif n >= 3:
            warnings.append(
                f"'{op}' appears {n}× — simplify to {n % 2} application(s)"
            )

    # rotate_shapes: check if net rotation is 0 mod 360
    shape_rots = [r for r in rules if r["op"] == "rotate_shapes"]
    if len(shape_rots) >= 2:
        net = sum(
            r.get("step", 45) if r.get("direction", "cw") == "cw" else -r.get("step", 45)
            for r in shape_rots
        )
        if net % 360 == 0:
            warnings.append(
                "rotate_shapes rules cancel out — net rotation is 0° (no visible change)"
            )

    # reflect_h + reflect_v = 180° rotation (Blum & Holling 2018)
    if "reflect_h" in ops and "reflect_v" in ops:
        warnings.append(
            "reflect_h + reflect_v = 180° rotation — "
            "consider {'op': 'rotate_shapes', 'step': 180} for clarity"
        )

    return warnings


# ── Spec validation ───────────────────────────────────────────────────────────

def _validate_cell(cell: list[dict], cell_name: str) -> list[str]:
    errors = []
    if not cell:
        errors.append(f"Missing or empty '{cell_name}'")
        return errors

    seen_pos = set()
    for s in cell:
        raw_pos = s.get("pos", "")
        pos = _canonical(raw_pos)
        if pos not in VALID_POS_CANONICAL:
            errors.append(f"'{cell_name}': unknown position {raw_pos!r}")
        elif pos in seen_pos:
            errors.append(f"'{cell_name}': duplicate position {pos!r}")
        else:
            seen_pos.add(pos)

        if s.get("shape") not in VALID_SHAPES:
            errors.append(f"'{cell_name}': unknown shape {s.get('shape')!r}")
        if s.get("size") not in VALID_SIZES:
            errors.append(f"'{cell_name}': unknown size {s.get('size')!r}")
        if not isinstance(s.get("filled"), bool):
            errors.append(f"'{cell_name}': 'filled' must be a boolean")
        rot = s.get("rotation", 0)
        if rot not in VALID_ROTATIONS:
            errors.append(f"'{cell_name}': rotation {rot!r} must be one of {sorted(VALID_ROTATIONS)}")

    return errors


def _validate_rules(rules: list[dict]) -> list[str]:
    errors = []
    for rule in rules:
        op = rule.get("op")
        if op not in VALID_OPS:
            errors.append(f"Unknown rule op: {op!r}")
            continue
        if op == "rotate_positions":
            if rule.get("direction") not in VALID_DIRS:
                errors.append("rotate_positions: direction must be 'cw' or 'ccw'")
            amt = rule.get("amount", 1)
            if not isinstance(amt, int) or amt < 1:
                errors.append("rotate_positions: amount must be a positive integer")
            if rule.get("ring", "corners") not in VALID_RINGS:
                errors.append(f"rotate_positions: ring must be one of {sorted(VALID_RINGS)}")
        elif op == "rotate_shapes":
            step = rule.get("step", 45)
            if step not in VALID_ROTATIONS or step == 0:
                errors.append(f"rotate_shapes: step must be one of {sorted(VALID_ROTATIONS - {0})}")
            if "direction" in rule and rule["direction"] not in VALID_DIRS:
                errors.append("rotate_shapes: direction must be 'cw' or 'ccw'")
        elif op == "shift_positions":
            if rule.get("direction") not in VALID_SHIFT_DIRS:
                errors.append(f"shift_positions: direction must be one of {sorted(VALID_SHIFT_DIRS)}")
    return errors


def validate_spec(spec: dict) -> list[str]:
    errors = []

    if spec.get("format") != "analogy":
        errors.append(f"format must be 'analogy', got: {spec.get('format')!r}")
        return errors

    explicit = "cell_b" in spec and "cell_d" in spec

    # Always validate cell_a and cell_c
    errors.extend(_validate_cell(spec.get("cell_a") or [], "cell_a"))
    errors.extend(_validate_cell(spec.get("cell_c") or [], "cell_c"))

    if explicit:
        # Explicit mode: validate cell_b and cell_d; explanation required
        errors.extend(_validate_cell(spec.get("cell_b") or [], "cell_b"))
        errors.extend(_validate_cell(spec.get("cell_d") or [], "cell_d"))
        if not spec.get("explanation"):
            errors.append("'explanation' is required in explicit mode (cell_b and cell_d provided)")
        # Rules are optional in explicit mode — validate them if present
        rules = spec.get("rules")
        if rules:
            errors.extend(_validate_rules(rules))
    else:
        # Legacy mode: rules required
        rules = spec.get("rules")
        if not rules:
            errors.append("'rules' must be a non-empty list (or provide cell_b + cell_d for explicit mode)")
        else:
            errors.extend(_validate_rules(rules))

    if not spec.get("content"):
        errors.append("'content' is required")
    if not spec.get("title"):
        errors.append("'title' is required")

    return errors


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process(spec: dict, verbose: bool = True) -> dict:
    """
    Full pipeline: validate → compute → render → upload → insert DB.
    Returns the API response dict on success.
    Raises ValueError if the spec is invalid.
    """
    errors = validate_spec(spec)
    if errors:
        raise ValueError("Invalid spec:\n" + "\n".join(f"  • {e}" for e in errors))

    cell_a = spec["cell_a"]
    cell_c = spec["cell_c"]
    rules  = spec.get("rules") or []

    explicit = "cell_b" in spec and "cell_d" in spec

    if explicit:
        cell_b      = spec["cell_b"]
        correct     = spec["cell_d"]
        explanation = spec.get("explanation", "")

        # Soft consistency check when rules are also provided
        if rules:
            computed_b = apply_rules(cell_a, rules)
            if _cell_key(computed_b) != _cell_key(cell_b):
                print("⚠ [consistency] apply_rules(cell_a, rules) ≠ cell_b — rules may not fully describe the transformation")
            computed_d = apply_rules(cell_c, rules)
            if _cell_key(computed_d) != _cell_key(correct):
                print("⚠ [consistency] apply_rules(cell_c, rules) ≠ cell_d — rules may not fully describe the transformation")

        distractors = auto_distractors_explicit(cell_c, cell_b, correct)

    else:
        cell_b      = apply_rules(cell_a, rules)
        correct     = apply_rules(cell_c, rules)
        explanation = spec.get("explanation") or _auto_explanation(rules)

        compat_warnings = _check_rule_compatibility(rules)
        for w in compat_warnings:
            print(f"⚠ [compatibility] {w}")

        diff = difficulty_score(rules)
        if verbose:
            print(f"Difficulty: {diff['level']} (score={diff['score']}, rules={diff['rule_count']})")

        distractors = auto_distractors_scd(cell_c, rules, correct)

    all_opts    = [correct] + distractors
    order       = list(range(len(all_opts)))
    random.shuffle(order)
    correct_idx = order.index(0)
    shuffled    = [all_opts[i] for i in order]

    labels = "ABCDE"

    if verbose:
        print("Uploading question composite…")
    q_url = upload_image(render_analogy_composite(cell_a, cell_b, cell_c), "analogi_q.png")
    if verbose:
        print(f"  {q_url}")

    opt_urls = []
    for i, shapes in enumerate(shuffled):
        url = upload_image(render_cell(shapes), f"analogi_opt{labels[i]}.png")
        opt_urls.append(url)
        if verbose:
            marker = " ✓" if i == correct_idx else ""
            print(f"  Option {labels[i]}{marker}: {url}")

    payload = {
        "quiz": {
            "title":      spec.get("title", "TIU - Analogi Gambar"),
            "category":   spec.get("category", "TIU"),
            "time_limit": spec.get("time_limit", 30),
        },
        "questions": [{
            "type":        "IMAGE",
            "subtype":     "ANALOGI_GAMBAR",
            "content":     spec["content"],
            "image_url":   q_url,
            "explanation": explanation,
            "position":    1,
            "options": [
                {
                    "label":   labels[i],
                    "content": opt_urls[i],
                    "score":   5 if i == correct_idx else 0,
                }
                for i in range(len(shuffled))
            ],
        }],
    }

    if verbose:
        print("Inserting into DB…")
    resp = requests.post(f"{API}/api/v1/admin/questions/bulk", json=payload)
    resp.raise_for_status()
    result = resp.json()
    if not explicit:
        result["difficulty"] = diff
    if verbose:
        diff_str = (
            f", difficulty={diff['level']} (score={diff['score']})"
            if not explicit else ""
        )
        print(
            f"Done! quiz_id={result.get('quiz_id')}, "
            f"questions={result.get('questions_imported')}, "
            f"correct={labels[correct_idx]}{diff_str}"
        )
    return result


def process_no_db(spec: dict) -> dict:
    """
    Render and upload images for a spec but do NOT save to DB.
    Returns question data dict: {content, image_url, explanation, options}.
    options: [{"label": "A", "content": <image_url>, "score": 0|5}, ...]
    Raises ValueError if spec is invalid.
    """
    errors = validate_spec(spec)
    if errors:
        raise ValueError("Invalid spec:\n" + "\n".join(f"  • {e}" for e in errors))

    cell_a  = spec["cell_a"]
    cell_c  = spec["cell_c"]
    rules   = spec.get("rules") or []
    explicit = "cell_b" in spec and "cell_d" in spec

    if explicit:
        cell_b      = spec["cell_b"]
        correct     = spec["cell_d"]
        explanation = spec.get("explanation", "")
        distractors = auto_distractors_explicit(cell_c, cell_b, correct)
    else:
        cell_b      = apply_rules(cell_a, rules)
        correct     = apply_rules(cell_c, rules)
        explanation = spec.get("explanation") or _auto_explanation(rules)
        distractors = auto_distractors_scd(cell_c, rules, correct)

    all_opts    = [correct] + distractors
    order       = list(range(len(all_opts)))
    random.shuffle(order)
    correct_idx = order.index(0)
    shuffled    = [all_opts[i] for i in order]
    labels      = "ABCDE"

    q_url = upload_image(render_analogy_composite(cell_a, cell_b, cell_c), "analogi_q.png")
    opt_urls = []
    for i, shapes in enumerate(shuffled):
        url = upload_image(render_cell(shapes), f"analogi_opt{labels[i]}.png")
        opt_urls.append(url)

    return {
        "content":     spec.get("content", "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?"),
        "image_url":   q_url,
        "explanation": explanation,
        "options": [
            {
                "label":   labels[i],
                "content": opt_urls[i],
                "score":   5 if i == correct_idx else 0,
            }
            for i in range(len(shuffled))
        ],
    }
