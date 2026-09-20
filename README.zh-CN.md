# template-advanced

简体中文 | [English](README.md)

`template-advanced` 是一个**零第三方运行时依赖**的 Python 工具集，同时也是一套面向可审计 Codex Sprint 的仓库治理模板。它把可执行的 Task Packet 工作流、两个本地工具以及可复现的发布流水线组合在一起：

- **Template Doctor**：审计从模板复制出来的项目是否已经完成初始化和发布卫生治理。
- **AIWF Run Guard**：记录只追加的执行证据，并对验证、所有权、重试、制品、审查以及跨会话命令预算进行门禁控制。
- **发布流水线**：构建确定性的归档文件和 manifest，并独立验证归档内容、文件模式以及干净解压后的结果。

## 适用场景

- 你希望 AI Agent 编码 Sprint 采用**可审计、证据优先**的工作流，并严格记录范围、重试和审查。
- 你希望项目从一开始就具备可发布能力，并让发布制品能够按字节复现。
- 你希望 Template Doctor 能发现复制项目中的初始化漂移和发布卫生问题。

## 不适用场景

- 把它当作应用框架：本项目提供的是治理工具，而不是业务功能。
- 项目不采用这套工作流：如果项目不使用 Codex Task Packet 或 Evidence Ledger，会保留一部分用不到的结构。
- 运行时必须依赖第三方 Python 包：这些工具按设计仅使用 Python 标准库。

## 环境要求

- Python 3.11、3.12 或 3.13（CI 会实际覆盖这三个版本）。
- Bash；Windows 支持 Git Bash。
- 真实克隆和 Git 基线需要 Git；公开仓库已经启用 GitHub Actions。

工具、测试和发布流水线都不要求安装第三方 Python 包。

## 五分钟快速开始

在仓库根目录执行：

```bash
bash scripts/setup.sh
bash scripts/verify.sh
bash evals/run-evals.sh
```

Windows 可以直接在 Git Bash 中执行相同命令，也可以直接调用 Git Bash 可执行文件；文档里的命令按名称调用 `bash`，因此不依赖 Unix executable bit。Linux 和 macOS 可以原样执行相同命令。

本文档中的 Python 启动方式按平台区分。Linux 和 macOS 使用 `python3`；Windows Git Bash 使用 `py -3`。部分 Windows 环境中的 `python` 可能会解析到 Microsoft Store / App Installer 的执行别名，而不是真正的 Python 解释器，因此命令会在 Python 尚未运行时失败；Windows shell 可能返回退出码 9009，而 Git Bash / MSYS 环境可能只显示其低字节值 49：

```bash
python3 -m unittest discover -s tests        # Linux / macOS
py -3 -m unittest discover -s tests          # Windows (Git Bash)
```

这些 Python 工具在 Windows 上不依赖 PowerShell 脚本执行。如果本地 Execution Policy 阻止 `.ps1` 文件，请直接使用 Python 模块入口；不要降低计算机或用户级策略，也不要使用 `Bypass`：

```powershell
py -3 -B -m tools.aiwf_run_guard --help
py -3 -B -m tools.template_doctor --root . --format json
py -3 -B -m tools.governance_v2 --help
```

如果要从 Windows shell 启动仓库中的 Bash 脚本，可以使用 Python launcher。它会定位 Git for Windows Bash，拒绝 System32 / WindowsApps / WSL launcher 路径，并保留脚本参数和原生退出码：

```powershell
py -3 -B scripts/invoke-git-bash.py scripts/verify.sh
```

验证命令不依赖事先设置 `PYTHONDONTWRITEBYTECODE`：测试套件和工具本身会通过 `-B` 以及内部保护抑制字节码写入。

## 完整验证

从仓库根目录执行所有命令，并记录每条命令的退出码。Linux 和 macOS 使用 `python3`，Windows（Git Bash）使用 `py -3`：

```bash
bash scripts/setup.sh
python3 -m unittest discover -s tests        # Windows: py -3
bash scripts/verify.sh
bash evals/run-evals.sh
python3 -B -m tools.template_doctor --root . --format json    # Windows: py -3
```

`setup.sh` 只检查环境，不安装任何软件。`verify.sh` 会执行 lint、基于标准库的结构检查（导入契约和注解契约，不等同于完整的语义类型推断）以及单元测试套件。eval harness 会运行 8 个确定性案例，覆盖 Run Guard、发布确定性、Doctor 漂移检测和干净模板初始化。

只有在缺少 Git baseline 时，Template Doctor 才会以退出码 `1` 表示这个明确延后的外部状态；CI gate 只允许这一项发现，其他问题都会阻止通过。缺少 CodeGraph 索引属于可选能力，会报告为非阻塞的 `skip`；使用 `--strict` 可以把它提升为阻塞失败。Doctor 的 CodeGraph 检查属于保守启发式：它只确认 SQLite 数据库可读取、`quick_check` 通过，并且至少包含一个已识别的候选表（例如 `nodes` 或 `edges`），并不保证完整 schema 兼容。

