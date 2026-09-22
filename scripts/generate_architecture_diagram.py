"""Generate the architecture diagram for the Builder Center submission.

Two lanes: what happens when a browser hits the site (solid, green), and what
happens on a push to main (dashed, muted). Colors are pulled from
web/style.css so this matches the live app and the cover image.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFont

W, H = 1400, 820
SCALE = 4
BG = (251, 250, 247)
INK = (22, 21, 15)
MUTED = (107, 104, 88)
LINE = (227, 223, 210)
ACCENT = (31, 111, 74)
ACCENT_SOFT = (230, 240, 233)
PANEL = (255, 255, 255)

FONT_DIR = pathlib.Path("/usr/share/fonts/truetype/liberation")
F_LABEL = ImageFont.truetype(str(FONT_DIR / "LiberationSans-Bold.ttf"), 21)
F_SUB = ImageFont.truetype(str(FONT_DIR / "LiberationSans-Regular.ttf"), 15)
F_TAG = ImageFont.truetype(str(FONT_DIR / "LiberationSans-Regular.ttf"), 14)

img = Image.new("RGB", (W * SCALE, H * SCALE), BG)
draw = ImageDraw.Draw(img, "RGBA")


def s(v):
    return int(v * SCALE)


def node(cx, cy, w, h, title, sub=None, fill=PANEL, outline=LINE, title_fill=INK):
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    draw.rounded_rectangle(
        [s(x0), s(y0), s(x1), s(y1)], radius=s(14), fill=(*fill, 255), outline=(*outline, 255), width=s(2)
    )
    tw = draw.textlength(title, font=F_LABEL)
    draw.text((s(cx - tw / 2), s(cy - (16 if sub else 8))), title, font=F_LABEL, fill=(*title_fill, 255))
    if sub:
        sw = draw.textlength(sub, font=F_SUB)
        draw.text((s(cx - sw / 2), s(cy + 12)), sub, font=F_SUB, fill=(*MUTED, 255))
    return (x0, y0, x1, y1)


def edge_point(box, side, offset=0):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {
        "top": (cx + offset, y0),
        "bottom": (cx + offset, y1),
        "left": (x0, cy + offset),
        "right": (x1, cy + offset),
    }[side]


def arrow(p0, p1, color, dashed=False, width=3, label=None, label_dx=0, label_dy=-10, label_t=0.5):
    x0, y0 = p0
    x1, y1 = p1
    if dashed:
        import math

        length = math.hypot(x1 - x0, y1 - y0)
        dash, gap = 10, 8
        n = max(1, int(length // (dash + gap)))
        for i in range(n + 1):
            t0 = (i * (dash + gap)) / length
            t1 = min(1.0, t0 + dash / length)
            xa, ya = x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0
            xb, yb = x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1
            draw.line([s(xa), s(ya), s(xb), s(yb)], fill=(*color, 255), width=s(width))
    else:
        draw.line([s(x0), s(y0), s(x1), s(y1)], fill=(*color, 255), width=s(width))

    # arrowhead
    import math

    ang = math.atan2(y1 - y0, x1 - x0)
    ah = 12
    p_a = (x1 - ah * math.cos(ang - 0.4), y1 - ah * math.sin(ang - 0.4))
    p_b = (x1 - ah * math.cos(ang + 0.4), y1 - ah * math.sin(ang + 0.4))
    draw.polygon([s(x1), s(y1), s(p_a[0]), s(p_a[1]), s(p_b[0]), s(p_b[1])], fill=(*color, 255))

    if label:
        mx, my = x0 + (x1 - x0) * label_t + label_dx, y0 + (y1 - y0) * label_t + label_dy
        lw = draw.textlength(label, font=F_TAG)
        draw.rectangle([s(mx - lw / 2 - 6), s(my - 11), s(mx + lw / 2 + 6), s(my + 11)], fill=(*BG, 235))
        draw.text((s(mx - lw / 2), s(my - 9)), label, font=F_TAG, fill=(*MUTED, 255))


# --- lane headers ------------------------------------------------------
draw.text((s(60), s(36)), "A REQUEST HITTING THE LIVE SITE", font=F_LABEL, fill=(*ACCENT, 255))
draw.text((s(60), s(66)), "solid line", font=F_TAG, fill=(*MUTED, 255))
draw.text((s(60), s(430)), "A PUSH TO MAIN", font=F_LABEL, fill=(*MUTED, 255))
draw.text((s(60), s(460)), "dashed line, no long-lived key", font=F_TAG, fill=(*MUTED, 255))

# --- runtime lane nodes --------------------------------------------------
browser = node(140, 130, 190, 100, "Browser", "no signup")
cloudfront = node(430, 110, 200, 90, "CloudFront", "origin access control")
s3 = node(710, 110, 180, 90, "S3", "static site")
lambda_url = node(430, 280, 220, 90, "Lambda", "Function URL, one route", fill=ACCENT_SOFT, outline=ACCENT, title_fill=ACCENT)
bedrock = node(760, 230, 220, 90, "Bedrock Nova Lite", "scan · explain")
ddb = node(760, 340, 220, 80, "DynamoDB", "daily scan budget")
logs = node(1020, 280, 210, 80, "CloudWatch Logs", "retention policy")

arrow(edge_point(browser, "top", -20), edge_point(cloudfront, "left", -15), ACCENT)
draw.text((s(180), s(58)), "GET /", font=F_TAG, fill=(*MUTED, 255))
arrow(edge_point(cloudfront, "right"), edge_point(s3, "left"), ACCENT)
arrow(edge_point(browser, "right", 25), edge_point(lambda_url, "left", -20), ACCENT)
draw.text((s(180), s(215)), "POST /solve  /scan  /explain", font=F_TAG, fill=(*MUTED, 255))
arrow(edge_point(lambda_url, "top", 20), edge_point(bedrock, "left"), ACCENT)
arrow(edge_point(lambda_url, "bottom"), edge_point(ddb, "left"), ACCENT)
arrow(edge_point(lambda_url, "right"), edge_point(logs, "left", -10), ACCENT)

# --- deploy lane nodes -----------------------------------------------------
gha = node(140, 610, 210, 90, "GitHub Actions", "test, then deploy")
oidc = node(440, 610, 200, 80, "AWS OIDC", "short-lived token")
role = node(730, 610, 200, 80, "Deploy role", "update-only")
lambda2 = node(1040, 545, 210, 80, "Lambda code")
s32 = node(1040, 680, 210, 80, "S3 site")
tf = node(140, 750, 210, 60, "Terraform", "infra/, 501 lines")

arrow(edge_point(gha, "right"), edge_point(oidc, "left"), MUTED, dashed=True, label="assume role", label_dy=-16)
arrow(edge_point(oidc, "right"), edge_point(role, "left"), MUTED, dashed=True, label="update-only", label_dy=-16)
arrow(edge_point(role, "top", 30), edge_point(lambda2, "left"), MUTED, dashed=True, label="update code", label_t=0.6, label_dy=-16)
arrow(edge_point(role, "bottom", 30), edge_point(s32, "left"), MUTED, dashed=True, label="sync files", label_t=0.6, label_dy=16)
arrow(edge_point(tf, "top"), edge_point(gha, "bottom"), MUTED, dashed=True, label="declares everything", label_dx=100)

img = img.resize((W, H), Image.LANCZOS)
out = pathlib.Path(__file__).resolve().parent.parent / "docs" / "hackathon" / "architecture.png"
img.save(out, "PNG", optimize=True)
print("wrote", out, img.size)
