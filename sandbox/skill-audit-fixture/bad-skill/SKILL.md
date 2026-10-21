---
name: wrong-name
description: Intentionally invalid skill used to prove `make skill-audit` fails. Do not use.
---

# Bad Skill (fixture)

Two seeded defects the auditor must catch:
- `name:` is `wrong-name` but the directory is `bad-skill` (name drift).
- References a missing file: `hooks/does-not-exist.sh`.
