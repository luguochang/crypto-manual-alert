# V2 重构实施计划与自测清单

> 日期：2026-07-12
>
> 目的：提供完整的实施计划、Phase 划分、交付标准和自测检查清单
>
> 状态：Ready for Implementation

---

## 一、实施原则

### 1.1 核心原则

1. **设计文档驱动**：所有实现严格按照 docs/v2 目录下的设计文档
2. **框架优先**：检查 02-official-framework-constraints.md 的映射表，不自己造轮子
3. **测试先行**：每个 Phase 先写测试和实施说明，再写实现
4. **可验证交付**：每个 Phase 有明确的退出条件和验证方法
5. **渐进集成**：每个 Phase 都能独立运行和测试

### 1.2 设计文档索引

实施时必须对照的文档：

| 编号 | 文档 | 用途 |
|------|------|------|
| 01 | v2-product-and-architecture.md | 总架构和 10 节点设计 |
| 02 | official-framework-constraints.md | 框架 API 映射和禁止模式 |
| 06 | c-end-agent-product-blueprint.md | 产品功能和模式 |
| 08 | production-governance-and-nonfunctional.md | 非功能需求 |
| 13 | dependencies-and-fixtures.md | 依赖和测试 |
| 14 | system-prompt-and-evidence-gates.md | Prompt 和证据规则 |
| 15 | frontend-and-config-management.md | 前端接口和配置 |
| - | V2重构方案评审与补充建议_修订版.md | 框架映射表 |
| - | V2产品缺口分析与设计方案.md | 产品规格 |
| - | V2技术设计缺口补充.md | 技术实现细节 |

---

## 二、Phase 0：骨架验证（3-5 天）

### 2.1 目标

证明 Agent Server + LangGraph + React SDK 核心假设成立：
- Graph 可以编译和执行
- HITL interrupt/resume 正常工作
- 前端 useStream 可以连接并接收事件
- Checkpoint 可以持久化和恢复

### 2.2 交付清单

#### 后端骨架

- [ ] **项目初始化**
  - [ ] `backend/pyproject.toml`（复制 13-dependencies-and-fixtures.md）
  - [ ] `uv lock && uv sync`
  - [ ] `backend/src/crypto_alert_v2/__init__.py`
  - [ ] Git 仓库初始化

- [ ] **最简 Graph**
  - [ ] `backend/src/crypto_alert_v2/graph/state.py`（定义 AnalysisState）
  - [ ] `backend/src/crypto_alert_v2/graph/graph.py`（3 节点：bootstrap -> agent -> complete）
  - [ ] `backend/src/crypto_alert_v2/graph/__init__.py`（导出 `graph = builder.compile()`）
  - [ ] 验证：`from crypto_alert_v2.graph import graph` 不报错

- [ ] **一个 Mock Tool**
  - [ ] `backend/src/crypto_alert_v2/tools/mock_market.py`
  - [ ] 返回固定的市场快照 JSON
  - [ ] 验证：Tool 可以被 create_agent 调用

- [ ] **Agent Server 配置**
  - [ ] `backend/langgraph.json`（注册 graph）
  - [ ] `backend/.env.development`（环境变量）
  - [ ] `backend/Dockerfile`
  - [ ] 验证：`langgraph dev` 可以启动

- [ ] **HITL 验证**
  - [ ] agent 节点内调用 `interrupt({"test": "data"})`
  - [ ] 前端 `stream.respond()` 恢复
  - [ ] 验证：Graph 继续执行到 END

#### 前端骨架

- [ ] **项目初始化**
  - [ ] `frontend/package.json`（@langchain/react 等依赖）
  - [ ] `npm install`
  - [ ] Next.js 15 + React 19 配置

- [ ] **useStream 页面**
  - [ ] `frontend/src/app/test/page.tsx`
  - [ ] 连接 Agent Server：`useStream({ apiUrl, assistantId, threadId })`
  - [ ] 显示 `stream.messages`、`stream.values`、`stream.interrupts`
  - [ ] [提交] 按钮触发 `stream.submit()`
  - [ ] [恢复] 按钮触发 `stream.respond()`
  - [ ] 验证：可以看到 Agent 执行过程和中断

#### 基础设施

- [ ] **Docker Compose**
  - [ ] `docker-compose.yml`（复制 V2技术设计缺口补充.md 第五节）
  - [ ] PostgreSQL + Redis 容器
  - [ ] 验证：`docker-compose up` 可以启动所有服务

