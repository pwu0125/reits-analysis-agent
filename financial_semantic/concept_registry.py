"""
概念注册表 — Concept Registry

管理 REITs 财务概念的完整生命周期:
  - 注册 (register)
  - 查询 (get / list / search)
  - 更新 (update)
  - 删除 (delete)
  - 持久化 (JSON 文件)

概念分类:
  valuation   — 估值类 (P/NAV, ROA, 资产负债率)
  performance — 业绩类 (ROA, 净利润率, 营收增速)
  market      — 市场类 (涨跌幅, 波动率)
  dividend    — 分红类 (分红率, DPU)
  operational — 运营类 (出租率, WALE — Phase 3)
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import os
import json
import re
import time


class ConceptError(Exception):
    """概念错误"""
    pass


class ConceptRegistry:
    """
    概念注册表 — JSON 文件持久化
    
    Usage:
        registry = ConceptRegistry("/path/to/concepts/")
        registry.register("ROA", roa_definition)
        concept = registry.get("ROA")
        results = registry.search("资产")
    """
    
    # 允许的分类
    VALID_CATEGORIES = {"valuation", "performance", "market", "dividend", "operational"}
    
    def __init__(self, concepts_dir: str):
        """
        Args:
            concepts_dir: 概念 JSON 文件存储目录 (e.g., financial_semantic/concepts/)
        """
        self._concepts_dir = concepts_dir
        self._concepts: Dict[str, Dict] = {}
        self._load_all()
    
    # ─── 持久化 ────────────────────────────────────────────
    
    def _load_all(self):
        """从 JSON 文件加载所有概念"""
        if not os.path.isdir(self._concepts_dir):
            os.makedirs(self._concepts_dir, exist_ok=True)
            return
        
        for filename in os.listdir(self._concepts_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self._concepts_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        concepts = json.load(f)
                    if isinstance(concepts, list):
                        for concept in concepts:
                            self._concepts[concept["id"]] = concept
                    elif isinstance(concepts, dict):
                        self._concepts[concepts["id"]] = concepts
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"⚠️ 跳过 {filename}: {e}")
    
    def _save_category(self, category: str):
        """保存一个分类的所有概念到 JSON 文件"""
        os.makedirs(self._concepts_dir, exist_ok=True)
        
        concepts_in_cat = [
            c for c in self._concepts.values()
            if c.get("category") == category
        ]
        
        filepath = os.path.join(self._concepts_dir, f"{category}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(concepts_in_cat, f, ensure_ascii=False, indent=2)
    
    # ─── CRUD ──────────────────────────────────────────────
    
    def register(self, concept: Dict) -> str:
        """
        注册一个概念
        
        Args:
            concept: 概念定义 dict，必须含 id/name_zh/category/expression
        
        Returns:
            concept_id
        
        Raises:
            ConceptError: 概念定义不完整或重复
        """
        required = ["id", "name_zh", "category", "expression"]
        missing = [f for f in required if f not in concept]
        if missing:
            raise ConceptError(f"概念定义缺少必填字段: {missing}")
        
        if concept["category"] not in self.VALID_CATEGORIES:
            raise ConceptError(
                f"无效分类 '{concept['category']}', 允许: {self.VALID_CATEGORIES}"
            )
        
        # 校验表达式
        from .expression_engine import validate as validate_expr
        valid, err = validate_expr(concept["expression"])
        if not valid:
            raise ConceptError(f"表达式校验失败: {err}")
        
        concept_id = concept["id"]
        
        # 添加元数据
        if "version" not in concept:
            concept["version"] = 1
        if "created_at" not in concept:
            concept["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        concept["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        
        self._concepts[concept_id] = concept
        self._save_category(concept["category"])
        
        return concept_id
    
    def get(self, concept_id: str) -> Optional[Dict]:
        """获取概念定义"""
        return self._concepts.get(concept_id)
    
    def list_by_category(self, category: Optional[str] = None) -> List[Dict]:
        """按分类列概念"""
        if category:
            return [c for c in self._concepts.values() if c.get("category") == category]
        return list(self._concepts.values())
    
    def search(self, query: str, field: str = "name_zh") -> List[Dict]:
        """
        搜索概念 (模糊匹配)
        
        Args:
            query: 搜索词
            field: 搜索字段 (name_zh / name_en / id / synonyms)
        
        Returns:
            匹配的概念列表
        """
        results = []
        q_lower = query.lower()
        
        for concept in self._concepts.values():
            if field in ("name_zh", "name_en", "id"):
                value = str(concept.get(field, "")).lower()
                if q_lower in value:
                    results.append(concept)
                    continue
            
            # 也搜索同义词
            synonyms = concept.get("synonyms", [])
            for syn in synonyms:
                if q_lower in syn.lower():
                    results.append(concept)
                    break
        
        return results
    
    def update(self, concept_id: str, updates: Dict):
        """更新概念的部分字段"""
        if concept_id not in self._concepts:
            raise ConceptError(f"概念不存在: {concept_id}")
        
        concept = self._concepts[concept_id]
        
        # 不允许修改 id
        if "id" in updates:
            del updates["id"]
        
        concept.update(updates)
        concept["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        
        # 如果修改了 expression，重新校验
        if "expression" in updates:
            from .expression_engine import validate as validate_expr
            valid, err = validate_expr(updates["expression"])
            if not valid:
                raise ConceptError(f"表达式校验失败: {err}")
        
        self._save_category(concept["category"])
    
    def delete(self, concept_id: str):
        """删除概念"""
        if concept_id not in self._concepts:
            raise ConceptError(f"概念不存在: {concept_id}")
        
        concept = self._concepts.pop(concept_id)
        self._save_category(concept["category"])
    
    def stats(self) -> Dict:
        """注册表统计"""
        by_cat = {}
        for c in self._concepts.values():
            cat = c.get("category", "unknown")
            by_cat[cat] = by_cat.get(cat, 0) + 1
        
        return {
            "total": len(self._concepts),
            "by_category": by_cat,
            "categories_covered": len(by_cat),
        }
