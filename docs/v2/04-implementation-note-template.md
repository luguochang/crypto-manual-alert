# V2 每轮实施说明模板

> 分类：Informative template（定义记录格式，不单独新增产品规范；实际说明不得保留示例值）
>
> 文件名格式：`docs/v2/implementation/YYYY-MM-DD-phase-N-slice-name.md`
>
> 每一轮涉及代码、依赖、配置、数据库、测试或产品行为的变更都必须填写。

# YYYY-MM-DD Phase N 本轮主题

```yaml
slice_id: task-NN-short-name
phase: phase-N
owner_role: task_NN_implementer
owner_agent_id: assigned-before-red
normative_sha: immutable-task-0-candidate-sha
base_sha: sha-before-red
candidate_sha: added-only-in-review-attestation
requirement_ids:
  - V2-REQ-source-stable-id
status: in_progress|verified|blocked
```

创建本轮说明草稿时必须先把示例值替换为真实值。`owner_agent_id`、`normative_sha`、`base_sha` 和 `requirement_ids` 必须在执行 RED 前确定；`candidate_sha` 在候选提交产生并完成审查后，只能通过 attestation-only 提交补入。CI 对实际实施说明中的示例值或共享兜底 owner 直接失败。

## 1. 本轮目标

- 本轮要完成什么。
- 对应 `03-v2-delivery-checklist.md` 的哪些条目。

## 2. 本轮明确不做

- 防止范围漂移。
- 说明为什么不影响当前主链验收。

## 3. 官方接口依据

| 能力 | 官方接口/组件 | 官方文档 | 为什么适用 |
| --- | --- | --- | --- |
| 示例 | `create_agent` | URL | 不自建 Agent Loop |

如果没有使用官方能力，必须链接对应 ADR。

- `llms.txt` 对应文档族与读取日期：
- 锁定版本和 stable/beta/alpha 状态：
- 与当前 SDK types/API Reference 的核对结果：
- 是否发现旧示例与当前接口不一致：

## 4. 设计与实现说明

### 4.1 数据流

说明输入、输出、状态变化和副作用。

### 4.2 关键约束

说明风险、租户、幂等、恢复、隐私等不变量。

### 4.3 中文注释

列出本轮哪些非直观业务逻辑增加了中文注释，以及注释解释的“为什么”。

## 5. 文件变更

| 文件 | 变更 | 职责 |
| --- | --- | --- |
| path | added/modified/deleted | description |

删除文件必须说明替代它的官方能力或新边界。

## 6. 契约变化

- Graph State：无/具体字段。
- API：无/具体 route/schema/version。
- Database：无/具体 migration。
- Frontend：无/具体 View Model/stream event。
- Event：无/官方 channel、custom extension、protocol/schema version。
- Middleware：无/角色、顺序、权限和 stream transformer。
- Observability：无/具体 metadata/trace。
- Migration forward/rollback：无/命令、数据影响和恢复方式。
- Feature flag/canary：无/启用范围、观察指标和回滚阈值。
- Retention/privacy/security：无/审查结论和数据类别变化。
- Cost/capacity：无/单 Run、并发、存储或外部服务变化。
- Runbook/alert/on-call：无/更新路径。

## 7. 测试证据

| 阶段 | requirement_id | 命令 | 退出码 | 日志 SHA-256 | 预期/实际失败分类 | 测试数量 | 环境/证据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RED | V2-REQ-source-stable-id | exact command | non-zero | hash | intended missing behavior | collected count | profile |
| GREEN | V2-REQ-source-stable-id | exact command | 0 | hash | pass | passed count | artifact path |

不能只写“测试通过”，必须记录实际命令和结果。

- Protocol v2 replay/ordering/dedup：
- Middleware order/permission contract：
- Visual regression/DOM 深度扫描：

## 8. 真实运行证据

- Thread ID：
- Run ID：
- Business ID：
- LangSmith Run/Trace：
- Langfuse Trace：
- Playwright screenshot/report：
- 是否使用真实模型/行情/搜索/通知：
- Production/canary 环境与发布批准：

没有真实运行时明确写“本轮未做真实运行”，不能用 mock 代替；本轮状态不能标记为 `verified`，对应阶段出口不能勾选。

## 9. 异常与修复记录

| 异常 | 根因 | 修复 | 回归证据 |
| --- | --- | --- | --- |

错误必须保留真实分类，禁止把失败改写成成功文案。

## 10. 自定义代码审计

- 是否新增 wrapper/runtime/adapter：是/否。
- 若是，业务价值是什么：
- 官方能力为什么不足：
- 是否新增 custom channel/extension；schema、owner、retention 和 consumer：
- 是否引入第二套 Runtime/Store/Queue/Event/HITL 状态；必须回答“否”：
- ADR：
- 未来删除条件：

## 11. 遗留问题

- 尚未完成的内容。
- 风险等级。
- 是否阻断下一阶段。
- 明确责任和下一动作。

## 12. 下一轮入口

给下一轮一个可执行起点，包括应先读的文件、应运行的命令和不能破坏的边界。

## 13. 对用户的本轮摘要

最终回复至少说明：

1. 改了什么以及用户能看到什么。
2. 使用了哪些官方框架能力。
3. 测试和真实运行结果。
4. 仍未完成或仍有风险的内容。
