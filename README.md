# Clinical Trial Matching with WHO MCP

面向多癌种、跨国家/地区患者的临床试验匹配项目。项目通过 WHO ICTRP MCP
完成数据库检索，并结合 WHO 门户增量、直接注册库核验、资格判断、风险与疗效分析、
论文证据和决策汇总生成患者报告。

本项目仅用于临床试验信息匹配和预筛，不构成医学建议、治疗推荐或入组结论。
试验状态、具体队列、中心、名额和完整入排标准必须由医生及研究中心确认。

## 项目结构

仓库包含五个可以独立发现的 sibling Skills：

- `clinical-trial-matching-who-mcp`：患者输入、检索、核验、编排和报告；
- `trial-gater`：逐试验资格判断；
- `trial-risk-annotator`：患者及癌种特异风险；
- `trial-efficacy-contextualizer`：疗效证据和标准治疗背景；
- `decision-synthesizer`：非排除候选的核实路径汇总。

安装全部 Skills：

```bash
npx skills add . --list
npx skills add . --skill '*'
```

当前流程架构：

```text
患者结构化 / Cancer Buddy 病历包
→ 核心搜索计划（可选扩展到八维）
→ WHO MCP 数据库检索 + WHO 门户增量
→ 统一去重、硬规则、A/B/C 分析优先级
→ 覆盖目标集的直接注册库核验
→ trial-gater（默认仅 Band A）
→ Band A 非排除试验的 risk + efficacy + 论文证据
→ decision-synthesizer
→ 患者版 report.html；完整覆盖时另出临床审核版
```

详细模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 运行要求

- Python 3.10 或更高版本；
- 支持 `database_metadata`、`execute_search_plan`、`get_trial` 的 WHO MCP；
- 一个模型执行后端：模型 API、Claude Code/Codex 类 CLI 或自定义 runner。

项目运行代码和测试仅使用 Python 标准库。WHO MCP 服务管理自己的数据库和依赖。

## 患者输入

`--patient` 支持两种输入：

1. `clinical-trial-matching-patient-v1` 扁平 JSON；
2. Cancer Buddy 多文件病历目录。

Cancer Buddy 目录可以包含 `profile.json`、`patient_summary.json`、`molecular.json`、
`treatment_lines.json`、`labs.json`、`comorbidities.json` 和 `readiness.json`。
患者国家/地区不得从语言或医院名称推断，应在病历数据或 `matching_context.json` 中明确提供。
平台或人工复核确认的匹配关键字段可写入 `matching_context.confirmed_fields`；归一化器只接受
白名单字段，并在输入审计中记录所有覆盖项。
`treatment_lines_completed` 最终是非负整数；平台应优先归一化输入，项目端同时兼容
`2`、`"2"`、`"2线"`、`"已完成2线治疗"` 和明确的英文等价写法。范围、下限或未知值
（例如 `2-3线`、`至少2线`）不会被猜成单一整数。
示例见
[matching_context.example.json](skills/clinical-trial-matching-who-mcp/examples/matching_context.example.json)。

未提供 `--plan` 时，程序会从规范化患者数据生成可审计的核心搜索计划（疾病+生物标志物、泛实体瘤、具名药物、区域注册库词）。联合靶点、通路、细胞治疗和免疫分支仅在 `matching_context.search_terms` 提供或 `SEARCH_EXPANDED_RECALL=1` 时展开。默认 `ANALYSIS_COVERAGE=patient` 只对 Band A（本国可及或正在招募的疾病/分子主命中）做完整模型分析。`--coverage full` 仍对 Band B 做 compact gater，但不做深度疗效/风险分析。
患者可使用任意报告语言描述癌种；项目会保留原始文本用于报告和区域注册库检索，
并在项目端确定性转换为 WHO/ClinicalTrials.gov 使用的英文疾病概念与常见同义词。
癌种、突变/分子状态、机制、治疗类型和已收录的中文药名都会在搜索计划层转换；
`chinese_registry_terms` 只供 ChiCTR 等区域注册库使用，不会传给 WHO MCP 或 WHO Portal。
MCP 调用边界会再次检查每个 `condition`/`term`，只要仍含中文就停止 Prepare 并要求提供
英文别名，保证中文病历不会产生中文 MCP 查询，也不会通过猜测未知药名来扩大召回。
罕见癌种可以通过 `matching_context.search_terms.disease_aliases` 提供英文别名，避免
由平台或 MCP 服务猜测临床语义。若完整 MCP 检索首次返回零项，项目默认重试一次；
可用 `MCP_ZERO_RESULT_RETRIES=0..2` 调整，重试结果写入检索审计。

