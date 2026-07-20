# Windows + Docker Desktop 开发交接

> 文档状态：当前 V2 开发交接说明
>
> 适用范围：crypto-manual-alert-v2 的 Windows 本地开发、真实 PostgreSQL 集成测试和 Docker Desktop 自测
>
> 生产结论：当前 V2 仍是 PARTIAL，Production Ready: NO。本地 Docker 绿色只代表本地证据，不能替代 hosted OIDC、HTTPS、灾备、真实外部观测和正式 SLO 证明。

## 1. 先看结论

Windows 可以支持开发，但推荐使用 Windows 11 + WSL2 Ubuntu + Docker Desktop WSL2 backend。不要把仓库长期放在 /mnt/c 下运行 Python、Node 和 PostgreSQL；将代码放在 WSL 的 Linux 文件系统中，例如 ~/src/crypto-manual-alert-v2，可以明显降低文件监听和磁盘 IO 开销。

当前完整本地拓扑是：

    浏览器
      -> Next.js frontend
      -> Product BFF
      -> LangGraph Agent Server custom /app routes
      -> Product PostgreSQL

    Agent Server
      -> LangGraph PostgreSQL checkpoint/store
      -> Redis queue

    统一 WorkerRuntime
      -> Product command/outbox/projection
      -> Agent Server resume

Docker Compose 中的服务包括：

    product-postgres
    agent-postgres
    langgraph-redis
    migrate
    internal-jwt-keys
    development-bootstrap
    langgraph-api
    langgraph-api-readiness
    command-worker
    frontend

这不是只启动一个前端页面。第一次构建会编译官方 LangGraph Agent Server 镜像，内存和磁盘占用都会明显高于普通 Next.js 项目。

### 1.1 当前唯一交接主线

当前交接和后续开发只使用下面这个远程分支：

    codex/v2-production-completion

当前交接基线：

    commit: 6739f817c648c233944c86c99ae1d9cfa9fb0b37

它包含当前 V2 工作树中已提交的后端、前端、测试、文档和 Windows/Docker 交接内容。这个分支是“当前最新实现”，但 V2 仍然是 `PARTIAL`，不能理解为已经通过全部生产门禁。

仓库中其他分支的定位如下：

| 分支 | 定位 | 是否作为当前开发基线 |
| --- | --- | --- |
| `codex/v2-production-completion` | 当前最新 V2 实现和交接 checkpoint | 是 |
| `main` | 默认分支，停留在较早的 Cockpit/重设计基线 | 否 |
| `codex/v2-final-20260713` | 2026-07-13 的旧 V2 vertical-slice checkpoint | 否，仅历史参考 |
| `codex/v2-architecture-design` | V2 架构设计评审资料 | 否，仅设计参考 |
| `codex/v2-prototype-backup-20260713` | 已审计的 V2 原型归档 | 否，仅回溯 |
| `codex/legacy-v1-backup-20260711` | V1 旧实现备份 | 否，不要用于 V2 开发 |
| `codex/complete-outcome-baselines` | 本地旧基线分支，与当前 `main` 同一旧提交 | 否 |

Windows 迁移时不要切到 `main` 或名字带 `final` 的旧 checkpoint。使用下面的命令确认自己没有落在旧分支：

    git fetch --all --prune
    git switch codex/v2-production-completion
    git pull --ff-only origin codex/v2-production-completion
    git rev-parse --short HEAD

最后一条命令当前应输出：

    6739f81

除非明确要做历史回溯，否则不要在这个工作树上删除旧分支；它们是备份和审计参考，不是并行生产版本。

## 2. Windows 前置条件

建议配置：

| 项目 | 最低 | 推荐 |
| --- | --- | --- |
| Windows | Windows 11 22H2 | 最新稳定版 Windows 11 |
| WSL | WSL2 + Ubuntu 22.04 或更新 | Ubuntu 24.04 |
| 内存 | 8 GB，仅适合轻量开发 | 16 GB 以上 |
| 磁盘 | 30 GB 可用空间 | 60 GB 以上 SSD 空间 |
| Docker Desktop | WSL2 backend | WSL integration 已开启 |
| Python | 3.12 | 由 uv 管理 |
| Node.js | 20+ | 22 LTS |

