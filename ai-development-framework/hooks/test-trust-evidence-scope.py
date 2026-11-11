"""R-11 (Phase 2A): the five evidence properties are different things; this pins what each one does today.

(a) HMAC sidecar (ADR 0030) = host-key authenticity of one file, shared secret; (b) the attempt journal links the
two events *inside one attempt*, never across attempts; (c) a bundle is self-digested and an A2A record links one
bundle, but nothing links bundles or journals to each other; (d) bundle provenance is component versions plus a
Git tree digest, not a repository or commit identity; (e) one key, no rotation (ADR 0038 Proposed).
Throwaway directories only; no host key is read.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from integration import evidence_signing as signing  # noqa: E402
from integration.adapter_attempt import AttemptJournal, verify_attempt  # noqa: E402

SCHEMAS = ROOT / "integration/v1/schemas"


def load(name): return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


class EvidenceScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.attempt_schema = load("adapter-attempt-event.schema.json")

    def attempt(self, outcome="deny"):
        journal = AttemptJournal(self.base / "evidence", "run-r11", self.attempt_schema, adapter_id="deny-only-gate")
        try:
            journal.finish({"outcome": outcome, "reason_code": "sensitive_path_denied", "bundle_id": None})
        finally:
            journal.close()
        return journal._path

    @staticmethod
    def events(path): return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    # (b) journal linking --------------------------------------------------------------------------------------

    def test_journal_links_two_events_within_one_attempt_only(self):
        first, second = self.attempt(), self.attempt()
        self.assertNotEqual(first, second, "one file per attempt")
        for path in (first, second):
            start, end = self.events(path)
            self.assertIsNone(start["previous_event_sha256"], "every attempt starts a fresh link: no cross-attempt chain")
            self.assertEqual(end["previous_event_sha256"], start["event_sha256"])
            self.assertEqual(verify_attempt(self.events(path), self.attempt_schema), "complete")

    def test_deleting_a_whole_attempt_is_not_detectable_from_the_rest(self):
        first, second = self.attempt(), self.attempt()
        first.unlink()
        self.assertEqual(verify_attempt(self.events(second), self.attempt_schema), "complete", "no sequence number or predecessor reveals the gap")

    def test_editing_an_event_breaks_its_attempt(self):
        path = self.attempt(); start, end = self.events(path)
        end["payload"]["reason_code"] = "allowed"
        self.assertEqual(verify_attempt([start, end], self.attempt_schema), "invalid")

    # (c) composition / (d) provenance ------------------------------------------------------------------------

    def test_bundle_has_no_link_to_previous_evidence_and_no_repository_identity(self):
        props = load("evidence-bundle.schema.json")["properties"]
        self.assertFalse([key for key in props if "previous" in key or "chain" in key or "journal" in key or "attempt" in key])
        self.assertFalse([key for key in props if key in ("repository", "revision", "commit", "commit_sha")])
        self.assertEqual(sorted(props["provenance"]["properties"]), ["adapter_version", "kind", "pdp_version", "pep_version"], "component versions, not ADF clone revision")
        self.assertIn("snapshot_digest", props, "content identity of the Git tree that was read")

    def test_a2a_record_links_exactly_one_bundle(self):
        props = load("a2a-evidence-record.schema.json")["properties"]
        self.assertIn("bundle_id", props)
        self.assertFalse([key for key in props if "previous" in key or "chain" in key])

    # (a) HMAC authenticity / (e) key custody -----------------------------------------------------------------

    def test_hmac_is_per_file_shared_secret(self):
        key_path = signing.init_key(self.base / "evidence.key"); key = signing.load_key(key_path)
        target = self.base / "bundle.json"; target.write_text('{"x":1}')
        self.assertEqual(signing.verify_file(target, None), "not_checked", "no key: integrity only")
        signing.sign_file(target, key)
        self.assertEqual(signing.verify_file(target, key), "valid")
        target.write_text('{"x":2}'); self.assertEqual(signing.verify_file(target, key), "invalid")
        target.with_name("bundle.json.sig").unlink()
        self.assertEqual(signing.verify_file(target, key), "unsigned", "deleting the sidecar downgrades to unsigned, not invalid")
        forged = self.base / "forged.json"; forged.write_text('{"forged":true}')
        signing.sign_file(forged, key)
        self.assertEqual(signing.verify_file(forged, key), "valid", "whoever holds the key (verifier included) can mint 'valid' evidence")

    def test_single_key_never_overwritten_no_rotation(self):
        path = signing.init_key(self.base / "evidence.key")
        with self.assertRaises(FileExistsError):
            signing.init_key(path)
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), oct(0o400))
        target = self.base / "f.json"; target.write_text("{}"); meta = json.loads(signing.sign_file(target, signing.load_key(path)).read_text())
        self.assertEqual(sorted(meta), ["alg", "key_id", "sig_version", "target_sha256", "value"], "key_id is a digest prefix; no keyring, validity window or revocation field")


if __name__ == "__main__":
    unittest.main(verbosity=2)
