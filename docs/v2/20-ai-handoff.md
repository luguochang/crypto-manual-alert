# V2 AI 接手与继续实施手册

> 适用对象：在新电脑、新 Codex 线程或其他 AI 编程环境中继续维护 `crypto-manual-alert-v2` 的工程代理。
>
> 当前结论：V2 是当前分支中功能最完整的实现，但仍为 `PARTIAL`，`Production Ready: NO`。接手代理不得把本地 development、fixture、mock、in-memory 或 skip 证据描述成生产通过。

## 1. 先锁定代码基线

仓库：

    https://github.com/luguochang/crypto-manual-alert

唯一当前开发分支：

    codex/v2-production-completion

当前完整代码 checkpoint：

    6739f817c648c233944c86c99ae1d9cfa9fb0b37

新环境首先执行：

    git fetch --all --prune
    git switch codex/v2-production-completion
    git pull --ff-only origin codex/v2-production-completion
    git rev-parse HEAD
    git merge-base --is-ancestor 6739f81 HEAD && echo "V2 implementation baseline present"

不要从 `main`、`codex/v2-final-20260713`、`codex/v2-architecture-design` 或 V1 备份分支继续开发。它们是旧基线、设计包或归档，不是当前产品版本。

## 2. 必读文档顺序

接手代理必须先阅读以下文档，再决定实现方式：

1. `docs/v2/README.md`
   - 文档分类、normative 与 informative 边界、官方框架约束和入口索引。
2. `docs/v2/13-v2-final-rebuild-spec.md`
   - V2 最终架构、重构边界、删除边界和不可偏离的产品定义。
3. `docs/v2/14-v2-final-implementation-plan.md`
   - 当前任务顺序、TDD、审查、证据和停止条件。执行顺序以本文件为准。
4. `docs/v2/02-official-framework-constraints.md`
   - LangChain、LangGraph、Deep Agents、LangSmith、Langfuse 的职责边界，以及禁止重复实现的内容。
5. `docs/v2/15-v2-implementation-status.md`
   - 当前状态总账。注意本文旧日期段落是历史审计记录，顶部的当前交接校正才是当前 Git 基线。
6. `docs/v2/18-v2-execution-ledger.md`
   - 按文件末尾向前阅读最新执行记录；不要只看早期章节。
7. `docs/v2/19-windows-docker-development.md`
   - Windows、WSL2、Docker Desktop、环境变量、密钥迁移、启动、迁移、备份和内存治理。
8. 相关 ADR 和 compatibility exception
   - 需要修改 Agent Server、checkpoint、state fork、Deep Agents、观测或部署时，先读 `docs/v2/adr/README.md` 和对应的 `docs/v2/compatibility-exceptions/`。

## 3. 配置和密钥边界

接手代理可以读取并修改配置模板：

    backend/.env.example

真实本机配置只允许存在于：

    backend/.env

`backend/.env` 被 `.gitignore` 忽略，禁止读取后打印，禁止提交，禁止写入交接文档。模型、Tavily、LangSmith、Langfuse、LangGraph license 和通知加密密钥必须由人工从密码管理器或服务控制台迁移；代理只负责检查变量是否存在、是否满足 readiness，不得在日志中输出值。

需要人工配置的主要变量：

    OPENAI_BASE_URL
    OPENAI_API_KEY
    MODEL_NAME
    SEARCH_PROVIDER
    TAVILY_API_KEY
    LANGGRAPH_CLOUD_LICENSE_KEY
    LANGSMITH_API_KEY
    LANGSMITH_TRACING
    LANGSMITH_PROJECT
    LANGFUSE_ENABLED
    LANGFUSE_PUBLIC_KEY
    LANGFUSE_SECRET_KEY
    LANGFUSE_HOST
    NOTIFICATION_CREDENTIAL_KEY
    NOTIFICATION_CREDENTIAL_KEY_VERSION
    NOTIFICATION_CREDENTIAL_DECRYPT_KEYS
    PRODUCT_DATABASE_URL

Compose 会自动生成并保存在 Docker volume 中的运行时密钥包括：

    internal-jwt-private
    internal-jwt-public
    product-inbox-cursor-key

不要把这些私钥复制到文档或 Git。恢复旧数据库时必须同时考虑对应 Docker volumes 和密钥轮换关系。此前在聊天中出现过的第三方凭据，正式使用前应先吊销或轮换。

## 4. 新环境配置顺序

1. 按 `docs/v2/19-windows-docker-development.md` 安装 Windows 11、WSL2 Ubuntu 和 Docker Desktop。
2. 将仓库放在 WSL Linux 文件系统，例如 `~/src/crypto-manual-alert-v2`，不要长期放在 `/mnt/c`。
3. 复制 `backend/.env.example` 为 `backend/.env`，由人工填入真实值。
4. 根据模型能力选择 `SEARCH_PROVIDER`。使用 Tavily 时才填写 `TAVILY_API_KEY`；不能把模型服务密钥当作 Tavily 密钥。
5. 如果启动 durable Docker Agent Server，准备 `LANGGRAPH_CLOUD_LICENSE_KEY` 或具备对应部署权限的 `LANGSMITH_API_KEY`。
6. 为当前环境生成独立的 `NOTIFICATION_CREDENTIAL_KEY`；如果恢复旧通知数据，必须保留旧解密密钥并执行轮换流程。
7. 先运行健康检查和静态测试，再启动完整 Compose，不要在配置未通过 readiness 时直接运行浏览器回归。

