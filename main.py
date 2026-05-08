# main.py
# 物流追踪自动化项目 - 主入口文件
# 功能：编排整个物流追踪流程，包括数据导入、爬虫调度、异常分析、通知推送、数据回写

import os
import json
import logging
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright

# 数据库与配置导入
from database import init_db, batch_upsert_shipments, get_pending_tasks, update_tracking_info
from config import (
    CREDENTIALS, DINGTALK_CONFIG, MANAGER_MAPPING,
    US_SITE_MANAGER, FILE_PATHS
)
from excel_handler import read_and_update_excel
from notice import DingTalkRobot
# 爬虫类导入
from spiders.dainifei import DainifeiSpider
from spiders.haiqiao import HaiqiaoSpider
from spiders.junglebird import JungleBirdSpider
from spiders.xinda import XinDaSpider
from spiders.yipai import YiPaiSpider
from spiders.niuku import NiuKuSpider
from spiders.local_strategies import LocalExcelStrategy

# 配置日志：同时输出到控制台和文件
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)  # 自动创建 logs 目录

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),                                              # 控制台输出
        logging.FileHandler(os.path.join(log_dir, 'app.log'), encoding='utf-8')  # 文件输出
    ]
)

logger = logging.getLogger(__name__)

# 爬虫映射表：建立货代名称与对应类的映射，方便工厂模式调用
# 注意：纽酷（NiuKuSpider）是 API 模式，不继承 BaseSpider，在 main.py 中有特殊处理逻辑
SPIDER_FACTORY = {
    '袋你飞': DainifeiSpider,
    '海桥': HaiqiaoSpider,
    '心达': XinDaSpider,
    '丛林鸟': JungleBirdSpider,
    '易派': YiPaiSpider,
    '纽酷': NiuKuSpider
}

def clean_excel_data(val, is_bool=False):
    """统一的数据清洗工具函数
    将 Excel 中的各种空值（NaN, None, 空字符串等）统一处理为 Python None
    对于布尔字段，支持中文"是/否"和英文"yes/no/true/false"等多种格式
    """
    if pd.isna(val) or str(val).lower() in ['nan', 'nat', 'none', '']:
        return None

    if is_bool:
        val_str = str(val).strip().lower()
        return val_str in ['是', 'yes', '1', 'true', 'y']

    return val

def load_excel_to_db(file_path):
    """读取 Excel 数据并入库（批量操作）
    从指定的 Excel 文件中读取"发货数据详情" sheet，清洗后批量写入数据库
    """
    logger.info(f"正在读取主 Excel 文件: {file_path}")
    try:
        df = pd.read_excel(file_path, sheet_name='发货数据详情', header=1)
        logger.info(f"成功读取到 {len(df)} 行数据")

        data_list = []

        for i, (_, row) in enumerate(df.iterrows(), start=3):
            shipment_id = clean_excel_data(row.get('发货ID'))
            if not shipment_id:
                logger.warning(f"跳过第 {i} 行：发货ID为空")
                continue
            data = {
                'shipment_id': shipment_id,
                'tracking_no': clean_excel_data(row.get('货运单号', '')),
                'forwarder': clean_excel_data(row.get('货代', '')),
                'shop_name': clean_excel_data(row.get('店铺', '')),
                'site': clean_excel_data(row.get('站点', '')),
                'fba_id': clean_excel_data(row.get('货件编号', '')),
                'fba_warehouse': clean_excel_data(row.get('FBA仓库', '')),
                'manager_name': clean_excel_data(row.get('负责人', '')),
                'status': clean_excel_data(row.get('货件在途状态', '')),
                'latest_info': clean_excel_data(row.get('货件状态备注', '')),
                'vessel_voyage': clean_excel_data(row.get('船名航次', '')),
                'etd': clean_excel_data(row.get('开船/起飞日期ETD', '')),
                'eta': clean_excel_data(row.get('到港时间\n（ETA）', '')),
                'signed_at': clean_excel_data(row.get('妥投\n日期', '')),
                'is_inspected': clean_excel_data(row.get('是否有被查验', ''), is_bool=True),
            }
            data_list.append(data)

        batch_upsert_shipments(data_list)

    except Exception as e:
        logger.error(f"Excel 导入数据库失败: {e}")

