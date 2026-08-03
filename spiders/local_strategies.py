import pandas as pd
import os
import re
import openpyxl
from datetime import datetime, timedelta

import logging

from spiders.base_spider import BaseSpider

logger = logging.getLogger(__name__)


class LocalExcelStrategy(BaseSpider):
    """本地 Excel 策略类：用于辰舟货代的数据查询
    直接读取本地 Excel 文件，通过 FBA ID 或发货 ID 进行匹配
    不使用浏览器，不需要登录
    """
    def __init__(self, **kwargs):
        """
        接受参数：
        - file_path: Excel 文件路径
        - forwarder_name: 货代名称 (用于日志和逻辑区分)
        - sheet_name: 要读取的 Sheet 名称或索引 (默认为第一个 Sheet)
        """
        self.file_path = kwargs.get('file_path')
        self.forwarder_name = kwargs.get('forwarder_name')
        self.sheet_name = kwargs.get('sheet_name', 0)
        self.df = None
        self.load_data()

    def load_data(self):
        """加载本地 Excel 文件到内存"""
        if not self.file_path or not os.path.exists(self.file_path):
            logger.error(f"[{self.forwarder_name}] 本地文件不存在: {self.file_path}")
            return
        
        try:
            # 指定 Sheet 读取
            # 注意：如果是 CSV 文件，pd.read_excel 可能报错，建议增加判断或直接用 read_excel (如果确实是xlsx)
            # 你的文件名为 .xlsx 但如果是 csv 格式需注意。这里默认是 excel 处理。
            self.df = pd.read_excel(self.file_path, sheet_name=self.sheet_name)
            
            # 清理列名：去除前后空格
            self.df.columns = self.df.columns.str.strip()
            
            # 预处理：将关键 ID 列转为字符串，去除 ".0" 等后缀
            for col in self.df.columns:
                if 'ID' in col or '单号' in col or '号' in col:
                     self.df[col] = self.df[col].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            
            logger.info(f"[{self.forwarder_name}] 成功加载本地数据: {len(self.df)} 条 (Sheet: {self.sheet_name})")
        except Exception as e:
            logger.error(f"[{self.forwarder_name}] 读取文件失败: {e}")

    def needs_browser(self) -> bool:
        """本地 Excel 策略不需要浏览器"""
        return False

    def needs_login(self) -> bool:
        """本地 Excel 策略不需要登录"""
        return False

    def login(self):
        """无需登录，空实现"""
        pass

    def search_order(self, task_info):
        """
        执行匹配逻辑
        """
        if self.df is None or self.df.empty:
            return None

        # 获取任务中的关键 ID
        fba_id = str(task_info.get('fba_id', '')).strip()
        shipment_id = str(task_info.get('shipment_id', '')).strip()
        
        matched_row = None

        # === 1. 定义本地 Excel 的匹配列名优先级 ===
        fba_cols = ['FBA单号']
        ship_cols = ['客户单号（发货ID）']

        # === 2. 优先尝试 FBA 号匹配 ===
        for col in fba_cols:
            if col in self.df.columns and fba_id:
                results = self.df[self.df[col].str.contains(fba_id, na=False)]
                if not results.empty:
                    # 获取该行在 df 中的索引（results.index[0]）
                    row_index = results.index[0]
                    matched_row = results.iloc[0]
                    # 传入行索引
                    return self._parse_row_data(matched_row, row_index)
        
        # === 3. 其次尝试 Shipment ID 匹配 ===
        if matched_row is None:
            for col in ship_cols:
                if col in self.df.columns and shipment_id:
                    results = self.df[self.df[col].str.contains(shipment_id, na=False)]
                    if not results.empty:
                        # 获取该行在 df 中的索引（results.index[0]）
                        row_index = results.index[0]
                        matched_row = results.iloc[0]
                        # 传入行索引
                        return self._parse_row_data(matched_row, row_index)

        return None

    def _parse_row_data(self, row, row_index):
        """根据不同货代的列名解析数据"""
        excel_row = row_index + 2     
        # 动态拼接 H 列地址
        h_cell_address = f"H{excel_row}"
        # 初始化字段
        latest_info = ""
        sail_time = ""
        arrive_time = ""
        sign_time = ""
        voyage_info = ""
        is_inspected = False
        
        if self.forwarder_name != "辰舟":
            return None

        # === 辰舟解析逻辑 ===
        latest_info = str(row.get('货物状态备注', ''))
        sail_time = self._clean_date(row.get('开船时间'))
        arrive_time = self._clean_date(row.get('到港时间'))
        if self.check_cell_color("唯镜录系统模板", h_cell_address):
            sign_time = self._clean_date(row.get('妥投时间'))
        if latest_info:
            latest_info = latest_info+'————（'+datetime.now().strftime('%Y-%m-%d')+'）'
            
        # 提取船名航次 (Voyage Info)
        voyage_info = ""
        if latest_info:
            # --- 优化后的正则表达式 ---
            # (?:ETD|开船|船名航次)[：:] -> 第一级匹配标签
            # \s*(?:(?:\d{4}[-/])?\d{1,2}[-/]\d{1,2}开?)? -> 匹配日期（如 1-1 或 1-1开）
            # \s*(?:船名航次[：:])? -> 【关键修改】如果后面又跟着一个“船名航次：”，则跳过它不抓取
            # \s*(.*?) -> 真正抓取我们要的船名
            # (?:[\n\r]|————|$) -> 到换行或我们加的分隔符停止
            # 1. 优先处理“换船/现换船至”的情况
            change_pattern = r'现换船至\s*(?:船名航次[：:])?\s*(?:(?:\d{4}[-/])?\d{1,2}[-/]\d{1,2}开?)?\s*(?:船名航次[：:])?\s*(.*?)(?:[\n\r]|————|$)'
            change_match = re.search(change_pattern, latest_info)
            
            if change_match:
                voyage_info = change_match.group(1).strip()
            else:
                # 2. 如果没有换船信息，使用通用的正则匹配
                pattern = r'(?:ETD|开船|船名航次)[：:]\s*(?:(?:\d{4}[-/])?\d{1,2}[-/]\d{1,2}开?)?\s*(?:船名航次[：:])?\s*(.*?)(?:[\n\r]|————|$)'
                match = re.search(pattern, latest_info, re.IGNORECASE)
                if match:
                    voyage_info = match.group(1).strip()

        # 查验判断
        # 在 latest_info 中查找关键字
        if "查验" in latest_info or "Inspection" in latest_info:
            is_inspected = True

        # 清理 None 字符串
        if latest_info == 'nan': latest_info = ""
        if voyage_info == 'nan': voyage_info = ""

        # --- 判断状态 ---
        # 如果签收时间不为空，则为"已签收"，否则为"在途"
        status = "签收" if sign_time else "在途"
        latest_info = "Done" if status == "签收" else latest_info
        return {
                "latest_info": latest_info,
                "sail_time": sail_time,
                "arrive_time": arrive_time,
                "sign_time": sign_time,
                "voyage_info": voyage_info,
                "is_inspected": is_inspected,
                "status": status  
            }

        
    def _clean_date(self, date_val):
        """核心修改：处理 Excel 数字日期及各种格式"""
        if pd.isna(date_val) or str(date_val).lower() in ['nan', 'nat', '']:
            return ""
        
        try:
            # 情况1: 已经是 datetime 或 Timestamp
            if isinstance(date_val, (datetime, pd.Timestamp)):
                return date_val.strftime("%Y-%m-%d")
            
            # 情况2: 是 Excel 的五位数字字符串/数字 (例如 '46056')
            date_str = str(date_val).strip()
            if date_str.replace('.', '').isdigit():
                # Excel 日期起点是 1899-12-30 (由于Excel早期Bug将1900记为闰年，需修正)
                days = int(float(date_str))
                actual_date = datetime(1899, 12, 30) + timedelta(days=days)
                return actual_date.strftime("%Y-%m-%d")
            
            # 情况3: 普通日期字符串处理
            date_str = date_str.replace('/', '-').split(' ')[0]
            parts = date_str.split('-')
            if len(parts) == 3:
                return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            
            return date_str
        except Exception as e:
            logger.warning(f"日期解析失败: {date_val}, 错误: {e}")
            return str(date_val)
        
    def check_cell_color(self, sheet_name, cell_address):
        """
        检查指定单元格的底色是否为目标颜色
        :param target_hex_color: 16进制颜色代码
        """
        # 加载工作簿
        wb = openpyxl.load_workbook(self.file_path, data_only=True)
        sheet = wb[sheet_name]
        cell = sheet[cell_address]
        # 处理合并单元格的情况：如果返回的是元组，取第一个元素
        if isinstance(cell, tuple):
            cell = cell[0]
        
        # 获取单元格填充颜色对象
        fill = cell.fill
        
        # 获取颜色值 (start_color 是填充的主要颜色)
        # 注意：Excel 颜色通常带 Alpha 通道（前两位），如 FFFFFFFF
        current_color = fill.start_color.index
        
        logger.debug(f"单元格 {cell_address} 的当前颜色代码为: {current_color}")
        
        if current_color == 'FFFFFF00':  # 黄色
            return True
        else:
            return False
        
def main():
    logging.basicConfig(level=logging.INFO)

    # 替换为你实际的文件路径
    real_file_path = r"C:\Users\25a04\Desktop\货代更新\【唯镜】物流状态更新模版——辰舟.xlsx"
    
    # 实例化
    app = LocalExcelStrategy(real_file_path, "辰舟", sheet_name=1)
    
    # 测试 FBA 单号 (请确保此单号在你的 Excel 中存在，例如 FBA15L75NKTG)
    # test_task = {'fba_id': 'FBA198T8L3MN'}
    test_task = {'shipment_id': '260311G-5'}
    
    # 打印结果
    print(app.search_order(test_task))

if __name__ == "__main__":
    main()
