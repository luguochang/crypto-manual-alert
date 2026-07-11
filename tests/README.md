# 本地自测入口

这个目录放项目级自测脚本，目标是复现真实本地使用链路，而不是只检查页面能不能打开。

## 一键完整检查

```powershell
python tools\local_stack\run_local_checks.py
```

执行内容：

1. Python 单元测试：`python -m pytest -p no:cacheprovider`
2. 前端类型检查：`npm run typecheck`
3. 前端生产构建：`npm run build`
4. Playwright 真实浏览器自测：生产 Next.js 构建 + 本地 API，覆盖桌面/移动产品路径、DOM 扫描和产品文案安全。
5. 本地栈 no-secret smoke 矩阵，按顺序执行：
   - 默认 fixture profile。
   - mock LLM profile。
   - actionable staging profile。
   - mocked outcome visibility profile。
   - collect-outcomes fixture profile。

注意：执行前需要确保 `8010`、`3001`、`8011`、`8012`、`8013` 端口没有被其他进程占用。脚本会给 pytest 分配独立临时目录，并在构建前清理 `frontend/.next`，避免历史缓存或上一次开发服务留下的锁影响结果。`8013` 仅用于 opt-in Server Component fault API，不代表真实生产服务端口。

该命令是不需要真实密钥的本地闭环矩阵；它不会把 `prod-actionable` release gate 混进绿色本地检查。真实生产可交付证明仍需单独运行：

```powershell
python tools\local_stack\smoke_local_stack.py --prod-actionable --fail-on-skip
```

缺少真实 Bark、OpenAI-compatible endpoint/model/key、`MACRO_EVENT_PROVIDER=no_active_event`，或缺少 `MACRO_EVENT_OPERATOR_REF` / `MACRO_EVENT_CONFIRMED_AT` / `MACRO_EVENT_SOURCE_REF` / `MACRO_EVENT_ASSERTION_HORIZON` / `MACRO_EVENT_VALID_UNTIL` 这组人工事件断言元数据时，上述严格门禁应非零退出；这表示生产证明未完成，不是本地矩阵失败。

## 只跑本地栈烟测

```powershell
python tools\local_stack\smoke_local_stack.py
```

默认会自动启动 API 和前端，检查完成后自动关闭。

默认烟测不会给手机发 Bark，避免普通 CI/本地检查产生真实副作用。要验证真实手机推送：

```powershell
$env:BARK_DEVICE_KEY="你的BarkKey"
python tools\local_stack\smoke_local_stack.py --with-bark
```

该命令会从手动运行接口触发真实 Bark，并检查本地 SQLite `notifications` 表里是否记录了发送成功。

## 启动给人工测试

```powershell
python tools\local_stack\start_local_stack.py
```

启动后访问：

- API: `http://127.0.0.1:8010`
- 前端: `http://127.0.0.1:3001`
- 可选故障 API: `http://127.0.0.1:8013`，仅在 `--with-error-internal-api` / Server Component fault tests 中启动。

停止服务：

```powershell
python tools\local_stack\stop_local_stack.py
```

如果你希望从页面点击“生成手动操作计划”后真实推送到手机，用：

```powershell
$env:BARK_DEVICE_KEY="你的BarkKey"
python tools\local_stack\start_local_stack.py --with-bark
```