安装顺序：

1. 在管理员 PowerShell 执行：wsl --install -d Ubuntu-24.04
2. 重启 Windows，第一次打开 Ubuntu 完成 Linux 用户创建。
3. 安装 Docker Desktop，选择 WSL2 backend。
4. Docker Desktop 的 Settings -> Resources -> WSL Integration 中开启 Ubuntu。
5. 在 Ubuntu 中确认：

    docker version
    docker compose version
    git --version
    curl --version

如果这些命令只能在 PowerShell 中运行，说明 Docker Desktop 尚未向 WSL 发行版开放集成。

## 3. 获取代码

在 Ubuntu 终端执行：

    mkdir -p ~/src
    cd ~/src
    git clone https://github.com/luguochang/crypto-manual-alert.git crypto-manual-alert-v2
    cd crypto-manual-alert-v2
    git fetch --all --prune
    git branch -a

V2 当前开发分支是：

    codex/v2-production-completion

切换到它：

    git switch codex/v2-production-completion
    git pull --ff-only origin codex/v2-production-completion

如果远程默认分支以后已经包含 V2，则以远程最新分支说明为准，不要在 Windows 端凭名称猜测分支。

## 4. 配置文件与密钥边界

### 4.1 配置文件位置

复制模板：

    cp backend/.env.example backend/.env
    chmod 600 backend/.env

backend/.env 只用于本机，不提交、不上传、不粘贴到 issue 或聊天窗口。仓库已经忽略：

    .env
    .env.*
    *.pem
    *.key
    *.p12
    *.pfx

backend/.env.example 只放空值和示例值。真实密钥应使用环境变量、Docker Desktop secret 管理、CI secret 或 Windows 凭据管理器注入。

### 4.2 必需配置

| 变量 | 本地用途 | 是否提交真实值 |
| --- | --- | --- |
| APP_ENVIRONMENT | 开发身份和安全模式 | 否 |
| OPENAI_BASE_URL | OpenAI-compatible 模型服务地址 | 否 |
| OPENAI_API_KEY | 模型调用密钥 | 否 |
| MODEL_NAME | 模型名称，例如 gpt-5.5 | 可以提交默认名，不提交密钥 |
| SEARCH_PROVIDER | builtin_web_search、tavily 或明确的本地 fallback | 可以提交选择，不提交密钥 |
| TAVILY_API_KEY | SEARCH_PROVIDER=tavily 时使用 | 否 |
| PRODUCT_DATABASE_URL | Product PostgreSQL 连接 | 否，生产使用 secret |
| AGENT_SERVER_URL | 官方 Agent Server 地址 | 可以提交本地默认地址 |
| LANGGRAPH_CLOUD_LICENSE_KEY | Docker durable Agent Server 授权 | 否 |
| LANGSMITH_API_KEY | LangGraph/LangSmith 平台授权或观测凭据 | 否 |
| NOTIFICATION_CREDENTIAL_KEY | Product 通知凭据加密主密钥 | 否 |
| LANGFUSE_SECRET_KEY | Langfuse 服务端观测凭据 | 否 |

### 4.3 LangGraph 授权不要混淆

以下密钥不是一回事：

    OPENAI_API_KEY              模型服务密钥
    TAVILY_API_KEY              Web Search 服务密钥
    LANGSMITH_API_KEY           LangSmith/LangGraph 平台密钥
    LANGGRAPH_CLOUD_LICENSE_KEY LangGraph Agent Server durable 部署授权
    NOTIFICATION_CREDENTIAL_KEY Product 通知凭据加密密钥

