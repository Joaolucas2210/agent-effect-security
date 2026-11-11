"""Phase 2C (ARCH-09/R-16, ADR 0040 Proposed): equivalence oracle for migrating `otel_export._flush_seconds`
onto `integration/host_config.py`.

The golden table was recorded against the pre-migration reader (`os.environ.get("ADF_OTEL_FLUSH_MS", "300")`)
and must keep passing, unchanged, after the migration. Synthetic env only (os.environ patched, cleared, restored).
"""
import contextlib
import inspect
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import integration.otel_export as otel  # noqa: E402
from integration import control_plane_pins  # noqa: E402
from integration.host_config import from_env, hook_environ  # noqa: E402

ABSENT = object()
# raw ADF_OTEL_FLUSH_MS -> seconds the hook waits for the span thread (recorded on the pre-migration code)
GOLDEN = [
    (ABSENT, 0.3), ("300", 0.3), ("", 0.3),  # absent / default / empty = default
    ("0", 0.0), ("1", 0.001), ("007", 0.007), ("1999", 1.999), ("2000", 2.0),  # overrides
    ("2001", 2.0), ("99999", 2.0), ("9" * 50, 2.0),  # capped
    ("-1", 0.3), ("abc", 0.3), ("1.5", 0.3), (" 7", 0.3), ("7 ", 0.3), ("+5", 0.3), ("3_0", 0.3),  # invalid -> default
    ("0x10", 0.3), ("٣", 0.3), ("７", 0.3), ("1e3", 0.3), ("\t", 0.3),  # non-ASCII digits, hex, exp, whitespace
]
SECRETS = {"ADF_A2A_HS256_SECRET": "ab" * 32, "ADF_OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic%20c2stbGVhaw",
           "ADF_OTEL_EXPORTER_OTLP_ENDPOINT": "https://user:pw-leak@collector.example"}


def env_for(raw):
    return {} if raw is ABSENT else {"ADF_OTEL_FLUSH_MS": raw}


def under(env):
    return mock.patch.dict(os.environ, env, clear=True)


class FakeThread:
    def __init__(self):
        self.timeouts = []

    def join(self, timeout=None):
        self.timeouts.append(timeout)


class FlushEquivalenceTest(unittest.TestCase):
    def test_golden_matrix(self):
        """Same value, same type (float), never raises, for every raw value."""
        for raw, expected in GOLDEN:
            with self.subTest(raw=raw), under(env_for(raw)):
                got = otel._flush_seconds()
                self.assertEqual((type(got), got), (float, expected))
                self.assertEqual(from_env(env_for(raw)).otel.flush_seconds, expected)  # the typed field agrees

    def test_call_site_uses_the_reader(self):
        """emit_local_read(hook=True) joins the span thread with exactly this timeout; hook=False never waits."""
        for raw, expected in GOLDEN:
            for hook in (True, False):
                thread = FakeThread()
                with self.subTest(raw=raw, hook=hook), under(env_for(raw)), mock.patch.object(otel, "emit_span", return_value=thread):
                    otel.emit_local_read("claude_read", {"outcome": "deny", "reason_code": "x", "bundle_id": None}, 0, hook=hook)
                self.assertEqual(thread.timeouts, [expected] if hook else [])

    def test_read_at_call_time_not_import_time(self):
        """No caching: a host that changes the variable between calls sees the new value."""
        with under({"ADF_OTEL_FLUSH_MS": "100"}):
            first = otel._flush_seconds()
            os.environ["ADF_OTEL_FLUSH_MS"] = "900"
            self.assertEqual((first, otel._flush_seconds()), (0.1, 0.9))

    def test_precedence_is_shell_only(self):
        """No hook default and no registered-env fallback exist for this variable: the shell value is the value."""
        self.assertNotIn("ADF_OTEL_FLUSH_MS", control_plane_pins._HOST_ENV)
        self.assertNotIn("ADF_OTEL_FLUSH_MS", hook_environ({}, "/repo", "/ev"))  # the hook never sets it
        self.assertEqual(hook_environ({"ADF_OTEL_FLUSH_MS": ""}, "/repo", "/ev")["ADF_OTEL_FLUSH_MS"], "")  # inherited passes through
        with under({"ADF_OTEL_FLUSH_MS": "50", "ADF_OTEL_ENABLED": "0"}):
            self.assertEqual(otel._flush_seconds(), 0.05)  # independent of the enable switch

    def test_no_output_and_no_secret_leak(self):
        """The reader is silent; neighbouring secrets never reach its result, stdout or stderr."""
        for raw in ("x", "500", ABSENT):
            out, err = io.StringIO(), io.StringIO()
            with under({**SECRETS, **env_for(raw)}), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                value = otel._flush_seconds()
                thread = FakeThread()
                with mock.patch.object(otel, "emit_span", return_value=thread):
                    otel.emit_local_read("claude_read", {"outcome": "deny", "reason_code": "x", "bundle_id": None}, 0, hook=True)
            text = out.getvalue() + err.getvalue() + repr(value)
            for leak in ("ab" * 32, "c2stbGVhaw", "pw-leak"):
                self.assertNotIn(leak, text)
            self.assertEqual(out.getvalue() + err.getvalue(), "")

    def test_explicit_config_is_honoured_when_supported(self):
        """Post-migration contract: `_flush_seconds(cfg)` reads the given config, not os.environ. Before the
        migration the reader takes no argument, and this check is recorded as not applicable (not a skip of
        the equivalence matrix above)."""
        if not inspect.signature(otel._flush_seconds).parameters:
            return
        with under({"ADF_OTEL_FLUSH_MS": "1500"}):
            self.assertEqual(otel._flush_seconds(from_env({"ADF_OTEL_FLUSH_MS": "40"})), 0.04)
            self.assertEqual(otel._flush_seconds(None), 1.5)
            self.assertEqual(otel._flush_seconds(), 1.5)


if __name__ == "__main__":
    unittest.main(verbosity=1)
