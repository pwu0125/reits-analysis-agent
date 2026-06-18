#!/usr/bin/env python3
"""
财务语义层 — 全链路 Demo

注册 5 个试点概念 → 编译 JSON 表达式 → 生成 SQL → 执行查询 → 返回结果

试点概念 (全部来自 DB1, 无需跨源):
  1. ROA         = net_profit / total_assets
  2. 资产负债率   = total_liabilities / total_assets
  3. 净利润率     = net_profit / revenue
  4. CFO/营收比   = operating_cash_flow / revenue

运行:
  cd REITs/REITs_Text_data_pipeline/reits-analysis-agent
  python3 -m financial_semantic.demo
"""

import sys
import os
import json
import sqlite3

# 确保 financial_semantic 可导入
_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _base not in sys.path:
    sys.path.insert(0, _base)

from financial_semantic.expression_engine import ExpressionEngine, validate, to_json
from financial_semantic.source_binder import SourceBinder
from financial_semantic.concept_registry import ConceptRegistry, ConceptError


def setup_registry(concepts_dir: str) -> ConceptRegistry:
    """初始化注册表并注册5个试点概念"""
    registry = ConceptRegistry(concepts_dir)
    
    # ─── 概念定义 ────────────────────────────────────────
    concepts = [
        {
            "id": "roa",
            "name_zh": "总资产收益率 (ROA)",
            "name_en": "Return on Assets",
            "category": "performance",
            "synonyms": ["ROA", "资产回报率", "总资产回报率"],
            "unit": "%",
            "expression": {
                "type": "division",
                "numerator": {"type": "ref", "name": "net_profit"},
                "denominator": {"type": "ref", "name": "total_assets"}
            }
        },
        {
            "id": "debt_ratio",
            "name_zh": "资产负债率",
            "name_en": "Debt-to-Asset Ratio",
            "category": "valuation",
            "synonyms": ["负债率", "杠杆率", "资产负债比率"],
            "unit": "%",
            "expression": {
                "type": "division",
                "numerator": {"type": "ref", "name": "total_liabilities"},
                "denominator": {"type": "ref", "name": "total_assets"}
            }
        },
        {
            "id": "net_margin",
            "name_zh": "净利润率",
            "name_en": "Net Profit Margin",
            "category": "performance",
            "synonyms": ["利润率", "净利率", "净利润占比"],
            "unit": "%",
            "expression": {
                "type": "division",
                "numerator": {"type": "ref", "name": "net_profit"},
                "denominator": {"type": "ref", "name": "revenue"}
            }
        },
        {
            "id": "cfo_revenue_ratio",
            "name_zh": "经营性现金流/营收比",
            "name_en": "CFO-to-Revenue Ratio",
            "category": "performance",
            "synonyms": ["CFO占比", "现金流营收比", "经营现金流比率"],
            "unit": "%",
            "expression": {
                "type": "division",
                "numerator": {"type": "ref", "name": "operating_cash_flow"},
                "denominator": {"type": "ref", "name": "revenue"}
            }
        },
    ]
    
    for concept in concepts:
        try:
            rid = registry.register(concept)
            print(f"  ✅ 已注册: {concept['id']} — {concept['name_zh']}")
        except ConceptError as e:
            print(f"  ⚠️ 注册失败 {concept['id']}: {e}")
    
    return registry


def demo_compile_and_build():
    """编译表达式并生成 SQL"""
    engine = ExpressionEngine()
    binder = SourceBinder()
    
    concepts_dir = os.path.join(_base, "financial_semantic", "concepts")
    registry = ConceptRegistry(concepts_dir)
    
    print("\n" + "=" * 60)
    print("📐 表达式 → SQL 编译测试")
    print("=" * 60)
    
    test_fund = "180101"
    test_date = "2025-12-31"
    
    for concept_id in ["roa", "debt_ratio", "net_margin", "cfo_revenue_ratio"]:
        concept = registry.get(concept_id)
        if not concept:
            print(f"  ⚠️ 未找到概念: {concept_id}")
            continue
        
        expr = concept["expression"]
        
        # 校验
        valid, err = validate(expr)
        assert valid, f"表达式无效: {err}"
        
        # 编译
        fragment = engine.compile(expr, binder)
        
        # 生成 SQL
        table = binder.get_table("DB1")
        sql, params = engine.build_sql(
            fragment,
            table,
            filters={"ts_code": test_fund, "report_date": test_date}
        )
        
        sql_display = sql
        for p in params:
            sql_display = sql_display.replace("?", repr(p), 1)
        
        print(f"\n  📌 {concept['name_zh']} ({concept_id})")
        print(f"     表达式: {to_json(expr, indent=0).replace(chr(10), ' ')}")
        print(f"     SQL:     {sql_display}")
    
    return engine, binder, registry


