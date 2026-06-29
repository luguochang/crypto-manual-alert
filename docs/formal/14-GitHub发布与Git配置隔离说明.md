# GitHub 发布与 Git 配置隔离说明

## 1. 结论

本项目后续可以推送到 GitHub 仓库：

```text
https://github.com/luguochang/crypto-manual-alert
```

但当前阶段只记录方案，不执行任何 Git 初始化、remote 修改、登录、提交或推送操作。

推荐原则：

- 不修改全局 Git 配置。
- 不删除或覆盖 Windows 凭据管理器中的任何现有凭据。
- 不影响公司内部 GitLab 仓库。
- 只在本项目目录内写入本地仓库配置，即后续只改 `project/crypto-manual-alert/.git/config`。

## 2. 当前本地检查结果

检查时间：2026-06-26。

只读检查结果：

- `project/crypto-manual-alert` 当前还不是 Git 仓库。
- 因为还不是 Git 仓库，所以该项目当前没有 `origin` remote。
- 全局 Git 配置中存在公司内部 GitLab 相关配置：

```text
credential.http://172.19.2.176:8929.provider=generic
http.http://172.19.2.176:8929/.proxy=
```

含义：

- `172.19.2.176:8929` 这个内部 GitLab 地址有单独的凭据 provider。
- 对该内部 GitLab 地址禁用了代理，避免走本地代理。

Windows 凭据管理器里看到的 Git 凭据目标是按 host 分开的：

```text
git:https://github.com
git:http://172.19.2.176:8929
git:https://gitee.com
```

因此 GitHub、公司 GitLab、Gitee 的凭据不会因为添加某一个仓库 remote 而互相覆盖。

## 3. 为什么不会影响公司 GitLab

Git 配置通常分为三层：

```text
system: Git 安装级配置
global: 当前 Windows 用户级配置
local: 单个仓库的 .git/config
```

公司 GitLab 当前主要依赖：

- 全局 host 专用配置。
- Windows 凭据管理器中 `git:http://172.19.2.176:8929` 的凭据。
- 其他已有仓库自己的 `.git/config`。

如果后续只在 `project/crypto-manual-alert` 目录里执行本地仓库操作，例如：

```powershell
git init -b main
git remote add origin https://github.com/luguochang/crypto-manual-alert.git
git config user.name "luguochang"
git config user.email "GitHub 提交邮箱"
```

这些配置只会写入：

```text
project/crypto-manual-alert/.git/config
```

不会修改公司 GitLab 的全局配置，也不会影响其他仓库的 remote。

## 4. 后续推荐操作

等确认要正式发布时，再在项目目录执行：

```powershell
cd E:\file\project\selfproject\project\crypto-manual-alert
git init -b main
git remote add origin https://github.com/luguochang/crypto-manual-alert.git
git remote -v
```

如需设置提交身份，建议只设置本仓库 local 配置：

```powershell
git config user.name "luguochang"
git config user.email "GitHub 提交邮箱"
```

然后再检查：

```powershell
git config --local --list
git status
```

确认无误后再添加文件、提交、推送。

## 5. 明确禁止的操作

除非明确知道影响范围，否则不要执行以下命令：

```powershell
git config --global credential.helper ...
git config --global http.proxy ...
git config --global https.proxy ...
git config --global user.name ...
git config --global user.email ...
git credential-manager erase ...
cmdkey /delete:...
```

原因：

- `--global` 会影响当前 Windows 用户下的所有 Git 仓库。
- 删除 credential 可能导致 GitHub、GitLab、Gitee 重新登录。
- 改全局代理可能影响公司内网 GitLab 的推送和拉取。

## 6. 凭据与密钥注意事项

本项目后续推到公开 GitHub 前，必须确认以下内容没有进入仓库：

- OpenAI 兼容接口 key。
- Bark key。
- OKX API key。
- `.env` 文件。
- `data/` 下的本地 SQLite 数据库和运行日志。
- IDE 本地配置，如 `.idea/`。

已有 `.env.example` 可以保留，但必须只包含变量名和示例占位值，不能包含真实 key。

## 7. 推荐仓库命名

当前 GitHub 仓库名：

```text
crypto-manual-alert
```

推荐本地 package/CLI 可暂时保持现状：

```text
project package: crypto-manual-alert
CLI command: crypto-alert
```

这样 GitHub 仓库名描述产品边界，Python 包名保留项目识别度。后续如需统一命名，可以单独做一次小范围重命名，不和首次发布混在一起。

