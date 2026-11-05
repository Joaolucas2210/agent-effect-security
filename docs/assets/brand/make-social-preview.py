#!/usr/bin/env python3
"""Render the opaque ADF social preview. Requires Pillow and DejaVu Sans."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).with_name("adf-social-preview.png")
image = Image.new("RGB", (1280, 640), "#0B1220")
draw = ImageDraw.Draw(image)
font = lambda size, bold=False: ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)

# The mark uses the same 64-unit geometry as adf-mark.svg, scaled four times.
x, y, scale = 85, 85, 4
draw.rounded_rectangle((x, y, x + 64 * scale, y + 64 * scale), radius=48, fill="#263548")
line = lambda xy, color, width: draw.line([(x + a * scale, y + b * scale) for a, b in xy], fill=color, width=width * scale)
line([(31, 8), (31, 24)], "#F3F7FC", 4)
line([(31, 40), (31, 56)], "#F3F7FC", 4)
line([(8, 32), (23, 32)], "#F3F7FC", 4)
line([(41, 32), (56, 32)], "#F3F7FC", 4)
draw.polygon([(x + a * scale, y + b * scale) for a, b in ((32, 25), (39, 32), (32, 39), (25, 32))], fill="#52D1B0")
draw.rectangle((x + 46 * scale, y + 45 * scale, x + 56 * scale, y + 55 * scale), outline="#52D1B0", width=3 * scale)

draw.text((385, 92), "ADF", font=font(132, True), fill="#F3F7FC")
draw.text((391, 262), "Agent Effect Security", font=font(38), fill="#B9C8D8")
draw.line((85, 400, 1195, 400), fill="#52D1B0", width=4)
draw.text((85, 432), "Decisions at the boundary.", font=font(50, True), fill="#F3F7FC")
draw.text((85, 497), "Evidence with explicit limits.", font=font(50, True), fill="#52D1B0")  # 9.90:1 on #0B1220
draw.text((87, 574), "Read decisions at supported, installed coding-agent edges.", font=font(27), fill="#B9C8D8")
image.save(OUT, optimize=True)  # Pillow writes no text/time chunks unless asked: no metadata to strip
if OUT.stat().st_size > 1_000_000:
    raise SystemExit("social preview exceeds 1 MB")
print(f"{OUT}: {image.width}x{image.height}, {OUT.stat().st_size} bytes")