项目提交到仓库中的 Codex 配置保持安全默认值：
`approval_policy = "on-request"`、`sandbox_mode = "workspace-write"`，并且除非仓库 owner 明确开启，否则网络访问关闭。Template Doctor 的 `config.safe_defaults` 规则会在已提交配置偏离这些默认值时阻止发布。

## Template Doctor

```bash
python3 -B -m tools.template_doctor --root . --format json
python3 -B -m tools.template_doctor --root . --format markdown
```

Windows Git Bash 请把 `python3` 替换为 `py -3`。报告是确定性的，每一项检查都会输出 rule ID、severity、status、evidence 和 recommendation。相互独立的规则通过有界线程池运行，最多使用 4 个 worker。

退出码：

- `0`：ready，所有阻塞检查都已通过。
- `1`：审计完成，但发现 readiness 问题。
- `2`：调用参数无效或发生运行错误。

CodeGraph 是可选的维护者能力：没有索引时，其 Doctor 规则报告非阻塞 `skip`，CI gate 不需要额外 allowlist 即可通过。如果索引是硬性要求，请使用 `--strict`。详见 [docs/architecture/CODEGRAPH.md](docs/architecture/CODEGRAPH.md)。

## AIWF Run Guard

```bash
python3 -B -m tools.aiwf_run_guard --help
python3 -B -m tools.aiwf_run_guard preflight --root . --format json
```

Windows Git Bash 请把 `python3` 替换为 `py -3`。当 PowerShell 脚本执行受到限制时，直接使用 `py -3 -B -m tools.aiwf_run_guard ...` 是受支持的非 PowerShell 入口。已有的 PowerShell wrapper `scripts/aiwf-run-guard.ps1` 仍然受到支持，并按 `py -3`、`python`、`python3` 的顺序查找 Python，同时要求 Python 3.11 或更高版本。

GitHub Task Issue 是正常情况下长期有效的 Sprint authority；如果 Issue 尚未建立，一个经过单独验证、由 owner 明确批准的 local bootstrap 可以暂时授权精确冻结的合同。Planning journal、cache 和 Run Guard evidence 都不能扩展 authority，也不能放宽 stop condition。详见 [AIWF Run Guard](docs/ai-workflow/AIWF_RUN_GUARD.md)。

## 构建发布制品

```bash
python3 scripts/build-release.py
python3 scripts/verify-release-archive.py \
  --archive dist/template-advanced-2.2.0.zip \
  --manifest dist/template-advanced-2.2.0.manifest.json \
  --require-release-set
```

Windows Git Bash 请把 `python3` 替换为 `py -3`。builder 使用显式的顶层 allowlist，并与 Template Doctor 共享可审计的排除规则；它会为每个文件记录相对路径、大小、SHA-256 和预期 POSIX mode，并生成固定时间戳的 ZIP，因此重复构建可以做到逐字节一致。

在 Git working tree 内，builder 会直接从 HEAD 对应的 Git object database 读取每个发布文件；只要任意 release file 为 untracked、deleted，或者内容与 HEAD 不一致，就会拒绝构建。因此 dirty workspace 不可能泄漏进已发布归档。Git working tree 之外默认拒绝构建，必须显式传入 `--allow-unverified`，并把结果标记为 `unverified-source-tree`。加入 `--validate` 后，工具还会把归档解压到干净目录，并在那里重新执行完整验证套件。

## 构建源码归档

源码交付应当使用 Git 快照，而不是直接压缩可变工作目录：

```bash
git archive --format=zip --output=template-advanced-source.zip HEAD
```

源码归档完全由 `HEAD` 对应的已提交 Git tree 生成，因此不会包含 `.git/`、`.claude/settings.local.json` 这类未跟踪本地状态、构建输出、缓存和临时文件。它的 ZIP 字节表示可能随着 Git、zlib 或操作系统实现不同而变化。项目保证跨平台字节确定性的是 `scripts/build-release.py` 生成的自定义 release artifact，而不是这个便捷的 Git source archive。

不要发布通过直接压缩工作目录得到的 ZIP，因为它可能包含 `.git/`、ignored files、untracked files 和本地工具状态。源码交付使用 `git archive HEAD`，正式发布制品使用 `scripts/build-release.py`。

## 验证下载后的归档

1. 从 Draft / Published GitHub Release 下载 ZIP、manifest、publication digest、payload digest、provenance、release-set 和 `SHA256SUMS`。
2. 验证 checksum：

   ```bash
   sha256sum -c SHA256SUMS
   ```

