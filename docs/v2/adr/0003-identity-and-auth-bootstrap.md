# ADR 0003：默认开发身份与正式鉴权

> 状态：Proposed
>
> 日期：2026-07-12

## 背景

第一阶段必须先跑通 Agent 主链，不能被登录系统阻断；最终产品又必须支持多用户和租户隔离，不能以后通过重写 Graph 补身份字段。

## 决策

- 定义稳定 `ActorContext`：`tenant_id`、`user_id`、`workspace_id`、`roles`、`permissions`、`plan`、`request_id`。
- 非生产环境允许 `DevIdentityProvider` 返回固定 `dev-tenant/dev-user/dev-workspace`。
- 开发身份必须由显式环境开关启用，生产构建和生产启动均默认拒绝。
- 正式身份推荐 Auth.js 管理 Web Session；Next.js BFF 生成短期内部令牌或可信身份头，Agent Server custom auth 验证。
- Agent Server resource auth 为 Thread/Run 添加 owner/tenant metadata 和过滤；Store 不依赖 metadata filter，必须在 `@auth.on.store.*` 中强制改写 namespace，并覆盖 put/get/search/delete/list_namespaces。
- Repository 不接收裸 `user_id`，只接收经过鉴权的 ActorContext。

## 替代方案

- Clerk/Keycloak/OIDC 可以替换 Auth.js，但必须实现相同 IdentityProvider/ActorContext 契约。
- 浏览器直传任意 tenant/user header 不可信，不采用。

## 安全门禁

- 生产无 Authorization 时 fail-closed。
- 用户 A 不能读取、恢复、取消、fork 或反馈用户 B 的资源。
- Integration secret 不进入 Graph State、Prompt、Trace 或浏览器存储。
