#!/usr/bin/env python3
"""
Generate a hard CPNS 'analogi gambar' question.

Rule A→B (and C→?):
  1. Rotate positions 90° clockwise: TL→TR, TR→BR, BR→BL, BL→TL
  2. Invert every fill simultaneously: filled(●)↔hollow(○)

Each bordered cell contains 4 shapes arranged in the 4 quadrant positions (TL/TR/BR/BL).
Shapes: circle, triangle, diamond, square — each either large or small, either filled or hollow.

Distractors target common mistakes:
  B — rotate only (forgot to invert fills)
  C — invert fills only (forgot to rotate)
  D — rotate CCW + invert (wrong rotation direction)
  E — rotate 180° + invert (wrong rotation amount)
"""

import io, requests
from PIL import Image, ImageDraw, ImageFont

API    = "http://localhost:3000"
CELL   = 220   # standalone option cell (px)
QC     = 155   # cell size inside question composite
BORDER = 8
LG     = 44    # large shape radius (in CELL coords)
SM     = 24    # small shape radius

# ── Drawing helpers ───────────────────────────────────────────────────────────

def get_font(size):
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


def poly_outline(draw, pts, color="black", width=4):
    for i in range(len(pts)):
        draw.line([pts[i], pts[(i + 1) % len(pts)]], fill=color, width=width)


