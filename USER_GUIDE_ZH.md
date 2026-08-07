# 临床试验匹配 Skill 完整使用教程

本文面向首次部署和运行 `clinical-trial-matching-who-mcp` 的使用者，覆盖项目认识、Skills 安装、WHO MCP 接入、患者数据准备、模型配置、正式全流程执行、断点恢复、报告审查和常见故障处理。

> 本项目用于临床试验信息匹配与预筛，不构成医疗建议、治疗推荐或入组结论。试验状态、中心、名额和完整入排标准必须由医生及研究中心确认。

## 1. 项目做什么

项目面向多癌种、跨国家/地区患者，将患者结构化信息与 WHO ICTRP 临床试验数据结合，执行以下流程：

```text
患者结构化 / Cancer Buddy 病历包
-> 八维搜索计划
-> WHO ICTRP MCP 数据库检索
-> WHO Portal 水位线后增量（可选且需授权）
-> 详情获取、统一去重、直接注册库实时核验
-> 保守的通用硬规则排除
-> trial-gater 逐试验资格判断
-> risk + efficacy + 论文证据分析
-> decision-synthesizer 决策核实路径
-> 地点和机制分类
-> 正式 HTML 报告
```

项目包含 5 个可独立发现的 sibling Skills：

| Skill | 作用 |
|---|---|
| `clinical-trial-matching-who-mcp` | 主流程：患者输入、检索、核验、编排和报告 |
| `trial-gater` | 逐项比对病种、分子条件和入排标准 |
| `trial-risk-annotator` | 分析患者及癌种特异风险 |
| `trial-efficacy-contextualizer` | 分析疗效背景和论文证据适用性 |
| `decision-synthesizer` | 汇总非排除候选的人工核实路径 |

正式流程分为两个用户命令：

1. `prepare`：完成患者规范化、检索、增量、去重、实时核验、硬规则筛查和任务生成。
2. `execute`：持续完成全部 Gater、Deep、Decision、Merge、Finalize，并生成报告。

用户不需要手工逐批调用子技能，也不应自行截取 Top-N 生成正式报告。

## 2. 运行前准备

### 2.1 必要条件

- Git；
- Python 3.10 或更高版本；
- Node.js 与 `npx`（安装 Skills 时使用）；
- 一个可用的 WHO ICTRP MCP 服务；
- 一种模型执行后端：模型 API、Claude Code/Codex 类 CLI，或自定义 runner；
- 访问 WHO Portal、ClinicalTrials.gov、Europe PMC 等外部数据源的网络权限（启用相应步骤时）。

主项目运行代码仅使用 Python 标准库，不需要安装额外 Python 包。WHO MCP 服务器的依赖由服务器项目单独管理。

检查环境：

```powershell
git --version
python --version
node --version
npx --version
```

macOS/Linux 使用相同命令。若系统命令为 `python3`，请将本文命令中的 `python` 替换为 `python3`。

### 2.2 获取项目

```bash
git clone https://github.com/FCX-28579/clinical-trial-matching-who-mcp.git
cd clinical-trial-matching-who-mcp
```

不要把真实患者文件、API Key、数据库、日志和运行报告提交到 Git。

## 3. 安装 Skills

先查看仓库内可安装的 Skills：

```bash
npx skills add . --list
```

安装全部 5 个 Skills：

```bash
npx skills add . --skill '*'
```

安装完成后，重新打开使用 Skills 的 Agent 会话，或按宿主工具的说明刷新 Skills。安装只负责让 Agent 发现技能说明；正式全流程仍由仓库中的确定性执行器启动。

如只需检查仓库结构是否符合 Skills 规范：

```bash
python scripts/validate_repository.py
```

预期结果为 5 个 Skills 均通过验证。

## 4. 接入 WHO MCP

MCP 提供数据库水位线、八维检索计划执行和试验详情读取。服务端必须提供以下工具：

- `database_metadata`
- `execute_search_plan`
- `get_trial`

凭证必须通过环境变量或 CI Secrets 注入，不要写入 README、患者文件、命令历史或 Git。

