# Clinical Trial Matching Skill: WHO MCP

通用多癌种临床试验匹配编排器。项目保留原 trial-gater、风险标注、疗效语境和决策综合子技能，只替换 WHO MCP 检索、跨注册库核验、机制展示和报告边界。

## 技能结构与安装

本仓库采用 `skills/<name>/SKILL.md` 的扁平多技能结构，符合 `vercel-labs/skills` 的默认发现规则。仓库包含 5 个可独立发现的技能：

- `clinical-trial-matching-who-mcp`：检索、核验、编排与报告生成；
- `trial-gater`：逐条入排标准判断；
- `trial-risk-annotator`：患者与癌种相关的风险分析；
- `trial-efficacy-contextualizer`：疗效与论文证据语境；
- `decision-synthesizer`：全局决策综合。

克隆仓库后可用官方 CLI 检查或选择安装：

    npx skills add . --list
    npx skills add . --skill clinical-trial-matching-who-mcp

主编排技能会引用其余 4 个同级子技能；需要运行完整流程时应一并安装全部技能。

## 依赖边界

本仓库不包含患者数据库，也不包含 WHO MCP 数据文件。运行时必须显式提供：

- Python 3.10 或更高版本；
- 一个支持 database_metadata、execute_search_plan 和 get_trial 的 stdio 或 Streamable HTTP MCP 服务；
- 与该服务兼容的 SQLite 临床试验数据库；
- 能按照 analysis_jobs.json 执行四个模型子技能的模型执行器。

仓库不保存 SSH 密码、API 密钥、患者运行结果或数据库文件。公开仓库所需凭证必须通过本地环境变量或 GitHub Actions Secrets 注入，禁止写入命令示例、配置文件或提交历史。

## 最短可运行基线

项目运行和单元测试仅使用 Python 标准库，无需安装第三方包。依赖声明用于明确这一边界：

    python -m pip install -r skills/clinical-trial-matching-who-mcp/requirements.txt
    python scripts/validate_repository.py
    python -m unittest discover -s skills/clinical-trial-matching-who-mcp/tests -p "test*.py" -v

执行真实 MCP 集成或正式 prepare 前选择一种传输：

- 本地 stdio：WHO_MCP_PYTHON、WHO_MCP_SERVER、WHO_MCP_DB；
- 远程 Streamable HTTP：WHO_MCP_TRANSPORT=streamable-http、WHO_MCP_URL、WHO_MCP_API_KEY；
- MCP_REQUEST_TIMEOUT_SECONDS：两种传输共用的单请求超时秒数，默认 60；
- MCP_DETAIL_CONCURRENCY：仅用于 Streamable HTTP 的详情请求并发数，默认 8；
- WHO_PORTAL_DELTA_MAX_AGE_HOURS：门户增量允许的最大数据年龄，默认 24 小时；
- WHO_PORTAL_CLOCK_SKEW_MINUTES：执行机时钟最多允许领先 5 分钟，范围 0–60。


## MCP 配置接口

仓库提供 .env.example，其中只有占位符。复制为 .env 后选择一种模式填写；.env 已被 .gitignore 排除，项目不会自动读取，需要由 shell 导入。

Linux / macOS：

    cp .env.example .env
    set -a
    source .env
    set +a

本地 stdio 模式：

    WHO_MCP_TRANSPORT=stdio
    WHO_MCP_PYTHON=/absolute/path/to/python3
    WHO_MCP_SERVER=/absolute/path/to/server.py
    WHO_MCP_DB=/absolute/path/to/trials.db

远程模式：

    WHO_MCP_TRANSPORT=streamable-http
    WHO_MCP_URL=https://mcp.example.org/mcp
    WHO_MCP_API_KEY=replace-with-a-random-secret

公网 URL 默认必须使用 HTTPS。只有 localhost 可直接使用 HTTP；受信任私网调试可显式设置 WHO_MCP_ALLOW_INSECURE_HTTP=1。API key 只通过 Authorization: Bearer 请求头发送，不进入 URL。

两种模式都必须通过正式状态机入口执行：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py prepare --patient patient.json --plan search-plan.json --portal-delta portal_delta.json --run-dir run

stdio 的显式命令行参数仍可覆盖环境变量。API key 只从环境变量读取，避免出现在进程命令行和 shell 历史中。

GitHub 普通单元测试不需要任何 Secret。要启用远程集成测试，在仓库 Settings → Secrets and variables → Actions 中添加 WHO_MCP_URL 和 WHO_MCP_API_KEY。非 PR 的 push 或手动 workflow 会调用远程 MCP；未配置时该任务明确说明跳过。来自 Fork 的 PR 不运行远程任务，也拿不到 Secrets。


