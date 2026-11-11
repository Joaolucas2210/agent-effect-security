"""R-13 / ARCH-05: the Community package builds as sdist + wheel and runs from a non-editable install.

Offline and outside the repository: the package sources are copied to a temporary directory (TMPDIR), built there
through setuptools' PEP 517 backend (no `build`, no network), and the wheel is installed with `pip --no-index --no-deps`
into a throwaway venv. Runtime dependencies are borrowed read-only from ADF_CONTRACTS_PYTHON through a `.pth` added
after the install, so pip never sees them. The repo, the project .venv, ~/.adf and pins are never touched.

Missing tooling (no Python with setuptools>=64, no venv/ensurepip, no jsonschema) prints SKIPPED and exits 77 (a reported skip), never a
pass line; ADF_PACKAGING_REQUIRED=1 turns a skip into a failure. ADF_PACKAGING_FIND_LINKS=<dir> lets a host provide a
local setuptools wheel for the build venv. ADF_PACKAGING_BUILD_PYTHON picks the build interpreter explicitly.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("tools", "runtime", "integration")
NAME, DIST = "adf-control-plane", "adf_control_plane"
WHEEL_FILE = re.compile(r"(tools|runtime|integration)/([A-Za-z0-9_]+\.py|v[12]/[A-Za-z0-9_./-]+\.json)\Z")
SDIST_EXTRA = re.compile(r"(PKG-INFO|pyproject\.toml|setup\.cfg|README\.md|MANIFEST\.in|LICENSE|adf_control_plane\.egg-info/[A-Za-z_]+\.txt|adf_control_plane\.egg-info/PKG-INFO)\Z")
JUNK = re.compile(r"(__pycache__|\.pyc\Z|(^|/)\.env|\.key\Z|(^|/)test_[^/]*\.py\Z|(^|/)\.venv/|/evidence/|\.egg-info/.*\.py)")
SMOKE = r"""
import json, subprocess, sys
from pathlib import Path
import integration, jsonschema
from integration.local_read_adapter import LocalReadAdapter, schemas
venv, base = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
assert Path(integration.__file__).resolve().is_relative_to(venv), integration.__file__
loaded = schemas()
assert len(loaded) >= 14 and all(isinstance(value, dict) for value in loaded.values())
repo = base / "proj"; repo.mkdir(); (repo / "README.md").write_text("public"); (repo / ".env").write_text("TOKEN=not-a-real-secret")
for args in (["init", "-q"], ["config", "user.email", "p@example.invalid"], ["config", "user.name", "p"], ["add", "-f", "."], ["commit", "-qm", "f"]):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
(base / "ws").mkdir()
adapter = LocalReadAdapter(repo, "HEAD", base / "evidence", base / "ws")  # no host policy: the reference demo
allowed, denied = adapter.read("run-pkg", "README.md", 64), adapter.read("run-pkg", ".env", 64)
print(json.dumps({"allowed": allowed["outcome"], "denied": denied["outcome"], "denied_reason": denied["reason_code"], "bundle": allowed["bundle_path"]}))
"""


class Skip(Exception):
    pass


def run(cmd, **kwargs):
    return subprocess.run([str(part) for part in cmd], capture_output=True, text=True, timeout=300, **kwargs)


def check(proc, what):
    if proc.returncode != 0:
        raise AssertionError(f"{what} failed (exit {proc.returncode}): {proc.stderr.strip()[-800:]}")
    return proc


def setuptools_ok(python):
    probe = "import setuptools as s; v = tuple(int(p) for p in s.__version__.split('.')[:2]); import importlib.util as u; raise SystemExit(0 if v >= (70, 1) or (v >= (64, 0) and u.find_spec('wheel')) else 1)"
    return run([python, "-c", probe]).returncode == 0


def build_python(scratch):
    """An interpreter whose setuptools can build a wheel, or a throwaway venv that gets one offline."""
    explicit = os.environ.get("ADF_PACKAGING_BUILD_PYTHON")
    names = [explicit] if explicit else [os.environ.get("ADF_CONTRACTS_PYTHON"), sys.executable] + [shutil.which(n) for n in ("python3", "python3.13", "python3.12", "python3.11", "python3.10")]
    seen = []
    for name in names:
        if name and Path(name).exists() and os.path.realpath(name) not in seen:
            seen.append(os.path.realpath(name))
    for python in seen:
        if setuptools_ok(python):
            return python, f"interpreter {python}"
    links = os.environ.get("ADF_PACKAGING_FIND_LINKS")
    for index, python in enumerate(seen):
        venv = scratch / f"build-venv-{index}"
        if run([python, "-m", "venv", venv]).returncode != 0:
            continue
        candidate = venv / "bin/python"
        if not setuptools_ok(candidate) and links:
            run([candidate, "-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--find-links", links, "setuptools>=64", "wheel"])
        if setuptools_ok(candidate):
            return candidate, f"venv from {python}"
    raise Skip("no Python with setuptools>=64 (or a venv that bundles it) offline; set ADF_PACKAGING_BUILD_PYTHON or ADF_PACKAGING_FIND_LINKS")


def copy_sources(dest):
    """Only what the backend reads, plus planted junk the archives must not carry."""
    for name in ("pyproject.toml", "README.md", "MANIFEST.in", "LICENSE"):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, dest / name)
    for package in PACKAGES:
        shutil.copytree(ROOT / package, dest / package, ignore=shutil.ignore_patterns("*.egg-info", "build", "dist"))
    (dest / "integration/.env").write_text("TOKEN=not-a-real-secret")
    (dest / "integration/evidence.key").write_text("not-a-real-key")
    (dest / "tools/__pycache__").mkdir(exist_ok=True)
    (dest / "tools/__pycache__/planted.cpython-310.pyc").write_bytes(b"junk")


def build(python, source, out):
    backend = "import sys; from setuptools import build_meta as b; print(getattr(b, sys.argv[1])(sys.argv[2]))"
    sdist = out / check(run([python, "-c", backend, "build_sdist", out], cwd=source), "build_sdist").stdout.strip().splitlines()[-1]
    with tarfile.open(sdist) as archive:
        archive.extractall(out / "unpacked")  # wheel from the sdist: proves the sdist is complete
    unpacked = out / "unpacked" / sdist.name[: -len(".tar.gz")]
    wheel = out / check(run([python, "-c", backend, "build_wheel", out], cwd=unpacked), "build_wheel").stdout.strip().splitlines()[-1]
    return sdist, wheel


def expected_version():
    version_file = ROOT / "VERSION" if (ROOT / "VERSION").is_file() else ROOT.parent / "VERSION"
    return version_file.read_text(encoding="utf-8").strip()


def check_metadata(wheel):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        info = f"{DIST}-{expected_version()}.dist-info"
        metadata = archive.read(f"{info}/METADATA").decode()
        entry_points = archive.read(f"{info}/entry_points.txt").decode()
    fields = [line.split(": ", 1) for line in metadata.split("\n\n", 1)[0].splitlines() if ": " in line]
    get = lambda key: [value for name, value in fields if name == key]
    assert get("Name") == [NAME], get("Name")
    assert get("Version") == [expected_version()], (get("Version"), expected_version())
    assert "MIT" in get("License") + get("License-Expression"), "license MIT"
    assert get("Requires-Python") == [">=3.10"], get("Requires-Python")
    requires = get("Requires-Dist")
    assert "jsonschema==4.26.0" in requires, requires
    assert [r for r in requires if "extra ==" not in r] == ["jsonschema==4.26.0"], f"unexpected runtime deps: {requires}"
    assert sorted(get("Provides-Extra")) == ["codex", "mcp"], get("Provides-Extra")
    scripts = re.search(r"\[console_scripts\]\n(.*?)(\n\[|\Z)", entry_points, re.S).group(1).split()
    assert scripts == ["adf", "=", "integration.cli:main"], f"only the adf console script (ADR 0025): {scripts}"
    return names


def check_contents(sdist, wheel_names):
    source_json = {str(p.relative_to(ROOT)) for package in PACKAGES for p in (ROOT / package).glob("v[12]/**/*.json")}
    source_py = {str(p.relative_to(ROOT)) for package in PACKAGES for p in (ROOT / package).glob("*.py")}
    files = {name for name in wheel_names if not name.startswith(f"{DIST}-")}
    missing = (source_json | source_py) - files
    assert not missing, f"wheel lacks package files: {sorted(missing)[:5]}"
    stray = [name for name in files if not WHEEL_FILE.match(name)]
    assert not stray, f"wheel carries unexpected files: {stray[:5]}"
    with tarfile.open(sdist) as archive:
        sdist_names = [m.name.split("/", 1)[1] for m in archive.getmembers() if m.isfile()]
    stray = [name for name in sdist_names if not (WHEEL_FILE.match(name) or SDIST_EXTRA.match(name))]
    assert not stray, f"sdist carries unexpected files: {stray[:5]}"
    junk = [name for name in sdist_names + wheel_names if JUNK.search(name)]
    assert not junk, f"junk in the archives: {junk[:5]}"
    for runtime_data in ("tools/v1/examples/tool-profile/valid/read-worktree.json", "runtime/v1/policies/sensitive-path-policy-v2.json", "integration/v1/schemas/evidence-bundle.schema.json", "integration/v2/schemas/attempt-timing.schema.json"):
        assert runtime_data in files, runtime_data
    return len(files)


def install_and_smoke(wheel, scratch):
    contracts = os.environ.get("ADF_CONTRACTS_PYTHON") or "python3"
    probe = run([contracts, "-c", "import os, jsonschema; print(os.path.dirname(os.path.dirname(jsonschema.__file__)))"])
    if probe.returncode != 0:
        raise Skip(f"jsonschema not importable from {contracts} (make install-dev)")
    deps = probe.stdout.strip()
    venv = scratch / "run-venv"
    if run([contracts, "-m", "venv", venv]).returncode != 0:
        raise Skip(f"`{contracts} -m venv` unavailable (Debian/Ubuntu: apt install python3-venv)")
    python, adf = venv / "bin/python", venv / "bin/adf"
    home, work = scratch / "home", scratch / "work"
    (home / ".adf").mkdir(parents=True); work.mkdir()
    env = {"PATH": f"{venv / 'bin'}:{os.environ.get('PATH', '/usr/bin:/bin')}", "HOME": str(home), "ADF_HOME": str(home / ".adf"), "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1"}
    check(run([python, "-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--no-deps", "-q", wheel], env=env, cwd=work), "pip install wheel")
    assert adf.is_file(), "console script adf not installed"
    purelib = run([python, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"], env=env).stdout.strip()
    pth = Path(purelib) / "zz-adf-packaging-test-deps.pth"
    pth.write_text(deps + "\n")  # after pip: deps borrowed read-only, never installed
    try:
        assert check(run([adf, "version"], env=env, cwd=work), "adf version").stdout.strip() == expected_version()
        smoke = json.loads(check(run([python, "-c", SMOKE, venv, scratch], env=env, cwd=work), "import/schema/demo-policy smoke").stdout)
        assert smoke["allowed"] == "delivered", smoke
        assert smoke["denied"] != "delivered" and smoke["denied_reason"], smoke
        verified = check(run([adf, "verify", smoke["bundle"]], env=env, cwd=work), "adf verify")
        assert verified.stdout.startswith("verified  evidence_bundle"), verified.stdout
        listed = run([adf, "projects", "list"], env=env, cwd=work)  # Phase 2C: the project list is a package module
        assert (listed.returncode, listed.stdout, listed.stderr) == (0, "", ""), (listed.returncode, listed.stderr)
        proc = run([adf, "policy", "build", "--run-id", "r", "--allow", "README.md", "--out", scratch / "p.json"], env=env, cwd=work)
        assert proc.returncode == 2 and "make install-dev" in proc.stderr, (proc.returncode, proc.stderr)  # the pack builder stays clone-only
        assert not any((home / ".adf").iterdir()), "the smoke wrote into ADF_HOME"
    finally:
        pth.unlink()
    check(run([python, "-m", "pip", "uninstall", "--disable-pip-version-check", "-y", "-q", NAME], env=env, cwd=work), "pip uninstall")
    assert not adf.exists(), "adf still present after uninstall"
    assert run([python, "-c", "import integration.cli"], env=env, cwd=work).returncode != 0, "integration importable after uninstall"
    return smoke


def main():
    required = os.environ.get("ADF_PACKAGING_REQUIRED") == "1"
    with tempfile.TemporaryDirectory(prefix="adf-packaging-") as temp:
        scratch = Path(temp).resolve()
        try:
            python, origin = build_python(scratch)
            source, out = scratch / "src", scratch / "dist"
            source.mkdir(); out.mkdir()
            copy_sources(source)
            sdist, wheel = build(python, source, out)
            count = check_contents(sdist, check_metadata(wheel))
            smoke = install_and_smoke(wheel, scratch)
        except Skip as reason:
            print(f"SKIPPED packaging-wheel: {reason}")
            return 1 if required else 77  # 77: skipped, reported as a skip by the gates, never green
        except AssertionError as failure:
            print(f"✗ packaging-wheel: {failure}")
            return 1
    print(f"✓ packaging-wheel: sdist + wheel built offline ({origin}); metadata {NAME} {expected_version()} MIT; {count} package files, no junk; "
          f"non-editable install: adf version, schemas, demo policy (allowed={smoke['allowed']}, sensitive={smoke['denied_reason']}), adf verify, adf projects; policy build exits 2 (clone-only); uninstall removes adf (hook decisions: test-hook-wheel-equivalence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
