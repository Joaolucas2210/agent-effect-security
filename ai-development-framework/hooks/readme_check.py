"""Presentation gate for the public entry points (README.md / README.pt-BR.md) and the brand assets.

docs_check.py already covers Markdown links, anchors and heading parity, and test-brand-assets.py the SVGs,
the social preview and contrast. This adds what neither sees: HTML `src`/`href` in the centered hero, alt text,
the badge budget, heading-level jumps, EN/PT-BR image parity and over-claim wording. Stdlib only.
Usage: python3 hooks/readme_check.py [REPO_ROOT]   (exit 1 on any problem)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_check  # noqa: E402

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
PAIRS = (("README.md", "README.pt-BR.md"),)
MAX_BADGES = 3
HTML_ATTR = re.compile(r'<(img|a)\b[^>]*?\b(src|href)="([^"]+)"[^>]*>', re.I)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
MD_IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
HEADING_MD = re.compile(r"^(#{1,6})\s+\S", re.M)
HEADING_HTML = re.compile(r"<h([1-6])\b", re.I)
BADGE = re.compile(r"shields\.io|badge\.svg", re.I)
OVERCLAIM = re.compile(r"\b(fail-closed by default|always fail[s]? closed|bulletproof|unbreakable|military-grade|100% (?:secure|coverage)|complete containment|any (?:read|command) is blocked)\b", re.I)


def _code_free(text):
    return docs_check.strip_code(text)


def _local(target):
    return not re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) and not target.startswith("//")


def check_readme(path):
    problems, text = [], _code_free(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT)
    for _tag, _attr, target in HTML_ATTR.findall(text):
        if not _local(target):
            continue
        file_part, _, anchor = target.partition("#")
        resolved = path if not file_part else (path.parent / file_part).resolve()
        if not resolved.exists():
            problems.append(f"{rel}: missing target {target}")
        elif anchor and resolved.suffix == ".md" and anchor not in docs_check.anchors(resolved):
            problems.append(f"{rel}: missing anchor {target}")
    for tag in IMG_TAG.findall(text):
        alt = re.search(r'\balt="([^"]*)"', tag)
        if not alt or len(alt.group(1).strip()) < 8:
            problems.append(f"{rel}: <img> without meaningful alt: {tag[:60]}")
    for alt, target in MD_IMG.findall(text):
        if len(alt.strip()) < 8:
            problems.append(f"{rel}: image without meaningful alt: {target}")
    badges = [t for t in IMG_TAG.findall(text) + [m[1] for m in MD_IMG.findall(text)] if BADGE.search(t)]
    if len(badges) > MAX_BADGES:
        problems.append(f"{rel}: {len(badges)} badges (max {MAX_BADGES})")
    levels = sorted([(m.start(), len(m.group(1))) for m in HEADING_MD.finditer(text)] + [(m.start(), int(m.group(1))) for m in HEADING_HTML.finditer(text)])
    previous = 0
    for _pos, level in levels:
        if previous and level > previous + 1:
            problems.append(f"{rel}: heading jumps from h{previous} to h{level}")
        previous = level
    if not levels or levels[0][1] != 1 or sum(1 for _p, lvl in levels if lvl == 1) != 1:
        problems.append(f"{rel}: needs exactly one h1, first")
    for match in OVERCLAIM.finditer(text):
        problems.append(f"{rel}: over-claim wording: {match.group(0)!r}")
    return problems


def images(path):
    text = _code_free(path.read_text(encoding="utf-8"))
    return sorted([t for _tag, attr, t in HTML_ATTR.findall(text) if attr == "src" and _local(t)] + [t for _alt, t in MD_IMG.findall(text) if _local(t)])


def main():
    problems = []
    for en, pt in PAIRS:
        en_path, pt_path = ROOT / en, ROOT / pt
        problems += check_readme(en_path) + check_readme(pt_path)
        if images(en_path) != images(pt_path):
            problems.append(f"{pt}: images differ from {en}: {images(en_path)} vs {images(pt_path)}")
    for problem in problems:
        print(f"  ✗ {problem}")
    print(f"{'✗' if problems else '✓'} presentation: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
