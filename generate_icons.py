"""
Generate PNG icons from the SVG source.
Run once: python generate_icons.py
Requires: pip install cairosvg  OR  pip install Pillow (fallback)
"""
import os
import shutil

SVG_PATH = "frontend/icons/icon.svg"
OUT_DIR = "frontend/icons"
SIZES = [192, 512]


def generate_with_cairosvg():
    import cairosvg
    for size in SIZES:
        out = os.path.join(OUT_DIR, f"icon-{size}.png")
        cairosvg.svg2png(url=SVG_PATH, write_to=out, output_width=size, output_height=size)
        print(f"  Generated {out}")


def generate_placeholder_pngs():
    """Fallback: create simple coloured PNG placeholders."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  Neither cairosvg nor Pillow available.")
        print("  Copy any 192x192 and 512x512 PNG files to frontend/icons/")
        return

    for size in SIZES:
        img = Image.new("RGBA", (size, size), (15, 17, 23, 255))
        draw = ImageDraw.Draw(img)
        # Simple blue rounded rectangle + text
        pad = size // 6
        draw.rounded_rectangle([pad, pad, size - pad, size - pad],
                                radius=size // 8, fill=(37, 99, 235, 255))
        text = "PA"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size // 3)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(((size - tw) // 2, (size - th) // 2), text, fill=(255, 255, 255, 255), font=font)
        out = os.path.join(OUT_DIR, f"icon-{size}.png")
        img.save(out)
        print(f"  Generated placeholder {out}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Generating app icons...")
    try:
        generate_with_cairosvg()
    except ImportError:
        print("  cairosvg not found, using Pillow fallback...")
        generate_placeholder_pngs()
    print("Done. Icons saved to frontend/icons/")
