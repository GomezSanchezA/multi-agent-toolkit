# Schemas

This directory contains JSON Schemas for structured outputs used by the toolkit.
They are intended to standardize results across agents and runs.

## Available schemas

- `session_report.schema.json`
  - Captures end-of-session summaries (actions, findings, next steps).
- `experiment_result.schema.json`
  - Captures test outputs and metrics.
- `task_status.schema.json`
  - Captures task assignment and status.

If you need a new schema (e.g., conversation transcript or peer review report),
add it here and update this list.
