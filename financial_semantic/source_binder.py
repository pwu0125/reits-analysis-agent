"""
数据源绑定器 — Source Binder

将概念表达式中的逻辑引用 (e.g., "net_profit") 解析为实际数据源的表.列。

支持的数据源:
  DB1  — reits_financials.db (SQLite)    76 REITs, 18 汇总财务指标
  DB3  — reits_financial.db (SQLite)     14 REITs, 三张报表明细
  MYSQL — reits (MySQL)                  28 REITs, 行情/分红/产品

数据源注册:
  每个数据源在 __init__ 时自动注册已知字段，
  外部可通过 add_source() / add_binding() 动态扩展。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import os


class SourceBinding:
    """单个数据源绑定 — 一个逻辑 ref → 一个物理表列"""
    __slots__ = ("ref_name", "source", "table", "column", "db_path")
    
    def __init__(
        self,
        ref_name: str,
        source: str,
        table: str,
        column: str,
        db_path: str = "",
    ):
        self.ref_name = ref_name
        self.source = source
        self.table = table
        self.column = column
        self.db_path = db_path


class SourceBinder:
    """
    数据源绑定器 — 管理所有概念字段 → 物理表的映射
    
    Usage:
        binder = SourceBinder()
        binder.add_source("DB1", db_path="/path/to/reits_financials.db",
                          table="fund_financials")
        binder.add_binding("net_profit", "DB1", "fund_financials", "net_profit")
        
        # 解析引用
        binding = binder.resolve("net_profit")
        # → {"source": "DB1", "table": "fund_financials", "column": "net_profit"}
    """
    
    def __init__(self):
        self._bindings: Dict[str, SourceBinding] = {}
        self._sources: Dict[str, Dict] = {}
        self._synonyms: Dict[str, str] = {}  # 同义词映射: alias → ref_name
        
        # 注册默认数据源
        self._register_default_sources()
        self._register_default_bindings()
        self._register_default_synonyms()
    
    # ─── 数据源管理 ─────────────────────────────────────────
    
    def _register_default_sources(self):
        """注册默认数据源"""
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        self._sources["DB1"] = {
            "name": "reits_financials.db",
            "type": "sqlite",
            "table": "fund_financials",
            "db_path": os.path.join(os.path.dirname(base), "reits_financials.db"),
            "description": "76 REITs 核心财务指标 (Phase 1 pdfplumber 提取)",
            "key_column": "ts_code",
            "time_column": "report_date",
        }
        
        self._sources["MYSQL"] = {
            "name": "reits (MySQL)",
            "type": "mysql",
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "Reits2025!",
            "database": "reits",
            "description": "28 REITs 行情/分红/产品信息",
            "key_column": "fund_code",
        }
    
    def add_source(self, source_id: str, **kwargs):
        """注册新数据源"""
        self._sources[source_id] = kwargs
    
    def get_source(self, source_id: str) -> Optional[Dict]:
        """获取数据源配置"""
        return self._sources.get(source_id)
    
    def get_table(self, source_id: str) -> str:
        """获取数据源默认表名"""
        source = self._sources.get(source_id)
        if source is None:
            raise KeyError(f"未知数据源: {source_id}")
        return source["table"]
    
    def get_db_path(self, source_id: str) -> str:
        """获取 SQLite 数据源 db 路径"""
        source = self._sources.get(source_id)
        if source is None:
            raise KeyError(f"未知数据源: {source_id}")
        if source["type"] != "sqlite":
            raise TypeError(f"数据源 {source_id} 不是 SQLite 类型")
        return source["db_path"]
    
    # ─── 字段绑定 ───────────────────────────────────────────
    
    def _register_default_bindings(self):
        """注册默认字段绑定 (DB1 的 18 个财务字段)"""
        db1_fields = [
            ("total_assets", "总资产"),
            ("total_liabilities", "总负债"),
            ("net_assets", "净资产"),
            ("revenue", "营业收入"),
            ("net_profit", "净利润"),
            ("operating_profit", "营业利润"),
            ("total_comprehensive_income", "综合收益总额"),
            ("operating_cash_flow", "经营性现金流"),
            ("investing_cash_flow", "投资性现金流"),
            ("financing_cash_flow", "融资性现金流"),
        ]
        
        for ref_name, description in db1_fields:
            self.add_binding(
                ref_name=ref_name,
                source="DB1",
                table="fund_financials",
                column=ref_name,
                description=description,
            )
    
    def add_binding(
        self,
        ref_name: str,
        source: str,
        table: str,
        column: str,
        description: str = "",
    ):
        """注册一个字段绑定"""
        db_path = ""
        if source in self._sources and self._sources[source]["type"] == "sqlite":
            db_path = self._sources[source]["db_path"]
        
        self._bindings[ref_name] = SourceBinding(
            ref_name=ref_name,
            source=source,
            table=table,
            column=column,
            db_path=db_path,
        )
    
    def resolve(self, ref_name: str) -> Optional[Dict]:
        """
        解析逻辑引用为实际表列信息
        
        查找链: 
          1. 精确匹配 ref_name
          2. 同义词映射
          3. 返回 None
        
        Returns:
            {"source": "DB1", "table": "fund_financials", "column": "net_profit", "db_path": "..."}
        """
        # 精确匹配
        if ref_name in self._bindings:
            b = self._bindings[ref_name]
            return {
                "source": b.source,
                "table": b.table,
                "column": b.column,
                "db_path": b.db_path,
            }
        
        # 同义词匹配
        if ref_name in self._synonyms:
            canonical = self._synonyms[ref_name]
            return self.resolve(canonical)
        
        return None
    
    def list_bindings(self, source: Optional[str] = None) -> List[Dict]:
        """列出所有绑定 (可按数据源过滤)"""
        result = []
        for ref_name, binding in self._bindings.items():
            if source is None or binding.source == source:
                result.append({
                    "ref_name": ref_name,
                    "source": binding.source,
                    "column": binding.column,
                })
        return sorted(result, key=lambda x: x["ref_name"])
    
    # ─── 同义词管理 ─────────────────────────────────────────
    
    def _register_default_synonyms(self):
        """注册默认同义词 — 解决招募书用语不一致问题"""
        defaults = {
            # 财务概念同义词
            "营收": "revenue",
            "总收入": "revenue",
            "营业总收入": "revenue",
            "利润": "net_profit",
            "净利": "net_profit",
            "总资产": "total_assets",
            "资产总计": "total_assets",
            "总负债": "total_liabilities",
            "负债合计": "total_liabilities",
            "净资产": "net_assets",
            "经营性现金流": "operating_cash_flow",
            "经营活动现金流": "operating_cash_flow",
            "经营现金流": "operating_cash_flow",
            # 将注册更多 Phase 2 同义词
        }
        self._synonyms.update(defaults)
    
    def add_synonym(self, alias: str, canonical: str):
        """添加同义词映射"""
        self._synonyms[alias] = canonical
    
    def list_synonyms(self, canonical: Optional[str] = None) -> Dict[str, str]:
        """列同义词"""
        if canonical:
            return {k: v for k, v in self._synonyms.items() if v == canonical}
        return dict(self._synonyms)
    
    # ─── 工具方法 ───────────────────────────────────────────
    
    def get_sources_summary(self) -> str:
        """数据源摘要"""
        lines = []
        for sid, src in self._sources.items():
            n_bindings = len([b for b in self._bindings.values() if b.source == sid])
            lines.append(f"  {sid}: {src['name']} ({src['type']}) — {n_bindings} 字段绑定")
        return "\n".join(lines)
