# 本地自测入口

这个目录放项目级自测脚本，目标是复现真实本地使用链路，而不是只检查页面能不能打开。

## 一键完整检查

```powershell
python tests\run_local_checks.py
```

执行内容：

1. Python 单元测试：`python -m pytest -p no:cacheprovider`
2. 前端类型检查：`npm run typecheck`
3. 前端生产构建：`npm run build`
4. 本地栈烟测：启动 API 和前端，检查健康接口、CORS 预检、手动运行、运行列表、运行详情和前端路由。

注意：执行前需要确保 `8010` 和 `3001` 端口没有被其他进程占用。脚本会给 pytest 分配独立临时目录，并在构建前清理 `frontend/.next`，避免历史缓存或上一次开发服务留下的锁影响结果。

## 只跑本地栈烟测

```powershell
python tests\smoke_local_stack.py
```

默认会自动启动 API 和前端，检查完成后自动关闭。

默认烟测不会给手机发 Bark，避免普通 CI/本地检查产生真实副作用。要验证真实手机推送：

```powershell
$env:BARK_DEVICE_KEY="你的BarkKey"
python tests\smoke_local_stack.py --with-bark
```

该命令会从手动运行接口触发真实 Bark，并检查本地 SQLite `notifications` 表里是否记录了发送成功。

## 启动给人工测试

```powershell
python tests\start_local_stack.py
```

启动后访问：

- API: `http://127.0.0.1:8010`
- 前端: `http://127.0.0.1:3001`

停止服务：

```powershell
python tests\stop_local_stack.py
```

如果你希望从页面点击“生成手动操作计划”后真实推送到手机，用：

```powershell
$env:BARK_DEVICE_KEY="你的BarkKey"
python tests\start_local_stack.py --with-bark
```
