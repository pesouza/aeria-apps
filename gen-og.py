#!/usr/bin/env python3
"""Gera OG image profissional para Aeria Apps (1200x630 PNG)."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
img = Image.new("RGB", (W, H), "#050814")
draw = ImageDraw.Draw(img)

# ─── Gradients ───
def gradient_h(draw, x1, y1, x2, y2, c1, c2):
    """Horizontal gradient overlay."""
    for x in range(x1, x2):
        t = (x - x1) / max(x2 - x1 - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(x, y1), (x, y2)], fill=(r, g, b))

def gradient_radial(draw, cx, cy, radius, c1, c2):
    """Radial gradient glow."""
    for r in range(radius, 0, -1):
        t = r / radius
        cl = tuple(int(c1[i] + (c2[i] - c1[i]) * (1 - t)) for i in range(3))
        a = int(80 * (1 - t**2))
        try:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cl + (a,) if a > 0 else cl)
        except:
            pass

# ─── Background layers ───
# Deep gradient from top-left to bottom-right
gradient_h(draw, 0, 0, W, H, (5, 8, 20), (10, 20, 46))
gradient_h(draw, 0, 0, W, H, (20, 10, 40), (5, 8, 20))
draw.rectangle([0, 0, W, H], fill=(5, 8, 20))

# Darker blue streak
for y in range(H):
    t = y / H
    r = int(5 + 8 * (1 - abs(t - 0.5) * 2))
    g = int(8 + 20 * (1 - abs(t - 0.5) * 2))
    b = int(20 + 46 * (1 - abs(t - 0.5) * 2))
    draw.line([(0, y), (W, y)], fill=(r, g, b))

# ─── Grid overlay ───
grid_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gdraw = ImageDraw.Draw(grid_img)
grid_color = (61, 109, 255, 12)
for x in range(0, W, 48):
    gdraw.line([(x, 0), (x, H)], fill=grid_color)
for y in range(0, H, 48):
    gdraw.line([(0, y), (W, y)], fill=grid_color)
img = Image.alpha_composite(img.convert("RGBA"), grid_img)
draw = ImageDraw.Draw(img)

# ─── Glows ───
def glow_circle(draw, cx, cy, radius, color, max_alpha=60):
    for r in range(radius, 0, -2):
        t = r / radius
        a = int(max_alpha * (1 - t**1.5))
        if a < 1:
            continue
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=tuple(int(c * (1 - t)) for c in color) + (a,),
        )

glow_circle(draw, 950, 150, 350, (0, 200, 255), 40)
glow_circle(draw, 200, 500, 280, (139, 92, 246), 35)
glow_circle(draw, 600, 300, 200, (6, 182, 212), 20)

# ─── Geometric decorative elements ───
# Circuit-like lines
line_color = (61, 109, 255, 30)
draw.line([(850, 450), (950, 450), (1000, 400), (1100, 400)], fill=line_color, width=2)
draw.line([(1000, 100), (1000, 200), (1050, 250), (1150, 250)], fill=line_color, width=2)
draw.line([(80, 80), (130, 80), (180, 130)], fill=line_color, width=2)

# Small dots
dot_color = (67, 232, 216, 60)
for (x, y) in [(850, 450), (1000, 400), (1100, 400), (1000, 100), (1050, 250), (80, 80), (180, 130)]:
    draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=dot_color)

# ─── Logo box ───
logo_box = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
ldraw = ImageDraw.Draw(logo_box)
# Gradient blue-purple rounded rect
for i in range(30):
    t = i / 30
    r = int(61 + (139 - 61) * t)
    g = int(109 + (92 - 109) * t)
    b = int(255 + (246 - 255) * t)
    ldraw.rectangle([i, i, 60 - i, 60 - i], fill=(r, g, b, 200))
img.paste(logo_box, (70, 65), logo_box)

# "A" letter inside logo
try:
    font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
except:
    font_bold = ImageFont.load_default()
ldraw2 = ImageDraw.Draw(img)
ldraw2.text((70 + 8, 65 + 6), "A", fill=(255, 255, 255), font=font_bold)

# ─── Brand text ───
try:
    font_semibold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
    font_bold_h1 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
    font_regular = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    font_tag = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
except:
    font_semibold = ImageFont.load_default()
    font_bold_h1 = ImageFont.load_default()
    font_regular = ImageFont.load_default()
    font_tag = ImageFont.load_default()

draw.text((142, 73), "Aeria", fill=(240, 244, 255), font=font_semibold)
# "Apps" in cyan
draw.text((142 + font_semibold.getlength("Aeria "), 73), "Apps", fill=(103, 232, 249), font=font_semibold)

# ─── Accent line ───
for i in range(80):
    t = i / 80
    r = int(61 + (139 - 61) * t)
    g = int(109 + (92 - 109) * t)
    b = int(255 + (246 - 255) * t)
    draw.rectangle([70 + i, 110, 70 + i, 114], fill=(r, g, b))

# ─── Main heading ───
draw.text((70, 130), "Sistemas autônomos", fill=(255, 255, 255), font=font_bold_h1)
draw.text((70, 190), "para reduzir fricção", fill=(255, 255, 255), font=font_bold_h1)
draw.text((70, 250), "operacional", fill=(255, 255, 255), font=font_bold_h1)

# ─── Subtitle ───
draw.text(
    (70, 330),
    "Selfwares que assumem tarefas repetitivas, acompanham processos\n"
    "e mantêm fluxos operacionais em movimento com menos dependência humana.",
    fill=(148, 163, 184),
    font=font_regular,
)

# ─── Tags ───
tags = [("Selfware", (61, 109, 255)), ("Automação", (6, 182, 212)), ("PME", (139, 92, 246)), ("Operação", (61, 109, 255))]
tx, ty = 70, 420
padding_x, padding_y = 16, 8
for tag, (tr, tg, tb) in tags:
    tag_w = font_tag.getlength(tag)
    draw.rounded_rectangle(
        [tx, ty - padding_y, tx + tag_w + padding_x * 2, ty + padding_y + 12],
        radius=20,
        fill=(tr, tg, tb, 15),
        outline=(tr, tg, tb, 50),
    )
    draw.text((tx + padding_x, ty), tag, fill=(tr, tg, tb), font=font_tag)
    tx += tag_w + padding_x * 2 + 10

# ─── URL ───
draw.text((W - 200, H - 50), "aeria-apps.com.br", fill=(148, 163, 184, 80), font=font_tag)

# ─── Save ───
out_path = "/workspace/aeria-apps/static/img/og-default.png"
img = img.convert("RGB")  # Remove alpha for JPEG compatibility
img.save(out_path, "PNG")
print(f"OG image saved: {out_path} ({os.path.getsize(out_path)} bytes)")