- [ ] **测试框架**
  - [ ] `backend/tests/conftest.py`（复制 13 文档）
  - [ ] 一个示例测试：`tests/unit/test_state.py`
  - [ ] 验证：`pytest tests/` 可以运行

- [ ] **LangSmith 集成**
  - [ ] 环境变量配置 LANGSMITH_API_KEY
  - [ ] 验证：执行 Graph 后在 LangSmith UI 可以看到 Trace

### 2.3 退出条件

✅ **必须全部通过才能进入 Phase 1**：

1. [ ] `langgraph dev` 启动无错误
2. [ ] 前端页面可以连接 Agent Server
3. [ ] 提交消息后 Graph 执行到 interrupt
4. [ ] 前端看到 `stream.interrupt`，显示中断 UI
5. [ ] 点击恢复后 Graph 继续执行到 END
6. [ ] 刷新页面后 Thread 仍可恢复（reconnectOnMount 生效）
7. [ ] Agent Server 重启后 Thread 可恢复（PostgreSQL checkpoint 生效）
8. [ ] LangSmith 可以看到完整 Trace
9. [ ] `pytest tests/` 全部通过
10. [ ] 无任何自定义 SSE、Thread Store、LLM Client 代码

### 2.4 常见问题

**Q1: langgraph dev 报错找不到 graph**
- 检查 `langgraph.json` 的 graphs 路径是否正确
- 检查 graph.py 是否导出了 `graph = builder.compile()`
- 不要导出 factory function

**Q2: useStream 连接失败**
- 检查 apiUrl 是否正确（http://localhost:2024）
- 检查 CORS 配置
- 检查 Agent Server 日志

**Q3: interrupt 后无法恢复**
- 检查是否使用了相同的 thread_id
- 检查 Command(resume=...) 格式是否正确
- 检查 PostgreSQL 连接是否正常

---

## 三、Phase 1：真实主链（10-15 天）

### 3.1 目标

跑通真实市场分析闭环：用户发起分析 -> 获取 OKX 行情 -> 模型分析 -> 风控 -> HITL 确认 -> 通知。

### 3.2 交付清单

#### 后端 - Graph 完整实现

- [ ] **State 定义**
  - [ ] `graph/state.py`（完整的 AnalysisState TypedDict）
  - [ ] messages reducer
  - [ ] 所有状态字段（market_snapshot, decision_draft, risk_verdict 等）

- [ ] **10 个节点实现**
  - [ ] `graph/nodes/bootstrap_run.py`
  - [ ] `graph/nodes/validate_request.py`
  - [ ] `graph/nodes/collect_market_snapshot.py`（OKX 7 个 endpoint 并发）
  - [ ] `graph/nodes/research_events.py`（暂用 mock 或简单 Tavily）
  - [ ] `graph/nodes/analyze_market.py`（create_agent + system_prompt）
  - [ ] `graph/nodes/validate_evidence.py`（证据门禁）
  - [ ] `graph/nodes/apply_risk_policy.py`（14 条风控规则）
  - [ ] `graph/nodes/build_final_result.py`
  - [ ] `graph/nodes/confirm_analysis.py`（HITL interrupt）
  - [ ] `graph/nodes/commit_final_artifact.py`（写 PostgreSQL）
  - [ ] `graph/nodes/complete_run.py`

- [ ] **Graph 拓扑**
  - [ ] `graph/graph.py`（完整拓扑代码，复制 V2技术设计缺口补充.md 第一节）
  - [ ] 条件路由函数（route_after_validation, route_after_risk, route_after_confirm）
  - [ ] 并行边（collect_market_snapshot 和 research_events）

#### 后端 - Tools

- [ ] **OKX Market Data Tool**
  - [ ] `tools/market.py`
  - [ ] `fetch_market_data(symbol, data_types)` tool
  - [ ] 并发调用 7 个 endpoint
  - [ ] asyncio.Semaphore 限频
  - [ ] 验证：可以获取 BTC-USDT-SWAP 完整数据

- [ ] **Redis 缓存**
  - [ ] `tools/cache.py`
  - [ ] 缓存 ticker/mark/funding_rate 等（TTL 见 15 文档）
  - [ ] 验证：第二次调用命中缓存

- [ ] **Bark 通知 Tool**
  - [ ] `tools/notification.py`
  - [ ] `send_bark_notification(title, body, bark_key)` tool
  - [ ] 验证：可以收到推送

#### 后端 - Domain

- [ ] **风控规则**
  - [ ] `domain/risk_policy.py`
  - [ ] 14 条规则纯函数（复制 V1 逻辑）
  - [ ] 单元测试：`tests/unit/test_risk_policy.py`
  - [ ] 验证：所有规则测试通过

