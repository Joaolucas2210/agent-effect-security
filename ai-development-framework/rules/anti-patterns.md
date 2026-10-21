# Anti-patterns (reject on sight)

## Over-engineering (Ponytail)
- Interface with one implementation; factory for one product; config for a constant.
- Speculative flexibility / "we might need it later". YAGNI.
- New dependency for what stdlib or an existing dep does in a few lines.
- Scaffolding/boilerplate "for later".
- Clever over boring — anything someone decodes at 3am.

## Token waste
- Re-reading whole files the graph already indexes.
- Dumping raw command output instead of RTK-compressed output.
- Pasting large logs/files into context "for reference".

## Review malpractice
- Approving on a line-by-line skim instead of metrics.
- Padding line coverage while mutants survive.
- Ignoring dependency cycles / rising complexity.

## Discipline failures
- Production code with no failing test first.
- Swallowed exceptions; missing validation at trust boundaries.
- Simplifying away security/validation/accessibility (never allowed).
