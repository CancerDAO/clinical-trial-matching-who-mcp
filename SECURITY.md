# Security and patient-data handling

Report security issues through the repository's private GitHub Security
Advisory form (`Security` -> `Advisories` -> `Report a vulnerability`) or
contact the maintainers privately. Do not open a public issue containing
credentials, patient information, or exploit details.

## Secrets

Provide MCP and model credentials only through environment variables or CI
secrets. Never commit `.env`, API keys, SSH passwords, databases, model runner
inputs, or generated reports.

## Patient data

Run the formal pipeline outside the repository when possible. The default
ignore rules cover `run/`, normalized patient inputs, runner inputs, state
files, and reports, but ignore rules are not a substitute for access control.
Delete run artifacts when the clinical review is complete and follow the
patient-data retention policy of the deploying organization.

Before a commit, inspect:

```text
git status --short
git diff --cached --name-only
```

Do not attach identifiable patient data to public bug reports or CI logs.

## Network access

The WHO portal delta crawler is disabled by default. Enable it only when the
operator has permission to access and process that source. Direct registry
verification permits HTTP(S) access only to allowlisted public registry hosts
and rejects local, private-network, and active-scheme URLs.

Formal runs require `EXTERNAL_REGISTRY_ACCESS_AUTHORIZED=1` or the one-run
`--authorize-external-registry-access` flag before WHO Portal auto queries or
direct primary-registry checks begin. This records operator consent but does
not override host-environment network approvals.

## Clinical scope

Generated reports support information matching and pre-screening only. They
are not medical advice or enrollment decisions. A qualified clinician and the
study centre must confirm current recruitment, available slots, and complete
eligibility.