def demo_execute():
    """执行查询 — 针对 180101 (蛇口产园) 2025年报"""
    engine = ExpressionEngine()
    binder = SourceBinder()
    concepts_dir = os.path.join(_base, "financial_semantic", "concepts")
    registry = ConceptRegistry(concepts_dir)
    
    db_path = binder.get_db_path("DB1")
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    
    print("\n" + "=" * 60)
    print("🔢 实际查询执行 — DB1 → reits_financials.db")
    print("=" * 60)
    
    test_cases = [
        ("180101", "2025-12-31", "蛇口产园 2025年报"),
        ("180101", "2024-12-31", "蛇口产园 2024年报"),
        ("508056", "2025-12-31", "普洛斯 2025年报"),
    ]
    
    for ts_code, report_date, label in test_cases:
        print(f"\n  🏢 {label} (ts_code={ts_code})")
        print(f"  {'─' * 50}")
        
        for concept_id in ["roa", "debt_ratio", "net_margin", "cfo_revenue_ratio"]:
            concept = registry.get(concept_id)
            if not concept:
                continue
            
            try:
                fragment = engine.compile(concept["expression"], binder)
                sql, params = engine.build_sql(
                    fragment,
                    binder.get_table("DB1"),
                    filters={"ts_code": ts_code, "report_date": report_date}
                )
                
                cursor = db.execute(sql, params)
                row = cursor.fetchone()
                
                if row and row["value"] is not None:
                    value = row["value"]
                    if concept.get("unit") == "%":
                        pct = value * 100
                        print(f"  {concept['name_zh']:12s} = {pct:8.2f}%  (raw={value:.6f})")
                    else:
                        print(f"  {concept['name_zh']:12s} = {value:10.4f}")
                else:
                    # 检查是否某个字段为 null
                    debug_sql = f"SELECT net_profit, total_assets, total_liabilities, revenue, operating_cash_flow FROM fund_financials WHERE ts_code='{ts_code}' AND report_date='{report_date}'"
                    debug_row = db.execute(debug_sql).fetchone()
                    if debug_row:
                        null_fields = [k for k in debug_row.keys() if debug_row[k] is None]
                        print(f"  {concept['name_zh']:12s} = NULL (缺少字段: {null_fields})")
                    else:
                        print(f"  {concept['name_zh']:12s} = N/A (无数据)")
                    
            except Exception as e:
                print(f"  {concept['name_zh']:12s} = ERROR: {e}")
    
    db.close()
    
    # ─── 汇总: 多少 REITs 有 2025 年报数据? ───
    db2 = sqlite3.connect(db_path)
    n = db2.execute(
        "SELECT COUNT(DISTINCT ts_code) FROM fund_financials WHERE report_date='2025-12-31'"
    ).fetchone()[0]
    print(f"\n  📊 DB1 覆盖: {n} 只 REITs 有 2025 年报数据")
    db2.close()


def demo_registry_stats():
    """注册表统计"""
    concepts_dir = os.path.join(_base, "financial_semantic", "concepts")
    registry = ConceptRegistry(concepts_dir)
    stats = registry.stats()
    
    print("\n" + "=" * 60)
    print("📋 概念注册表统计")
    print("=" * 60)
    print(f"  总概念数: {stats['total']}")
    for cat, count in stats["by_category"].items():
        print(f"    {cat}: {count}")


if __name__ == "__main__":
    concepts_dir = os.path.join(_base, "financial_semantic", "concepts")
    registry = setup_registry(concepts_dir)
    demo_compile_and_build()
    demo_execute()
    demo_registry_stats()
    print("\n🎉 全链路 Demo 完成!")
