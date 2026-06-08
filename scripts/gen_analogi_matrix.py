#!/usr/bin/env python3
"""
Generate a very hard CPNS analogi gambar — 3×3 MATRIX format.

Each cell shows a NESTED shape (large outer + small inner).
Rules the test-taker must discover:
  - Outer shape is determined by COLUMN: col0=circle, col1=square, col2=triangle
  - Inner shape is determined by ROW:    row0=circle, row1=square, row2=triangle
  - Fill pattern (checkerboard): if (r+c) is even → outer FILLED, inner HOLLOW
                                  if (r+c) is odd  → outer HOLLOW, inner FILLED

Answer = cell (row2, col2):
  (2+2)=4 → even → filled triangle (outer) containing hollow triangle (inner)

Distractors each violate exactly one rule:
  A: swapped fills  (hollow-triangle outer, filled-triangle inner)
  B: wrong outer    (filled-circle outer, hollow-triangle inner)
  C: CORRECT        (filled-triangle outer, hollow-triangle inner)
  D: wrong inner    (filled-triangle outer, hollow-circle inner)
  E: wrong outer    (filled-square outer, hollow-triangle inner)
"""

import io
import requests
from PIL import Image, ImageDraw, ImageFont

API     = "http://localhost:3000"
CELL    = 200   # standalone option cell
QCELL   = 150   # cell inside the 3×3 matrix
GAP     = 6     # gap between cells
BORDER  = 8
OUTER_R = 58    # outer shape radius (CELL coords)
INNER_R = 25    # inner shape radius
LW      = 5     # default line width
SHAPES  = ["circle", "square", "triangle"]


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


def poly_outline(draw, pts, color, width):
    for i in range(len(pts)):
        draw.line([pts[i], pts[(i + 1) % len(pts)]], fill=color, width=width)


