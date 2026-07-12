"""评测包 - V2 评测体系。

模块：
- dataset.py: 评测集构建（100 条，8 维度覆盖）
- judge.py: LLM-as-Judge（G-Eval 方法，4 维度评分）
- regression.py: 回归测试 runner（三级门禁）
- outcome.py: Outcome 追踪（成熟窗口、hit_rate、Brier Score 等）

来源：V2重构方案评审与补充建议_修订版.md 第六节。
"""
