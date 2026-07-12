"""observability 包 - 日志、配置、告警。

模块：
- logging.py: structlog 配置（JSON 格式日志 + correlation ID 注入）
- config_loader.py: YAML 配置加载 + Feature flags
- alerts.py: 9 条告警规则（触发和通知）

来源：V2技术设计缺口补充.md 第九节。
"""
