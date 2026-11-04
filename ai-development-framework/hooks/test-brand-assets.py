"""Dependency-free checks for the committed ADF brand assets."""
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "docs/assets/brand"
SVGS = ("adf-mark", "adf-wordmark-light", "adf-wordmark-dark", "adf-hero", "adf-architecture", "adf-evidence-flow")


def safe_svg(source):
    root = ET.fromstring(source)
    assert root.tag.endswith("}svg")
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in {"script", "foreignObject", "image", "iframe", "use"}:
            return False
        for name, value in element.attrib.items():
            name = name.rsplit("}", 1)[-1].lower()
            if name.startswith("on") or (name == "href" and not value.startswith("#")):
                return False
            if re.search(r"url\((?!#)|https?://|data:", value, re.I):
                return False
    return bool(root.attrib.get("viewBox")) and any(e.tag.endswith("}title") for e in root)


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(a, b):
    x, y = sorted((luminance(a), luminance(b)))
    return (y + 0.05) / (x + 0.05)


def main():
    assert not safe_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><title>x</title><script/></svg>')
    assert contrast("#111111", "#111111") < 4.5
    for name in SVGS:
        path = ASSETS / f"{name}.svg"
        assert safe_svg(path.read_text(encoding="utf-8")), path
    png = ASSETS / "adf-social-preview.png"
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (1280, 640)
    assert len(data) <= 1_000_000
    for foreground, background in (("#111827", "#F6F8FB"), ("#F3F7FC", "#0B1220"),
                                   ("#B9C8D8", "#0B1220"), ("#075E50", "#F6F8FB"),
                                   ("#52D1B0", "#0B1220")):
        assert contrast(foreground, background) >= 4.5
    for readme in (ROOT / "README.md", ROOT / "README.pt-BR.md"):
        text = readme.read_text(encoding="utf-8")
        assert re.search(r'^# <img src="docs/assets/brand/adf-mark\.svg" alt="[^"]+" width="40" height="40"> ADF · Agent Effect Security$', text, re.M), readme
        for name in ("adf-hero.svg", "adf-architecture.svg", "adf-evidence-flow.svg"):
            assert re.search(r"!\[[^\]]+\]\(docs/assets/brand/" + re.escape(name) + r"\)", text), (readme, name)
    print(f"brand assets: {len(SVGS)} safe SVGs, 1280x640 PNG under 1 MB, contrast and alt text OK")


if __name__ == "__main__":
    main()