### 4.1 远程 Streamable HTTP（推荐）

#### Windows PowerShell

```powershell
$env:WHO_MCP_TRANSPORT = "streamable-http"
$env:WHO_MCP_URL = "https://你的MCP域名/mcp"
$env:WHO_MCP_API_KEY = Read-Host "请输入 WHO MCP API Key"
$env:MCP_REQUEST_TIMEOUT_SECONDS = "60"
$env:MCP_DETAIL_CONCURRENCY = "4"
$env:MCP_TRANSIENT_RETRIES = "4"
$env:MCP_RETRY_BASE_SECONDS = "1"
```

#### macOS/Linux

```bash
export WHO_MCP_TRANSPORT=streamable-http
export WHO_MCP_URL='https://你的MCP域名/mcp'
read -s WHO_MCP_API_KEY && export WHO_MCP_API_KEY
export MCP_REQUEST_TIMEOUT_SECONDS=60
export MCP_DETAIL_CONCURRENCY=4
export MCP_TRANSIENT_RETRIES=4
export MCP_RETRY_BASE_SECONDS=1
```

公网服务应使用 HTTPS。仅在明确知情的本地或受信任测试网络中使用 HTTP：

```powershell
$env:WHO_MCP_ALLOW_INSECURE_HTTP = "1"
```

```bash
export WHO_MCP_ALLOW_INSECURE_HTTP=1
```

HTTP 会以明文传输 API Key 和患者衍生检索条件，不适合正式或公网生产环境。

### 4.2 本地 stdio MCP

当 MCP Server 脚本和 SQLite 数据库位于同一台机器时：

#### Windows PowerShell

```powershell
$env:WHO_MCP_TRANSPORT = "stdio"
$env:WHO_MCP_PYTHON = "C:\absolute\path\to\python.exe"
$env:WHO_MCP_SERVER = "C:\absolute\path\to\server.py"
$env:WHO_MCP_DB = "C:\absolute\path\to\who_trials.db"
```

#### macOS/Linux

```bash
export WHO_MCP_TRANSPORT=stdio
export WHO_MCP_PYTHON=/absolute/path/to/python
export WHO_MCP_SERVER=/absolute/path/to/server.py
export WHO_MCP_DB=/absolute/path/to/who_trials.db
```

`.db` 是数据库文件，不是目录，不能对它执行 `cd`。

### 4.3 MCP 最小验证

建议先运行仓库测试，确认客户端配置和通信基础无误：

```bash
python -m unittest discover \
  -s skills/clinical-trial-matching-who-mcp/tests \
  -p "test_mcp_stdio_integration.py" -v
```

远程服务无凭证返回 `401 Unauthorized` 通常说明 Nginx/服务端鉴权已工作，不代表 MCP 故障。规范 MCP 请求还需要正确的 `Authorization: Bearer ...`、`Accept` 和初始化 JSON-RPC 数据，优先使用项目客户端测试，不要用空 JSON `{}` 判断服务可用性。

## 5. 准备患者输入

`--patient` 支持两类输入。

### 5.1 扁平患者 JSON

可参考：

```text
skills/clinical-trial-matching-who-mcp/examples/
  SYNTHETIC-CN-CRC-KRAS-G12C-patient.json
  SYNTHETIC-US-NSCLC-EGFR-patient.json
  SYNTHETIC-DE-BREAST-HER2-patient.json
```

关键内容应包括：

- 患者 ID；
- 当前国家/地区及城市；
- 癌种、分期和转移部位；
- 分子变异和生物标志物；
- 既往治疗、当前治疗和明确治疗线证据；
- ECOG、器官功能、合并症和用药；
- 是否接受跨地区旅行等匹配上下文。

### 5.2 Cancer Buddy 多文件病历目录

目录可以包含：

```text
patient-directory/
  profile.json
  patient_summary.json
  molecular.json
  treatment_lines.json
  labs.json
  comorbidities.json
  readiness.json
  matching_context.json
```

