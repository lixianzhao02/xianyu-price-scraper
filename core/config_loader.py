# -*- coding: utf-8 -*-
"""
配置加载模块 — 从 config.yaml 读取配置
"""

import os
import yaml
from pathlib import Path

_CONFIG = None


def get_config_path():
    """获取配置文件路径"""
    # 优先环境变量，其次默认路径
    env_path = os.environ.get("XIANYU_CONFIG")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent / "config.yaml"


def load_config():
    """加载配置文件"""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    path = get_config_path()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        _CONFIG = yaml.safe_load(f)

    return _CONFIG


def get_db_config():
    """获取数据库配置"""
    cfg = load_config()
    return cfg.get("database", {})


def get_scraper_config():
    """获取爬虫配置"""
    cfg = load_config()
    return cfg.get("scraper", {})


def get_pricing_config():
    """获取价格算法配置"""
    cfg = load_config()
    return cfg.get("pricing", {})


def get_output_config():
    """获取输出配置"""
    cfg = load_config()
    return cfg.get("output", {})


def get_schedule_config():
    """获取定时任务配置"""
    cfg = load_config()
    return cfg.get("schedule", {})
