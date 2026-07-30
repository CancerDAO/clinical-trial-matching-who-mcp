# Clinical Trial Matching with WHO MCP

面向多癌种患者的临床试验匹配流程。项目保留独立的
`trial-gater`、`trial-risk-annotator`、`trial-efficacy-contextualizer`
和 `decision-synthesizer` Skill，并使用 WHO ICTRP MCP 完成数据库检索、
详情核验、去重和数据水位线审计。

本项目用于信息匹配和预筛，不构成医学建议或入组结论。试验状态、中心、
名额和完整入排标准必须由医生和研究中心确认。

## Skill 结构

仓库包含五个可独立发现的 sibling skills：

- `clinical-trial-matching-who-mcp`
- `trial-gater`
- `trial-risk-annotator`
- `trial-efficacy-contextualizer`
- `decision-synthesizer`

完整流程必须安装全部 Skill：

```bash
npx skills add . --list
npx skills add . --skill '*'
```

## 运行条件

- Python 3.10 或更高版本；
- 支持 `database_metadata`、`execute_search_plan` 和 `get_trial` 的 WHO MCP；
- stdio 使用本地 MCP 脚本和 SQLite，或使用 Streamable HTTP MCP；
- Claude Code/Codex 类 CLI、受支持的模型 API，或自定义批处理 runner。

项目运行代码只使用 Python 标准库：

```bash
python scripts/validate_repository.py
python -m unittest discover \
  -s skills/clinical-trial-matching-who-mcp/tests \
  -p "test_*.py" -v
```

## 配置 MCP

凭证只能通过环境变量或 CI Secrets 注入，不要写入仓库。

远程 Streamable HTTP：

```bash
export WHO_MCP_TRANSPORT=streamable-http
export WHO_MCP_URL=https://mcp.example.org/mcp
export WHO_MCP_API_KEY=replace-me
export MCP_REQUEST_TIMEOUT_SECONDS=60
export MCP_DETAIL_CONCURRENCY=4
```

本地 stdio：

```bash
export WHO_MCP_TRANSPORT=stdio
export WHO_MCP_PYTHON=/absolute/path/to/python
export WHO_MCP_SERVER=/absolute/path/to/server.py
export WHO_MCP_DB=/absolute/path/to/trials.db
```

公网 MCP 必须使用 HTTPS。只有本机或受信任私网调试才能显式设置
`WHO_MCP_ALLOW_INSECURE_HTTP=1`。

## 患者输入

`--patient` 支持：

- 旧版扁平 `patient.json`；
- Cancer Buddy 的患者目录。

Cancer Buddy 目录应包含 `profile.json`、`patient_summary.json`、
`molecular.json`、`treatment_lines.json`、`labs.json` 和
`comorbidities.json`。患者国家不能从语言或医院名称推断，应通过
`matching_context.json` 明确提供。示例见：

[matching_context.example.json](skills/clinical-trial-matching-who-mcp/examples/matching_context.example.json)

未提供 `--plan` 时，程序会从规范化患者数据生成覆盖八个维度的基础搜索计划。

## 正式流程

正式流程只有两个用户入口：

1. `prepare`：执行确定性患者适配、八维 MCP 检索、详情读取、去重、
   实时状态核验、规则化硬排除和任务生成。
2. `execute`：确定性执行全部 gater、deep、论文证据、decision、merge
   和 finalize 阶段，支持重试、隔离无效响应、断点恢复和精确 ID 覆盖。

不要把手工生成的分析 JSON 当作正式结果。

### 1. Prepare

```bash
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  prepare \
  --patient /path/to/patient-or-cancer-buddy-directory \
  --run-dir /path/outside/repository/run \
  --mcp-transport streamable-http
```

WHO 门户访问默认关闭。只有获得相应访问授权时才能显式启用：

```bash
export EXTERNAL_REGISTRY_ACCESS_AUTHORIZED=1
--portal-delta-mode auto
```

该变量同时授权将已召回的试验 ID 发送到白名单内的主要注册库进行实时
状态核验。也可在单次 `prepare` 中使用
`--authorize-external-registry-access`。这项设置记录项目操作人员的授权，
不会绕过 Codex、CI、操作系统或网络平台自身的安全审批。

使用已捕获且可审计的增量：

```bash
--portal-delta-mode file --portal-delta /path/to/portal_delta.json
```

`off` 模式不会访问门户，但如果数据库快照和实时注册库核验满足要求，
仍可依据数据库时效性取得正式数据门资格。

### 2. Execute

模型 API 示例：

```bash
export MODEL_EXECUTION_BACKEND=api
export MODEL_PROVIDER=minimax
export MODEL_NAME=MiniMax-M2.7
export MINIMAX_API_KEY=replace-me

python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  execute --run-dir /path/outside/repository/run
```

支持 `openai`、`anthropic`、`minimax`、`glm` 和
`openai-compatible`。详细配置见 [MODEL_API_EXECUTION.md](MODEL_API_EXECUTION.md)。

查看状态：

```bash
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  status --run-dir /path/outside/repository/run
```

## 正式报告条件

只有以下条件全部成立才生成 `report.html`：

- 召回结果非空，每条记录具有唯一有效 ID；
- 查询未截断，分页和 query audit 完整；
- 每个召回 ID 都进入硬排除或 gater 结果集合；
- 所有 match/conditional ID 都完成 risk、efficacy 和 evidence；
- 没有预算遗漏；
- Portal Delta 或数据库快照处于允许时效范围；
- 每条召回均尝试直接注册库核验，且 unknown/error 比例不超过阈值。

未通过时只生成 `validation-report.html`。

## 安全与数据处理

- WHO 门户 crawler 默认关闭；
- 直接注册库核验只允许 HTTP(S) 注册库白名单，并拒绝本地和私网地址；
- 报告链接只允许 HTTP(S)；
- `run/`、患者输入、runner inputs、数据库和报告均被 `.gitignore` 排除；
- 推荐把运行目录放在仓库外；
- 不要在公开 issue、CI 日志或 PR 中包含患者信息和 API key。

完整政策见 [SECURITY.md](SECURITY.md)。第三方数据许可和引用见
[NOTICE.md](NOTICE.md)。

## 进一步文档

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [MODEL_API_EXECUTION.md](MODEL_API_EXECUTION.md)
- [DEVELOPMENT_TESTING.md](DEVELOPMENT_TESTING.md)
