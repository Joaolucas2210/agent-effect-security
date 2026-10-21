"""hooks/docs_check.py: the repo's Markdown links, anchors and EN/pt-BR parity hold, and the checker can go red."""
import importlib.util
import io
import contextlib
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("docs_check", ROOT / "hooks/docs_check.py")
docs = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(docs)


def check(root):
    out = io.StringIO()
    docs.ROOT = Path(root).resolve(); docs.anchors.__defaults__[0].clear()
    with contextlib.redirect_stdout(out):
        code = docs.main()
    return code, out.getvalue()


class DocsCheckTest(unittest.TestCase):
    def test_repository_docs_are_consistent(self):
        code, out = check(ROOT.parent)
        self.assertEqual(code, 0, out)

    def test_checker_catches_each_class_of_problem(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "d").mkdir()
            (base / "a.md").write_text('# Título Ação\n\n## Vários projetos, um hook (REQ-MP-01)\n\n<a id="velho"></a>\n## Novo\n\n'
                                       'ok [a](#vários-projetos-um-hook-req-mp-01) [b](#velho) [c](d/x.md#seção-2) `[ignored](nope.md)`\n\n'
                                       '```\n[ignored too](nope.md)\n```\n[bad1](missing.md) [bad2](#nope) [bad3](d/x.md#none) [web](https://x.y/z.md#q)\n')
            (base / "d/x.md").write_text("# X\n\n## Seção 2\n")
            (base / "p.md").write_text("# P\n\n**English** · [Português (Brasil)](p.pt-BR.md)\n## A\n")
            (base / "p.pt-BR.md").write_text("# P\n\n[English](p.md) · **Português (Brasil)**\n## A\n## B\n")
            (base / "q.pt-BR.md").write_text("# Q\n")
            (base / "r.md").write_text("# R\n## A\n")
            (base / "r.pt-BR.md").write_text("# R\n\n[English](r.md) · **Português (Brasil)**\n## A\n")
            subprocess.run(["git", "init", "-q", str(base)], check=True); subprocess.run(["git", "-C", str(base), "add", "-A"], check=True)
            code, out = check(base)
        self.assertEqual(code, 1)
        for expected in ("a.md: missing target missing.md", "a.md: missing anchor #nope", "a.md: missing anchor d/x.md#none",
                         "p.pt-BR.md: heading structure differs", "q.pt-BR.md: no English original", "r.md: missing language switcher"):
            self.assertIn(expected, out)
        self.assertEqual(out.count("  ✗ "), 6, out)  # good links, code spans, fenced blocks and URLs are not flagged

    def test_github_slug_rules(self):
        for heading, slug in (("Vários projetos com um hook só (REQ-MP-01)", "vários-projetos-com-um-hook-só-req-mp-01"),
                              ("3. Correlation: span → evidence → verification", "3-correlation-span--evidence--verification"),
                              ("`adf` and [link](x.md)", "adf-and-link"), ("Codex Bash read-equivalent (P4)", "codex-bash-read-equivalent-p4")):
            self.assertEqual(docs.slug(heading), slug)


if __name__ == "__main__": unittest.main(verbosity=2)
