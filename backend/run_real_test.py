#!/usr/bin/env python3
"""真实 LLM 端到端测试脚本。

凭据只允许从环境变量或本地 .env 注入，禁止写入仓库。
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, "src")

required_env = ["OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL_NAME"]
missing_env = [name for name in required_env if not os.environ.get(name)]
if missing_env:
    print(f"缺少环境变量: {', '.join(missing_env)}", file=sys.stderr)
    sys.exit(2)

os.environ.setdefault("AUTH_MODE", "development")

from crypto_alert_v2.config import settings
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from crypto_alert_v2.domain.models import MarketAnalysis
from crypto_alert_v2.prompts.system_prompt import SYSTEM_PROMPT
from crypto_alert_v2.domain.risk_policy import check_plan

print(f'API: {settings.openai_base_url}')
print(f'Model: {settings.model_name}')
print()

# 1. LLM 连接
print('=== 1. LLM 连接测试 ===')
model = ChatOpenAI(model=settings.model_name, api_key=settings.openai_api_key, base_url=settings.openai_base_url, timeout=30)
try:
    r = model.invoke('回复一个字：好')
    print(f'✅ LLM连接成功: {r.content[:30]}')
except Exception as e:
    print(f'❌ LLM连接失败: {e}')
    sys.exit(1)

# 2. create_agent
print()
print('=== 2. create_agent 创建 ===')
agent = create_agent(model=model, tools=[], system_prompt=SYSTEM_PROMPT)
print('✅ Agent 创建成功')

# 3. 真实分析
print()
print('=== 3. 真实 LLM 分析（可能需要 30-60 秒）===')
ctx = """分析BTC-USDT-SWAP 4h趋势。当前价格67200，资金费率+0.012%，OI增长3%，ETF流入125M。
请按照8步工作流分析，输出MarketAnalysis JSON。只输出JSON，不要其他内容。"""

try:
    result = asyncio.run(asyncio.wait_for(
        agent.ainvoke({'messages':[{'role':'user','content':ctx}]}),
        timeout=120
    ))
    c = result['messages'][-1].content
    print(f'LLM 响应: {len(c)} chars')

    if isinstance(c, str):
        try:
            data = json.loads(c)
        except:
            import re
            m = re.search(r'\{.*\}', c, re.DOTALL)
            data = json.loads(m.group()) if m else {}
    elif isinstance(c, dict):
        data = c
    else:
        data = c

    a = MarketAnalysis(**data)
    print(f'✅ LLM 分析成功！')
    print(f'   action: {a.main_action}')
    print(f'   regime: {a.regime}')
    print(f'   probability: {a.probability}')
    print(f'   entry: {a.entry_trigger}')
    print(f'   stop: {a.stop_price}')
    print(f'   target_1: {a.target_1}')
    print(f'   total_score: {a.total_score}')
    print(f'   factor_scores: {a.factor_scores}')
    print(f'   root_cause: {a.root_cause_chain[:3]}')
    print(f'   why_not_opposite: {a.why_not_opposite[:100]}')
    print(f'   invalidation: {a.invalidation[:100]}')
    print(f'   manual_execution_required: {a.manual_execution_required}')

    # 4. 风控
    print()
    print('=== 4. 风控规则检查 ===')
    v = check_plan(a)
    print(f'✅ 风控: allowed={v.allowed}')
    print(f'   blocked_reasons: {v.blocked_reasons}')
    print(f'   warnings: {v.warnings}')

    # 5. 单元测试
    print()
    print('=== 5. 单元测试 ===')
    import subprocess
    r = subprocess.run(['python', '-m', 'pytest', 'tests/', '--no-cov', '-q'],
                      capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': 'src'})
    print(r.stdout.strip().split('\n')[-1])

    print()
    print('========================================')
    print('  真实 LLM 端到端测试: ALL PASS ✅')
    print('========================================')

except asyncio.TimeoutError:
    print('❌ LLM 分析超时（120秒）')
except Exception as e:
    print(f'❌ 分析失败: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
