# config.py
import os
import json
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


def validate_config():
    """启动时校验关键配置项是否存在"""
    errors = []

    # 数据库必填项
    required_db = {
        "DB_HOST": DB_CONFIG["host"],
        "DB_PASSWORD": DB_CONFIG["password"],
    }
    for name, val in required_db.items():
        if not val:
            errors.append(f"缺少必填配置: {name}")

    # 钉钉必填项
    for name, val in DINGTALK_CONFIG.items():
        env_key = f"DINGTALK_{name.upper()}"
        if not val:
            errors.append(f"缺少必填配置: {env_key}")

    # 主 Excel 路径
    if not FILE_PATHS.get("main_excel"):
        errors.append("缺少必填配置: MAIN_EXCEL_PATH")

    if errors:
        msg = "配置校验失败，请检查 .env 文件:\n" + "\n".join(f"  - {e}" for e in errors)
        raise SystemExit(msg)


# 数据库配置
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "tracking"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

# 钉钉机器人配置
DINGTALK_CONFIG = {
    "app_key": os.getenv("DINGTALK_APP_KEY"),
    "app_secret": os.getenv("DINGTALK_APP_SECRET"),
    "robot_code": os.getenv("DINGTALK_ROBOT_CODE"),
}

# 业务逻辑解析
try:
    MANAGER_MAPPING: dict = json.loads(os.getenv("MANAGER_MAPPING") or "{}")
except json.JSONDecodeError as e:
    raise ValueError(f"配置项 MANAGER_MAPPING 的 JSON 格式有误: {e}")

try:
    US_SITE_MANAGER: list = json.loads(os.getenv("US_SITE_MANAGER") or "[]")
except json.JSONDecodeError as e:
    raise ValueError(f"配置项 US_SITE_MANAGER 的 JSON 格式有误: {e}")

# 爬虫账号配置
CREDENTIALS = {
    "袋你飞": {
        "user": os.getenv("DAINIFEI_USERNAME"),
        "pwd": os.getenv("DAINIFEI_PASSWORD")
    },
    "海桥": {
        "user": os.getenv("HAIQIAO_USERNAME"),
        "pwd": os.getenv("HAIQIAO_PASSWORD")
    },
    "纽酷": {
        "user": os.getenv("NIUKU_USERNAME"),
        "pwd": os.getenv("NIUKU_PASSWORD")
    },
    "丛林鸟": {
        "user": os.getenv("CLN_USERNAME"),
        "pwd": os.getenv("CLN_PASSWORD")
    },
    "心达": {
        "user": os.getenv("XINDA_USERNAME"),
        "pwd": os.getenv("XINDA_PASSWORD")
    }
}

# 文件路径配置
FILE_PATHS = {
    "chenzhou": os.getenv("CHENZHOU_FILE_PATH"),
    "oujie": os.getenv("OUJIE_FILE_PATH"),
    "main_excel": os.getenv("MAIN_EXCEL_PATH")
}

validate_config()