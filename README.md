# Clinical Trial Matching Skill: WHO MCP

通用多癌种临床试验匹配编排器。项目保留原 trial-gater、风险标注、疗效语境和决策综合子技能，只替换 WHO MCP 检索、跨注册库核验、机制展示和报告边界。

## 依赖边界

本仓库不包含患者数据库，也不包含 WHO MCP 数据文件。运行时必须显式提供：

- Python 3.10 或更高版本；
<<<<<<< HEAD
- 一个支持 database_metadata、execute_search_plan 和 get_trial 的 stdio 或 Streamable HTTP MCP 服务；
=======
- 一个支持 database_metadata、execute_search_plan 和 get_trial 的 stdio MCP 服务脚本；
>>>>>>> b913ed9 (feat: 添加依赖)
- 与该服务兼容的 SQLite 临床试验数据库；
- 能按照 analysis_jobs.json 执行四个模型子技能的模型执行器。

仓库不保存 SSH 密码、API 密钥、患者运行结果或数据库文件。公开仓库所需凭证必须通过本地环境变量或 GitHub Actions Secrets 注入，禁止写入命令示例、配置文件或提交历史。

## 最短可运行基线

项目运行和单元测试仅使用 Python 标准库，无需安装第三方包。依赖声明用于明确这一边界：

    python -m pip install -r skills/clinical-trial-matching-who-mcp/requirements.txt
    python -m unittest discover -s skills/clinical-trial-matching-who-mcp/tests -p "test*.py" -v

<<<<<<< HEAD
执行真实 MCP 集成或正式 prepare 前选择一种传输：

- 本地 stdio：WHO_MCP_PYTHON、WHO_MCP_SERVER、WHO_MCP_DB；
- 远程 Streamable HTTP：WHO_MCP_TRANSPORT=streamable-http、WHO_MCP_URL、WHO_MCP_API_KEY；
- MCP_REQUEST_TIMEOUT_SECONDS：可选，单个请求超时秒数，默认 60。


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

两种模式执行同一 prepare 命令：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/full_pipeline.py prepare --patient patient.json --plan search-plan.json --portal-delta portal_delta.json --out run

stdio 的显式命令行参数仍可覆盖环境变量。API key 只从环境变量读取，避免出现在进程命令行和 shell 历史中。

GitHub 普通单元测试不需要任何 Secret。要启用远程集成测试，在仓库 Settings → Secrets and variables → Actions 中添加 WHO_MCP_URL 和 WHO_MCP_API_KEY。非 PR 的 push 或手动 workflow 会调用远程 MCP；未配置时该任务明确说明跳过。来自 Fork 的 PR 不运行远程任务，也拿不到 Secrets。
=======
执行真实 MCP 集成或正式 prepare 前设置：

- WHO_MCP_PYTHON：运行 MCP 服务的 Python 可执行文件；
- WHO_MCP_SERVER：WHO MCP stdio 服务脚本路径；
- WHO_MCP_DB：与服务兼容的 SQLite 数据库路径；
- MCP_REQUEST_TIMEOUT_SECONDS：可选，单个 JSON-RPC 请求超时秒数，默认 60。
>>>>>>> b913ed9 (feat: 添加依赖)


## 正式流程

1. prepare 调用真实 MCP，执行完整八维搜索、逐条详情读取、核验和去重，再以状态、检索排名和机制多样性构建可审计模型工作集。
2. 外部模型执行器按 analysis_jobs.json 的批次依次运行 trial-gater、trial-risk-annotator 和 trial-efficacy-contextualizer。
3. 所有批次结束后运行 decision-synthesizer。
4. analysis_batch_manager.py 合并并验证全部模型输出。
5. finalize 通过质量门后生成患者报告。

示例：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/full_pipeline.py prepare       --patient patient.json       --plan search-plan.json       --db /path/to/trials.db       --mcp-python python       --mcp-server /path/to/server.py       --portal-delta portal_delta.json       --out run

检查批次进度：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/analysis_batch_manager.py status       --jobs run/analysis_jobs.json --batch-dir run/batches

合并模型输出后生成报告：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/analysis_batch_manager.py merge       --jobs run/analysis_jobs.json --patient patient.json --batch-dir run/batches       --decision run/decision_report.json --out run/analysis_bundle.json       --model MODEL_NAME --output-language en

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/full_pipeline.py finalize       --prepared run/prepared.json --analysis run/analysis_bundle.json --out run/final

PowerShell 中请使用反引号或单行命令代替上面的反斜杠续行。

## 正式报告质量门

formal_report_ready 只有在以下三项同时成立时才为 true：

- 所有预筛候选均完成四个规范模型子技能，且不存在仅因模型预算上限而遗漏的候选；
- MCP 全局和每个查询分支均未截断；
- WHO 门户增量已按完全相同的 database_as_of 水位线执行。

WHO 门户的注册日期增量不能发现所有“旧记录后续修改”，报告会保留这一数据源限制。增量新鲜度在 prepare 时验证并固化，不会因报告文件保存超过 24 小时而失效；窗口可用 WHO_PORTAL_DELTA_MAX_AGE_HOURS 配置。
WHO ICTRP 对部分来源（包括 ClinicalTrials.gov）可能只提供国家列表而没有具名中心。国家列表命中只会归为“国家记录待核实”，不能证明存在正在开放的可及中心；NCT 编号本身也不作为美国地点证据。

## 在 Codex 中运行（无需 OpenAI API）

可以在 Codex 桌面端交互式运行，不要求项目持有 OpenAI API key。先执行 prepare；Codex 读取 analysis_jobs.json 及其中引用的四个 SKILL.md，按批次生成规范 JSON，再由 analysis_batch_manager.py merge 和 full_pipeline.py finalize 完成报告。

低成本真实验证建议先用：

    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/full_pipeline.py prepare ... --prefilter-limit 12 --analysis-limit 8

prefilter-limit 限制模型工作集，analysis-limit 进一步抽取工程验证子集。只要任一预筛候选因预算被省略，质量门就会把结果标为 validation，不能冒充正式完整报告。正式运行需提高上限直至 budget_omitted_count=0。Codex 交互执行适合开发验证；无人值守 CI 或生产批量处理仍需单独的模型执行器和相应凭证。

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