## 5. 接手后的第一轮验证

先确认没有读取或提交真实 env：

    git status --short --branch
    git check-ignore -v backend/.env
    git diff --name-only

低成本基线验证：

    cd backend
    uv run ruff check .
    uv run python -m compileall -q src tests
    uv run pytest -q tests/contract/test_product_api.py

    cd ../frontend
    npm run typecheck
    npm run lint
    npm run test:unit
    npm run build

完整本地结构验证：

    cd ..
    uv run pytest -q tests/structure tests/deployment

只有这些检查通过后，才启动 `bash tools/v2/start_integration_stack.sh`。完整 Docker 栈会同时启动 Product PostgreSQL、Agent PostgreSQL、Redis、官方 Agent Server、readiness、Worker 和 Next.js，内存不足时不要重复启动第二套服务。

## 6. 当前主线和生产缺口

当前已经存在并形成较完整本地证据的能力包括：

- Product Task admission、PostgreSQL 持久化和多用户资源边界。
- 官方 LangGraph Graph、Agent Server 协议适配和 Worker 生命周期。
- LangChain `create_agent`、结构化输出、官方 `interrupt()` 和官方 stream 能力。
- Work、Runs、Inbox、Library、Monitor、Settings 和 Artifact 页面。
- OKX/搜索证据、Evidence/Risk gate、Artifact、Decision 和失败状态投影。
- HITL、Inbox 单成员直接审核、批量审核边界、retry、cancel、fork 和刷新重连逻辑。
- Local development Agent Server、PostgreSQL、Playwright、DOM、axe、响应式布局和构建测试证据。

当前仍然开放的生产门禁包括：

- 授权版持久化 Agent Server 的真实 restart/replay、checkpoint recovery 和 state fork 证明。
- Hosted OIDC、HTTPS 和真实多用户身份/权限矩阵。
- LangSmith 和 Langfuse 的真实外部投递、关联、脱敏和 outage 证据。
- 正式通知 provider 回执、失败重试和人工 resend 闭环。
- Memory、Outcome、完整 entitlement/usage 和 webhook worker。
- PostgreSQL PITR、跨环境备份恢复、正式 RTO/RPO 和灾备演练。
- 正式 SLO、压力测试、安全审计、SBOM、发布签名和 release attestation。
- Inbox 新增直接审核路径在真实持久化 Agent Server 上的完整 Playwright 点击回读证明。

## 7. 继续实施顺序

不要一接手就做全仓库重构，也不要先做视觉细节。推荐顺序：

1. 先恢复新环境并跑通现有本地 Product 主流程，确认真实页面能看到 Task、Evidence、Artifact 和失败状态。
2. 优先关闭 Task 8：授权版 Agent Server、checkpoint、restart/replay、state fork 和跨重启 Product Task 绑定。
3. 再关闭外部观测和通知回执，确保同一执行可以通过 correlation ID 在 Product、LangSmith、Langfuse 和通知 Outbox 中追踪。
4. 再做 PITR/DR、OIDC/HTTPS、多用户矩阵、SLO、安全和发布证明。
5. 最后补齐 Inbox 真实持久化点击回归、Memory/Outcome、entitlement/usage/webhook 等剩余产品门禁。

每完成一个切片，必须同时更新：

- 对应实现代码和测试。
- `docs/v2/18-v2-execution-ledger.md` 的最新记录。
- `docs/v2/15-v2-implementation-status.md` 的当前状态或证据引用。
- 测试命令、环境前提、真实/fixture/in-memory/hosted 证据边界。

没有真实运行证据时只能写 `UNPROVEN`、`PARTIAL` 或 `RED`，不能因为单元测试通过就写成生产完成。

## 8. 可直接发送给新 AI 的接手指令

将下面内容作为新环境 AI 的第一条任务说明：

```text
你接手的是 crypto-manual-alert-v2。先不要改代码，也不要读取或打印 backend/.env 的真实值。

1. 从 GitHub 拉取仓库并切到 codex/v2-production-completion。
2. 确认当前分支包含 6739f81，当前远程 HEAD 以仓库实际状态为准。
3. 按顺序阅读 docs/v2/README.md、13-v2-final-rebuild-spec.md、14-v2-final-implementation-plan.md、02-official-framework-constraints.md、15-v2-implementation-status.md、18-v2-execution-ledger.md、19-windows-docker-development.md、20-ai-handoff.md。
4. 先报告：当前分支、代码版本、前后端拓扑、已完成能力、未完成生产门禁、当前环境缺失的变量名和不能声称的证据。
5. 读取 backend/.env.example 的变量名，但不要输出 backend/.env 的任何值。真实密钥由人工配置。
6. 先跑低成本 backend/frontend/root 基线测试，再决定是否启动完整 Docker 栈；注意本机内存，不要重复启动服务。
7. 先跑通当前 Product 主流程，再按本文第 7 节的顺序关闭生产缺口。不要先做无关视觉重构或大范围重写。
8. 必须使用官方 LangChain/LangGraph/Deep Agents/Agent Server/SDK 边界；不要重新实现 checkpoint、interrupt、SSE、stream dedup 或通用 Agent loop。
9. 每次修改都要追加 docs/v2/18-v2-execution-ledger.md，记录命令、结果和 real/fixture/in-memory/hosted 证据边界。
10. 不要把 skip、mock、fixture、development Agent Server 或本地成功描述成生产完成。当前总状态保持 V2 PARTIAL / Production Ready NO，直到全部生产门禁有真实证据。
```