OpenAI-compatible 密钥不能替代 LangSmith 或 LangGraph 授权。没有 LANGGRAPH_CLOUD_LICENSE_KEY，也没有具有对应部署能力的 LANGSMITH_API_KEY 时，tools/v2/start_integration_stack.sh 会拒绝启动 durable Docker Agent Server，这是有意的生产门禁，不要通过删除检查来“修复”。

### 4.3.1 密钥迁移清单（只迁移值，不提交值）

本节只记录变量名、用途和迁移位置，不记录任何真实密钥值。不要新建“密钥文档”，不要把密钥值粘贴到 GitHub、README、截图、Playwright fixture、Issue 或聊天记录中。

| 变量 | 用途 | Windows 迁移位置 | 是否需要从旧环境手工迁移 |
| --- | --- | --- | --- |
| `OPENAI_BASE_URL` | OpenAI-compatible 模型服务地址 | `backend/.env` | 是，按实际模型服务填写 |
| `OPENAI_API_KEY` | 模型服务访问凭据 | `backend/.env` 或 Windows Secret Manager | 是 |
| `MODEL_NAME` | 模型名称，例如 `gpt-5.5` | `backend/.env` | 是配置，不是密钥 |
| `SEARCH_PROVIDER` | `builtin_web_search`、`tavily` 或本地 fallback | `backend/.env` | 是配置，不是密钥 |
| `TAVILY_API_KEY` | Tavily 搜索服务凭据，仅 `SEARCH_PROVIDER=tavily` 时需要 | `backend/.env` 或 Windows Secret Manager | 是 |
| `LANGGRAPH_CLOUD_LICENSE_KEY` | Docker durable Agent Server 授权 | WSL 当前 shell、Docker secret 或 CI secret | 是，按授权环境注入 |
| `LANGSMITH_API_KEY` | LangSmith/LangGraph 观测或平台访问凭据 | `backend/.env`、Docker secret 或 CI secret | 是，启用对应能力时需要 |
| `LANGSMITH_TRACING` | 是否发送 LangSmith trace | `backend/.env` | 是配置，不是密钥 |
| `LANGSMITH_PROJECT` | LangSmith 项目名 | `backend/.env` | 是配置，不是密钥 |
| `LANGFUSE_ENABLED` | 是否启用 Langfuse | `backend/.env` | 是配置，不是密钥 |
| `LANGFUSE_PUBLIC_KEY` | Langfuse 公钥标识 | `backend/.env` 或 Secret Manager | 启用 Langfuse 时迁移 |
| `LANGFUSE_SECRET_KEY` | Langfuse 服务端密钥 | `backend/.env` 或 Secret Manager | 启用 Langfuse 时迁移 |
| `LANGFUSE_HOST` | Langfuse 服务地址 | `backend/.env` | 是配置，不是密钥 |
| `NOTIFICATION_CREDENTIAL_KEY` | 通知凭据数据库加密主密钥 | WSL 当前 shell、Docker secret 或 Secret Manager | 是，必须与旧数据库匹配 |
| `NOTIFICATION_CREDENTIAL_KEY_VERSION` | 通知加密密钥版本 | `backend/.env`/Compose 环境 | 是配置 |
| `NOTIFICATION_CREDENTIAL_DECRYPT_KEYS` | 轮换期间的旧密钥解密集合 | Secret Manager 或 Compose 环境 | 只有保留旧通知凭据时需要 |
| `PRODUCT_DATABASE_URL` | Product PostgreSQL 连接 | `backend/.env` 或 Compose 环境 | Windows 新环境通常重新生成 |
| `PRODUCT_POSTGRES_PASSWORD` | Product PostgreSQL 初始化密码 | Compose secret/环境 | Windows 新卷通常重新生成 |
| `AGENT_POSTGRES_PASSWORD` | LangGraph PostgreSQL 初始化密码 | Compose secret/环境 | Windows 新卷通常重新生成 |

