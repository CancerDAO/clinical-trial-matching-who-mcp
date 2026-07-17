# Repository Guidance

- Treat `clinical-trial-matching-skill-who-mcp` as a parallel project. Never modify the original sibling project from this repository.
- Preserve patient location fields and keep retrieval global; apply country only when labeling domestic/international access.
- Always call MCP metadata before search and carry `database_as_of` through the report.
- Keep eligibility verdict, mechanism category, and feasibility score independent.
- Use MCP `get_trial` details before eligibility gating.
- Never store SSH passwords or clinical credentials in project files.
- Run unit tests and skill validation after changes.
