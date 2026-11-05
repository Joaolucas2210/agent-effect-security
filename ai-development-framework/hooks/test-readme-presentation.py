"""hooks/readme_check.py: the repository's public entry points pass, and every class of problem goes red."""
import importlib.util
import io
import contextlib
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("readme_check", ROOT / "hooks/readme_check.py")
check = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(check)


def run(root):
    out = io.StringIO()
    check.ROOT = Path(root).resolve(); check.docs_check.anchors.__defaults__[0].clear()
    with contextlib.redirect_stdout(out):
        code = check.main()
    return code, out.getvalue()


GOOD_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><title>t</title><desc>d</desc><rect/></svg>'
HERO = '<p align="center"><img src="mark.svg" alt="A meaningful mark description"></p>\n\n<h1 align="center">X</h1>\n\n'


class ReadmeCheckTest(unittest.TestCase):
    def fixture(self, en, pt):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); base = Path(temp.name)
        (base / "mark.svg").write_text(GOOD_SVG)
        (base / "README.md").write_text(en); (base / "README.pt-BR.md").write_text(pt)
        subprocess.run(["git", "init", "-q", str(base)], check=True)
        return base

    def test_repository_entry_points_pass(self):
        code, out = run(ROOT.parent)
        self.assertEqual(code, 0, out)

    def test_a_clean_fixture_passes(self):
        body = HERO + '<p align="center"><a href="#two">Go</a></p>\n\n## Two\n\ntext\n'
        code, out = run(self.fixture(body, body))
        self.assertEqual(code, 0, out)

    def test_each_problem_goes_red(self):
        en = (HERO + '<p align="center"><a href="#nope">Go</a> <img src="missing.png" alt="Something missing here"> <img src="mark.svg"></p>\n\n'
              + "".join(f'<img src="https://img.shields.io/badge/{i}" alt="badge number {i} here">' for i in range(4))
              + "\n\n#### Jump\n\nADF is bulletproof.\n\n![x](mark.svg)\n")
        pt = HERO + "## Dois\n"
        code, out = run(self.fixture(en, pt))
        self.assertEqual(code, 1)
        for expected in ("missing anchor #nope", "missing target missing.png", "<img> without meaningful alt", "badges (max 3)", "heading jumps from h1 to h4",
                         "over-claim wording", "image without meaningful alt", "images differ"):
            self.assertIn(expected, out)

    def test_code_blocks_are_ignored(self):
        body = HERO + "## Two\n\n```html\n<img src=\"nope.png\">\nfail-closed by default\n```\n"
        self.assertEqual(run(self.fixture(body, body))[0], 0)


if __name__ == "__main__": unittest.main(verbosity=2)