## 正式流程

1. `run_formal_pipeline.py prepare` 调用真实 MCP，执行完整八维搜索、逐条详情读取、核验和去重。
2. 外部模型执行器完成 `analysis_jobs.json` 中的全部 gater 批次。
3. `run_formal_pipeline.py deep-jobs` 验证 gater 集合完整后创建深度分析任务。
4. 外部模型执行器完成全部风险、疗效和论文证据批次，再运行 decision-synthesizer。
5. `run_formal_pipeline.py merge` 验证两个分析阶段的 ID 集合并生成唯一分析包。
6. `run_formal_pipeline.py finalize` 调用 `full_pipeline.py finalize`。只有质量门全部通过才生成 `report.html`。

示例：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py prepare --patient patient.json --plan search-plan.json --mcp-transport streamable-http --portal-delta portal_delta.json --run-dir run

检查批次进度：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py status --run-dir run

合并模型输出后生成报告：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py deep-jobs --run-dir run

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py merge --run-dir run --decision run/decision_report.json --model MODEL_NAME --output-language en

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py finalize --run-dir run

PowerShell 中请使用反引号或单行命令代替上面的反斜杠续行。

不要手写 `gating_results.json`、`analysis_bundle.json` 或患者报告 HTML，不要自行选择 Top-N。绕过状态机的产物不属于本项目的正式报告。

## 正式报告质量门

formal_report_ready 只有在以下三项同时成立时才为 true：

- 所有预筛候选均完成四个规范模型子技能，且不存在仅因模型预算上限而遗漏的候选；
- MCP 全局和每个查询分支均未截断；
- WHO 门户增量已按完全相同的 database_as_of 水位线执行。

`budget_omitted_count > 0` 或任一集合等式不成立时，不生成正式患者模板。系统只输出醒目的 `validation-report.html`，其中不包含患者试验卡片。

WHO 门户的注册日期增量不能发现所有“旧记录后续修改”，报告会保留这一数据源限制。增量新鲜度在 prepare 时验证并固化，不会因报告文件保存超过 24 小时而失效；窗口可用 WHO_PORTAL_DELTA_MAX_AGE_HOURS 配置。执行时间不得早于数据库水位线；为容纳轻微主机时钟漂移，仅允许 WHO_PORTAL_CLOCK_SKEW_MINUTES（默认 5 分钟）以内的未来时间。
WHO ICTRP 对部分来源（包括 ClinicalTrials.gov）可能只提供国家列表而没有具名中心。国家列表命中只会归为“国家记录待核实”，不能证明存在正在开放的可及中心；NCT 编号本身也不作为美国地点证据。

## 在 Codex 中运行（无需 OpenAI API）

可以在 Codex 桌面端交互式运行，不要求项目持有 OpenAI API key。Codex必须通过 `run_formal_pipeline.py` 推进状态，读取其中引用的四个SKILL.md并完成所有批次。低成本子集验证命令只放在 [DEVELOPMENT_TESTING.md](DEVELOPMENT_TESTING.md)，不得用于患者正式报告。

HTTP客户端默认对超时、网络错误及502/503/504执行最多4次退避重试。可用 `MCP_TRANSIENT_RETRIES` 和 `MCP_RETRY_BASE_SECONDS` 调整。

## 测试

单元测试不需要外部数据库：

    python -m unittest discover -s skills/clinical-trial-matching-who-mcp/tests -p "test*.py" -v

真实 MCP 集成测试任选一种配置：

- stdio：WHO_MCP_PYTHON、WHO_MCP_SERVER、WHO_MCP_DB；
- HTTP：WHO_MCP_TRANSPORT=streamable-http、WHO_MCP_URL、WHO_MCP_API_KEY。


未设置时该项测试会明确跳过。

## 隐私与发布

production-runs、test-artifacts、数据库和缓存默认被 .gitignore 排除。不要把真实患者 JSON、生成报告、模型批次或数据库上传到公共仓库。examples 中只能保留明确标记的合成患者。

## 确定性重渲染

已有 `pipeline.json` 可使用当前标题、地点、机制、链接和乱码修复规则重新渲染，而不重新执行模型临床分析：

    python skills/clinical-trial-matching-who-mcp/scripts/render/rerender_pipeline.py --pipeline run/pipeline.json --out run/rerendered

该命令保留原 `formal_report_ready` 和临床分析 provenance，不会把 validation 产物提升为正式报告。
