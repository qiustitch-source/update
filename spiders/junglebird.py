import re
from datetime import datetime
import os
import time
import random
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from spiders.base_spider import BaseSpider

import logging

logger = logging.getLogger(__name__)


class JungleBirdSpider(BaseSpider):

    def login(self):
        """执行登录逻辑（丛林鸟系统无滑块）"""
        logger.info("正在登录丛林鸟物流...")
        self.page.goto("http://forest-bird.nextsls.com/tms/wos/login?redirect_url=%2Ftms%2Fwos")
        
        # 填写账号密码
        self.page.get_by_role("textbox", name="用户名").fill(self.username)
        self.page.get_by_role("textbox", name="密码").fill(self.password)
        
        # 点击登录
        self.page.get_by_role("button", name="登 录").click()

        try:
            # --- 判断登录成功：等待弹窗或跳转 ---
            try:
                self.page.get_by_text("×").click(timeout=3000)
                logger.info("检测到并关闭了登录弹窗")
            except:
                logger.info("未检测到登录弹窗，继续执行")

            # 2. 点击侧边栏的 "运单" 菜单，验证是否进入主界面，如果能点击，说明已经登录成功
            self.page.get_by_text("发货").click()
            order_menu = self.page.get_by_role("link", name=" 运单")
            order_menu.wait_for(timeout=10000)
            order_menu.click()
            
            logger.info("登录并进入主界面成功")
            self.is_logged_in = True
            
        except Exception as e:
            logger.error(f"登录失败: {e}")

    @staticmethod
    def parse_logistics_data(raw_list):
        """
        处理物流原始数据，提取规范化的物流列表及关键节点信息
        """
        # --- 初始化结果 ---
        trace = []
        latest_info = ""
        sail_time = ""
        arrive_time = ""
        sign_time = ""
        voyage_info = ""
        
        # 当前年份
        current_year = datetime.now().year

        # --- 辅助函数：标准化短日期格式 ---
        def standardize_short_date(date_str, base_year=current_year):
            if not date_str:
                return ""
            # 统一替换分隔符
            date_str = date_str.replace('/', '-').replace('.', '-')
            
            # 匹配 MM-DD 或 M-D 或 MM.DD 等格式
            match = re.search(r"(?<!\d)(\d{1,2})-(\d{1,2})(?![\d])", date_str)
            if match:
                month, day = int(match.group(1)), int(match.group(2))
                if 1 <= month <= 12 and 1 <= day <= 31:
                    try:
                        dt = datetime(base_year, month, day)
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
            return ""

        # --- 辅助函数：提取日期 ---
        def extract_date(text):
            # 优先匹配 YYYY-MM-DD 格式
            match = re.search(r"\d{4}-\d{2}-\d{2}", text)
            if match:
                return match.group()
            
            # 尝试匹配 "预计开船时间 9/4" 这种格式
            est_match = re.search(r"(?:预计|新船期).*?(\d{1,2})[\/\-\.](\d{1,2})", text)
            if est_match:
                month, day = int(est_match.group(1)), int(est_match.group(2))
                try:
                    dt = datetime(current_year, month, day)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return ""

        # --- 第一步：数据清洗与重组 ---
        if raw_list and isinstance(raw_list, list):
            raw_str = raw_list[0]
            parts = raw_str.split('\n')
            parts = [p.strip() for p in parts if p.strip()]
            
            for i in range(0, len(parts), 2):
                if i + 1 < len(parts):
                    timestamp = parts[i]
                    content = parts[i + 1]
                    trace.append(f"{timestamp} ：{content}")
        
        # --- 第二步：提取关键信息 ---
        # 1. 最新物流信息取第一条
        if trace:
            latest_info = trace[0] + "————（" + datetime.now().strftime('%Y-%m-%d') + "）"

        # 2. 从前往后遍历 (最新的记录 -> 最旧的记录)
        # 一旦找到对应信息就跳出，确保取到的是最新状态下的数据
        for item in trace:
            content_part = item.split('：', 1)[1] if '：' in item else item

            # --- 获取当前日志行的年份---
            try:
                log_year = int(item[:4]) # 提取 "2025"
            except:
                log_year = current_year

            # --- 提取签收时间 (最新一条) ---
            if not sign_time and ("已签收" in content_part or "Delivered" in content_part or 'DELIVERED' in content_part):
                sign_time = standardize_short_date(content_part, log_year) or extract_date(item) 

            # --- 提取开船时间 (已离港/已开船) ---
            if not sail_time and ("已离港" in content_part or "已开船" in content_part):
                temp_content = content_part.split("预计到港")[0].split("预计抵达")[0].split("预计")[0]
                sail_time = standardize_short_date(temp_content, log_year) or extract_date(item) 
            
            # 如果状态里没找到，尝试从 ETD 或 预计开船时间提取
            if not sail_time:
                # 查找 ETD
                etd_match = re.search(r"ETD:?([^，\s]+)", content_part)
                if etd_match:
                    raw_etd = etd_match.group(1)
                    sail_time = standardize_short_date(raw_etd, log_year) or extract_date(raw_etd)
                
                # 查找“预计开船时间”
                if not sail_time:
                    est_dep_match = re.search(r"预计开船时间.*?(\d{1,2}[\/\-\.]\d{1,2})", content_part)
                    if est_dep_match:
                        sail_time = standardize_short_date(est_dep_match.group(1), log_year)

            # --- 提取到港时间 (已到港) ---
            if not arrive_time and "已到港" in content_part:
                temp_arrive_content = re.sub(r'\d+-\d+\s*天', '', content_part)
                arrive_time = standardize_short_date(temp_arrive_content, log_year) or extract_date(item)
            
            # 如果状态里没找到，尝试从 ETA 或 预计到港时间提取
            if not arrive_time:
                # 查找 ETA
                eta_match = re.search(r"ETA:?([^，\s]+)", content_part)
                if eta_match:
                    raw_eta = eta_match.group(1)
                    arrive_time = standardize_short_date(raw_eta, log_year) or extract_date(raw_eta)
                
                # 查找“预计到港时间”
                if not arrive_time:
                    est_arr_match = re.search(r"预计到港时间.*?(\d{1,2}[\/\-\.]\d{1,2})", content_part)
                    if est_arr_match:
                        arrive_time = standardize_short_date(est_arr_match.group(1), log_year)

            # --- 提取船名航次 (优先级：新船期 > 船名航次，且取最新的) ---
            # 因为是从前往后遍历，找到第一个就立刻赋值并跳出，保证是最新的
            if not voyage_info:
                # 优先查找“新船期”
                voyage_match = re.search(r"新船期：([^，。；\n]+)", content_part)
                if not voyage_match:
                    # 如果没有“新船期”，再找“船名航次”
                    voyage_match = re.search(r"船名航次：([^，。；\n]+)", content_part)
                
                if voyage_match:
                    raw_voyage = voyage_match.group(1).strip()
                    # 清理前缀(content_part 可能是 "新船名航次：..." 或 "船名航次：...")
                    raw_voyage = re.sub(r'^(新?船名?航次|新船期)[：:]\s*', '', raw_voyage).strip()
                    # 清理：移除 ETA/ETD 部分
                    clean_voyage = re.split(r"\s*(?:ETD|ETA|预计):", raw_voyage)[0].strip()
                    # 去除末尾可能的日期时间
                    clean_voyage = re.split(r"\s+\d{1,2}[/\-\.]\d{1,2}", clean_voyage)[0].strip()
                    voyage_info = clean_voyage

            # --- 处理新船期中的时间范围 (例如：9/11-9/27) ---
            # 如果匹配到了新船期且包含横杠，尝试提取后面的日期作为 ETA
            if "新船期" in content_part and "-" in content_part and not arrive_time:
                # 尝试匹配类似 9/11-9/27 这样的模式
                range_match = re.search(r"(\d{1,2})[/\-\.](\d{1,2})\s*-\s*(\d{1,2})[/\-\.](\d{1,2})", content_part)
                if range_match:
                    # 取后面的日期作为 ETA
                    month, day = int(range_match.group(3)), int(range_match.group(4))
                    try:
                        dt = datetime(current_year, month, day)
                        arrive_time = dt.strftime("%Y-%m-%d")
                    except ValueError:
                        pass

        return trace, latest_info, sail_time, arrive_time, sign_time, voyage_info

    def search(self, tracking_no):
        """
        查询单个运单号。
        """
        if not self.is_logged_in:
            logger.warning("请先登录")
            return None

        logger.info(f"正在查询: {tracking_no}")
        try:
            # 1. 填入单号并回车查询
            search_box = self.page.get_by_role("textbox", name="输入单号查询，多个请用“,”隔开")
            search_box.fill(tracking_no)
            search_box.press("Enter") # 模拟回车键
            
            # 等待列表刷新
            time.sleep(1) 

            # 2. 点击具体的单号（进入详情页）
            #    这里假设填入单号回车后，列表会刷新，点击列表中的单号查看轨迹
            locator_a = self.page.get_by_text(tracking_no, exact=True)
            locator_b = self.page.get_by_text(f"【{tracking_no}】")
            # 2. 关键：等待其中任意一个出现 (防止页面未加载完成就检测，导致都误判为不存在)
            try:
                locator_a.or_(locator_b).wait_for(timeout=5000) # 设置一个合理的超时
            except:
                logger.warning("两个元素都没出现")
                # 这里可以添加 return 或 报错处理

            # 3. 收集所有当前可见的元素
            candidates = []
            if locator_a.is_visible():
                candidates.append(locator_a)
            if locator_b.is_visible():
                candidates.append(locator_b)

            # 4. 如果有候选元素，随机选一个点击
            if candidates:
                random.choice(candidates).click()

            # 等待详情页加载
            time.sleep(3)

            # --- 数据提取逻辑 ---
            # 轨迹信息在 class="pod-route-info" 的元素中
            texts = []
            latest_info = ""
            sail_time = ""
            arrive_time = ""
            sign_time = ""
            voyage_info = ""
            is_inspected = False
            result_locator = self.page.locator(".pod-route-info")
            
            if result_locator.count() > 0:
                texts = result_locator.all_inner_texts()
                self.page.keyboard.press("Escape")

            if texts: 
                texts_str = texts[0]
                if texts_str.startswith("UPS") or texts_str.startswith("FEDEX"):
                    # 找到第一个换行符的位置
                    first_newline_index = texts_str.find('\n')
                    if first_newline_index != -1:
                        # 取换行符之后的所有内容（+1 是为了跳过 \n 本身）
                        texts_str = texts_str[first_newline_index + 1:]
                texts = [texts_str]
                logger.info(f"轨迹信息: {texts}")
                trace, latest_info, sail_time, arrive_time, sign_time, voyage_info = self.parse_logistics_data(texts)
                # --- 判断是否被查验 ---
                is_inspected = any("查验" in item for item in trace)
                # --- 判断状态 ---
                # 如果签收时间不为空，则为"已签收"，否则为"在途"
                status = "签收" if sign_time else "在途"
                latest_info = "Done" if status == "签收" else latest_info

                # --- 返回整合数据 ---
                return {
                    "voyage_info": voyage_info,      # 船名航次
                    "trace": "\n".join(trace),       # 完整轨迹
                    "latest_info": latest_info,      # 最新轨迹
                    "sail_time": sail_time,          # 开船时间
                    "arrive_time": arrive_time,      # 到港时间
                    "sign_time": sign_time,          # 签收时间
                    "is_inspected": is_inspected,    # 是否被查验
                    "status": status                 # 当前状态
                }         
                
            else:
                logger.warning("未找到轨迹信息节点 (.pod-route-info)")
                return {"error": "未找到轨迹", "trace": "", "latest_info": ""}

        except Exception as e:
            logger.error(f"查询 {tracking_no} 出错: {e}")
            return None


