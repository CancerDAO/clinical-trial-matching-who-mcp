# 远程测试人员全流程提示词指南

## 测试人员需要准备

1. 克隆并安装本仓库的5个skills。
2. 在本地环境变量中配置 `WHO_MCP_URL`、`WHO_MCP_API_KEY` 和传输方式。
3. 将本次测试所需的真实患者病历放入一个独立文件夹。不要把患者文件提交到Git。
4. 在VS Code中打开仓库，并让Claude Code/Codex只能读取该患者文件夹和本仓库。

测试人员不需要提前编写 `patient.json` 或 `search-plan.json`。模型应根据病历完成结构化，但必须把所有推断和缺失信息明确标记。

## 可直接粘贴的测试提示词

```text
请使用当前仓库 clinical-trial-matching-who-mcp 对我提供的真实患者病历执行正式全流程临床试验匹配。

患者病历唯一来源：
<在这里填写患者病历文件夹的绝对路径>

强制要求：
1. 只读取上述患者病历文件夹，不读取仓库中其他患者、历史报告或示例病例。
2. 根据病历生成结构化 patient.json 和完整八维 search-plan.json。不能把推测写成已知事实；缺失信息标记为 unknown。
3. 正式流程只能使用：
   skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py
4. 从 prepare 开始，使用远程 Streamable HTTP MCP。API Key只能从环境变量读取，不能写入文件、命令参数、日志或报告。
5. 禁止设置 prefilter-limit 或 analysis-limit，禁止自行选择Top-N，禁止只分析“高相关”子集。
6. prepare后，逐批完成analysis_jobs.json中的全部trial-gater任务。每个召回试验必须满足：
   召回ID集合 = 硬规则排除ID集合 ∪ gater完成ID集合
7. 只有全部gater批次完成后，才能运行run_formal_pipeline.py deep-jobs。
8. 对全部match/conditional试验完成risk、efficacy和development evidence分析。必须满足：
   match/conditional ID集合 = risk完成集合 = efficacy完成集合 = evidence完成集合
9. 完成decision-synthesizer后，只能运行run_formal_pipeline.py merge和finalize。
10. 禁止手写gating_results.json、analysis_bundle.json、pipeline.json或HTML报告。
11. 正式患者报告只能是full_pipeline.py finalize间接生成的final/report.html。
12. 如果只生成validation-report.html，说明流程不完整。不要把它改名为report.html，也不要宣称全流程完成；继续补齐状态文件指出的缺失项。
13. 每完成一个阶段都运行：
    python skills/clinical-trial-matching-who-mcp/scripts/pipeline/run_formal_pipeline.py status --run-dir <运行目录>
14. 最终向我报告：
    - 数据库水位线
    - 召回数
    - 硬规则排除数
    - gater完成数
    - match/conditional数
    - risk/efficacy/evidence完成数
    - 遗漏数
    - formal_report_ready
    - report.html的绝对路径
15. 只有formal_report_ready=true且遗漏数为0时，才能说正式全流程完成。

开始前先简要复述病历数据范围、患者国家/地区、报告语言和运行目录，然后直接执行，不要自行缩小范围。
```

## 预期目录

```text
run/
  formal-run-state.json
  prepared.json
  analysis_jobs.json
  gater-batches/
  deep_jobs.json
  deep-batches/
  decision_report.json
  analysis_bundle.json
  final/
    pipeline.json
    run-manifest.json
    report.html
```

如果质量门失败，`final/`中只会出现 `validation-report.html`，不会出现正式患者模板。
