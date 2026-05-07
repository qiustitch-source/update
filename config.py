# config.py
import os
import json
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

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
# 使用 json.loads 将字符串解析为 Python 字典/列表
MANAGER_MAPPING = json.loads(os.getenv("MANAGER_MAPPING", "{}"))
US_SITE_MANAGER = json.loads(os.getenv("US_SITE_MANAGER", "[]"))

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