其中 `patient_summary.json` 是结构化诊断的权威来源，`molecular.json` 提供分子信息。`matching_context.json` 必须明确提供患者当前国家/地区；项目不会根据语言、文件名或医院名称猜测国家。

示例见：

```text
skills/clinical-trial-matching-who-mcp/examples/matching_context.example.json
```

冲突、未知或待确认信息会保留为未知，不会静默推断。治疗事件顺序也不会自动当作明确治疗线数。

### 5.3 搜索计划

未提供 `--plan` 时，程序会从规范化患者数据生成八维基础搜索计划：

1. 病种 + 精确生物标志物；
2. 泛癌种生物标志物；
3. 合理联合靶点；
4. 通路和耐药策略；
5. 已批准或研究中药物；
6. 细胞和生物治疗；
7. 免疫治疗策略；
8. 患者国家及相关区域注册词。

正式计划中的每个查询必须包含生物标志物、机制、药物或治疗模态锚点。项目不会仅凭患者国家过滤第一轮召回。

也可以显式传入审阅后的计划：

```text
--plan /absolute/path/to/search-plan.json
```

## 6. 配置模型执行后端

三种后端执行相同任务并接受相同的覆盖校验，只选择一种即可。

### 6.1 模型 API

#### OpenAI

```powershell
$env:MODEL_EXECUTION_BACKEND = "api"
$env:MODEL_PROVIDER = "openai"
$env:MODEL_NAME = "你的模型ID"
$env:OPENAI_API_KEY = Read-Host "请输入 OpenAI API Key"
```

#### Anthropic

```powershell
$env:MODEL_EXECUTION_BACKEND = "api"
$env:MODEL_PROVIDER = "anthropic"
$env:MODEL_NAME = "你的模型ID"
$env:ANTHROPIC_API_KEY = Read-Host "请输入 Anthropic API Key"
```

#### GLM 或 MiniMax

```powershell
$env:MODEL_EXECUTION_BACKEND = "api"
$env:MODEL_PROVIDER = "glm"  # 或 minimax
$env:MODEL_NAME = "你的模型ID"
$env:GLM_API_KEY = Read-Host "请输入 API Key"  # MiniMax 使用 MINIMAX_API_KEY
```

MiniMax 中国大陆端点可额外设置：

```powershell
$env:MODEL_BASE_URL = "https://api.minimaxi.com/v1"
```

#### 任意 OpenAI-compatible API

```powershell
$env:MODEL_EXECUTION_BACKEND = "api"
$env:MODEL_PROVIDER = "openai-compatible"
$env:MODEL_BASE_URL = "https://provider.example/v1"
$env:MODEL_NAME = "provider-model-id"
$env:MODEL_API_KEY = Read-Host "请输入模型 API Key"
```

该模式要求服务实现 OpenAI `/v1/chat/completions` 请求和响应协议。模型名称不会写死在项目中，可使用供应商支持的任意模型 ID。

macOS/Linux 将 `$env:NAME = "value"` 替换为 `export NAME='value'`。

### 6.2 Claude Code/Codex 类 CLI

```powershell
$env:MODEL_EXECUTION_BACKEND = "cli"
$env:MODEL_AGENT_COMMAND_JSON = '["claude","-p","--output-format","text"]'
$env:MODEL_AGENT_TIMEOUT_SECONDS = "1800"
```

CLI 必须能从标准输入读取完整任务，并在标准输出返回严格 JSON。具体命令取决于本机安装的 Agent CLI。

### 6.3 自定义 runner

```powershell
$env:MODEL_EXECUTION_BACKEND = "custom"
$env:MODEL_BATCH_RUNNER_JSON = '["python","model_runner.py","--input","{input}","--output","{output}"]'
```

runner 必须读取 `{input}` 并把严格 JSON 写入 `{output}`。

### 6.4 推荐的初始吞吐配置

