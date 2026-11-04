# INC-03: Supabase MCP SQL exfiltration through support tickets

- **Date / source:** 2025-07 · General Analysis
- **Threat:** THR-03 · **Legs:** 1, 2, 3 · **OWASP:** ASI02
- **Status:** out_of_scope · **Eval:** —

## Vector

A customer writes SQL-shaped instructions in a support ticket. A developer's Cursor session, using the
Supabase MCP with a service-role key, reads the ticket and dutifully selects `integration_tokens` into a
public table.

## Lesson

"Private data" is not only files: a database read through an MCP tool is leg 1. Read-only mode on the
MCP server would have stopped the write-back but not the read.

## ADF

`read` in ADF v1 is filesystem only; the PDP already has `repository` and `network` scope kinds but no
operation uses them. Entering this case needs a design partner demand (IMPLEMENTATION_PLAN registered demand)
and an ADR for a mediated SQL/HTTP read — explicitly not planned now.
