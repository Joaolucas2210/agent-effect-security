<!-- Evidence over claims. Fill the table; "n/a" is a valid answer for what this repo can't measure yet. -->

## Summary

<!-- What changed and why. -->

## Evidence

| Signal          | Result | How measured                                  |
| --------------- | ------ | --------------------------------------------- |
| Tests / gates   |        | `make quality` (verdict + gate count, or "no gates" for stackless repos) |
| Graph freshness |        | `make graph-check` (fresh / stale)            |
| Token cost      |        | `make rtk-report` → `docs/metrics/rtk-report.txt` (or n/a if no RTK) |
| Metrics row     |        | `make metrics-snapshot` appended a row to `docs/metrics/history.csv`? |

> Small / stackless projects: `n/a` is honest — don't invent numbers. `make quality`
> reporting "no gates evaluated" is a valid, non-green result, not a failure to hide.

## Risks / follow-ups

<!-- Known risks, what stayed out of scope, and anything a reviewer should watch. -->