以下配置字段也属于敏感或环境绑定信息，不能写入公共文档：`MARKET_DATA_HTTP_PROXY`、`SEARCH_HTTP_PROXY`、`BARK_KEY`、`FAILURE_INJECTION_CONTROL_TOKEN`、`AGENT_SERVER_LOCAL_TOKEN`。其中 `AGENT_SERVER_LOCAL_TOKEN` 只用于本地 `langgraph dev`，不要把它当作生产 Agent Server 凭据。

迁移顺序：

1. 从旧电脑、密码管理器或对应服务控制台取得新环境所需的值；不要从 Git 历史恢复密钥。
2. 复制 `backend/.env.example` 为 `backend/.env`，只在本机填入需要的变量。
3. `SEARCH_PROVIDER=tavily` 时填入 `TAVILY_API_KEY`；使用官方模型 Web Search 时不要无条件填写 Tavily。
4. 启动 durable Compose 前，在当前 WSL shell 或 Docker Secret 中注入 `LANGGRAPH_CLOUD_LICENSE_KEY`、`LANGSMITH_API_KEY` 和 `NOTIFICATION_CREDENTIAL_KEY` 等 Compose 插值变量。
5. 启用 LangSmith/Langfuse 前同时设置对应的开关、地址和凭据，并先用脱敏 trace 验证关联 ID。
6. 启动后执行 readiness、Product API、Worker 和最小分析流程检查；不要只根据容器启动成功判断迁移完成。
7. 使用 `git status --ignored` 和 `git check-ignore -v backend/.env` 确认本地 env 被忽略，确认后再提交代码。

安全提醒：此前曾在聊天中直接提供过模型服务和 Tavily 凭据。正式迁移前应在对应服务控制台吊销或轮换这些值，再把新值手工写入 Windows/WSL 的本地 secret 位置。本仓库和本交接文档不保存、也不重复展示这些真实值。

### 4.3.2 Compose 自动生成的运行时密钥

Compose 的 `internal-jwt-keys` 服务会在 Docker volume 中生成并保存：

    internal-jwt-private
    internal-jwt-public
    product-inbox-cursor-key

这些是运行时密钥，不需要从旧电脑复制到文档，也不应该通过环境变量把私钥粘贴进仓库。迁移到全新 Windows Docker volume 时它们会重新生成；如果要恢复旧数据库和旧任务历史，必须同时保留对应 Docker volumes，或者按正式密钥轮换/恢复流程迁移，不能只恢复 PostgreSQL 数据。

`docker compose down -v` 会删除这些 volume，并可能导致旧的内部 JWT、Inbox 游标和 Agent 状态不可恢复。执行前先确认是否只做全新本地环境。

### 4.4 推荐的 Windows 本地设置

在 backend/.env 中至少确认以下非密钥配置：

    APP_ENVIRONMENT=development
    MODEL_NAME=gpt-5.5
    OPENAI_BASE_URL=https://api.openai.com/v1
    SEARCH_PROVIDER=tavily
    AGENT_SERVER_URL=http://127.0.0.1:8123
    DEVELOPMENT_BOOTSTRAP_ENABLED=true
    DEVELOPMENT_BOOTSTRAP_PROFILE=local-proof
    DEVELOPMENT_BOOTSTRAP_SUBJECT=dev-user
    DEVELOPMENT_BOOTSTRAP_TENANT_ID=dev-tenant
    DEVELOPMENT_BOOTSTRAP_WORKSPACE_ID=dev-workspace
    DEVELOPMENT_BOOTSTRAP_ROLES=["member"]
    DEVELOPMENT_BOOTSTRAP_PERMISSIONS=["analysis:read","analysis:write"]
    LANGSMITH_TRACING=false
    LANGFUSE_ENABLED=false

如果模型服务不支持官方 Responses Web Search，使用 Tavily：

    SEARCH_PROVIDER=tavily
    TAVILY_API_KEY=<只在本机环境变量中填写>

不要把 TAVILY_API_KEY 写进文档、截图、Playwright fixture 或提交历史。

## 5. 启动完整 Docker 栈

### 5.1 在 WSL 中准备 shell 密钥

