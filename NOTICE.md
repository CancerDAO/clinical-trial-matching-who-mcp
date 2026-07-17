# Third-Party Attributions

This repository builds on the following upstream projects. We gratefully
acknowledge their authors.

## NCBI TrialGPT (conceptual lineage only)

- Upstream: https://github.com/ncbi-nlp/TrialGPT
- License: U.S. Government Work / Public Domain
- Scope: earlier versions of this repository vendored NCBI's Python
  package under `repo/trialgpt_matching/`, `repo/trialgpt_ranking/`,
  and `repo/trialgpt_retrieval/keyword_generation.py` plus
  `hybrid_fusion_retrieval.py`. Those modules called Azure OpenAI
  directly and were never invoked by this skill's workflow (Claude
  performs all LLM reasoning in the conversation), so the directories
  and files were removed; the remaining retrieval code (now under
  `repo/retrieval/`) is CancerDAO-original. The 8-dimension keyword
  strategy and criterion-level evaluation pattern are conceptually
  inspired by the NCBI paper.
- Suggested citation if you build on this work:

  > Qiao Jin, Zifeng Wang, Charalampos S. Floudas, Fangyuan Chen, Changlin
  > Gong, Dara Bracken-Clarke, Elisabetta Xue, Yifan Yang, Jimeng Sun,
  > Zhiyong Lu. *Matching Patients to Clinical Trials with Large Language
  > Models.*

## WHO ICTRP and source registries

- Role: clinical-trial records are queried through the separately deployed WHO ICTRP MCP database.
- Registry records retain their original registry identifiers and source URLs. WHO ICTRP and source registries remain authoritative for record content; this repository does not vendor their services or datasets.
- The former direct `chictr-mcp-server` runtime is not used by this parallel WHO MCP build.
## CancerDAO Enhancements

The following additions are contributed by CancerDAO and released under the
MIT license (see `LICENSE`):

- WHO MCP search-plan normalization and source merging (`scripts/retrieval/who_mcp_adapter.py`)
  — pure stdlib, no LLM client, no external Python dependencies.
- Self-contained deterministic HTML report renderer (`scripts/render/html_renderer.py`).
- The `SKILL.md` skill definition: 8-dimension keyword strategy,
  criterion-level chain-of-thought evaluation, hard grading rules (R1–R5),
  three-stage verification pipeline, compliance guardrails, and the Chinese
  clinical workflow.
