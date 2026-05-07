
import os
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, Playwright
import time
from datetime import datetime


class HaiqiaoSpider:
    def __init__(self, page: Page, username, password):
        self.page = page
        self.username = username
        self.password = password
        self.is_logged_in = False

    def login(self):
        """执行登录逻辑（包含滑块验证）"""
        print("正在登录海桥物流...")
        self.page.goto("https://app.ocean-bridges.com/login")
        
        # 填写账号密码 
        self.page.get_by_role("textbox", name="用户名").fill(self.username)
        self.page.get_by_role("textbox", name="密码").fill(self.password)

        try:
            # --- 核心逻辑：处理滑块验证  ---
            slider_handle = self.page.locator(".dv_handler") 
            
            # 等待滑块出现
            if slider_handle.count() > 0: # 检查是否存在
                print("检测到滑块，正在处理...")
                box = slider_handle.bounding_box()
                
                if box:
                    # 计算鼠标起始点：滑块的中心位置
                    start_x = box["x"] + box["width"] / 2
                    start_y = box["y"] + box["height"] / 2
                    
                    # 开始模拟拖拽
                    # 1. 鼠标移动到滑块上
                    self.page.mouse.move(start_x, start_y)
                    # 2. 按下鼠标左键
                    self.page.mouse.down()
                    # 3. 移动鼠标 (向右移动 300 像素，steps=20 表示分20步移过去，模拟人手速度)
                    self.page.mouse.move(start_x + 300, start_y, steps=20) 
                    # 4. 松开鼠标
                    self.page.mouse.up()
                    
                    print("滑块拖动完成")
                    # 等待验证结果
                    time.sleep(1.5)
            
            # 尝试点击登录按钮
            login_btn = self.page.get_by_role("button", name="登录")
            if login_btn.is_visible():
                login_btn.click()
                
            # 简单判断是否登录成功,假设出现查询框代表登录成功
            order_input = self.page.get_by_role("textbox", name="订单号（运单号），如：OBEC240453611")
            order_input.wait_for(timeout=10000)       
            print("检测到查询页面，登录成功")
            self.is_logged_in = True
            
        except Exception as e:
            print(f"登录或滑块处理失败: {e}")

    @staticmethod
    def parse_logistics_list(lines, nodes):
        """
        解析物流信息列表
        :param lines: 原始文本列表 (e.g. ['已签收', '2025-08-11', '已预约', ...])
        :param nodes: 物流节点定义 (e.g. ['已签收', '已预约', ...])
        :return: 合并后的列表 (e.g. ['已签收,2025-08-11', ...])
        """
        if not lines:
            return []

        result = []
        current_item = [] # 用于暂存当前条目的各个部分

        # 将 nodes 转为集合，加快查找速度
        node_set = set(nodes)

        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line in node_set:
                # 情况1：当前行是一个新的物流节点
                # 如果 current_item 不为空，说明上一个条目结束了，将其保存
                if current_item:
                    result.append("，".join(current_item))
                    current_item = []
                
                # 开启一个新的条目，存入节点名称
                current_item.append(line)
                
            else:
                # 情况2：当前行是详情（日期、船名等）
                # 将其追加到当前条目的详情中
                if current_item:
                    current_item.append(line)
                # 如果 current_item 为空，说明详情在节点之前出现，可以选择忽略或打印日志

        if current_item:
            result.append("，".join(current_item))

        return result

    @staticmethod
    def parse_logistics_list_data(node_list):
        """
        解析物流节点列表，提取关键信息
        :param node_list: 物流节点列表，例如 ['已签收，2025-08-11', '已离港，OOCL UTAH 077E ETA:7.29，2025-07-14', ...]
        :return:  voyage_info, sail_time, arrive_time, sign_time, latest_info 
        """
        
        # --- 初始化结果 ---
        voyage_info = ""
        sail_time = ""
        arrive_time = ""
        sign_time = ""
        latest_info = ""
        
        # --- 辅助函数：标准化日期格式 ---
        def standardize_date(date_str, base_year=None):
            if not date_str:
                return ""
            date_str = date_str.strip()

            # 1. 如果已经是 YYYY-MM-DD 格式，直接返回
            if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                return date_str

            # 2. 处理 M.D 或 MM.DD 格式 (例如 7.29)
            match = re.match(r"^(\d{1,2})[.\-/](\d{1,2})", date_str)
            if match:
                month, day = int(match.group(1)), int(match.group(2))
                if 1 <= month <= 12 and 1 <= day <= 31:
                    year = base_year or datetime.now().year
                    try:
                        dt = datetime(year, month, day)
                        # 如果解析出的日期距今超过90天在未来，说明是去年的日期
                        if (dt - datetime.now()).days > 90:
                            dt = datetime(year - 1, month, day)
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
            return ""
        
        # --- 变量声明 ---
        found_latest = False # 标记是否已找到最新物流

        # 获取当前年份（基于开船时间或排舱时间），用于处理 ETA 的年份
        current_year = datetime.now().year
        for item in node_list:
            if "已离港" in item or "已排舱" in item:
                date_match = re.search(r"20\d{2}", item)
                if date_match:
                    current_year = int(date_match.group())
                    break

        # 遍历提取数据
        for item in node_list:
            if not item or "，" not in item:
                continue
                
            # 分割状态和详情
            parts = item.split("，", 1)
            status = parts[0].strip()
            details = parts[1].strip() if len(parts) > 1 else ""
            
            # --- 1. 寻找最新物流信息 ---
            # 逻辑：取列表中第一个包含日期（YYYY-MM-DD格式）的元素
            if not found_latest:
                date_match = re.search(r"\d{4}-\d{2}-\d{2}", details)
                if date_match:
                    latest_info = item+ "————（"+datetime.now().strftime('%Y-%m-%d')+"）"
                    found_latest = True
            
            # --- 2. 处理【已离港】节点 (提取船名和开船时间) ---
            if status == "已离港":
                # 提取开船时间 (标准日期)
                sail_date_match = re.search(r"\d{4}-\d{2}-\d{2}", details)
                if sail_date_match:
                    sail_time = sail_date_match.group()
                
                # 提取船名航次
                # 步骤A: 移除标准日期 (如 2026-02-04)
                temp_details = re.sub(r"\d{4}-\d{2}-\d{2}", "", details)
                # 步骤B: 移除 ETA:xxx 和 ETD:xxx 部分
                temp_details = re.sub(r"(ETD|ETA)[:：][^，\s]*", "", temp_details, flags=re.IGNORECASE)
                # 步骤C: 移除中文说明 (如 "以实际离港时间为准")
                temp_details = re.sub(r"[\u4e00-\u9fa5]+", "", temp_details)
                
                # 步骤D: 正则提取船名
                # 新正则: r"[A-Z0-9][A-Z0-9a-z\s\d/\-]+"
                # 解释: 允许包含斜杠 /，且允许数字开头，并包含小写字母(以防万一)
                voyage_match = re.search(r"[A-Z0-9][A-Z0-9a-z\s\d/\-\.]+", temp_details)
                
                if voyage_match:
                    # 清理多余空格
                    voyage_info = re.sub(r"\s+", " ", voyage_match.group()).strip()
                    
            # --- 3. 处理【已到港】节点 (提取实际到港时间) ---
            elif status == "已到港":
                arrive_date_match = re.search(r"\d{4}-\d{2}-\d{2}", details)
                if arrive_date_match:
                    arrive_time = arrive_date_match.group()
            
            # --- 4. 处理【已签收】节点 (提取签收时间) ---
            elif status == "已签收":
                sign_date_match = re.search(r"\d{4}-\d{2}-\d{2}", details)
                if sign_date_match:
                    sign_time = sign_date_match.group()
        
            # 如果【已离港】没有时间，尝试从【已离港】的 ETD 中获取 ---
            if not sail_time and "已离港" in item:
                # 这里需要重新检查详情，寻找 ETD
                etd_match = re.search(r"ETD:([^\s，]+)", details)
                if etd_match:
                    raw_etd = etd_match.group(1)
                    sail_time = standardize_date(raw_etd, current_year)
            # 如果【已到港】没有时间，尝试从【已离港】的 ETA 中获取 ---
            if not arrive_time and "已离港" in item:
                # 这里需要重新检查详情，寻找 ETA
                eta_match = re.search(r"ETA:([^\s，]+)", details)
                if eta_match:
                    raw_eta = eta_match.group(1)
                    arrive_time = standardize_date(raw_eta, current_year)
        
        return latest_info, sail_time, arrive_time, sign_time, voyage_info

    def search(self, tracking_no):
        """
        查询单个运单号。
        注意：代码逻辑是 fill -> click query -> click result text。
        """
        if not self.is_logged_in:
            print("请先登录")
            return None

        print(f"正在查询: {tracking_no}")
        try:
            # 1. 填入单号
            self.page.get_by_role("textbox", name="订单号（运单号），如：OBEC240453611").fill(tracking_no)
            
            # 2. 点击查询
            self.page.get_by_role("button", name="查询").click()
            self.page.wait_for_timeout(3000) 
            
            # --- 数据提取逻辑  ---
            # 获取特定文本的所有 inner_text
            latest_info = ""
            sail_time = ""
            arrive_time = ""
            sign_time = ""
            voyage_info = ""
            is_inspected = False
            result_locator = self.page.locator("#card_qjVgDylinVVAFwE > .arco-card-body")
            
            texts = []
            if result_locator.count() > 0:
                texts = result_locator.all_inner_texts()
            
            if texts:
                texts = texts[0].split("\n")
                node_list = self.parse_logistics_list(texts,["已签收", "已预约", "已提柜", "已到港", "已清关", "已离港", "已排舱", "已入库", "已订舱"])
                # print(f"提取到的物流轨迹信息节点：\n{node_list}")
                latest_info, sail_time, arrive_time, sign_time, voyage_info = self.parse_logistics_list_data(node_list)

                # --- 判断是否被查验 ---
                is_inspected = any("查验" in item for item in node_list)
                # --- 判断状态 ---
                # 如果签收时间不为空，则为"已签收"，否则为"在途"
                status = "签收" if sign_time else "在途"
                latest_info = "Done" if status == "签收" else latest_info

                # --- 返回整合数据 ---
                return {
                    "voyage_info": voyage_info,      # 船名航次
                    "trace": node_list,             # 完整轨迹
                    "latest_info": latest_info,      # 最新轨迹
                    "sail_time": sail_time,          # 开船时间
                    "arrive_time": arrive_time,      # 到港时间
                    "sign_time": sign_time,          # 签收时间
                    "is_inspected": is_inspected,    # 是否被查验
                    "status": status                 # 当前状态
                }
            else:
                print("未找到轨迹信息")
                return {"error": "未找到轨迹", "trace": "", "latest_info": ""}

        except Exception as e:
            print(f"查询 {tracking_no} 出错: {e}")
            return None


def main():
    # --- 第一步：加载 .env 文件 ---
    load_dotenv()

    # --- 第二步：从环境变量中获取配置 ---
    username = os.getenv("HAIQIAO_USERNAME", "cs_weijing") 
    password = os.getenv("HAIQIAO_PASSWORD", "1!P\\<{f<")
    headless = os.getenv("CRAWLER_HEADLESS", "false").lower() == "true" # 默认 false 方便观察

    if not username or not password:
        print("❌ 错误：未在 .env 文件中找到账号或密码")
        return

    print(f"ℹ️ 正在使用账号: {username} 初始化爬虫...")

    # --- 第三步：启动 Playwright ---
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=50) # slow_mo 方便观察
        context = browser.new_context()
        page = context.new_page()

        try:
            spider = HaiqiaoSpider(page, username, password)
            spider.login()

            if spider.is_logged_in:
                # 这里使用原代码中的测试单号
                result = spider.search("OBEC260211251")
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