启动脚本需要在当前 shell 中看到 LangGraph/LangSmith 授权。推荐通过 Windows secret manager 或临时 shell 环境变量注入；不要把真实值提交到仓库：

    export LANGGRAPH_CLOUD_LICENSE_KEY='<从 LangGraph/LangSmith 平台获取的本地开发授权>'
    export NOTIFICATION_CREDENTIAL_KEY="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
    export NOTIFICATION_CREDENTIAL_KEY_VERSION="local-$(date +%Y%m%d)"

如果没有 openssl：

    sudo apt-get update
    sudo apt-get install -y openssl

NOTIFICATION_CREDENTIAL_KEY 丢失后，旧数据库中的加密通知凭据不能解密。开发环境可以重新配置通知目的地；需要保留已有通知凭据时，必须使用密钥轮换流程，不要直接换密钥。

### 5.2 构建和启动

在仓库根目录执行：

    export V2_STACK_PROFILE=production
    bash tools/v2/start_integration_stack.sh

脚本会执行：

1. 检查锁定的官方 LangGraph Agent Server base image。
2. 构建 Product migration 和前端镜像。
3. 使用官方 langgraph build 构建 Agent image。
4. 校验构建镜像确实从锁定的官方 base image 派生。
5. 启动 PostgreSQL、Redis、Agent Server、readiness、Worker 和 frontend。
6. 等待 Compose healthcheck 通过。

默认地址：

    Frontend:   http://127.0.0.1:3001
    Agent API:  http://127.0.0.1:8123
    Agent docs: http://127.0.0.1:8123/docs

浏览器打开：

    http://127.0.0.1:3001/work

### 5.3 查看和停止

    docker compose --project-name crypto-manual-alert-v2 ps
    docker compose --project-name crypto-manual-alert-v2 logs --tail=200 langgraph-api command-worker frontend
    docker compose --project-name crypto-manual-alert-v2 logs -f command-worker
    bash tools/v2/stop_integration_stack.sh

不要使用 docker compose down -v 清理普通开发环境，除非确认要删除本地 PostgreSQL、LangGraph checkpoint/store 和内部密钥卷。删除 volume 会使本地任务历史和 checkpoint 不可恢复。

## 6. 内存不足时的开发策略

Docker Desktop 会同时运行 PostgreSQL、Redis、LangGraph runtime、Worker 和 Next.js。电脑内存不足时常见表现是 Docker Desktop 卡死、WSL OOM、Next 编译被杀或 Agent 请求超时。

按以下顺序处理：

1. 关闭旧的 Compose 项目和不使用的 Docker 容器。
2. 不要同时运行 langgraph dev、完整 Compose 和多个 Playwright 栈。
3. Docker Desktop 的 Resources 中限制 CPU/内存，但不要低于 Agent Server 的实际需求；过低只会制造假性超时。
4. 代码放到 WSL Linux 文件系统，不要放 /mnt/c。
5. 开发 UI 或纯 Product API 时只运行已存在的共享栈，不重复启动第二个 Next dev server。
6. 需要完整 M1-M6、真实 Agent Server restart、Playwright 和数据库集成时，使用 16 GB 以上机器或远程开发机。

轻量代码迭代可以用官方开发服务器：

    cd backend
    APP_ENVIRONMENT=development \
    AGENT_SERVER_LOCAL_TOKEN='<仅当前 shell 使用的临时 token>' \
    uv run langgraph dev --config langgraph.json --host 127.0.0.1 --port 8126 --no-browser

但是 langgraph dev 使用 in-memory runtime，只能用于代码调试和局部测试，不证明 Docker durable Agent Server 的 checkpoint、restart、replay 或生产恢复能力。

## 7. 数据库迁移、备份与恢复

Compose 会在启动依赖链中执行：

    alembic -c alembic.ini upgrade head

手动查看当前版本：

    docker compose --project-name crypto-manual-alert-v2 exec langgraph-api \
      alembic -c /app/backend/alembic.ini current

