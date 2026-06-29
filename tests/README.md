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
