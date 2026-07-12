"""bootstrap_run 节点 - 启动节点（Phase 1）。

设计文档 7.3 节节点 1：注入开发/生产身份、生成 ID、建立业务运行记录。
Phase 1 实现：从配置注入开发身份，生成 run_id。
"""

import uuid

from crypto_alert_v2.config import settings
from crypto_alert_v2.graph.state import AnalysisState


def bootstrap_run(state: AnalysisState) -> dict:
    """启动节点：注入开发身份、生成 run_id。

    Phase 1 实现：
    - 从 settings 读取开发身份（设计文档 9.1 节开发模式）
    - 生成唯一 run_id
    - 写入 identity 和 run_context

    生产环境额外需要：建立 agent_runs 业务记录、初始化 heartbeat。
    """
    run_id = str(uuid.uuid4())

    # 开发身份注入（设计文档 9.1 节）
    identity = {
        "tenant_id": settings.dev_tenant_id,
        "user_id": settings.dev_user_id,
        "auth_mode": settings.auth_mode,
    }

    # 运行上下文 ID（设计文档 14.3 节 ID 契约）
    run_context = {
        "run_id": run_id,
        "tenant_id": settings.dev_tenant_id,
        "user_id": settings.dev_user_id,
    }

    return {
        "identity": identity,
        "run_context": run_context,
        "progress_events": [
            {
                "stage": "bootstrap",
                "status": "completed",
                "run_id": run_id,
            },
        ],
    }
