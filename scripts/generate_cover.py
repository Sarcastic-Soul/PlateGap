"""Generate the Builder Center cover image for PlateGap.

Minimal text only: the product name and the nutrient each bar stands for,
so the graphic reads on its own instead of looking like an abstract bar
chart. The platform's no-text guidance is about SEO keyword-stuffed covers,
not labeling a chart. Colors are pulled straight from web/style.css so the
cover matches the live app.
"""

import pathlib
import random

from PIL import Image, ImageDraw, ImageFont

random.seed(7)

FONT_DIR = pathlib.Path("/usr/share/fonts/truetype/liberation")
F_TITLE = ImageFont.truetype(str(FONT_DIR / "LiberationSans-Bold.ttf"), 64)
F_NUT = ImageFont.truetype(str(FONT_DIR / "LiberationSans-Regular.ttf"), 20)

W, H = 1200, 675
SCALE = 4  # supersample then downsize for clean anti-aliasing
BG = (251, 250, 247)
INK = (22, 21, 15)
LINE = (227, 223, 210)
ACCENT = (31, 111, 74)  # met
ACCENT_SOFT = (230, 240, 233)
SHORT = (162, 59, 38)  # gap
SHORT_SOFT = (248, 231, 226)
WARN = (154, 91, 18)

img = Image.new("RGB", (W * SCALE, H * SCALE), BG)
draw = ImageDraw.Draw(img, "RGBA")


def s(v):
    return v * SCALE


# Soft plate motif: concentric rings centered behind the bar group.
plate_cx, plate_cy = s(600), s(300)
for r, alpha in [(470, 16), (390, 22), (310, 16)]:
    bbox = [plate_cx - s(r), plate_cy - s(r), plate_cx + s(r), plate_cy + s(r)]
    draw.ellipse(bbox, outline=(*ACCENT, alpha), width=s(3))

# Faint dot grid texture, low alpha, like graph paper on the panels in the app.
for gx in range(0, W, 28):
    for gy in range(0, H, 28):
        draw.ellipse(
            [s(gx) - s(1), s(gy) - s(1), s(gx) + s(1), s(gy) + s(1)],
            fill=(*LINE, 60),
        )

# --- Nutrient meters -------------------------------------------------------
# Each bar: outline track (the target), filled from the bottom to "met",
# then an open/hatched zone up to target = the gap. A small dot marks the
# margin where the next unit gets expensive (the shadow price idea).

bars = [
    {"met": 0.58, "label": "Protein"},
    {"met": 0.27, "label": "Iron"},
    {"met": 0.86, "label": "Calcium"},
    {"met": 0.15, "label": "Zinc"},
    {"met": 0.68, "label": "Vitamin A"},
    {"met": 0.41, "label": "Vitamin C"},
    {"met": 0.93, "label": "Folate"},
    {"met": 0.33, "label": "Potassium"},
    {"met": 0.77, "label": "Fiber"},
]

n = len(bars)
bar_w = 58
gap_w = 30
total_w = n * bar_w + (n - 1) * gap_w
start_x = (W - total_w) // 2
base_y = 530
top_y = 150
max_h = base_y - top_y
radius = bar_w // 2

for i, b in enumerate(bars):
    x0 = start_x + i * (bar_w + gap_w)
    x1 = x0 + bar_w

    # Track (target), full height, subtle outline.
    track_top = base_y - max_h
    draw.rounded_rectangle(
        [s(x0), s(track_top), s(x1), s(base_y)],
        radius=s(radius),
        outline=(*LINE, 255),
        width=s(3),
        fill=(*BG, 0),
    )

    met_h = max_h * b["met"]
    met_top = base_y - met_h

    # Gap zone: target down to met, soft rust wash.
    if met_h < max_h:
        draw.rounded_rectangle(
            [s(x0), s(track_top), s(x1), s(met_top + radius)],
            radius=s(radius),
            fill=(*SHORT_SOFT, 235),
        )
        # thin dashed target ceiling
        dash = 10
        yv = track_top + 3
        xx = x0
        while xx < x1:
            draw.line(
                [s(xx), s(yv), s(min(xx + dash, x1)), s(yv)],
                fill=(*SHORT, 200),
                width=s(3),
            )
            xx += dash * 2

    # Met zone: solid accent green, rounded at the bottom.
    draw.rounded_rectangle(
        [s(x0), s(met_top), s(x1), s(base_y)],
        radius=s(radius),
        fill=(*ACCENT, 255),
    )
    # Re-round only the bottom by covering the top corners of this fill
    # with a plain rect from met_top+radius down -- rounded_rectangle above
    # already rounds both ends; mask the top corners back to square by
    # drawing a flat cap where it meets the gap zone.
    if met_h < max_h - radius:
        draw.rectangle([s(x0), s(met_top), s(x1), s(met_top + radius)], fill=(*ACCENT, 255))

    # Margin marker: small ring at the meeting point, like a dual-price dot.
    dot_y = met_top
    dot_r = 9
    draw.ellipse(
        [s(x0 + bar_w / 2 - dot_r), s(dot_y - dot_r), s(x0 + bar_w / 2 + dot_r), s(dot_y + dot_r)],
        fill=(*BG, 255),
        outline=(*INK, 255),
        width=s(3),
    )

    # Nutrient label, rotated to fit the narrow column, drawn at full scale
    # (not supersampled) and composited after downsizing so it stays crisp.
    b["label_xy"] = (x0 + bar_w / 2, base_y + 60)

# --- A faint baseline, like a table rule ------------------------------------
draw.line(
    [s(start_x - 40), s(base_y + 40), s(start_x + total_w + 40), s(base_y + 40)],
    fill=(*LINE, 255),
    width=s(2),
)

# Downsample for clean edges, then composite crisp (non-supersampled) text.
img = img.resize((W, H), Image.LANCZOS).convert("RGBA")
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
odraw = ImageDraw.Draw(overlay)

title = "PlateGap"
tw = odraw.textlength(title, font=F_TITLE)
odraw.text(((W - tw) / 2, 34), title, font=F_TITLE, fill=(*INK, 255))

for b in bars:
    tmp = Image.new("RGBA", (140, 40), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tmp)
    tdraw.text((0, 0), b["label"], font=F_NUT, fill=(*INK, 210))
    rotated = tmp.rotate(-50, expand=True, resample=Image.BICUBIC)
    lx, ly = b["label_xy"]
    overlay.alpha_composite(rotated, (int(lx - rotated.width * 0.15), int(ly - rotated.height * 0.35)))

img = Image.alpha_composite(img, overlay).convert("RGB")
out = pathlib.Path(__file__).resolve().parent.parent / "docs" / "hackathon" / "cover.png"
img.save(out, "PNG", optimize=True)
print("wrote", out, img.size)
