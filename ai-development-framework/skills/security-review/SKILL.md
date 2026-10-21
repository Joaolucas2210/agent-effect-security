---
name: security-review
description: Full security sweep of pending changes — taint tracing via the graph, authz, secrets, deps. Controls are never simplified away. Use for /security-review.
---

# Security Review

> **Archetype:** Maintainer — controls are never simplified away.

Ponytail is suspended here. Minimalism = less attack surface, never fewer controls.

## Steps
1. **Trace taint via graph.** `/graphify query "flow from <untrusted source> to <sink>"`.
2. **Check each sink:** SQL, shell, HTML/DOM, filesystem path, deserialization, template.
3. **Authz:** every new endpoint/action default-deny and gated.
4. **Secrets:** none in code/logs/errors; sourced from a manager.
5. **Dependencies:** new ones scanned for CVEs and maintenance status.
6. **Crypto:** vetted libs, correct modes, no home-rolled.

## Example
```
/graphify query "flow from req.query to db.execute"
→ handlers/report.ts: req.query.id → raw SQL  ❌ injection
FIX: parameterized query / ORM binding
```

## Quality gates (block on any)
- [ ] Every taint path mitigated
- [ ] Every new action authz-gated
- [ ] No secrets leaked
- [ ] No unsafe deserialization/eval on untrusted data
- [ ] New deps CVE-clean

## Integration
security-reviewer agent · Graphify (taint) · RTK (scanner output). Complements, never
overridden by, Ponytail.
