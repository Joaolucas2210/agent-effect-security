#!/usr/bin/env python3
"""Render docs/assets/adf-demo.gif from real ADF commands against a synthetic fixture.

Every line shown in the GIF is captured from the actual `adf` CLI and PreToolUse entry point, run against a
throwaway repository and an isolated ADF_HOME created by this script. No client is involved. Only two
substitutions are made for readability: the temporary repository path is shown as `~/dev/my-app` and the
temporary ADF_HOME as `~/.adf`. Needs: the repo's `.venv` (`make install-dev`) and Pillow on the Python that runs
this script (`python3 -m pip install Pillow`). No asciinema/agg/ffmpeg required; see README.md next to this file
for the live-recording alternative.

    python3 docs/assets/make-demo-gif.py            # writes docs/assets/adf-demo.gif
"""
import json
import os
import textwrap
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ai-development-framework/e2e"))
from demo import make_fixture  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ADF = ROOT / ".venv/bin/adf"
OUT = ROOT / "docs/assets/adf-demo.gif"
COLS, ROWS, CELL_W, CELL_H, PAD = 92, 17, 11, 22, 18
BG, FG, DIM, GREEN, RED, CYAN, YELLOW = (24, 26, 32), (222, 224, 230), (130, 136, 150), (110, 220, 140), (255, 110, 110), (110, 190, 255), (240, 200, 90)
FONT = next(p for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf") if Path(p).exists())


def sh(args, env, stdin=None):
    proc = subprocess.run(args, input=stdin, capture_output=True, text=True, env=env, timeout=120)
    return (proc.stdout + proc.stderr).strip()


def hook(env, tool_input, repo):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "demo-session", "tool_input": tool_input}
    out = sh([str(ADF), "hook"], {**env, "CLAUDE_PROJECT_DIR": str(repo)}, stdin=json.dumps(payload))
    decision = json.loads(out)["hookSpecificOutput"]
    return decision["permissionDecision"], decision["permissionDecisionReason"]


def capture():
    """Call the real entry points with synthetic inputs; return the scene list."""
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp).resolve(); home = base / "adf-home"; home.mkdir()
        repo = make_fixture(base)  # the same synthetic project `make demo` uses (e2e/demo.py)
        env = {"PATH": os.environ["PATH"], "HOME": str(base), "ADF_HOME": str(home)}
        scenes = []
        scenes.append(("adf projects enable ~/dev/my-app", [sh([str(ADF), "projects", "enable", str(repo)], env)]))
        key_line = sh([str(ADF), "key", "init"], env); env["ADF_EVIDENCE_KEY_FILE"] = str(home / "evidence.key")
        scenes.append(("adf key init", [key_line]))
        allow = hook(env, {"file_path": str(repo / "README.md")}, repo)
        scenes.append(("# Hook fixture → Read README.md", [f"{allow[0]:<6} {allow[1]}"]))
        deny = hook(env, {"file_path": str(repo / ".env")}, repo)
        scenes.append(("# Hook fixture → Read .env", [f"{deny[0]:<6} {deny[1]}"]))
        bundle_id = deny[1].split("bundle=")[1]
        bundle = next((home / "evidence").rglob(f"{bundle_id}.json"))
        shown = f"~/.adf/evidence/…/demo-session/{bundle_id[:8]}….json"  # elided for the frame width; the file name is the full bundle id
        scenes.append((f"adf verify {shown} --key ~/.adf/evidence.key", [sh([str(ADF), "verify", str(bundle), "--key", str(home / "evidence.key")], env)]))
        scenes.append(("adf projects reasons", sh([str(ADF), "projects", "reasons"], env).splitlines()[:2]))
        text = json.dumps(scenes).replace(str(repo), "~/dev/my-app").replace(str(home), "~/.adf").replace(str(base), "~")
        return json.loads(text)


def colour(line):
    if line.startswith("allow"): return GREEN
    if line.startswith("deny") or "NOT verified" in line: return RED
    if line.startswith("verified"): return GREEN
    if line.startswith("enabled") or line.startswith("export"): return CYAN
    return FG


def render(scenes):
    font = ImageFont.truetype(FONT, 16)
    width, height = PAD * 2 + COLS * CELL_W, PAD * 2 + ROWS * CELL_H
    frames, durations, screen = [], [], []

    def draw(hold_ms, cursor=True):
        img = Image.new("RGB", (width, height), BG); d = ImageDraw.Draw(img)
        d.rectangle([0, 0, width, 30], fill=(36, 38, 46)); d.text((PAD, 7), "adf · isolated hook fixture · no client", fill=DIM, font=font)
        y = 30 + 8
        rows = []
        for kind, text in screen:
            chunks = textwrap.wrap(text, COLS - (2 if kind == "prompt" else 0), break_long_words=True, break_on_hyphens=False) or [""]
            rows.extend((kind, i, chunk) for i, chunk in enumerate(chunks))
        for kind, i, text in rows[-ROWS:]:
            if kind == "prompt":
                if i == 0: d.text((PAD, y), "$ ", fill=YELLOW, font=font)
                d.text((PAD + 2 * CELL_W, y), text, fill=FG, font=font)
            else:
                d.text((PAD, y), text, fill=colour(text) if i == 0 else colour(rows[rows.index((kind, i, text)) - i][2]), font=font)
            y += CELL_H
        if cursor and y < height - CELL_H:
            d.rectangle([PAD, y + 3, PAD + CELL_W - 2, y + CELL_H - 3], fill=FG)
        frames.append(img.quantize(colors=48, method=Image.Quantize.MEDIANCUT)); durations.append(hold_ms)

    draw(600)
    for prompt, lines in scenes:
        typed = ""
        for i in range(0, len(prompt), 6):
            typed = prompt[: i + 6]; screen.append(("prompt", typed)); draw(35); screen.pop()
        screen.append(("prompt", prompt)); draw(250)
        for line in lines:
            screen.append(("out", line))
        draw(1100)
        screen.append(("out", ""))
    draw(2200, cursor=False)
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=1)
    return sum(durations) / 1000, OUT.stat().st_size


if __name__ == "__main__":
    scenes = capture()
    for prompt, lines in scenes:
        print(f"$ {prompt}"); [print("  " + l) for l in lines]
    seconds, size = render(scenes)
    print(f"\nwrote {OUT.relative_to(ROOT)}: {seconds:.1f}s, {size / 1024:.0f} KiB, {len(scenes)} scenes")
    sys.exit(0 if size < 3 * 1024 * 1024 else 1)