```powershell
$env:MODEL_GATER_BATCH_SIZE = "3"
$env:MODEL_DEEP_BATCH_SIZE = "2"
$env:MODEL_GATER_CONCURRENCY = "3"
$env:MODEL_DEEP_CONCURRENCY = "3"
$env:MODEL_MAX_IN_FLIGHT_REQUESTS = "3"
$env:MODEL_API_TIMEOUT_SECONDS = "600"
$env:MODEL_API_RETRIES = "4"
$env:MODEL_API_RETRY_BASE_SECONDS = "1"
```

先根据供应商限流保守设置，再逐步提高并发。网络错误由 API 层重试；结构、Schema 或 ID 覆盖错误由批处理层恢复，避免无意义的重试乘法。

## 7. 授权外部注册库访问

`prepare` 可访问 WHO Portal、ClinicalTrials.gov、CTIS、ChiCTR 等直接注册来源。查询可能包含患者衍生的癌种、变异或药物信息，因此必须由操作者明确授权：

```powershell
$env:EXTERNAL_REGISTRY_ACCESS_AUTHORIZED = "1"
```

并在命令中加入：

```text
--portal-delta-mode auto --authorize-external-registry-access
```

三种增量模式：

| 模式 | 含义 |
|---|---|
| `auto` | 自动访问 WHO Portal，检索数据库水位线之后的新登记 |
| `file` | 复用已有且仍有效的 `portal_delta.json` |
| `off` | 不进行 WHO Portal 增量检索 |

Portal Delta 只补充数据库水位线后的新登记，不能证明旧试验仍在招募。旧试验状态由直接注册库实时核验处理。

## 8. 执行完整正式流程

建议把运行目录放在仓库外，避免患者资料和结果被误提交。

以下 PowerShell 示例假设：

```powershell
$PROJECT = "D:\path\to\clinical-trial-matching-who-mcp"
$PATIENT = "D:\private\patient.json"
$RUN = "D:\private-runs\patient-001"
Set-Location $PROJECT
```

macOS/Linux 示例路径：

```bash
PROJECT="$HOME/clinical-trial-matching-who-mcp"
PATIENT="$HOME/private/patient.json"
RUN="$HOME/private-runs/patient-001"
cd "$PROJECT"
```

### 8.1 第一步：Prepare

远程 Streamable HTTP MCP：

```powershell
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py `
  prepare `
  --patient $PATIENT `
  --run-dir $RUN `
  --mcp-transport streamable-http `
  --portal-delta-mode auto `
  --authorize-external-registry-access
```

macOS/Linux：

```bash
python3 skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  prepare \
  --patient "$PATIENT" \
  --run-dir "$RUN" \
  --mcp-transport streamable-http \
  --portal-delta-mode auto \
  --authorize-external-registry-access
```

Prepare 完成后应生成规范化患者、检索审计、核验结果、硬排除结果和 `analysis_jobs.json`。此时尚未调用 Gater/Deep 模型分析。

### 8.2 查看状态

```powershell
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py `
  status --run-dir $RUN
```

重点检查：

- 召回数；
- 硬排除数；
- 等待 Gater 数；
- MCP 查询是否截断；
- 直接注册库核验是否完成；
- 当前状态是否为 `gater_pending`。

### 8.3 第二步：Execute

确认模型环境变量已配置后运行：

```powershell
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py `
  execute --run-dir $RUN
```

macOS/Linux：

```bash
python3 skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  execute --run-dir "$RUN"
```

执行器会按状态机连续完成：

```text
全部 Gater
-> 非排除试验论文预取
-> Risk + Efficacy + Evidence Deep 分析
-> Decision
-> Merge
-> Finalize
-> 中国患者叙事翻译（按配置）
-> report.html
```

不要并行启动两个 `execute` 进程操作同一运行目录。执行器使用进程锁防止重复计费和结果互相覆盖。

### 8.4 中断与断点续跑

网络中断、模型超时或终端关闭后，使用同一命令恢复：

```powershell
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py `
  execute --run-dir $RUN
```

有效批次会被复用；无效响应会被隔离。整批结构失败时，执行器可拆成单试验任务恢复，不需要从头重新检索或重新分析已经通过校验的批次。

恢复前可先查看状态：

```powershell
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py `
  status --run-dir $RUN
```

