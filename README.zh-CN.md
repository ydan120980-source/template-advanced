# template-advanced

简体中文 | [English](README.md)

**面向 AI 编码 Agent 与 Codex 工作流的确定性、证据驱动工程基线。**

[亮点](#亮点) · [工作原理](#工作原理) · [快速开始](#快速开始) · [完整验证](#完整验证) · [核心工具](#核心工具) · [发布](#发布) · [持续集成](#持续集成) · [仓库工作流](#仓库工作流)

**当前版本：** v2.2.0 · **Python：** 3.11–3.13 · **平台：** Linux、macOS、Windows（Git Bash）· **许可证：** Apache-2.0

## 亮点

| 能力 | 提供什么 |
|---|---|
| 明确的任务授权 | GitHub Task Issue 中冻结的 `governance.task/v2` 合同；只有在 Issue 尚未建立时，才允许使用经过验证且由 owner 明确批准的 local bootstrap。 |
| 证据优先执行 | 有界执行、只追加诊断证据、显式重试、验证结果、独立审查和 Evidence Ledger，避免只凭“已完成”声明判断结果。 |
| Template Doctor | 只读 readiness 审计，覆盖初始化、发布卫生、已提交 Codex 安全默认值、Git baseline、文档漂移、发布清单和可选 CodeGraph 状态。 |
| 精确 SHA 远程门禁 | Governance v2 将 workflow、job、Check Run、仓库和精确 40 位 commit SHA 绑定；缺失、skipped、neutral、partial 或无法访问的证据都不能算成功。 |
| 确定性发布制品 | 发布文件从已提交 `HEAD` 读取，按确定性元数据打包，再由独立 verifier 校验，并在干净解压目录中重新验证。 |
| 跨平台 CI | GitHub Actions 在 Ubuntu、Windows、macOS 上覆盖 Python 3.11、3.12、3.13，并分别处理候选验证、正式发布和安全检查。 |

## 工作原理

`已验证 Task Issue / owner 批准的 bootstrap → 有界执行 → 证据与验证 → Template Doctor → 精确 SHA 远程门禁 → 确定性发布 → 干净解压验证`

GitHub Task Issue 是正常情况下长期有效的规划权威。Issue 尚未建立时，经过独立批准和验证的 `local_bootstrap` 可以临时授权完全一致的冻结合同。Validated cache、planning journal、聊天摘要和 AIWF Run Guard ledger 都只是证据，不能扩大范围、放宽 stop condition，也不能替代远程发布证据。

Governance v2 负责验证授权与远程状态，AIWF Run Guard 记录本地执行诊断，Template Doctor 审计仓库 readiness，发布流水线生成并独立验证可发布制品。详见 [Task Issue Contract](docs/ai-workflow/TASK_ISSUE_CONTRACT.md)、[Remote Gates](docs/ai-workflow/REMOTE_GATES.md) 和 [架构说明](docs/architecture/README.md)。

## 适用 / 不适用

### 适合使用

- 你需要 AI Agent 编码 Sprint 具备可审计、证据优先的执行方式，并显式管理范围、重试、审查和验收。
- 你希望仓库从一开始就具备治理、精确 SHA CI 证据和确定性发布能力。
- 你需要一套可复用 Python 基线，同时希望治理和发布工具仅依赖标准库。

### 不适合使用

- 你需要的是带业务功能、UI 组件、数据库抽象或 Web Server 运行时能力的应用框架。
- 项目不会采用 Task Issue / Evidence Ledger 治理模型，额外控制结构只会成为闲置负担。
- 这些治理工具本身必须依赖第三方 Python 包。

## 环境要求

- Python 3.11、3.12 或 3.13。
- Bash；Windows 支持 Git Bash。
- 真实 clone 和 Git baseline 需要 Git。
- 仓库的远程 CI 与发布门禁依赖 GitHub Actions。

工具、测试和发布流水线均不要求安装第三方 Python 包。

## 快速开始

### 验证当前仓库

在仓库根目录执行：

```bash
bash scripts/setup.sh
bash scripts/verify.sh
bash evals/run-evals.sh
```

`setup.sh` 只做环境检查，不安装软件。`verify.sh` 会运行 lint、标准库结构检查和单元测试。eval harness 会执行 8 个确定性 workflow case。

### 作为项目基线使用

这个仓库**当前没有配置为 GitHub Template Repository**（`is_template=false`），因此 GitHub 不提供一键 **Use this template** 流程。

请从你自己控制的干净 fork 或源码副本开始。在进行任何受治理的远程写入之前，
先建立新的仓库身份和 remote，再建立项目自己的 Git baseline 与治理合同。随后按照
[Task Issue Contract](docs/ai-workflow/TASK_ISSUE_CONTRACT.md) 完成初始化，并持续运行
Template Doctor，直到项目自己的 readiness finding 被解决。不要把原仓库的 planning
evidence、authority 或 remote identity 当成新项目的授权依据。

## 平台说明

Linux 和 macOS 使用 `python3`，Windows Git Bash 使用 `py -3`：

```bash
python3 -m unittest discover -s tests        # Linux / macOS
py -3 -m unittest discover -s tests         # Windows (Git Bash)
```

部分 Windows 环境中的 `python` 会解析到 Microsoft Store / App Installer 执行别名，而不是真正的解释器。Windows shell 可能返回退出码 9009；Git Bash 或 MSYS 可能只显示低字节值 49。

这些 Python 工具不依赖 PowerShell 脚本执行。如果本地 Execution Policy 阻止 `.ps1` wrapper，请直接调用模块入口；不要降低计算机或用户级策略，也不要使用 `Bypass`：

```powershell
py -3 -B -m tools.governance_v2 --help
py -3 -B -m tools.aiwf_run_guard --help
py -3 -B -m tools.template_doctor --root . --format json
```

需要从 Windows shell 启动仓库 Bash 脚本时：

```powershell
py -3 -B scripts/invoke-git-bash.py scripts/verify.sh
```

launcher 会选择 Git for Windows Bash，拒绝 System32 / WindowsApps / WSL launcher 路径，保留参数和原生退出码；验证流程也不要求预先设置 `PYTHONDONTWRITEBYTECODE`，测试套件和工具会自行抑制字节码写入。

## 完整验证

从仓库根目录执行以下命令，并逐条检查原生退出码：

```bash
bash scripts/setup.sh
python3 -m unittest discover -s tests
bash scripts/verify.sh
bash evals/run-evals.sh
python3 -B -m tools.template_doctor --root . --format json
python3 -B scripts/ci-doctor-gate.py --root .
python3 -B -m tools.governance_v2 gate static --root .
```

Windows Git Bash 请把 `python3` 替换为 `py -3`。

`verify.sh` 会检查 lint、import / annotation contract 和单元测试；这里的结构检查不等同于完整的语义类型推断。eval harness 覆盖 Run Guard、发布确定性、Doctor 漂移检测和干净模板初始化。

Template Doctor 退出码：

| 退出码 | 含义 |
|---:|---|
| `0` | 审计完成，未发现阻塞 readiness 的问题。 |
| `1` | 审计完成，并发现一个或多个 readiness 问题。 |
| `2` | 调用参数无效或发生运行错误。 |

退出码 `1` 是正常的审计结果，可以代表**任意** readiness finding。更窄的 `scripts/ci-doctor-gate.py` 策略只允许延后的 `git.baseline` failure；其他 failed rule、report error 或运行错误都会阻止 CI gate。

CodeGraph 仍然是可选能力。没有索引时，`codegraph.initialized` 默认报告非阻塞 `skip`；`--strict` 会把缺失索引提升为阻塞失败。已经存在但不可读取、损坏或无法识别的数据库始终阻塞。该检查有意保持为启发式：数据库必须能被 SQLite 读取、通过 `PRAGMA quick_check`，并至少包含一个已识别候选表，例如 `nodes` 或 `edges`；它不能证明与完整或官方 CodeGraph schema 兼容。详见 [CodeGraph](docs/architecture/CODEGRAPH.md)。

已提交的 Codex 配置同样属于 readiness 范围。`config.safe_defaults` 要求 `approval_policy = "on-request"`、`sandbox_mode = "workspace-write"`，并默认关闭 network access。

## 核心工具

### Governance v2

```bash
python3 -B -m tools.governance_v2 --help
python3 -B -m tools.governance_v2 gate static --root .
```

Governance v2 管理冻结的 `governance.task/v2` 合同、local bootstrap 验证与 adoption、Issue 事件链、静态 workflow 检查和精确 SHA GitHub gate。本地命令使用确定性结果码：`0` pass、`1` fail、`2` blocked、`3` cached、`4` not run。远程 Issue 写入仅存在于要求显式 `--confirm-write` 和凭据的命令中，并会通过 readback 验证；gate 路径本身是只读的。详见 [Task Issue Contract](docs/ai-workflow/TASK_ISSUE_CONTRACT.md) 和 [Remote Gates](docs/ai-workflow/REMOTE_GATES.md)。

### AIWF Run Guard

```bash
python3 -B -m tools.aiwf_run_guard --help
python3 -B -m tools.aiwf_run_guard preflight --root . --format json
```

Run Guard 是可选的本地诊断层，用于记录路径、failure、retry lineage、handoff、validation、review、liveness 和 command summary。它不会启动 agent，不会替代 Task Issue，也不能单独证明 GitHub release 合格。PowerShell wrapper `scripts/aiwf-run-guard.ps1` 仍受支持，并按 `py -3`、`python`、`python3` 顺序查找 Python，要求 Python 3.11 或更高版本。详见 [AIWF Run Guard](docs/ai-workflow/AIWF_RUN_GUARD.md)。

### Template Doctor

```bash
python3 -B -m tools.template_doctor --root . --format json
python3 -B -m tools.template_doctor --root . --format markdown
```

Template Doctor 是只读、仅依赖标准库的审计工具。确定性报告会为每项检查输出 rule ID、severity、status、evidence 和 recommendation。相互独立的规则通过有界线程池运行，最多使用 4 个 worker。详见 [Template Doctor](docs/ai-workflow/TEMPLATE_DOCTOR.md)。

## 发布

### 正式构建

```bash
python3 scripts/build-release.py
python3 scripts/verify-release-archive.py \
  --archive dist/template-advanced-2.2.0.zip \
  --manifest dist/template-advanced-2.2.0.manifest.json \
  --require-release-set \
  --validate
```

Windows Git Bash 请把 `python3` 替换为 `py -3`。

builder 使用显式顶层 allowlist，并与 Template Doctor 共享可审计的排除规则。它会记录每个文件的相对路径、大小、SHA-256 和预期 POSIX mode，并生成固定时间戳 ZIP，因此受信任的重复构建可以做到逐字节一致。

在 Git working tree 内，每个 release file 都从已提交 `HEAD` 对应的 Git object database 读取。只要某个发布文件为 untracked、deleted，或与 `HEAD` blob 不一致，就会阻止构建并报告对应路径。Git working tree 之外默认拒绝构建；必须显式使用 `--allow-unverified`，并把结果标记为 `unverified-source-tree`。`--validate` 会把归档解压到干净目录，并在那里执行完整验证套件。

### 源码快照

源码交付使用 Git snapshot：

```bash
git archive --format=zip --output=template-advanced-source.zip HEAD
```

快照只来自已提交 Git tree，因此不会包含 `.git/`、ignored / untracked 本地状态、cache、构建输出和临时文件。它的 ZIP 字节可能随 Git、zlib 或操作系统实现变化；跨平台字节确定性只针对 `scripts/build-release.py` 生成的正式制品。不要发布直接压缩可变 working directory 得到的 ZIP。

### 验证下载后的发布

从 Draft / Published GitHub Release 下载 ZIP、manifest、publication digest、payload digest、provenance、release-set 和 `SHA256SUMS`，然后执行：

```bash
sha256sum -c SHA256SUMS

python3 scripts/verify-release-archive.py \
  --archive template-advanced-2.2.0.zip \
  --manifest template-advanced-2.2.0.manifest.json \
  --require-release-set \
  --validate
```

Windows Git Bash 请把 `python3` 替换为 `py -3`。verifier 会独立检查 release set 和 clean extraction，而不是信任 builder 自身结果。

### 发布制品集合

| 制品 | 用途 |
|---|---|
| `template-advanced-2.2.0.zip` | 确定性 release archive。 |
| `template-advanced-2.2.0.manifest.json` | 文件路径、大小、SHA-256、预期 mode 和 publication digest 元数据。 |
| `template-advanced-2.2.0.digest.txt` | Publication digest。 |
| `template-advanced-2.2.0.payload.digest.txt` | Archive bytes 的 SHA-256。 |
| `template-advanced-2.2.0.provenance.json` | Source 与 companion asset provenance。 |
| `template-advanced-2.2.0.release-set.json` | 非自引用 release-set digest 与 asset summary。 |
| `SHA256SUMS` | 上述 6 个 release asset 的 SHA-256。 |

## 持续集成

| Workflow | 职责 |
|---|---|
| `ci.yml` | 在 Ubuntu、Windows、macOS 上覆盖 Python 3.11、3.12、3.13；执行 setup、unit tests、verify、evals 和 Doctor CI gate。 |
| `release-candidate.yml` | 在 pull request 和 `main` push 上执行只读候选验证：payload review、clean extraction、完整本地验证和定向 workflow 检查。 |
| `release-artifacts.yml` | 基于 clean commit 执行 release integration：双构建、字节比较、完整 clean-extraction validation、archive / release-set verification、checksum，并在 annotated `v*` tag 上附加 Draft Release 制品。 |
| `security.yml` | CodeQL、credential scanning 和 documentation local-path hygiene。 |

GitHub Actions 固定到完整 commit SHA，Dependabot 持续更新这些 pin。macOS 验证由 GitHub Actions 执行，因此只有仓库中实际可见的 workflow result 才能作为该平台证据。

## 仓库工作流

1. 阅读 `AGENTS.md` 并验证当前 GitHub Task Issue；如果 Issue 尚未建立，则验证已明确批准的 local bootstrap。
2. 冻结有界 `governance.task/v2` 合同，包括 goal、allowed / forbidden paths、acceptance、base SHA、budget 和 stop conditions。
3. 只在该授权范围内执行；较长的 Standard / Full 工作才使用隔离 planning journal。
4. 执行定向和必需验证，记录原生退出码和关键证据。
5. 在要求时进行独立审查，并返回 Evidence Ledger。
6. 验收后再把持久状态压缩进 Task Issue event chain；本地 journal 和诊断 ledger 始终是从属证据。

## 安全

请通过仓库的 private vulnerability reporting channel 报告漏洞。支持版本和响应流程详见 [SECURITY.md](SECURITY.md)。不要在公开 Issue 中披露尚未修复的漏洞。

## 贡献

贡献前置条件、工作流、合同变更规则、本地验证和 Evidence Ledger 要求详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 当前限制

- 受信任 release build 要求 clean Git commit。Dirty、untracked、deleted 或本地偏离 `HEAD` 的 release file 会被拒绝；非 Git source tree 必须显式使用 `--allow-unverified`，并标记为 `unverified-source-tree`。
- 单元测试是快速、定向检查。递归发布验证位于 `scripts/integration-test-release.sh`，覆盖确定性双构建、clean extraction、companion metadata 和 corrupt-tree rejection。
- CodeGraph 是可选能力，仓库不提交 index。缺少 index 默认是 `skip`，`--strict` 会使缺失成为阻塞失败；损坏或无效数据库始终阻塞。Doctor 的检查只是健康启发式，不能证明完整 schema 兼容。
- 外部全局 Codex 配置，例如 Hooks、memory 和 MCP server，不受本仓库控制。
- 某些 GitHub 安全功能取决于 repository permission 和 account type；实际状态必须以 repository settings 为准，不能直接假定。

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。归属和附加声明请参阅 [NOTICE](NOTICE)。