def process_crawlers(bot=None):
    """使用工厂模式的核心爬虫调度逻辑
    1. 从数据库获取待处理任务（未签收且有货运单号）
    2. 按货代名称分组
    3. 对每组任务：
       - 辰舟/欧杰：使用本地 Excel 策略
       - 纽酷：使用 API 模式（不继承 BaseSpider）
       - 其他：使用 Playwright 浏览器自动化
    4. 每个查询结果更新到数据库
    """
    tasks = get_pending_tasks()
    if not tasks:
        logger.info("暂无待查询任务。")
        return
    logger.info(f"发现 {len(tasks)} 个待查询任务")

    # 按货代对任务进行分组
    tasks_by_fw = {}
    for task in tasks:
        fw = task['forwarder']
        tasks_by_fw.setdefault(fw, []).append(task)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for fw_name, fw_tasks in tasks_by_fw.items():
            logger.info(f">>> 开始处理 [{fw_name}] 任务，共 {len(fw_tasks)} 条")

            try:
                # 1. 处理本地 Excel 策略类的货代
                if fw_name in ['辰舟', '欧杰']:
                    config_key = 'chenzhou' if fw_name == '辰舟' else 'oujie'
                    sheet_idx = 1 if fw_name == '辰舟' else 0
                    spider = LocalExcelStrategy(FILE_PATHS[config_key], fw_name, sheet_idx)
                    for task in fw_tasks:
                        result = spider.search_order(task)
                        if result:
                            update_tracking_info(task['shipment_id'], result, bot=bot)
                    continue

                # 2. 处理在线爬虫类的货代
                spider_cls = SPIDER_FACTORY.get(fw_name)
                if not spider_cls:
                    logger.warning(f"未知货代类型: {fw_name}，跳过。")
                    continue

                cred = CREDENTIALS.get(fw_name, {})
                username = cred.get('user') or ""
                password = cred.get('pwd') or ""

                context = browser.new_context()
                page = context.new_page()

                try:
                    if fw_name == '纽酷':
                        spider = spider_cls(username=username, password=password)
                    else:
                        spider = spider_cls(page, username, password)

                    spider.login()

                    for task in fw_tasks:
                        if fw_name == '纽酷':
                            result = spider.search(task['tracking_no'])
                        else:
                            result = spider.search_with_retry(task['tracking_no'])
                        if result:
                            update_tracking_info(task['shipment_id'], result, bot=bot)

                except Exception as e:
                    logger.error(f"处理货代 [{fw_name}] 时发生内部错误: {e}")
                finally:
                    context.close()
            except Exception as e:
                logger.error(f"处理货代 [{fw_name}] 时发生异常: {e}")

        browser.close()

