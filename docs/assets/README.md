# Assets

**English** · [Português (Brasil)](README.pt-BR.md)

The [brand guidelines](../brand/BRAND_GUIDELINES.md) document the SVG system, contrast, diagram semantics and
the social preview. `python3 docs/assets/brand/make-social-preview.py` regenerates the 1280 × 640 PNG with Pillow
and an installed DejaVu Sans font. A maintainer must upload that PNG in GitHub Settings → General → Social preview;
the committed file alone does not change link previews.

| File | What it shows | How it is made |
| --- | --- | --- |
| `adf-demo.gif` | Real ADF commands on a synthetic fixture: enable a project, create the evidence key, a Claude-style `Read` payload for `README.md` allowed with a signed bundle, a `Read` payload for `.env` denied by the PDP with a bundle, `adf verify … --key` passing offline, `adf projects reasons`. ~12 s, ~400 KiB, 1048×410. | `python3 docs/assets/make-demo-gif.py` |

## Regenerating the GIF

`make-demo-gif.py` runs the **real** `adf` CLI and the **real** `PreToolUse` hook with synthetic payloads against a throwaway repository and
an isolated `ADF_HOME`, captures their output, and renders terminal frames with Pillow. Nothing in the GIF is typed
by hand. This is a hook contract demo, not a recorded Claude Code client session. Two substitutions keep it readable: the temporary repository is shown as `~/dev/my-app` and the temporary
`ADF_HOME` as `~/.adf`; the bundle path in the `adf verify` line is elided to its first eight hex digits.

```bash
make install-dev                      # the script calls .venv/bin/adf
python3 -m pip install Pillow         # on the Python that runs the script (system Python is fine)
python3 docs/assets/make-demo-gif.py  # rewrites docs/assets/adf-demo.gif; exits 1 above 3 MiB
```

Regenerate it whenever a line it shows changes (reason codes, `adf verify` output, `project-reasons` format);
the bundle ids differ on every run, which is expected.

## Live recording (alternative)

For a recording of an interactive terminal instead of rendered frames, with `asciinema` and `agg` installed:

```bash
asciinema rec docs/assets/adf-demo.cast --cols 92 --rows 17 --idle-time-limit 1.5
#   then, by hand, the same six steps the script runs (enable, key init, two hook reads, verify, reasons)
agg --cols 92 --rows 17 --font-size 16 --speed 1.2 docs/assets/adf-demo.cast docs/assets/adf-demo.gif
```

Keep the same six steps and the same path substitutions so both methods show the same thing. Never record a
real repository or a real `~/.adf`: evidence paths and project ids are host-specific.
