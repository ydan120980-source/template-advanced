# 高效率低成本运行指南

这份指南用于把 AI Coding Workflow 从“完整方法论”压缩成日常可执行的低成本操作流。

目标：默认轻量、必要升级、每轮有证据、不让流程本身吞掉效率。

## 1. 默认运行策略

建议把日常任务按这个比例管理：

| 占比 | Workflow Mode | 使用场景 | 核心要求 |
| --- | --- | --- | --- |
| 80% | Lite | 小修、文档统一、命名修正、局部测试修复、轻量 closeout | 短任务包 + focused validation + compact Evidence Ledger |
| 15% | Standard | 多文件一致性、已有模式复用、局部 hardening、中等功能切片 | Scorecard + 明确 Allowed Paths + full Evidence Ledger |
| 5% | Full | 新主轴、新 contract / public entrypoint、边界敏感变更、状态迁移 | 完整 control-state loop + reviewer / Meta Reviewer 判断 |

判断原则：优先选择能安全完成任务的最轻模式。不要因为模板存在，就每轮都跑完整流程。

## 2. 固定入口

真实项目里建议固定使用一个执行入口：

```text
GitHub Task Issue + validated offline cache
```

任务 Issue 是长期规划权威；离线缓存只保存可审计证据，不能扩大范围或放宽停止条件。Codex 每轮只执行当前已验证的合同，这样可以避免上下文散落在聊天记录里。

最小文件组合：

```text
.aiwf/cache/<task-id>/
  <verified-contract>.json
  events/
```

推荐完整组合：

```text
.aiwf/cache/<task-id>/
  contract.json
  events/
  evidence-ledger.md
.aiwf/runs/<run-id>/
  local diagnostics
```

## 3. 规划端提示词（可选：Web GPT 等规划助手）

规划是可选角色：可以直接在 GitHub 上维护 Task Issue，也可以使用 Web GPT 等规划助手辅助。无论使用哪种方式，规划端都不能成为第二个规划权威——一切规划结论都要落到 Task Issue 的合同与事件链上。

每轮开始时，把下面这段给规划助手：

```text
你是本项目的规划助手（cloud planner）。

请读取：
- 当前 GitHub Task Issue 及其治理 v2 合同
- 必要时读取已验证的 `.aiwf/cache/<task-id>/` 证据
- 读取任务指定的架构和验证文档

你的任务：
1. 判断当前最高价值的 bounded sprint。
2. 选择 Workflow Mode：Lite / Standard / Full，优先选择能安全完成任务的最轻模式。
3. 如果 Outcome Impact + Project Value < 7，不要生成实现任务，改为 closeout / context fill / switch axis。
4. 如果 Verification Confidence <= 2，生成 preflight / read-only probe，不要生成实现任务。
5. 如果 Boundary Risk >= 4，缩小范围或升级为 Full + reviewer。
6. 生成一份可直接交给执行端（Codex）的有界 Task Packet；所有规划变更经治理 CLI 写回 Task Issue，不要创建第二个规划权威。

任务包必须包含：
- Goal
- Why This Sprint
- Workflow Mode
- Required Reading
- Allowed Paths
- Forbidden Paths
- Budget
- Validation Commands
- Stop Conditions
- Required Return Format
```

## 4. Codex 执行提示词

每轮交给 Codex 时使用：

```text
Read AGENTS.md and the current GitHub Task Issue.

Execute only the task packet.
Respect Workflow Mode, Allowed Paths, Forbidden Paths, Budget, and Stop Conditions.

For Lite:
- read only required task files;
- make the smallest coherent change;
- run focused validation;
- return compact Evidence Ledger;
- do not update state files unless explicitly asked.

For Standard / Full:
- read the control-state files explicitly listed in the task packet;
- run the requested validation;
- return full Evidence Ledger;
- propose state updates only when needed.

If the task needs broader scope, extra files, dependency changes, architecture decisions, or more validation than declared, stop and report escalation instead of silently expanding.
```

## 5. Lite 任务包最小模板

日常小任务优先用这个模板，不要复制完整大模板。任务包是任务 Issue 的本地执行镜像，放在 `.planning/<task-id>/` 下，不能扩大 Issue 范围或放宽停止条件：