## 配置 WHO MCP

凭证只能通过环境变量或 CI Secrets 注入，不得写入仓库。

### Streamable HTTP

```bash
export WHO_MCP_TRANSPORT=streamable-http
export WHO_MCP_URL=https://mcp.example.org/mcp
export WHO_MCP_API_KEY=replace-locally
export MCP_REQUEST_TIMEOUT_SECONDS=60
export MCP_DETAIL_CONCURRENCY=4
```

公网 MCP 应使用 HTTPS。只有本机或受信任私网调试可以显式设置：

```bash
export WHO_MCP_ALLOW_INSECURE_HTTP=1
```

### 本地 stdio

```bash
export WHO_MCP_TRANSPORT=stdio
export WHO_MCP_PYTHON=/absolute/path/to/python
export WHO_MCP_SERVER=/absolute/path/to/server.py
export WHO_MCP_DB=/absolute/path/to/trials.db
```

## 正式流程

正式执行只有两个主要入口，不需要模型自行决定是否继续下一批。

### 1. Prepare

`prepare` 完成患者适配、搜索计划、MCP 检索、WHO 增量、去重、直接注册库核验、
通用硬规则和 gater 任务生成。
如果任一检索查询被截断，Prepare 会返回 `retrieval_incomplete`，不得继续产生模型分析费用。

```bash
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  prepare \
  --patient /path/to/patient-or-cancer-buddy-directory \
  --run-dir /path/outside-repository/run \
  --mcp-transport streamable-http
```

WHO 门户检索和直接注册库访问会发送患者衍生查询或试验 ID。获得操作授权后启用：

```bash
export EXTERNAL_REGISTRY_ACCESS_AUTHORIZED=1
```

并在 `prepare` 中使用：

```bash
--portal-delta-mode auto --authorize-external-registry-access
```

复用已经获取且仍有效的增量文件：

```bash
--portal-delta-mode file --portal-delta /path/to/portal_delta.json
```

`--portal-delta-mode off` 不访问 WHO 门户。Portal Delta 使用数据库水位线前默认
48 小时重叠窗口补充新登记记录，并明确区分“完整执行但零新增”和可疑零结果。它仍
不能把登记日期等同于最后更新时间，因此原始注册库实时核验继续承担状态更新检查。

正式 Prepare 在召回与 Gater 之间执行确定性锚点分层：疾病/分子直接匹配进入主
Gater，篮子试验等部分匹配进入次级 Gater，状态未知且缺少患者特异锚点的记录进入
审计延后集合。延后不等于不符合，所有召回 ID 仍出现在运行清单中。

### 2. Execute

`execute` 确定性地连续完成全部 gater、论文预取、deep、decision、merge 和 finalize，
支持并发、重试、无效响应隔离、单试验恢复和断点续跑。

通用 OpenAI-compatible API 示例：

```bash
export MODEL_EXECUTION_BACKEND=api
export MODEL_PROVIDER=openai-compatible
export MODEL_BASE_URL=https://provider.example/v1
export MODEL_NAME=provider-model-id
export MODEL_API_KEY=replace-locally

python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  execute --run-dir /path/outside-repository/run
```

