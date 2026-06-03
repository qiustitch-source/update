
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import time
from datetime import datetime
from typing import Optional
from playwright.sync_api import sync_playwright, Frame

from spiders.base_spider import BaseSpider

import logging

logger = logging.getLogger(__name__)


class YiPaiSpider(BaseSpider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.frame: Optional[Frame] = None
        self.is_logged_in = True

    def login(self):
        """该网站无需登录，导航到查询页面并等待加载即可。"""
        assert self.page is not None
        try:
            self.page.goto("http://track2.e-express.com/")
            # 页面使用 frameset，实际内容在 name="main" 的子 frame 中
            self.frame = self.page.frame(name="main")
            if self.frame:
                self.frame.wait_for_selector("textarea#cno", timeout=15000)
                logger.info("E-Express 查询页面已加载")
            else:
                logger.error("未找到页面子 frame")
        except Exception as e:
            logger.error(f"页面加载失败: {e}")

    @staticmethod
    def extract_logistics_info(log_text):
        """
        从物流轨迹文本中提取开船、到港、签收时间和查验状态。
        """
        
        # 定义结果变量，默认为 "" (空)
        sail_time = ""
        arrive_time = ""
        sign_time = ""
        is_inspected = False
        
        # 1. 判断是否被查验
        # 全局搜索“查验”二字
        if "查验" in log_text:
            is_inspected = True
            
        # 将文本按行分割并进行预处理
        lines = log_text.strip().split('\n')
        parsed_logs = []
        
        # 正则：匹配行首的时间戳 (支持 YYYY-MM-DD HH:MM:SS)
        timestamp_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}')
        
        # 将日志解析为结构化数据 [{"date": "2026-01-20", "full_dt": datetime, "content": "..."}]
        for line in lines:
            line = line.strip()
            match = timestamp_pattern.match(line)
            if match:
                date_str = match.group(1)
                # 提取完整时间用于后续年份推断
                full_dt_str = match.group(0) 
                full_dt = datetime.strptime(full_dt_str, "%Y-%m-%d %H:%M:%S")
                # 提取时间戳之后的内容（用 " : " 分隔，避免误切时间中的冒号）
                content = line.split(' : ', 1)[1].strip() if ' : ' in line else line
                parsed_logs.append({
                    "date_str": date_str,
                    "full_dt": full_dt,
                    "content": content
                })
                
        # 辅助函数：从文本内容中提取日期 (例如 "预计1月14日...")
        def extract_date_from_text(content, ref_datetime):
            # 匹配格式：2026年1月11日 或 1月11日 或 12月10号
            # Group 1: Year (Optional), Group 2: Month, Group 3: Day
            date_pattern = re.compile(r'(?:(\d{4})[年\.-])?(\d{1,2})[月\.-](\d{1,2})[日号]?')
            match = date_pattern.search(content)
            
            if match:
                year, month, day = match.groups()
                month, day = int(month), int(day)
                
                # 确定年份
                if year:
                    current_year = int(year)
                else:
                    # 如果文本没写年份，需要根据消息时间(ref_datetime)推断
                    # 逻辑：如果提取的月份比消息月份小很多（比如消息12月，提取出1月），说明跨年了
                    if month < ref_datetime.month and (ref_datetime.month - month) > 6:
                        current_year = ref_datetime.year + 1
                    elif month > ref_datetime.month and (month - ref_datetime.month) > 6:
                        # 极少见情况：消息是1月，提到了去年12月
                        current_year = ref_datetime.year - 1
                    else:
                        current_year = ref_datetime.year
                
                # 格式化
                return f"{current_year}-{month:02d}-{day:02d}"
            return None

        # --- 提取逻辑 (注意：日志通常是倒序的，从新到旧) ---
        # 我们遍历所有日志来寻找匹配项。
        
        # 2. 提取开船时间 (Sail Time)
        for log in parsed_logs:
            content = log['content']
            # 逻辑修改：
            # 情况A：强状态词（航行中、已开船、已离港）。只要出现这些词，就认为已开船，忽略后面是否包含“预计抵达”等字样。
            if any(k in content for k in ["航行中", "已开船", "已离港"]):
                sail_time = log['date_str']
                break
            # 情况B：弱状态词（开船）。如果只写了“开船”，则必须确保没有“预计”，防止匹配到“预计开船”。
            elif "开船" in content and "预计" not in content:
                sail_time = log['date_str']
                break
        
        # 如果没找到实际开船，再找预计
        if not sail_time:
            for log in parsed_logs:
                if "预计" in log['content'] and "开船" in log['content']:
                    extracted = extract_date_from_text(log['content'], log['full_dt'])
                    if extracted:
                        sail_time = extracted
                        break

        # 3. 提取到港时间 (Arrive Time)
        for log in parsed_logs:
            content = log['content']
            # 逻辑修改：同理，如果有“已抵达”等强状态，忽略行内可能存在的后续计划中的“预计”
            strong_arrival_keywords = ["已抵达", "已到港", "抵达目的港", "到港"]
            if any(k in content for k in strong_arrival_keywords):
                extracted = extract_date_from_text(content, log['full_dt'])
                if extracted:
                    arrive_time = extracted
                else:
                    # 如果文本里没写具体时间，才用日志头的时间
                    arrive_time = log['date_str']
                break
            # 弱状态词检查（防止匹配到“预计靠港”）
            elif "靠港" in content and "预计" not in content:
                arrive_time = log['date_str']
                break

        # 如果没找到实际到港，再找预计
        if not arrive_time:
            for log in parsed_logs:
                if "预计" in log['content'] and any(k in log['content'] for k in ["到港", "抵达", "靠港"]):
                    extracted = extract_date_from_text(log['content'], log['full_dt'])
                    if extracted:
                        arrive_time = extracted
                        break

        return sail_time, arrive_time, is_inspected

    def search(self, tracking_no):
        assert self.page is not None
        assert self.frame is not None
        logger.info(f"正在查询 E-Express 单号: {tracking_no}")
        try:
            # 1. 直接用 GET 请求导航到查询结果页
            # 使用 goto() 代替表单 POST，因为 goto() 会阻塞等待 frame 完全加载，
            # 避免表单提交后 frame 异步刷新导致读到上一个单号的旧数据
            self.frame.goto(f"http://120.77.146.129:8082/trackIndex.htm?documentCode={tracking_no}", timeout=15000)
            # 该网站有请求频率限制，连续快速查询会导致服务器返回空结果，需要间隔
            time.sleep(2)

            # 2. 定位第一个结果表格中的行
            rows = self.frame.locator("table").first.locator("tbody tr").all()
            if not rows:
                return {"trace": "未找到轨迹数据", "latest_info": "", "status": ""}

            trace_data = []
            sail_time = ""
            arrive_time = ""
            sign_time = ""
            is_inspected = False

            # 3. 遍历每一行进行提取
            for row in rows:
                # 获取这一行下的所有单元格
                cells = row.locator("td").all()

                # 检查单元格数量是否足够 (至少要有 Date 和 Trace Record)
                if len(cells) >= 3:
                    try:
                        date_text = cells[0].inner_text().strip()      # Date 列
                        record_text = cells[2].inner_text().strip()    # Trace Record 列

                        if date_text and record_text:
                            trace_data.append(f"{date_text} : {record_text}")

                    except Exception as e:
                        logger.warning(f"提取某行数据时出错: {e}")
                        continue

            # 4. 格式化结果
            if trace_data:
                result_text = "\n".join(trace_data)
                sail_time, arrive_time, is_inspected = self.extract_logistics_info(result_text)
                latest_time = self.frame.locator("div.menu_ ul:nth-child(2) li.div_li2").first.inner_text(timeout=10000)
                latest_status = self.frame.locator("div.menu_ ul:nth-child(2) li.div_li4").first.inner_text(timeout=10000)
                sign_keywords = ["已签收", "签收", "已派送", "POD", "DELIVERED"]
                if any(k in latest_status for k in sign_keywords):
                    sign_time = latest_time.split(" ")[0]
                else:
                    sign_time = ""
                status = "签收" if sign_time else "在途"
                latest_info = "Done" if status == "签收" else (latest_time+":"+latest_status+ "————（" + datetime.now().strftime('%Y-%m-%d') + "）" if trace_data else "")
                return {
                    "trace": result_text,
                    "latest_info": latest_info,
                    "sail_time": sail_time,
                    "arrive_time": arrive_time,
                    "sign_time": sign_time,
                    "is_inspected": is_inspected,
                    "voyage_info": "",
                    "status": status
                }
            else:
                return {"trace": "未找到轨迹数据", "latest_info": "", "status": ""}

        except Exception as e:
            logger.error(f"查询 {tracking_no} 出错: {e}")
            return None

