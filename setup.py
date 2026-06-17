"""
REITs多智能体分析系统 — 安装配置

GitHub仓库名: reits-analysis-agent
Python包名: knowledge_retrieval（内部导入约定）
"""
from setuptools import setup, find_packages

setup(
    name="knowledge_retrieval",
    version="3.0.0",
    description="中国基础设施公募REITs多智能体分析系统",
    author="pyemini",
    packages=find_packages(include=["*"], exclude=["mcp_servers.*", "finetune.*", "docker.*"]),
    python_requires=">=3.10",
    install_requires=[
        "openai-agents>=1.0.0",
        "openai>=1.0.0",
        "pymysql>=1.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "pymilvus>=2.3.0",
        "elasticsearch>=8.0.0",
        "matplotlib>=3.7.0",
        "python-dotenv>=1.0.0",
    ],
)