def analyze_logistics_exceptions():
    """异常货件统计与分类逻辑
    检测三类异常：
    1. 延期：当前日期 - ETA > 5 天（US 站单独统计，其他站按负责人分组）
    2. 查验：is_inspected == True（按负责人分组）
    3. 延误：latest_info 包含"延误"、"延迟"或"延至"（按负责人分组）
    """
    logger.info("\n>>> 开始进行物流异常数据分析...")

    tasks = get_pending_tasks()
    today = datetime.now().date()

    us_exception_list = []
    other_exceptions = {}
    inspections = {}
    delations = {}

    for task in tasks:
        s_id = task['shipment_id']
        site = task['site']
        eta = task['eta']
        latest_info = task['latest_info']
        manager = task['manager_name']

        # --- 逻辑 A: 延期检测 (Today - ETA > 5) ---
        if eta:
            diff_days = (today - eta).days
            if diff_days > 5:
                if site == 'US':
                    us_exception_list.append(s_id)
                else:
                    other_exceptions.setdefault(manager, []).append(s_id)

        # --- 逻辑 B: 查验检测 ---
        if task['is_inspected']:
            inspections.setdefault(manager, []).append(s_id)

        # --- 逻辑 C: 延误检测 ---
        if latest_info:
            keywords = ['延误', '延迟', '延至']
            if any(k in latest_info for k in keywords):
                delations.setdefault(manager, []).append(s_id)

    # --- 结果展示 ---
    logger.info("=" * 30)
    logger.info(f"US 异常货件 (延期>5天): {us_exception_list}")
    logger.info(f"US站点异常货件数量: {len(us_exception_list)}")
    logger.info(f"其他站点异常汇总: {json.dumps(other_exceptions, ensure_ascii=False)}")
    logger.info(f"查验货件汇总: {json.dumps(inspections, ensure_ascii=False)}")
    logger.info(f"延误货件汇总: {json.dumps(delations, ensure_ascii=False)}")
    logger.info("=" * 30)

    return us_exception_list, other_exceptions, inspections, delations

def send_notifications(us_list, others, inspections, delations, bot=None):
    """聚合发送消息推送
    将异常分析结果通过钉钉机器人发送给相关负责人：
    - US 站异常：发给 US_SITE_MANAGER 列表中的所有用户
    - 其他站点延期/查验/延误：通过 MANAGER_MAPPING 查找负责人钉钉 ID 发送
    """
    if bot is None:
        bot = DingTalkRobot(DINGTALK_CONFIG['app_key'], DINGTALK_CONFIG['app_secret'], DINGTALK_CONFIG['robot_code'])

    # 1. 美国站点汇总发送
    if us_list:
        msg = f"### 📌 US 站点异常提醒\n\n**当前有 {len(us_list)} 个异常货件（延期>5天）：**\n📦 {', '.join(us_list)}"
        for user_id in US_SITE_MANAGER:
            bot.send_private_message(user_id, msg)

    # 2. 其他站点异常汇总 (按负责人聚合)
    for manager, ids in others.items():
        user_id = MANAGER_MAPPING.get(manager)
        if user_id:
            msg = f"### ⚠️ 延期提醒 - {manager}\n\n您负责的以下货件已延期超过5天：\n{'- ' + '- '.join(ids)}"
            bot.send_private_message(user_id, msg)

    # 3. 查验提醒汇总 (按负责人聚合)
    for manager, ids in inspections.items():
        user_id = MANAGER_MAPPING.get(manager)
        if user_id:
            msg = f"### 🔍 查验提醒 - {manager}\n\n以下货件已被查验，请重点关注：\n{'- ' + '- '.join(ids)}"
            bot.send_private_message(user_id, msg)

    # 4. 延误提醒汇总 (按负责人聚合)
    for manager, ids in delations.items():
        user_id = MANAGER_MAPPING.get(manager)
        if user_id:
            msg = f"### 🚧 延误提醒 - {manager}\n\n以下货件存在延误情况，请及时处理：\n{'- ' + '- '.join(ids)}"
            bot.send_private_message(user_id, msg)

if __name__ == "__main__":
    # 执行全流程
    init_db()
    load_excel_to_db(FILE_PATHS['main_excel'])

    # 创建一个 DingTalkRobot 实例，全程复用
    bot = DingTalkRobot(DINGTALK_CONFIG['app_key'], DINGTALK_CONFIG['app_secret'], DINGTALK_CONFIG['robot_code'])

    process_crawlers(bot=bot)

    us_list, others, inspections, delations = analyze_logistics_exceptions()
    send_notifications(us_list, others, inspections, delations, bot=bot)

    # 数据写回 Excel
    read_and_update_excel(FILE_PATHS['main_excel'], '发货数据详情')
    logger.info("全流程执行完毕。")
