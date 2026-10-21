"""Docs gate: every relative Markdown link resolves (file and #anchor); every X.pt-BR.md mirrors X.md.

English is the primary language (AGENTS.md). A bilingual document has a pt-BR sibling with the same heading
structure and a language switcher in each file. Anchors follow GitHub's slug rules; `<a id>` keeps an old anchor alive.
Usage: python3 hooks/docs_check.py [REPO_ROOT]   (tracked *.md files only; exit 1 on any problem)
"""
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
EXPLICIT = re.compile(r"<a\s+(?:id|name)=\"([^\"]+)\"", re.I)
SWITCH_EN = re.compile(r"^\*\*English\*\* · \[Português \(Brasil\)\]\(([^)]+\.pt-BR\.md)\)$", re.M)
SWITCH_PT = re.compile(r"^\[English\]\(([^)]+\.md)\) · \*\*Português \(Brasil\)\*\*$", re.M)


def slug(text):
    """GitHub heading anchor: drop markdown/HTML, lowercase, keep letters/digits/-/_ and spaces->-."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    out = []
    for char in text:
        if char in " ":
            out.append("-")
        elif char in "-_" or unicodedata.category(char)[0] in ("L", "N"):
            out.append(char)
    return "".join(out)


def strip_code(text):
    text = re.sub(r"^(```|~~~).*?^\1\s*$", "", text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "", text)


def anchors(path, cache={}):
    if path not in cache:
        seen, found = {}, set()
        text = path.read_text(encoding="utf-8")
        for line in re.sub(r"^(```|~~~).*?^\1\s*$", "", text, flags=re.S | re.M).splitlines():
            match = HEADING.match(line)
            if match:
                base = slug(match.group(2)); count = seen.get(base, 0); seen[base] = count + 1
                found.add(base if count == 0 else f"{base}-{count}")
        found.update(EXPLICIT.findall(text))
        cache[path] = found
    return cache[path]


def headings(path):
    text = re.sub(r"^(```|~~~).*?^\1\s*$", "", path.read_text(encoding="utf-8"), flags=re.S | re.M)
    return [len(m.group(1)) for m in map(HEADING.match, text.splitlines()) if m]


def main():
    files = [ROOT / name for name in subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.md"], capture_output=True, text=True, check=True).stdout.split()]
    problems = []
    for source in files:
        if not source.exists():
            continue
        text = strip_code(source.read_text(encoding="utf-8"))
        for match in LINK.finditer(text):
            target = match.group(1) or match.group(2)
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("//"):
                continue
            file_part, _, anchor = target.partition("#")
            resolved = source if not file_part else (source.parent / file_part).resolve()
            rel = source.relative_to(ROOT)
            if not resolved.exists():
                problems.append(f"{rel}: missing target {target}")
            elif anchor and resolved.suffix == ".md" and anchor not in anchors(resolved):
                problems.append(f"{rel}: missing anchor {target}")
    for pt in [path for path in files if path.name.endswith(".pt-BR.md")]:
        en = pt.with_name(pt.name[: -len(".pt-BR.md")] + ".md")
        rel = pt.relative_to(ROOT)
        if not en.exists():
            problems.append(f"{rel}: no English original"); continue
        if not SWITCH_EN.search(en.read_text(encoding="utf-8")):
            problems.append(f"{en.relative_to(ROOT)}: missing language switcher to {pt.name}")
        if not SWITCH_PT.search(pt.read_text(encoding="utf-8")):
            problems.append(f"{rel}: missing language switcher to {en.name}")
        if headings(en) != headings(pt):
            problems.append(f"{rel}: heading structure differs from {en.name} ({len(headings(pt))} vs {len(headings(en))})")
    for line in problems:
        print(f"  ✗ {line}")
    print(f"{'✓' if not problems else '✗'} docs: {len(files)} Markdown files, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