```text
# Lite Task Packet (mirror of the verified GitHub Task Issue)

Task ID:
Task Size: Small
Workflow Mode: Lite

## Goal
<one sentence>

## Why This Sprint
<why this is the highest-value small step>

## Required Reading
- AGENTS.md
- <specific file>

## Allowed Paths
- <path>

## Forbidden Paths
- everything outside Allowed Paths

## Budget
- Maximum files changed: 1-3
- Maximum commands run: 1-3
- Maximum retries: 1

## Validation Commands
- <focused command or static check>

## Stop Conditions
- required file missing
- task needs files outside Allowed Paths
- validation cannot run
- diff exceeds Lite budget
- shared contract / public interface change is required

## Required Return Format
Evidence Ledger
- Goal:
- Files changed:
- Commands run:
- Validation result:
- Scope check:
- Follow-up:
```

## 6. Standard 任务包最小模板

中等任务使用，同样只作为任务 Issue 的本地执行镜像：

```text
# Standard Task Packet (mirror of the verified GitHub Task Issue)

Task ID:
Task Size: Medium
Workflow Mode: Standard

## Goal
<one bounded sprint>

## Scorecard Summary
- Outcome Impact:
- Project Value:
- Verification Confidence:
- Boundary Risk:
- Reversibility:
- Context Completeness:
- Reviewer Worthiness:
- Decision:

## Required Reading
- AGENTS.md
- the verified Task Issue contract and any task-specific cache
- <task-specific files>

## Allowed Paths
- <paths>

## Forbidden Paths
- <paths / surfaces>

## Budget
- Maximum files changed:
- Maximum commands run:
- Maximum retries:

## Validation Commands
- Focused:
- Adjacent:

## Stop Conditions
- scope crosses declared boundary
- public interface / frozen contract change is needed
- validation setup contradicts task assumptions
- reviewer becomes necessary

## Required Return Format
Full Evidence Ledger with files changed, commands run, validation result, risks, follow-up, and state update recommendation.
```

## 7. 升级规则

| 发现的问题 | 不要做什么 | 应该做什么 |
| --- | --- | --- |
| Lite 需要改 Allowed Paths 外文件 | 静默扩大 diff | 停止，升级 Standard |
| 缺关键上下文 | 猜测实现 | context fill |
| 验证命令跑不了 | 声称理论可行 | 记录 Verification Failure |
| 触碰 public interface / frozen contract | 顺手改接口 | Full + reviewer |
| Outcome Impact + Project Value < 7 | 开实现 sprint | closeout / switch axis |
| 同一主轴收益变低 | 继续深挖 | Context Compression + NEXT_AXIS |

## 8. Evidence Ledger 压缩策略

Lite 只写 compact ledger：

```text
Evidence Ledger
- Goal:
- Files changed:
- Commands run:
- Validation result:
- Scope check:
- Follow-up:
```

Standard / Full 再写完整 ledger。完整模板见 `EVIDENCE_LEDGER_TEMPLATE.md`。

原则：Evidence Ledger 必须足够让下一轮接手，但不能把小任务变成文书工作。

## 9. 每周维护动作

如果项目连续运行多轮，建议每周或每 5-8 个 sprint 做一次维护：

1. 核对任务 Issue 事件链：保持事实完整，不补写空话。
2. 把已接受的稳定结论压缩进后续 Issue 合同或验证过的离线缓存。
3. 标记已封板区域为 `BUGFIX_ONLY`。
4. 归档过期的本地任务包与规划日志，保持 `.planning/` 只含活跃证据。
5. 检查默认验证命令是否仍然有效。
6. 判断当前主轴是否应该 closeout 或 switch axis。

## 10. 成本控制硬规则

- 不为小任务打开 Full。
- 不把 Web GPT 用作长时间实现器。
- 不让 Codex 在任务包外自由探索。
- 不让 helper 模型做最终验收。
- 不接受没有验证命令或明确原因的完成声明。
- 不把所有 sprint 结果都塞进单个 Issue 事件。

最有效的实践是：规划端只通过治理 CLI 更新 GitHub Task Issue（经确认写入），执行端只执行当前已验证的合同，Evidence Ledger 只记录本轮事实；三个角色可以由不同工具承担，也可以按需合并，但不得产生第二个规划权威。