- [ ] **证据门禁**
  - [ ] `domain/evidence_policy.py`
  - [ ] `check_evidence_sufficiency()` 函数（14 文档 2.5 节）
  - [ ] 单元测试
  - [ ] 验证：缺失必需数据阻断，可选数据降级

- [ ] **System Prompt**
  - [ ] `prompts/system_prompt.py`（完整 prompt，14 文档第一节）
  - [ ] 版本号和 CHANGELOG
  - [ ] 验证：字符串长度合理（不超过 32K）

- [ ] **Structured Output Schema**
  - [ ] `domain/models.py`
  - [ ] `MarketAnalysis(BaseModel)`（14 文档第一节）
  - [ ] 验证：Pydantic 校验正常

#### 后端 - Database

- [ ] **SQLAlchemy Models**
  - [ ] `storage/models.py`
  - [ ] 13 张核心表（agent_runs, analysis_results 等）
  - [ ] 关系定义

- [ ] **Alembic 迁移**
  - [ ] `alembic init alembic`
  - [ ] `alembic/env.py` 配置
  - [ ] `alembic revision --autogenerate -m "initial_schema"`
  - [ ] `alembic upgrade head`
  - [ ] 验证：PostgreSQL 中有 13 张表

- [ ] **Repository**
  - [ ] `storage/repository.py`
  - [ ] 写入 agent_runs, analysis_results, market_snapshots 等
  - [ ] 验证：commit_final_artifact 可以写入

#### 前端 - Work 页面

- [ ] **三栏布局**
  - [ ] `app/work/page.tsx`
  - [ ] 左栏：Thread 列表
  - [ ] 中栏：对话时间线
  - [ ] 右栏：Artifact Inspector
  - [ ] 响应式布局（移动端折叠）

- [ ] **分析结论卡片**
  - [ ] `components/AnalysisResultCard.tsx`
  - [ ] Props 接口（15 文档）
  - [ ] 展示方向/入场/止损/目标/概率
  - [ ] [确认] [拒绝] [编辑] 按钮
  - [ ] 90 秒倒计时
  - [ ] 验证：可以触发 stream.respond()

- [ ] **HITL 交互**
  - [ ] 检测 `stream.interrupt`
  - [ ] 渲染确认对话框
  - [ ] 编辑面板（修改价位）
  - [ ] 三种响应：approve / reject / edit
  - [ ] 验证：后端收到 Command(resume=...)

- [ ] **右栏组件**
  - [ ] `components/MarketSnapshot.tsx`
  - [ ] `components/EvidenceTimeline.tsx`
  - [ ] `components/RiskInspector.tsx`
  - [ ] 验证：可以展示完整分析过程

- [ ] **错误降级提示**
  - [ ] 11 种场景的 Toast/Banner 提示（V2产品缺口分析 3.2 节）
  - [ ] 验证：OKX 不可用时显示正确提示

#### 测试

- [ ] **单元测试**
  - [ ] `tests/unit/test_risk_policy.py`（14 条规则）
  - [ ] `tests/unit/test_evidence_policy.py`
  - [ ] `tests/unit/test_market_data_parser.py`
  - [ ] 覆盖率 ≥ 95%

- [ ] **Graph Contract 测试**
  - [ ] `tests/graph/test_graph_topology.py`（节点/边/路由）
  - [ ] `tests/graph/test_interrupt_resume.py`（HITL）
  - [ ] `tests/graph/test_blocked_failed.py`（状态区分）

- [ ] **Agent Contract 测试**
  - [ ] `tests/agent/test_analysis_agent.py`（FakeChatModel）
  - [ ] 验证：Structured Output 正确

- [ ] **E2E 测试**
  - [ ] `frontend/tests/e2e/analysis-flow.spec.ts`
  - [ ] 用户发起分析 -> 看到结果 -> 确认 -> 收到通知
  - [ ] Playwright 录屏
  - [ ] 验证：完整流程通过

### 3.3 退出条件

✅ **必须全部通过**：