3. 根据 manifest 验证归档：

   ```bash
   python3 scripts/verify-release-archive.py \
     --archive template-advanced-2.2.0.zip \
     --manifest template-advanced-2.2.0.manifest.json \
     --require-release-set \
     --validate
   ```

   Windows Git Bash 请把 `python3` 替换为 `py -3`。

4. 可选：解压 ZIP，并在解压目录中执行 `bash scripts/setup.sh`、`bash scripts/verify.sh`、`bash evals/run-evals.sh` 和 Template Doctor。

## 发布制品

- `template-advanced-2.2.0.zip` —— 确定性 release archive。
- `template-advanced-2.2.0.manifest.json` —— 每个文件的路径、大小、SHA-256 和 mode，以及 publication digest。
- `template-advanced-2.2.0.digest.txt` —— publication digest。
- `template-advanced-2.2.0.payload.digest.txt` —— archive byte SHA-256。
- `template-advanced-2.2.0.provenance.json` —— source 和 companion asset provenance。
- `template-advanced-2.2.0.release-set.json` —— 非自引用 release-set digest 与 asset summary。
- `SHA256SUMS` —— 上述 6 个 release asset 的 SHA-256。

## 持续集成

公开仓库运行 4 条 workflow：

- `ci.yml` —— Ubuntu、Windows 和 macOS runner，分别覆盖 Python 3.11、3.12 和 3.13；执行 setup、unit tests、verify、evals 和 Doctor CI gate。
- `release-candidate.yml` —— 在 pull request 和 `main` push 上执行只读候选验证，包括 payload review、clean extraction、完整本地验证和定向 workflow 检查。
- `release-artifacts.yml` —— 基于 clean commit 执行 release integration（双构建、字节比较、完整 clean-extraction validation）、archive verification、release-set checksum，并在 annotated `v*` tag 上附加 Draft Release 制品。
- `security.yml` —— 运行 CodeQL、credential scanning 和 documentation local-path hygiene。

这些 workflow 将三类职责分开：仓库治理工具由 `ci.yml` 验证；运行诊断工具（Run Guard、Template Doctor）随工具集一起发布，并由同一 matrix 执行；发布验证由 `release-candidate.yml` 和 `release-artifacts.yml` 负责，同时运行 `security.yml`。GitHub Actions 固定到完整 commit SHA，Dependabot 持续保持其更新。

macOS 验证由 GitHub Actions 执行；只有仓库中实际显示的 workflow 结果才能作为该平台的验证证据。

## 仓库工作流

1. 阅读 `AGENTS.md` 和已经验证的 GitHub Task Issue。
2. 使用项目的 `aiwf-plan-sprint` Skill 规划有界 Sprint，并把合同记录到 Task Issue。
3. 只有较长的 Standard / Full 工作才使用隔离的 planning journal。
4. 在 Task Issue 的边界内执行和验证。
5. 在需要时进行独立审查，并返回 Evidence Ledger。
6. 只把已接受的结果压缩进 Task Issue event chain。

## 安全

请通过仓库的 private vulnerability reporting channel 报告漏洞；支持版本和响应流程详见 [SECURITY.md](SECURITY.md)。不要在公开 Issue 中披露尚未修复的漏洞。

## 贡献

贡献流程、合同变更规则和本地验证要求请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 当前限制

- Release build 要求 Git commit 干净：builder 从 HEAD 的 Git object database 读取 release file，并拒绝 dirty、untracked 或 deleted 的发布文件。非 Git source tree 必须显式使用 `--allow-unverified`，并把归档标记为 `unverified-source-tree`。
- 单元测试套件只运行快速、定向测试；完整发布验证（在干净解压目录中递归执行 setup / verify / evals / doctor）位于 `scripts/integration-test-release.sh`，release CI 会实际执行它。
- CodeGraph 是可选 maintainer capability；仓库不提交索引，并且在当前环境中没有可用工具用于验证真实 indexing。没有索引时，Template Doctor 默认报告 `skip/info`，在 `--strict` 下报告 `fail/error`；已经存在但损坏或无效的数据库始终是阻塞失败。Doctor 的检查属于启发式，并不能证明与完整或官方 CodeGraph schema 兼容。
- 外部全局 Codex 配置（Hooks、memory、MCP server）不受本仓库控制。
- 某些 GitHub 安全功能取决于仓库权限和账号类型；实际状态以 repository settings 为准，不能直接假定已经启用。

## 许可证

本项目根据 Apache License, Version 2.0（“License”）授权；除非遵守该 License，否则不得使用本项目。你可以在以下地址获得 License 副本：

    http://www.apache.org/licenses/LICENSE-2.0

除非适用法律要求或另有书面约定，否则根据 License 分发的软件按“AS IS”基础提供，不附带任何明示或暗示的保证或条件。详见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。
