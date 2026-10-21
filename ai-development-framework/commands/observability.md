---
description: Record or inspect structured archetype hand-offs, trajectory, and token health.
---

# /observability

For a hand-off, record the current archetype, token input/output, remaining sub-budget,
duration, and dynamic-switch trigger with `make observability-record`. At task completion run
`make observability-complete`; it writes the structured event and trajectory. Use `make metrics`
for the concise health summary. Never estimate a provider cost or expose task content as telemetry.
