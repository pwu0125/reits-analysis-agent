"""
表达式引擎 — Expression Engine

将 JSON 表达式树编译为可执行 SQL 片段。

支持的运算类型 (7种):
  ref         引用数据源字段 (e.g., {"type":"ref","name":"revenue"})
  literal     常数 (e.g., {"type":"literal","value":1.09})
  add         二元加法 (e.g., {"type":"add","left":...,"right":...})
  multiply    二元乘法 (e.g., {"type":"multiply","left":...,"right":...})
  division    二元除法 (e.g., {"type":"division","numerator":...,"denominator":...})
  aggregate   聚合函数 (e.g., {"type":"aggregate","func":"sum","expr":...})
  cross_source 跨源组合 (e.g., {"type":"cross_source","sources":[...]})

编译流程:
  1. validate(expr)        → 校验表达式树结构
  2. compile(expr, binder) → 递归遍历，生成 SQL 片段
  3. build_sql(fragments)  → 组装完整 SQL 查询

设计原则:
  - 纯 Python, 零外部依赖 (标准库 only)
  - 表达式树不可变 — 编译过程不改原材料
  - 编译结果可缓存 (未来 feature)
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Tuple
import json
import re


class ExpressionType(Enum):
    """表达式节点类型"""
    REF = "ref"
    LITERAL = "literal"
    ADD = "add"
    MULTIPLY = "multiply"
    DIVISION = "division"
    AGGREGATE = "aggregate"
    CROSS_SOURCE = "cross_source"


class ExpressionError(Exception):
    """表达式错误"""
    pass


class ValidationError(ExpressionError):
    """表达式校验错误"""
    pass


class CompileError(ExpressionError):
    """表达式编译错误"""
    pass


# ─── SQL Fragment ──────────────────────────────────────────────

class SQLFragment:
    """
    SQL 编译片段 — 编译过程的中间产物
    
    一棵表达式树编译后产生一棵 SQLFragment 树，
    根节点的 .sql 就是最终的 SQL 表达式字符串。
    """
    __slots__ = ("sql", "params", "source_refs", "is_aggregated")
    
    def __init__(
        self,
        sql: str = "",
        params: Optional[List[Any]] = None,
        source_refs: Optional[List[str]] = None,
        is_aggregated: bool = False,
    ):
        self.sql = sql
        self.params = params or []
        self.source_refs = source_refs or []
        self.is_aggregated = is_aggregated
    
    def __repr__(self):
        return f"SQLFragment(sql={self.sql!r}, params={self.params}, refs={self.source_refs})"


# ─── Expression Validator ──────────────────────────────────────

def validate(expr: Dict) -> Tuple[bool, Optional[str]]:
    """
    校验表达式树结构
    
    Returns:
        (valid, error_message) — 有效时 error_message=None
    """
    if not isinstance(expr, dict):
        return False, f"表达式必须是 dict, 收到 {type(expr).__name__}"
    
    expr_type = expr.get("type")
    if expr_type is None:
        return False, "表达式必须有 'type' 字段"
    
    if expr_type not in [e.value for e in ExpressionType]:
        return False, f"未知表达式类型: {expr_type}, 支持: {[e.value for e in ExpressionType]}"
    
    # 递归校验子节点
    if expr_type == ExpressionType.REF.value:
        if "name" not in expr:
            return False, "ref 表达式必须有 'name' 字段"
    
    elif expr_type == ExpressionType.LITERAL.value:
        if "value" not in expr:
            return False, "literal 表达式必须有 'value' 字段"
        if not isinstance(expr["value"], (int, float)):
            return False, f"literal value 必须是数字, 收到 {type(expr['value']).__name__}"
    
    elif expr_type in (ExpressionType.ADD.value, ExpressionType.MULTIPLY.value):
        if "left" not in expr or "right" not in expr:
            return False, f"{expr_type} 表达式必须有 'left' 和 'right' 字段"
        left_valid, left_err = validate(expr["left"])
        if not left_valid:
            return False, f"left: {left_err}"
        right_valid, right_err = validate(expr["right"])
        if not right_valid:
            return False, f"right: {right_err}"
    
    elif expr_type == ExpressionType.DIVISION.value:
        if "numerator" not in expr or "denominator" not in expr:
            return False, "division 表达式必须有 'numerator' 和 'denominator' 字段"
        num_valid, num_err = validate(expr["numerator"])
        if not num_valid:
            return False, f"numerator: {num_err}"
        den_valid, den_err = validate(expr["denominator"])
        if not den_valid:
            return False, f"denominator: {den_err}"
    
    elif expr_type == ExpressionType.AGGREGATE.value:
        if "func" not in expr or "expr" not in expr:
            return False, "aggregate 表达式必须有 'func' 和 'expr' 字段"
        valid_funcs = {"sum", "avg", "max", "min", "count", "median"}
        if expr["func"] not in valid_funcs:
            return False, f"aggregate func 必须是 {valid_funcs}, 收到 {expr['func']}"
        sub_valid, sub_err = validate(expr["expr"])
        if not sub_valid:
            return False, f"aggregate.expr: {sub_err}"
    
    elif expr_type == ExpressionType.CROSS_SOURCE.value:
        if "sources" not in expr:
            return False, "cross_source 表达式必须有 'sources' 字段"
        if not isinstance(expr["sources"], list) or len(expr["sources"]) < 2:
            return False, "cross_source 的 sources 必须是长度≥2的列表"
    
    return True, None


# ─── Expression Compiler ───────────────────────────────────────

class ExpressionCompiler:
    """
    表达式编译器 — 将 JSON 表达式树递归编译为 SQLFragment 树
    
    Usage:
        engine = ExpressionCompiler()
        fragment = engine.compile(expression, source_binder)
        print(fragment.sql)  # "net_profit / NULLIF(total_assets, 0)"
    """
    
    # 聚合函数 SQL 映射
    AGG_FUNCS = {
        "sum": "SUM",
        "avg": "AVG",
        "max": "MAX",
        "min": "MIN",
        "count": "COUNT",
        "median": "MEDIAN",
    }
    
    def compile(
        self,
        expr: Dict,
        binder: "SourceBinder",
    ) -> SQLFragment:
        """
        编译表达式树为 SQL 片段
        
        Args:
            expr: JSON 表达式树
            binder: SourceBinder 实例，用于解析 ref → 实际表列
        
        Returns:
            SQLFragment — 编译后的 SQL 片段树
        """
        valid, err = validate(expr)
        if not valid:
            raise CompileError(f"表达式无效: {err}")
        
        expr_type = expr["type"]
        
        if expr_type == ExpressionType.REF.value:
            return self._compile_ref(expr, binder)
        elif expr_type == ExpressionType.LITERAL.value:
            return self._compile_literal(expr)
        elif expr_type == ExpressionType.ADD.value:
            return self._compile_binary(expr, binder, " + ")
        elif expr_type == ExpressionType.MULTIPLY.value:
            return self._compile_binary(expr, binder, " * ")
        elif expr_type == ExpressionType.DIVISION.value:
            return self._compile_division(expr, binder)
        elif expr_type == ExpressionType.AGGREGATE.value:
            return self._compile_aggregate(expr, binder)
        elif expr_type == ExpressionType.CROSS_SOURCE.value:
            return self._compile_cross_source(expr, binder)
        else:
            raise CompileError(f"未实现的表达式类型: {expr_type}")
    
    def _compile_ref(self, expr: Dict, binder: "SourceBinder") -> SQLFragment:
        """编译 ref 节点: 将逻辑引用解析为实际表列"""
        ref_name = expr["name"]
        binding = binder.resolve(ref_name)
        if binding is None:
            raise CompileError(f"未找到数据源绑定: {ref_name}")
        
        return SQLFragment(
            sql=binding["column"],
            source_refs=[binding["source"]],
        )
    
    def _compile_literal(self, expr: Dict) -> SQLFragment:
        """编译 literal 节点: 常数值"""
        value = expr["value"]
        return SQLFragment(
            sql=str(value),
            params=[value],
        )
    
    def _compile_binary(self, expr: Dict, binder: "SourceBinder", operator: str) -> SQLFragment:
        """编译二元运算 (add / multiply)"""
        # 确定字段名 (add→left/right, multiply→left/right)
        left_key = "left"
        right_key = "right"
        
        left = self.compile(expr[left_key], binder)
        right = self.compile(expr[right_key], binder)
        
        return SQLFragment(
            sql=f"({left.sql} {operator} {right.sql})",
            params=left.params + right.params,
            source_refs=list(set(left.source_refs + right.source_refs)),
            is_aggregated=left.is_aggregated or right.is_aggregated,
        )
    
    def _compile_division(self, expr: Dict, binder: "SourceBinder") -> SQLFragment:
        """编译除法: 自动添加 NULLIF(denominator, 0) 防除零"""
        numerator = self.compile(expr["numerator"], binder)
        denominator = self.compile(expr["denominator"], binder)
        
        # 防除零保护
        denom_sql = f"NULLIF({denominator.sql}, 0)"
        
        return SQLFragment(
            sql=f"({numerator.sql} / {denom_sql})",
            params=numerator.params + denominator.params,
            source_refs=list(set(numerator.source_refs + denominator.source_refs)),
            is_aggregated=numerator.is_aggregated or denominator.is_aggregated,
        )
    
    def _compile_aggregate(self, expr: Dict, binder: "SourceBinder") -> SQLFragment:
        """编译聚合: SUM/AVG/MAX/MIN/COUNT/MEDIAN"""
        func = expr["func"]
        sql_func = self.AGG_FUNCS[func]
        inner = self.compile(expr["expr"], binder)
        
        return SQLFragment(
            sql=f"{sql_func}({inner.sql})",
            params=inner.params,
            source_refs=inner.source_refs,
            is_aggregated=True,
        )
    
    def _compile_cross_source(self, expr: Dict, binder: "SourceBinder") -> SQLFragment:
        """
        编译跨源组合: 当前仅占位，完整实现见 Phase 3
        
        设计思路:
          1. 解析每个 source 的表达式
          2. 按 JOIN key 拼接
          3. 生成子查询/CTE 包装
        """
        raise CompileError("cross_source 暂未实现 (Phase 3)")


# ─── Query Builder ─────────────────────────────────────────────

class QueryBuilder:
    """
    SQL 查询构建器 — 从编译后的 SQL 片段生成完整 SELECT 语句
    
    Usage:
        builder = QueryBuilder()
        sql = builder.build(
            fragment=fragment,
            table="fund_financials",
            filters={"ts_code": "180101", "report_date": "2025-12-31"}
        )
    """
    
    def build(
        self,
        fragment: SQLFragment,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Tuple[str, List[Any]]:
        """
        构建完整 SELECT 查询
        
        Args:
            fragment: 编译后的 SQL 片段
            table: FROM 子句表名
            filters: WHERE 条件 dict (支持 = 和 IN)
            order_by: ORDER BY 子句
            limit: LIMIT 子句
        
        Returns:
            (sql, params) — 完整 SQL 和参数列表
        """
        sql_parts = [f"SELECT {fragment.sql} AS value"]
        sql_parts.append(f"FROM {table}")
        
        params = []
        if filters:
            conditions = []
            for col, val in filters.items():
                if isinstance(val, (list, tuple)):
                    placeholders = ", ".join("?" * len(val))
                    conditions.append(f"{col} IN ({placeholders})")
                    params.extend(val)
                else:
                    conditions.append(f"{col} = ?")
                    params.append(val)
            if conditions:
                sql_parts.append("WHERE " + " AND ".join(conditions))
        
        if order_by:
            sql_parts.append(f"ORDER BY {order_by}")
        
        if limit is not None:
            sql_parts.append(f"LIMIT {limit}")
        
        return " ".join(sql_parts), params


# ─── Top-Level Engine API ─────────────────────────────────────

class ExpressionEngine:
    """
    表达式引擎顶层 API — 编译 JSON 表达式 → 生成可执行 SQL
    
    Usage:
        engine = ExpressionEngine()
        
        # 定义概念
        concept = {
            "name_zh": "ROA",
            "expression": {
                "type": "division",
                "numerator": {"ref": "net_profit"},
                "denominator": {"ref": "total_assets"}
            }
        }
        
        # 编译 + 生成 SQL
        fragment = engine.compile(concept["expression"], binder)
        sql, params = engine.build_sql(fragment, binder.get_table("DB1"))
        # → "SELECT (net_profit / NULLIF(total_assets, 0)) AS value FROM fund_financials"
    """
    
    def __init__(self):
        self.compiler = ExpressionCompiler()
        self.builder = QueryBuilder()
    
    def compile(self, expr: Dict, binder: "SourceBinder") -> SQLFragment:
        """编译表达式树"""
        return self.compiler.compile(expr, binder)
    
    def build_sql(
        self,
        fragment: SQLFragment,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Tuple[str, List[Any]]:
        """构建完整 SQL"""
        return self.builder.build(fragment, table, filters, order_by, limit)


def to_json(expr: Dict, indent: int = 2) -> str:
    """表达式树 → 格式化 JSON 字符串"""
    return json.dumps(expr, ensure_ascii=False, indent=indent)


def from_json(json_str: str) -> Dict:
    """JSON 字符串 → 表达式树 (含校验)"""
    expr = json.loads(json_str)
    valid, err = validate(expr)
    if not valid:
        raise ValidationError(f"JSON 表达式无效: {err}")
    return expr