升级前先备份 Product PostgreSQL。仓库内的备份脚本是本地 logical dump rehearsal，不等于 PITR、跨区域恢复或线上 RTO/RPO 证明：

    bash tools/v2/rehearse_product_database_backup.sh

迁移失败时不要手工删除 app.alembic_version。先保存日志、确认当前 revision，再按对应 migration 的 downgrade/recovery 说明处理。

## 8. Windows 常见故障

### docker: command not found

Docker Desktop 没有启用 WSL integration，或当前 Ubuntu 不是 Docker Desktop 已选中的发行版。执行 wsl -l -v 确认发行版版本为 2。

### A LangGraph Cloud license key ... is required

这是 durable Agent Server 门禁。需要把授权注入当前 WSL shell，或者使用仅用于局部代码调试的 langgraph dev。OpenAI/Tavily key 不能解决这个错误。

### NOTIFICATION_CREDENTIAL_KEY is required

Compose 需要通知凭据加密主密钥。开发环境可用 openssl rand -base64 32 生成临时值；生产环境必须从 secret manager 注入并记录轮换版本。

### port is already allocated

查看端口占用：

    ss -ltnp | rg ':3001|:8123|:5432|:6379'
    docker compose --project-name crypto-manual-alert-v2 ps

停止当前项目后再启动。不要为了绕过端口冲突同时启动多个共享数据库和 Worker。

### Agent 任务长时间 running 或 agent_run_timeout

先看 Worker 和 Agent readiness：

    docker compose --project-name crypto-manual-alert-v2 ps
    docker compose --project-name crypto-manual-alert-v2 logs --tail=300 command-worker langgraph-api langgraph-api-readiness

然后确认模型 endpoint、搜索 provider、代理地址和 Docker 容器是否能访问外网。不要把 timeout 直接改大来掩盖 Worker、授权或 provider 不可用问题。

### WSL 内存被杀

停止所有临时开发进程，关闭不必要的 IDE/浏览器标签，再重启 Docker Desktop。若仍然发生，换用远程开发机；Windows 只改变运行环境，不会消除 V2 全链路的内存需求。

## 9. Windows 下执行真实回归

服务稳定后，在 WSL 中运行：

    cd ~/src/crypto-manual-alert-v2
    cd frontend
    npm ci
    npm run typecheck
    npm run lint
    npm run build

真实 PostgreSQL 测试必须显式设置 REAL_DATABASE_TESTS=1 和隔离的 PRODUCT_DATABASE_URL。不要把共享开发数据库当作测试数据库。

Playwright 运行在 WSL 中，浏览器可以由 Playwright 管理：

    PLAYWRIGHT_EXTERNAL_SERVER=1 \
    PLAYWRIGHT_FRONTEND_BASE_URL=http://127.0.0.1:3001 \
    npm run e2e -- --project=fixture-desktop --project=fixture-pixel-7

如果测试需要真实外部 provider，必须额外设置对应 profile 的环境变量；test.skip、fixture、route interception 和本地 mock 只能记录为 local/fixture evidence，不能标成生产通过。

## 10. 当前交付状态

截至当前 V2 工作树，已经有真实 Product API、PostgreSQL 持久化、官方 LangGraph Agent Server 接入、Worker、HITL、Runs/Library/Monitor/Notification/Data Lifecycle 等多个切片；本次备份提交后仍要保留以下事实：

- V2: PARTIAL
- Production Ready: NO
- 真实 hosted Agent Server restart/replay/fork 证明未完成。
- LangSmith/Langfuse 外部 trace 交付证明未完成。
- 正式通知 provider receipt、Email/Web Push、PITR/DR、HTTPS/OIDC 多用户矩阵和正式 SLO 未完成。
- Memory/Outcome、完整 entitlement/usage、SBOM 签名和发布证明仍有缺口。

这份文档的目标是让 Windows 开发者能复现当前状态，不把“能启动 Docker”误解为“已经达到生产交付”。