def draw_shape_fill(draw, shape, cx, cy, r, fill, lw):
    """Draw shape with given fill color (None = transparent/skip fill)."""
    if shape == "circle":
        bbox = [cx - r, cy - r, cx + r, cy + r]
        if fill is not None:
            draw.ellipse(bbox, fill=fill)
        draw.ellipse(bbox, outline="black", width=lw)
    elif shape == "square":
        bbox = [cx - r, cy - r, cx + r, cy + r]
        if fill is not None:
            draw.rectangle(bbox, fill=fill)
        draw.rectangle(bbox, outline="black", width=lw)
    elif shape == "triangle":
        pts = [(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
        if fill is not None:
            draw.polygon(pts, fill=fill)
        poly_outline(draw, pts, "black", lw)


def draw_nested(draw, outer_shape, inner_shape, cx, cy, outer_r, inner_r, outer_filled, lw=LW):
    """
    Outer shape is always opposite fill from inner shape.
    outer_filled=True  → outer BLACK, inner WHITE (hollow)
    outer_filled=False → outer WHITE outline only, inner BLACK (filled)
    """
    scale_lw = lw
    if outer_filled:
        # Outer: solid black
        draw_shape_fill(draw, outer_shape, cx, cy, outer_r, "black", scale_lw)
        # Inner: white hole punched through, with black border
        draw_shape_fill(draw, inner_shape, cx, cy, inner_r, "white", max(3, scale_lw - 1))
    else:
        # Outer: hollow (white fill = background, black outline)
        draw_shape_fill(draw, outer_shape, cx, cy, outer_r, "white", scale_lw)
        # Inner: solid black
        draw_shape_fill(draw, inner_shape, cx, cy, inner_r, "black", scale_lw)


def make_cell(outer_shape, inner_shape, outer_filled, size=None, qmark=False):
    if size is None:
        size = CELL
    img  = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    b = max(4, BORDER * size // CELL)
    for i in range(b):
        draw.rectangle([i, i, size - 1 - i, size - 1 - i], outline="black")

    if qmark:
        fnt = get_font(size // 2)
        draw.text((size // 2, size // 2), "?", fill="#aaaaaa", font=fnt, anchor="mm")
        return img

    cx = cy = size // 2
    scale  = size / CELL
    outer_r = max(8, int(OUTER_R * scale))
    inner_r = max(4, int(INNER_R * scale))
    lw = max(3, int(LW * scale))
    draw_nested(draw, outer_shape, inner_shape, cx, cy, outer_r, inner_r, outer_filled, lw)
    return img


def cell_at(r, c):
    """Return (outer_shape, inner_shape, outer_filled) for matrix position (r,c)."""
    return SHAPES[c], SHAPES[r], (r + c) % 2 == 0


# ── Matrix question image ─────────────────────────────────────────────────────

def make_matrix_img():
    pad  = 12
    w    = 3 * QCELL + 2 * GAP + 2 * pad
    h    = 3 * QCELL + 2 * GAP + 2 * pad
    img  = Image.new("RGB", (w, h), "#e8e8e8")

    for r in range(3):
        for c in range(3):
            x = pad + c * (QCELL + GAP)
            y = pad + r * (QCELL + GAP)
            if r == 2 and c == 2:
                cell = make_cell(None, None, False, QCELL, qmark=True)
            else:
                outer_s, inner_s, outer_f = cell_at(r, c)
                cell = make_cell(outer_s, inner_s, outer_f, QCELL)
            img.paste(cell, (x, y))
    return img


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


# ── Answer and distractors ────────────────────────────────────────────────────

# Correct: cell(2,2) → outer=triangle, inner=triangle, outer_filled=(2+2)%2==0→True
#          = filled-triangle outer, hollow-triangle inner
OPTS = [
    ("triangle", "triangle", False),  # A: swapped fills  ← wrong
    ("circle",   "triangle", True),   # B: wrong outer shape (circle instead of triangle)
    ("triangle", "triangle", True),   # C: CORRECT
    ("triangle", "circle",   True),   # D: wrong inner shape (circle instead of triangle)
    ("square",   "triangle", True),   # E: wrong outer shape (square instead of triangle)
]
CORRECT_IDX = 2  # option C


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Building 3×3 matrix image...")
    mat_img = make_matrix_img()
    print("Uploading matrix image...")
    q_url = upload(mat_img, "analogi_matrix_q.png")
    print(f"  {q_url}")

    labels   = "ABCDE"
    opt_urls = []
    for i, (os_, is_, of) in enumerate(OPTS):
        img = make_cell(os_, is_, of)
        url = upload(img, f"analogi_matrix_opt{labels[i]}.png")
        opt_urls.append(url)
        print(f"  Option {labels[i]}: {url}")

    payload = {
        "quiz": {
            "title": "TIU - Matriks Analogi Gambar (Sangat Sulit)",
            "category": "TIU",
            "time_limit": 30,
        },
        "questions": [
            {
                "type": "IMAGE",
                "subtype": "ANALOGI_GAMBAR",
                "content": (
                    "Perhatikan matriks 3×3 berikut. "
                    "Tentukan gambar yang tepat untuk mengisi sel bertanda tanya (?)."
                ),
                "image_url": q_url,
                "explanation": (
                    "Aturan pola matriks:\n"
                    "1. Bentuk LUAR ditentukan KOLOM: kol-1=lingkaran, kol-2=persegi, kol-3=segitiga.\n"
                    "2. Bentuk DALAM ditentukan BARIS: baris-1=lingkaran, baris-2=persegi, baris-3=segitiga.\n"
                    "3. Pola isian (papan catur): jika (baris+kolom) genap → luar HITAM & dalam PUTIH; "
                    "jika ganjil → luar PUTIH & dalam HITAM.\n"
                    "Sel (baris 3, kolom 3): (3+3)=6 (genap) → segitiga besar hitam dengan segitiga kecil putih di dalam."
                ),
                "position": 1,
                "options": [
                    {
                        "label":      labels[i],
                        "content":    opt_urls[i],
                        "score":      5 if i == CORRECT_IDX else 0,
                        "is_correct": i == CORRECT_IDX,
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