def main():
    # --- 第一步：加载 .env 文件 ---
    load_dotenv()

    # --- 第二步：从环境变量中获取配置 ---
    username = os.getenv("CLN_USERNAME", "dmjj") # 提供默认值方便测试
    password = os.getenv("CLN_PASSWORD", "123456")
    headless = os.getenv("CRAWLER_HEADLESS", "false").lower() == "true"

    print(f"ℹ️ 正在使用账号: {username} 初始化爬虫...")

    # --- 第三步：启动 Playwright ---
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=50)
        context = browser.new_context()
        page = context.new_page()

        try:
            spider = JungleBirdSpider(page=page, username=username, password=password)
            spider.login()

            if spider.is_logged_in:
                # 使用测试单号
                result = spider.search("FBA1943GY9T7")
                if result:
                    print("=== 查询结果 ===")
                    print(f"最新状态: {result.get('latest_info')}")
                    print(f"完整轨迹: \n{result.get('trace')}")
                    print(f"船名航次: {result.get('voyage_info')}")
                    print(f"开船时间: {result.get('sail_time')}")
                    print(f"到港时间: {result.get('arrive_time')}")
                    print(f"签收时间: {result.get('sign_time')}")
                    print(f"是否查验: {result.get('is_inspected')}")
                    print(f"当前状态: {result.get('status')}")
            else:
                print("登录失败，无法查询")

        except Exception as e:
            print(f"运行出错: {e}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