还支持 `openai`、`anthropic`、`glm` 和 `openai-compatible`。不同阶段可以分别设置
`GATER_MODEL_*`、`DEEP_MODEL_*` 和 `DECISION_MODEL_*`。完整配置见
[MODEL_API_EXECUTION.md](MODEL_API_EXECUTION.md)。

查看断点状态：

```bash
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  status --run-dir /path/outside-repository/run
```

可在正式检索前对各阶段模型执行一次低成本预检：

```bash
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  prepare --patient /path/patient.json --run-dir /path/run \
  --model-preflight
```

预检分别验证 Gater、Deep、Decision 和 Translation 当前配置的连通性、JSON
契约与必要的中文输出，并将成功路由写入运行目录的 `model-routing.json`。后续
`execute` 会使用这份固定路由；文件不包含 API Key。该选项会产生每个已配置阶段
一次很小的模型调用，因此默认不隐式启用。

未指定具体模型时，可以从受控候选池自动选择：

```bash
export MODEL_PROVIDER=minimax
export MINIMAX_API_KEY='...'
export MODEL_CANDIDATES='fast-model,strong-model'
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  prepare --patient /path/patient.json --run-dir /path/run \
  --auto-select-models
```

阶段专用的 `GATER_MODEL_CANDIDATES`、`DEEP_MODEL_CANDIDATES`、
`DECISION_MODEL_CANDIDATES` 和 `TRANSLATION_MODEL_CANDIDATES` 优先于通用候选池。
项目为 OpenAI、Anthropic、MiniMax 和 GLM 提供最多两个模型的阶段默认池，按理论
性价比排列；`openai-compatible` 不猜测私有模型名。Prepare 按顺序测试候选，首个
通过立即选用，不再调用后续模型。只有没有内置池和用户候选池时才访问供应商
`/models` 接口，并过滤明显的 embedding、rerank、图像和音频模型。Translation
使用 10 条临床文本执行批量契约与吞吐测试。

当前 MiniMax 默认池为 `MiniMax-M3 → MiniMax-M2.7`。M3 在当前账号的合成结构和
10 条翻译基准中均通过，并显著快于 M2.7；高价 highspeed 型号不进入默认池，仍可由
操作者通过 `*_MODEL_CANDIDATES` 显式加入。内置池带有复核日期，生产环境应定期结合
供应商模型下线和价格变化更新。
`MODEL_SELECTION_MAX_CANDIDATES` 和 `MODEL_SELECTION_MAX_CALLS` 控制
选型费用。该过程只使用合成提示，不发送患者信息。
路由审计同时记录 `estimated_minutes_per_100k_characters`，按配置并发和保守的
70% 并发效率估算；这是容量规划指标，不是临床质量分数或硬门禁。

同一 MiniMax API 下也可以在 Prepare 命令中直接指定阶段模型：

```bash
export MINIMAX_API_KEY='...'
python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py \
  prepare --patient /path/patient.json --run-dir /path/run \
  --model-provider minimax \
  --model-base-url 'https://api.minimaxi.com/v1' \
  --gater-model '<fast-json-model>' \
  --deep-model '<reasoning-model>' \
  --decision-model '<reasoning-model>' \
  --translation-model '<fast-non-reasoning-model>'
```

任一阶段模型参数都会自动触发预检。模型名称以账户实际可用列表为准；项目不把
MiniMax 或其他供应商的具体型号写死在代码中。

正式报告只由 `finalize` 路径生成。运行清单会记录召回、硬排除、gater、deep、risk、
efficacy、evidence 和遗漏数量；存在集合遗漏时不会生成正式模板。

## 中文报告

报告结构、筛选分栏和确定性标签会按患者语言渲染。若模型仍输出英文临床叙事，可以
正式流程根据患者明确的 `country` 自动选择报告语言：中国患者的 Deep 与 Decision
直接生成中文患者可见叙事，`finalize` 只补译残余英文；其他国家患者直接生成英文报告。
补译不重新进行检索、入排判断或临床决策。历史 `pipeline.json` 仍可手工执行后翻译：