## 9. 中文报告与翻译

报告语言由患者明确的当前国家决定：

- 中国患者：Deep/Decision 直接生成简体中文患者可见叙事，Finalize 只补译残余英文；
- 其他国家患者：直接生成英文报告。

Gater 保持紧凑、语言无关的结构化资格结果。残余翻译模块不重新检索、不改变入排判断，也不修改试验 ID、药物名、生物标志物、数值、引用和 URL。若已生成中文且没有残余英文，即使 `TRANSLATION_MODE=required` 也不需要额外翻译 API。

默认配置：

```powershell
$env:TRANSLATION_MODE = "auto"
```

- `auto`：中国患者有可用模型 API 时翻译；无 API 时记录 `skipped_no_model_api`。
- `required`：中国患者缺少翻译 API 时停止，不生成未翻译的正式交付。
- `off`：关闭后翻译。

翻译模型默认继承 `MODEL_*`。也可以单独使用成本更低、速度更快的模型：

```powershell
$env:TRANSLATION_MODEL_PROVIDER = "openai-compatible"
$env:TRANSLATION_MODEL_BASE_URL = "https://provider.example/v1"
$env:TRANSLATION_MODEL_NAME = "translation-model-id"
$env:TRANSLATION_MODEL_API_KEY = Read-Host "请输入翻译模型 API Key"
$env:TRANSLATION_MODEL_CONCURRENCY = "3"
```

翻译结果和检查点保存在 `report-translations.json`，中断后只继续未完成的唯一文本。

## 10. 运行结果说明

成功完成的正式运行通常包含：

| 文件 | 用途 |
|---|---|
| `report.html` | 患者可见正式报告 |
| `pipeline.json` | 完整结构化流水线结果 |
| `run-manifest.json` | 召回、排除、Gater、Deep、Evidence 和遗漏审计 |
| `analysis_bundle.json` | 经契约校验的子技能分析结果 |
| `portal_delta.json` | WHO 水位线后增量记录（启用时） |
| `report-translations.json` | 中文翻译缓存和审计（适用时） |

正式报告页面按以下地点维度筛选：

- 全部；
- 国内/本国可及；
- 国家记录待核实；
- 境外。

报告再按机制分类展示。地点分类与机制分类独立，资格判定也不会被机制或可行性分数覆盖。

若运行完整性不足，项目只能生成明显标识的 `validation-report.html`，不能生成正式 `report.html`。常见原因包括 ID 集合遗漏、Deep 未覆盖全部非排除试验或使用了验证限额。

## 11. 正式报告人工审查

运行清单只能证明流程覆盖完整，不能证明每项临床判断正确。交付前必须使用：

```text
FINAL_REPORT_REVIEW_CHECKLIST_CONCISE.md
```

重点人工核查：

1. 每个推荐试验的疾病、队列和分子条件是否与患者相符；
2. 排除和 conditional 判断是否正确引用完整入排标准；
3. 招募状态是否已通过直接注册库核实；
4. 国内/本国可及是否有具名中心，国家记录是否被正确标为待核实；
5. 机制分类、患者可见标题和治疗组合是否准确；
6. 论文是否真实、链接有效，并且证据适用于相应药物、队列和癌种；
7. 风险、疗效和决策核实路径是否有实际信息，是否存在过度推荐措辞；
8. 中文报告是否完整翻译且未改变临床事实、数字和引用。

试验卡片应作为医生或研究协调员核实的起点，不应直接作为患者自行决策依据。

## 12. 测试项目

仓库结构验证：

```bash
python scripts/validate_repository.py
```

完整单元测试：

```bash
python -m unittest discover \
  -s skills/clinical-trial-matching-who-mcp/tests \
  -p "test_*.py" -v
```

PowerShell 也可以写成一行：

```powershell
python -m unittest discover -s skills/clinical-trial-matching-who-mcp/tests -p "test_*.py" -v
```

远程 MCP 集成测试只有在配置 `WHO_MCP_URL` 和 `WHO_MCP_API_KEY` 时才运行；其余测试不需要真实凭证。