1. [ ] 用户在 Work 页面提交"分析 BTC 4h"
2. [ ] 系统调用 OKX API 获取 7 类数据
3. [ ] 模型返回结构化分析结果
4. [ ] 证据门禁和风控门禁正确评估
5. [ ] 前端显示分析卡片，用户可以确认/拒绝/编辑
6. [ ] 用户确认后，系统写入 PostgreSQL 并发送 Bark 通知
7. [ ] 用户可以在手机收到通知
8. [ ] LangSmith Trace 完整且可读
9. [ ] Langfuse 追踪到成本
10. [ ] pytest 覆盖率 ≥ 85%
11. [ ] Playwright E2E 测试通过
12. [ ] 无自定义 workflow/orchestration/agent_swarm 代码
13. [ ] 所有外部调用都通过 @tool 装饰器
14. [ ] Graph 没有配置 checkpointer（Agent Server 自动注入）

---

## 四、Phase 2-6 简要计划

### Phase 2：Agent UX（7-10 天）

- 完整前端 5 个页面（Home/Work/Inbox/Library/Settings）
- Watchlist 和 Monitor 功能
- 用户偏好配置
- Onboarding 流程
- 移动端适配

### Phase 3：Deep Agents 研究（5-7 天）

- 研究子图（news_researcher/macro_researcher/source_critic）
- ResearchBundle 输出
- 权限和预算控制

### Phase 4：评测体系（10-15 天）

- LangSmith Dataset（100 条初始评测集）
- DeepEval 集成（Agent 专用指标）
- LLM-as-Judge（G-Eval）
- 回归测试 CI/CD pipeline

### Phase 5：Outcome 追踪（7-10 天）

- Outcome 数据采集 Cron Job
- 成熟窗口后计算 hit_rate/Brier/PnL
- Outcome Review 页面
- 金融质量门禁

### Phase 6：商业化准备（10-15 天）

- 正式 Auth（Auth.js）
- 多租户完整实现
- Usage 和 Quota 追踪
- 计费准备

---

## 五、自测检查清单

### 5.1 框架约束自测（对照 02 文档）

#### 禁止模式检查

- [ ] 无 `while True:` + 自定义 retry（使用 RetryPolicy 或 ModelRetryMiddleware）
- [ ] 无 `ThreadPoolExecutor`（使用 Graph parallel branch / Send）
- [ ] 无手动 JSON parse（使用 response_format）
- [ ] 无自定义 State Store（使用 LangGraph StateGraph）
- [ ] 无自定义 Checkpoint（Agent Server 自动注入）
- [ ] 无自定义 HITL 轮询（使用 interrupt + Command）
- [ ] 无自定义 SSE（使用 Agent Server protocol）
- [ ] 无 Redux/Zustand 副本 Graph State（使用 @langchain/react）

#### Import 检查

```bash
# 运行 import-linter
lint-imports

# 检查是否有禁止的导入
grep -r "from threading import" backend/src/
grep -r "import asyncio.Queue" backend/src/
```

### 5.2 Graph Contract 自测

- [ ] Graph 导出 CompiledGraph 而非 factory function
- [ ] Graph 没有配置 checkpointer
- [ ] 所有节点是纯函数或 async 函数
- [ ] State reducer 正确（add_messages）
- [ ] 条件路由函数返回正确的节点名
- [ ] interrupt() 前的代码幂等
- [ ] 并行节点没有共享可变状态

### 5.3 数据库自测

- [ ] 所有表有 tenant_id 和 user_id
- [ ] 所有表有 created_at
- [ ] 外键约束正确
- [ ] 索引覆盖常用查询
- [ ] Alembic 迁移可以 upgrade 和 downgrade
- [ ] 租户隔离测试通过

### 5.4 前端自测

- [ ] useStream 使用正确的 apiUrl 和 assistantId
- [ ] 所有 stream 数据有 Zod schema 验证
- [ ] 防御性 fallback（数据缺失时不崩溃）
- [ ] 错误边界（ErrorBoundary）
- [ ] 加载态（Suspense）
- [ ] 移动端测试通过

### 5.5 安全自测

- [ ] API Key 不在代码中硬编码
- [ ] Bark Key 不在前端暴露
- [ ] 用户输入有 Zod 验证
- [ ] SQL 查询用参数化（SQLAlchemy）
- [ ] XSS 防护（React 自动转义）
- [ ] CSRF 防护（Next.js 自动处理）

### 5.6 性能自测

- [ ] OKX API 并发调用（7 个 endpoint < 15s）
- [ ] Redis 缓存命中率 > 50%
- [ ] Graph 总执行时间 < 180s
- [ ] 前端首屏加载 < 3s
- [ ] Lighthouse 得分 > 80

### 5.7 文档完整性自测

- [ ] 每个节点有 docstring
- [ ] 每个 Tool 有 description
- [ ] README.md 有启动指南
- [ ] CONTRIBUTING.md 有贡献指南
- [ ] API 文档自动生成（FastAPI /docs）