def main():
    # --- 第一步：加载 .env 文件 ---
    # load_dotenv() # 该网站无需账号，不需要加载

    # --- 第二步：配置参数 ---
    username = ""
    password = ""
    headless = True # 默认 False 方便观察

    print(f"正在初始化 E-Express 爬虫...")

    # --- 第三步：启动 Playwright ---
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=50)
        context = browser.new_context()
        page = context.new_page()

        try:
            spider = YiPaiSpider(page=page, username=username, password=password)
            spider.login() # 初始化页面

            # 测试查询
            test_list = ['260331C-3','260327Q-1','260428K-1','260417N-5','260331G-5 ','260408B-1','260409H-5',
                        '260429N-5', '260513C-2','260514F-1','260515K-2','260522H-3','260522J-2']
            
            for tracking_no in test_list:
                result = spider.search(tracking_no)
                if result:
                    print("=== 查询结果 ===")
                    print(f"当前单号: {tracking_no}")
                    print(f"最新状态: {result.get('latest_info')}")
                    print(f"完整轨迹: \n{result.get('trace')}")
                    print(f"开船时间: {result.get('sail_time')}")
                    print(f"到港时间: {result.get('arrive_time')}")
                    print(f"签收时间: {result.get('sign_time')}")
                    print(f"是否查验: {result.get('is_inspected')}")
                    print(f"状态: {result.get('status')}")

        except Exception as e:
            print(f"运行出错: {e}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()