## 13. 常见问题

### 13.1 `401 Unauthorized`

检查：

- `WHO_MCP_API_KEY` 是否为当前有效 Key；
- Key 是否包含多余空格或换行；
- 服务端 systemd 环境文件和客户端 Key 是否一致；
- Nginx 是否把 `Authorization` 头传给后端。

无 Key 的 `401` 是正常鉴权行为。

### 13.2 `404 Not Found`

确认 URL 路径是否为 `/mcp`。向 MCP 发送空 JSON `{}` 不能作为规范初始化测试，也可能返回 4xx。

### 13.3 Host / DNS-rebinding 错误

这是 MCP SDK 的 Host 校验。服务端需要允许实际公网 Host，或由 Nginx 代理时把上游 Host 设置为服务端允许的值。不要为了绕过校验而关闭所有 Host 防护。

### 13.4 `address already in use`

端口已有服务监听。先查进程，不要重复启动：

```bash
ss -ltnp | grep ':18080'
pgrep -af 'mcp_service/server.py'
```

`kill <PID>` 中的尖括号只是占位符。实际命令应类似 `kill 2409278`。

### 13.5 MCP 查询被截断

查看运行清单中的分页和 truncation 审计。截断属于召回范围警告，不得将结果宣称为数据库全量召回。根据 MCP 分页能力调整服务端查询或检索计划，而不是静默只分析前若干项。

### 13.6 模型返回 JSON 不符合契约

不要手工编辑为成功结果。重新执行同一 `execute` 命令，执行器会重试、隔离无效响应，并在必要时拆成单试验恢复。

### 13.7 Deep 阶段耗时较长

Deep 同时分析风险、疗效和预取论文适用性，通常是主要耗时阶段。可在供应商限流允许范围内提高 `MODEL_DEEP_CONCURRENCY`，或为 Deep 配置更快的 `DEEP_MODEL_*`，但不要跳过非排除候选，也不要降低 ID 覆盖要求。

### 13.8 中国患者报告仍有英文

检查：

- 患者 `country` 是否明确为中国；
- `TRANSLATION_MODE` 是否为 `auto` 或 `required`；
- 翻译 API 是否可用；
- `report-translations.json` 中是否记录 `skipped_no_model_api` 或失败批次。

### 13.9 只有 `validation-report.html`

说明正式完整性条件未满足。运行 `status` 并检查：

- 每个召回 ID 是否已硬排除或完成 Gater；
- 所有 `match/conditional` 是否都有 Risk、Efficacy 和 Evidence；
- 是否存在遗漏、额外或重复 ID；
- 是否曾使用 `analysis-limit` 或 `prefilter-limit`。

正式运行只使用 `run_formal_pipeline.py prepare/execute`，不要使用开发子集命令生成患者报告。

## 14. 推荐的最短正式操作清单

1. 克隆仓库并运行 `npx skills add . --skill '*'`。
2. 配置 `WHO_MCP_TRANSPORT`、`WHO_MCP_URL`、`WHO_MCP_API_KEY`。
3. 配置患者文件，并明确当前国家/地区。
4. 配置一个模型 API 或 CLI 后端。
5. 明确授权外部注册库访问。
6. 运行 `prepare`。
7. 运行 `status`，检查召回、截断和实时核验。
8. 运行 `execute`，中断时用同一命令续跑。
9. 确认生成 `report.html` 和 `run-manifest.json`。
10. 使用正式报告审查清单完成人工复核。

## 15. 进一步文档

- `README.md`：项目概览和最短入口；
- `ARCHITECTURE.md`：模块边界与正式不变量；
- `MODEL_API_EXECUTION.md`：模型供应商、并发、重试与恢复；
- `DEVELOPMENT_TESTING.md`：仅限开发的子集验证；
- `FINAL_REPORT_REVIEW_CHECKLIST_CONCISE.md`：正式报告人工审查；
- `SECURITY.md`：凭证和患者数据安全；
- `NOTICE.md`：第三方数据许可与引用。
