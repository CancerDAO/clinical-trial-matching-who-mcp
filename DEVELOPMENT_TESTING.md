# Development-only subset validation

This document is only for engineering smoke tests. Outputs from limited runs are
validation artifacts and must never be delivered as patient reports.

```bash
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/full_pipeline.py prepare \
  --patient skills/clinical-trial-matching-who-mcp/examples/SYNTHETIC-CN-CRC-KRAS-G12C-patient.json \
  --plan skills/clinical-trial-matching-who-mcp/examples/SYNTHETIC-CN-CRC-KRAS-G12C-search-plan.json \
  --prefilter-limit 12 \
  --analysis-limit 8 \
  --out test-artifacts/subset-run
```

Any positive `prefilter-limit` or `analysis-limit` causes budget omissions when
the recalled workload exceeds the limit. `full_pipeline.py finalize` then emits
only `validation-report.html`; it never emits `report.html`.

Formal patient runs must use `run_formal_pipeline.py`, which does not expose
either limit.
