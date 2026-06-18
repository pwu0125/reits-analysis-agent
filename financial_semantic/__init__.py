"""
REITs 财务语义层 — Financial Semantic Layer

三层架构:
  定义层 (concepts/*.json) → 编译层 (expression_engine.py) → 执行层 (source_binder.py)

核心理念:
  "说出一个REITs专业概念，即使数据库里没有这个字段，Agent也能自动算出"
  
示例:
  用户说"ROA" → expression = {ref: net_profit} / {ref: total_assets}
  → engine.compile() → SQL: SELECT net_profit/total_assets FROM fund_financials
  → source_binder.resolve() → 连接 DB1 执行 → 返回 0.042 (4.2%)
"""

from .expression_engine import ExpressionEngine, ExpressionType
from .source_binder import SourceBinder
from .concept_registry import ConceptRegistry

__all__ = ["ExpressionEngine", "ExpressionType", "SourceBinder", "ConceptRegistry"]
__version__ = "0.1.0"
