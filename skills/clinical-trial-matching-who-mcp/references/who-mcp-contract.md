# WHO MCP contract

## Remote stdio server

Use SSH key authentication or a host alias configured in `~/.ssh/config`; the helper intentionally has no password parameter. It sends the remote launch script over encrypted stdin so database and executable paths do not appear in the local SSH process arguments. Never store host names, user names, passwords, private keys, or private paths in this repository.

    ./scripts/run-who-mcp-over-ssh.ps1 -HostName $env:WHO_MCP_HOST -UserName $env:WHO_MCP_USER -RemoteDatabase $env:WHO_MCP_DB -RemotePython $env:WHO_MCP_PYTHON -RemoteServer $env:WHO_MCP_SERVER
## Required calls

1. `database_metadata {}`: capture `database_as_of`, build time, schema, and index version.
2. `execute_search_plan {search_plan, country: "", max_per_query, total_limit}`: run all original keyword groups against the local FTS index. The matching endpoint enforces `interventional_only=true`; the generic multidimensional tool exposes this as an optional audit parameter.
3. `get_trial {registry_id}`: retrieve canonical registry IDs, locations, interventions, and parsed eligibility criteria for every trial sent to gating.

Use `search_trials_multidimensional` for targeted follow-up queries. Do not replace the full search plan with a single broad query.

## Online delta

Use `database_as_of` as the lower boundary for a WHO portal registration-date search. The portal does not expose a trustworthy general-purpose "record modified after" filter, so label this branch `registration_date_proxy`. It catches newly registered trials but can miss older records modified after the watermark.

## Result provenance

Every merged trial must carry:

- `retrieval_provenance`: `who_mcp_database`, `who_portal_delta`, or both.
- `database_as_of`.
- all known `registry_ids`.
- `patient_country_site_count` after detail enrichment.
- `verification.source = WHO ICTRP MCP get_trial` before gating.

### Portal delta artifact

prepare accepts --portal-delta with this minimum JSON contract:

    {
      "status": "executed",
      "database_as_of": "<exact MCP watermark>",
      "executed_at": "<ISO-8601 timestamp>",
      "source": "WHO ICTRP portal",
      "trials": []
    }

A mismatched watermark, missing execution timestamp, non-executed status, or non-list trials field is a hard error. Execution must not predate the database watermark. A future timestamp is accepted only within `WHO_PORTAL_CLOCK_SKEW_MINUTES` (default 5, allowed range 0–60); this tolerance is written into the audit record. Delta-only rows may remain detail-unverified and must therefore be handled conservatively by trial-gater. Portal status not_executed prevents formal-report readiness.