def draw_shape(draw, shape, cx, cy, r, filled, lw=5):
    if shape == "circle":
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill="black" if filled else "white",
            outline="black",
            width=lw,
        )
    elif shape == "square":
        draw.rectangle(
            [cx - r, cy - r, cx + r, cy + r],
            fill="black" if filled else "white",
            outline="black",
            width=lw,
        )
    elif shape == "triangle":
        pts = [(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
        if filled:
            draw.polygon(pts, fill="black", outline="black")
        else:
            poly_outline(draw, pts, "black", lw)
    elif shape == "diamond":
        pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        if filled:
            draw.polygon(pts, fill="black", outline="black")
        else:
            poly_outline(draw, pts, "black", lw)


def make_cell(shapes_data, size=None, qmark=False):
    """
    shapes_data: [TL, TR, BR, BL] — each {'shape', 'r', 'filled'}
    Returns a PIL Image.
    """
    if size is None:
        size = CELL
    img  = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)

    # Thick outer border
    b = max(4, BORDER * size // CELL)
    for i in range(b):
        draw.rectangle([i, i, size - 1 - i, size - 1 - i], outline="black")

    if qmark:
        fnt = get_font(size // 2)
        draw.text((size // 2, size // 2), "?", fill="#aaaaaa", font=fnt, anchor="mm")
        return img

    # Light divider lines at midpoints (helps eye locate quadrants)
    mid = size // 2
    draw.line([(b + 2, mid), (size - b - 2, mid)], fill="#dddddd", width=1)
    draw.line([(mid, b + 2), (mid, size - b - 2)], fill="#dddddd", width=1)

    q      = size // 4
    centers = [(q, q), (3 * q, q), (3 * q, 3 * q), (q, 3 * q)]  # TL TR BR BL
    scale  = size / CELL
    lw     = max(3, int(5 * scale))

    for sd, (cx, cy) in zip(shapes_data, centers):
        r = max(4, int(sd["r"] * scale))
        draw_shape(draw, sd["shape"], cx, cy, r, sd["filled"], lw)

    return img


# ── Transformation helpers ────────────────────────────────────────────────────

def rotate_cw(d):
    tl, tr, br, bl = d
    return [bl, tl, tr, br]   # TL←BL  TR←TL  BR←TR  BL←BR


def rotate_ccw(d):
    tl, tr, br, bl = d
    return [tr, br, bl, tl]


def rotate_180(d):
    tl, tr, br, bl = d
    return [br, bl, tl, tr]


def inv(d):
    return [{**s, "filled": not s["filled"]} for s in d]


def transform(d):              # the intended rule
    return inv(rotate_cw(d))


# ── Cell definitions ──────────────────────────────────────────────────────────

# Cell A: large filled ● TL, small hollow △ TR, small filled ◆ BR, large hollow □ BL
cell_a = [
    {"shape": "circle",   "r": LG, "filled": True},
    {"shape": "triangle", "r": SM, "filled": False},
    {"shape": "diamond",  "r": SM, "filled": True},
    {"shape": "square",   "r": LG, "filled": False},
]
cell_b = transform(cell_a)  # derived

# Cell C: small hollow ◆ TL, large filled △ TR, large hollow ● BR, small filled □ BL
cell_c = [
    {"shape": "diamond",  "r": SM, "filled": False},
    {"shape": "triangle", "r": LG, "filled": True},
    {"shape": "circle",   "r": LG, "filled": False},
    {"shape": "square",   "r": SM, "filled": True},
]

# Answer options (index 0 = correct = A)
opts = [
    transform(cell_c),         # A — correct: rotate CW + invert
    rotate_cw(cell_c),         # B — rotate only (forgot invert)
    inv(cell_c),               # C — invert only (forgot rotate)
    inv(rotate_ccw(cell_c)),   # D — CCW + invert (wrong direction)
    inv(rotate_180(cell_c)),   # E — 180° + invert (wrong amount)
]


# ── Upload helper ─────────────────────────────────────────────────────────────

def upload(img, name):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    r = requests.post(
        f"{API}/api/v1/admin/upload/image",
        files={"file": (name, buf, "image/png")},
    )
    r.raise_for_status()
    return r.json()["url"]


# ── Question composite image ──────────────────────────────────────────────────

def make_question_img():
    fnt   = get_font(28)
    sep_w = 30
    pad   = 16
    total_w = 4 * QC + 3 * sep_w + 2 * pad
    total_h = QC + 2 * pad

    img  = Image.new("RGB", (total_w, total_h), "white")
    draw = ImageDraw.Draw(img)

    items = [
        ("cell",  cell_a),
        ("sep",   ":"),
        ("cell",  cell_b),
        ("sep",   "="),
        ("cell",  cell_c),
        ("sep",   ":"),
        ("qmark", None),
    ]

    x = pad
    for kind, data in items:
        if kind == "cell":
            img.paste(make_cell(data, QC), (x, pad))
            x += QC
        elif kind == "qmark":
            img.paste(make_cell(None, QC, qmark=True), (x, pad))
            x += QC
        else:  # sep
            draw.text(
                (x + sep_w // 2, total_h // 2),
                data,
                fill="black",
                font=fnt,
                anchor="mm",
            )
            x += sep_w

    return img


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Uploading question composite image...")
    q_url = upload(make_question_img(), "analogi_v3_q.png")
    print(f"  {q_url}")

    labels   = "ABCDE"
    opt_urls = []
    for i, od in enumerate(opts):
        url = upload(make_cell(od), f"analogi_v3_opt{labels[i]}.png")
        opt_urls.append(url)
        print(f"  Option {labels[i]}: {url}")

    payload = {
        "quiz": {
            "title": "TIU - Analogi Gambar (Sulit)",
            "category": "TIU",
            "time_limit": 30,
        },
        "questions": [
            {
                "type": "IMAGE",
                "content": "Tentukan gambar yang tepat untuk melengkapi analogi: A : B = C : ?",
                "image_url": q_url,
                "explanation": (
                    "Aturan transformasi dari A→B (dan C→?):\n"
                    "1. Putar seluruh susunan 90° searah jarum jam: "
                    "TL→TR, TR→BR, BR→BL, BL→TL.\n"
                    "2. Balikkan semua isian secara bersamaan: hitam↔putih (●↔○).\n"
                    "Kedua aturan diterapkan sekaligus."
                ),
                "position": 1,
                "options": [
                    {
                        "label":      labels[i],
                        "content":    opt_urls[i],
                        "score":      5 if i == 0 else 0,
                        "is_correct": i == 0,
                    }
                    for i in range(5)
                ],
            }
        ],
    }

    print("\nInserting question into DB...")
    r = requests.post(f"{API}/api/v1/admin/questions/bulk", json=payload)
    if r.ok:
        res = r.json()
        print(f"Done! quiz_id={res.get('quiz_id')}, questions={res.get('questions_imported')}")
    else:
        print(f"Error {r.status_code}: {r.text}")


if __name__ == "__main__":
    main()
