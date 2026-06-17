# config/db_config.py
# 数据库配置

import os


def get_db_announcement_config():
    """
    返回 MySQL 数据库连接配置（优先读取环境变量）。
    环境变量：
      - DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_DATABASE
    默认数据库名：reits（部署环境实际DB名）
    """
    db_announcement_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_DATABASE', 'reits'),
        'charset': 'utf8mb4',
        'init_command': "SET SESSION collation_connection = 'utf8mb4_unicode_ci'"
    }
    return db_announcement_config


def get_vector_db_config():
    """
    返回向量数据库（Milvus）的连接配置信息（优先读取环境变量）。
    环境变量：MILVUS_HOST, MILVUS_PORT
    默认：localhost:19530（Docker部署）
    """
    vector_db_config = {
        'host': os.getenv('MILVUS_HOST', 'localhost'),
        'port': int(os.getenv('MILVUS_PORT', '19530')),
        'user': os.getenv('MILVUS_USER', ''),
        'password': os.getenv('MILVUS_PASSWORD', '')
    }
    return vector_db_config

def get_elasticsearch_config():
    """
    返回 Elasticsearch 数据库的连接配置信息（优先读取环境变量）。
    环境变量：ES_HOST, ES_PORT
    默认：localhost:9200, http, 无认证（Docker部署）
    """
    elasticsearch_config = {
        'host': os.getenv('ES_HOST', 'localhost'),
        'port': int(os.getenv('ES_PORT', '9200')),
        'username': os.getenv('ES_USERNAME', ''),
        'password': os.getenv('ES_PASSWORD', ''),
        'scheme': os.getenv('ES_SCHEME', 'http')
    }
    return elasticsearch_config