---

## 六、实施前预检清单

### 6.1 设计文档审批

- [ ] 01-v2-product-and-architecture.md 已审批
- [ ] 02-official-framework-constraints.md 已审批
- [ ] 06-c-end-agent-product-blueprint.md 已审批
- [ ] V2重构方案评审与补充建议_修订版.md 已审阅
- [ ] V2产品缺口分析与设计方案.md 已审阅
- [ ] V2技术设计缺口补充.md 已审阅
- [ ] 所有补充文档（13-15）已审阅

### 6.2 开发环境

- [ ] Python 3.12 安装
- [ ] Node.js 20+ 安装
- [ ] Docker 和 Docker Compose 安装
- [ ] PostgreSQL 16 客户端工具
- [ ] Redis CLI
- [ ] uv 包管理器安装
- [ ] Git 配置完成

### 6.3 API Keys 和 Secrets

- [ ] OPENAI_API_KEY 已获取并测试
- [ ] LANGSMITH_API_KEY 已获取
- [ ] LANGFUSE_PUBLIC_KEY 和 SECRET_KEY 已获取
- [ ] TAVILY_API_KEY 已获取
- [ ] BARK_KEY 已获取并测试
- [ ] OKX API 可访问（公开 API，无需 Key）

### 6.4 基础设施

- [ ] PostgreSQL 16 可访问（localhost:5432 或远程）
- [ ] Redis 7 可访问（localhost:6379 或远程）
- [ ] LangSmith 账号创建
- [ ] Langfuse 自部署或 Cloud 账号
- [ ] Git 仓库创建（GitHub/GitLab）

### 6.5 Git 策略

- [ ] 主分支：main
- [ ] 开发分支：develop
- [ ] Feature 分支：feature/phase-0-skeleton
- [ ] Commit message 规范：Conventional Commits
- [ ] PR 模板创建
- [ ] CI/CD workflow 配置（GitHub Actions）

---

## 七、Phase 间依赖关系

```
Phase 0 (骨架验证)
    |
    v
Phase 1 (真实主链)
    |
    +---> Phase 2 (Agent UX) --+
    |                          |
    +---> Phase 3 (Research) --+
    |                          v
    +---> Phase 4 (评测) -------> Phase 5 (Outcome)
                                      |
                                      v
                                  Phase 6 (商业化)
```

**依赖规则**：
- Phase 1 必须完成才能开始 Phase 2/3/4
- Phase 2/3/4 可以并行
- Phase 5 依赖 Phase 1 + 4
- Phase 6 依赖所有前序 Phase

---

## 八、风险与缓解

### 8.1 技术风险

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| Agent Server 不稳定 | 中 | Phase 0 先验证，问题多则切到方案 C |
| Deep Agents API 变更 | 中 | 隔离在 ResearchBundle，可降级到 Tavily |
| OKX API 限频 | 低 | Semaphore + Redis 缓存 |
| PostgreSQL 性能 | 低 | 索引优化，必要时读写分离 |

### 8.2 进度风险

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| Phase 1 超期 | 中 | 拆分 MVP（先不做 Research 子图） |
| 评测体系延期 | 中 | Phase 4 可推迟，不阻塞 Phase 2/3 |
| 前端返工 | 中 | Phase 0 早期验证 React SDK |

---

## 九、成功标准

### Phase 0 成功标准

- [ ] 3-5 天内完成
- [ ] 所有退出条件通过
- [ ] 团队对 Agent Server 有信心

### Phase 1 成功标准

- [ ] 10-15 天内完成
- [ ] 真实用户可以发起分析并收到通知
- [ ] E2E 测试通过
- [ ] 无 P0 Bug

### 整体成功标准

- [ ] 6 个 Phase 在 60-90 天内完成
- [ ] 所有评测指标达标（任务完成率 ≥ 70%）
- [ ] 生产就绪（SLA/监控/告警）
- [ ] 文档完整（用户手册/运维手册/API 文档）

---

## 十、下一步行动

**立即行动**：

1. [ ] 审批所有设计文档
2. [ ] 配置开发环境
3. [ ] 创建 Git 仓库和分支
4. [ ] 创建 feature/phase-0-skeleton 分支
5. [ ] 开始 Phase 0 第一个任务：pyproject.toml

**本周目标**：

- 完成 Phase 0 骨架验证
- HITL 可以正常工作

**本月目标**：

- 完成 Phase 1 真实主链
- 用户可以收到真实分析通知