```bash
python skills/clinical-trial-matching-who-mcp/scripts/render/report_translation.py \
  --input /path/to/final/pipeline.json \
  --output /path/to/translated-pipeline.json

python skills/clinical-trial-matching-who-mcp/scripts/render/rerender_pipeline.py \
  --pipeline /path/to/translated-pipeline.json \
  --out /path/to/translated-report \
  --report-language zh-CN
```

翻译模块保留试验 ID、药物名、生物标志物、数值、引用和 URL。它不绑定任何厂商
或模型：`TRANSLATION_MODEL_*` 可配置 OpenAI、Anthropic、GLM、MiniMax 或任意
OpenAI-compatible API；未配置时依次继承 `DECISION_MODEL_*`、`DEEP_MODEL_*`、
`GATER_MODEL_*` 或通用 `MODEL_*`。重新渲染属于展示验证产物，会输出
`validation-report.html`，不会伪装成重新完成时效核验的正式报告。

大批量中文报告可按供应商能力将临床分析模型与翻译模型分开配置。翻译器会复用
完全相同的叙事、跳过纯临床 token，并使用占位符保护临床事实；每批结果写入
`report-translations.json` 检查点，中断后只续跑尚未完成的唯一文本。患者网页中的
排除试验仅翻译简明排除依据；完整逐标准审计仍保留在 `pipeline.json`，避免为网页未
展示的重复审计文本付出翻译成本。批次与并发可用
`TRANSLATION_BATCH_MAX_UNITS`、`TRANSLATION_BATCH_MAX_CHARACTERS` 和
`TRANSLATION_MODEL_CONCURRENCY` 调整。中国患者默认采用
`TRANSLATION_MODE=required`，缺少可复用 API 时停止。项目自动读取仓库根目录下被 Git
忽略的 `.env`，可跨终端保存本地配置；API Key 不会写入运行清单或提交到仓库。

## 报告审查

自动清单证明流程覆盖，不证明每项临床判断正确。正式交付前应使用
[FINAL_REPORT_REVIEW_CHECKLIST_CONCISE.md](FINAL_REPORT_REVIEW_CHECKLIST_CONCISE.md)
人工核对试验描述、病种/队列、分子条件、机制分类、地点分类、招募状态、入排判断、
论文和链接。

## 测试与仓库校验

```bash
python scripts/validate_repository.py
python -m unittest discover \
  -s skills/clinical-trial-matching-who-mcp/tests \
  -p "test_*.py" -v
```

远程 MCP 集成测试只在 CI Secrets 中配置 `WHO_MCP_URL` 和 `WHO_MCP_API_KEY` 时运行；
其余测试不需要真实凭证。

## 安全与数据处理

- 不提交 API Key、SSH 密码、`.env`、数据库、患者输入、运行日志或患者报告；
- 运行目录应放在仓库外，`production-runs/`、`run/` 和报告文件已被忽略；
- 直接注册库核验只允许访问配置的 HTTP(S) 注册库域名，并拒绝本地和私网目标；
- 不在公开 issue、CI 日志或 PR 中包含患者信息和凭证。

安全政策见 [SECURITY.md](SECURITY.md)，第三方数据许可与引用见 [NOTICE.md](NOTICE.md)。

## 文档

- [USER_GUIDE_ZH.md](USER_GUIDE_ZH.md)：中文完整安装、MCP 接入与正式运行教程；
- [ARCHITECTURE.md](ARCHITECTURE.md)：当前模块和数据流；
- [MODEL_API_EXECUTION.md](MODEL_API_EXECUTION.md)：模型 API、并发与恢复配置；
- [DEVELOPMENT_TESTING.md](DEVELOPMENT_TESTING.md)：开发与测试约定；
- [FINAL_REPORT_REVIEW_CHECKLIST_CONCISE.md](FINAL_REPORT_REVIEW_CHECKLIST_CONCISE.md)：正式报告人工审查。
