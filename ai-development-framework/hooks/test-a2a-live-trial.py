"""hooks/run-a2a-live-trial.py: the matrix is a gate, and the committed report carries no secret."""
import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("run_a2a_live_trial", ROOT / "hooks/run-a2a-live-trial.py")
trial = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(trial)


class A2ALiveTrialTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def run_trial(self, trial_id="t", auth="hs256"):
        with contextlib.redirect_stderr(io.StringIO()):  # the server logs method/route/status per request
            return trial.run(trial_id, self.base / "out", self.base / "evidence" / trial_id, auth)

    def test_matrix_passes_records_verify_and_report_is_redacted(self):
        ok, target = self.run_trial()
        summary, rows = json.loads((target / "summary.json").read_text()), json.loads((target / "rows.json").read_text())
        self.assertTrue(ok)
        self.assertEqual((summary["as_expected"], summary["total"], summary["verify_record_false"], summary["redaction_leaks"]), (len(trial.CASES), len(trial.CASES), 0, 0))
        self.assertEqual(summary["verify_record_true"], summary["records"]); self.assertGreater(summary["records"], 0)
        delivered = {row["case"] for row in rows if row["content_delivered"]}
        self.assertEqual(delivered, {"T6", "T7b"}, "only the approved README is ever delivered")
        text = "".join(path.read_text() for path in target.iterdir())
        for forbidden in (trial.SECRET, trial.PUBLIC.strip(), str(self.base), "eyJ", "Bearer "): self.assertNotIn(forbidden, text)

    @unittest.skipUnless(shutil.which("openssl"), "openssl CLI not installed: RS256 trial skipped, not passed")
    def test_rs256_mode_uses_only_the_pinned_public_jwks(self):
        ok, target = self.run_trial("rs", auth="rs256")
        summary = json.loads((target / "summary.json").read_text())
        self.assertTrue(ok); self.assertEqual((summary["auth_mode"], summary["as_expected"]), ("rs256_jwks_openssl_test_idp", len(trial.CASES)))
        methods = {json.loads(path.read_text())["principal"]["authn_method"] for path in (self.base / "evidence/rs/_a2a").glob("*.json")}
        self.assertEqual(methods, {"bearer_jwt_rs256"})
        self.assertNotIn("PRIVATE KEY", "".join(path.read_text() for path in target.iterdir()))

    def test_unexpected_result_fails_the_trial_and_reports_never_overwrite(self):
        wrong = [case[:-2] + (200, "read_delivered") if case[0] == "T5a" else case for case in trial.CASES]
        with patch.object(trial, "CASES", wrong): ok, target = self.run_trial("wrong")
        self.assertFalse(ok)
        self.assertEqual([row["case"] for row in json.loads((target / "rows.json").read_text()) if not row["as_expected"]], ["T5a"])
        with self.assertRaises(FileExistsError): self.run_trial("wrong")


if __name__ == "__main__": unittest.main(verbosity=2)
