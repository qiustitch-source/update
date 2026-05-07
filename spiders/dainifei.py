
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright.sync_api import Page
import time
import re
from datetime import datetime

class DainifeiSpider:
    def __init__(self, page: Page, username, password):
        self.page = page
        self.username = username
        self.password = password
        self.is_logged_in = False

    def login(self):
        """执行登录逻辑"""
        print("正在登录袋你飞...")
        self.page.goto("https://dainifei.vastfreight.com/#/passport/login")
        self.page.get_by_role("textbox", name="用户名或邮箱").fill(self.username)
        self.page.get_by_role("textbox", name="密码").fill(self.password)
        self.page.get_by_role("button", name="登录").click()
        
        # 简单判断是否登录成功 (等待某个登录后才有的元素出现)
        try:
            self.page.wait_for_selector("text=状态追踪", timeout=10000)
            print("登录成功")
            self.is_logged_in = True
        except:
            print("登录失败，请检查账号密码")
    
    @staticmethod
    def extract_latest_logistics_info(raw_text):
        """
        从原始文本中提取最新物流信息。
        
        逻辑：按流程顺序查找，最后一个出现的具体时间，即为当前最新的物流状态。
        返回：
        - latest_info: 最新的物流状态描述
        - sail_time: 开船时间 (优先取实际，次选预计)
        - arrive_time: 到港时间 (优先取实际，次选预计)
        - sign_time: 签收时间 (亚马逊入库)
        """
        # 1. 定义物流流程的顺序
        process_steps = [
            "客户订舱下单时间",
            "货件国内入库时间",
            "船舶预计离港时间",
            "船舶实际离港时间",
            "船舶预计靠港时间",
            "实际到港日",
            "清关放行时间",
            "预计送货时间",
            "货件入库亚马逊仓库时间"
        ]
        
        # 2. 初始化一个字典，用来存储提取到的时间
        timeline = {}
        is_inspected = False
                
        # 3. 按行分割文本，并去除首尾空白
        lines = raw_text.strip().split('\n')
        
        # 4. 遍历每一行，尝试匹配关键词和时间
        for line in lines:
            line = line.strip()
            # 简单的分割：假设格式是 "关键词 时间"
            # 这里使用正则表达式来稳健地分离中文关键词和后面的时间
            import re
            # 匹配：开头任意字符(非贪婪) + 结尾的日期格式(如 2026-01-01 或 2026/01/01)
            match = re.match(r'(.*?)\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})', line)
            if match:
                desc = match.group(1).strip() # 关键词
                date_str = match.group(2).strip() # 时间字符串
                
                # 只保留我们关心的流程节点
                if desc in process_steps:
                    timeline[desc] = date_str
        
        # --- 提取特定时间 ---
        # 开船时间：优先取“船舶实际离港时间”，没有则取“船舶预计离港时间”
        sail_time = timeline.get("船舶实际离港时间") 
        if not sail_time:
            sail_time = timeline.get("船舶预计离港时间", "") # 如果预计也没有，设为空字符串

        # 到港时间：优先取“实际到港日”，没有则取“船舶预计靠港时间”
        arrive_time = timeline.get("实际到港日")
        if not arrive_time:
            arrive_time = timeline.get("船舶预计靠港时间", "")

        # 签收时间：取“货件入库亚马逊仓库时间”
        sign_time = timeline.get("货件入库亚马逊仓库时间", "")
        
        # 5. 核心逻辑：按流程顺序查找最新节点
        # 从上往下遍历流程，找到最后一个在文本中出现的时间，就是最新的物流状态
        latest_info = ""
        for step in process_steps:
            if step in timeline:
                latest_info = f"{step} {timeline[step]} ————（"+datetime.now().strftime('%Y-%m-%d')+"）"

        return latest_info, sail_time, arrive_time, sign_time, is_inspected

    def search(self, tracking_no):
        """查询单个运单号，返回结果字典"""
        if not self.is_logged_in:
            return None

        print(f"正在查询: {tracking_no}")
        try:
            # 导航到查询页
            self.page.locator("a").filter(has_text="状态追踪").click()
            
            # 填入单号并搜索
            self.page.get_by_role("textbox", name="主提单号/H提单号/客户编号/进仓编号/业务编号").fill(tracking_no)
            self.page.get_by_role("button", name="查询").click()
            
            # 点击业务信息查看详情
            self.page.get_by_role("button", name="业务信息").click()
            
            # --- 数据提取逻辑 ---
            # 1. 提取船名航次
            voyage_info = ""
            try:
                # 等待元素出现，最多5秒
                sv_locator = self.page.locator("sv:nth-child(10) > .sv__detail").first
                sv_locator.wait_for(timeout=5000)
                voyage_info = sv_locator.inner_text().strip()
                voyage_info = '' if voyage_info == '-' else voyage_info
            except Exception as e:
                print(f"船名航次提取失败: {e}")

            # 2. 提取轨迹信息 
            trace_text = ""
            latest_info = ""
            sail_time = ""
            arrive_time = ""
            sign_time = ""
            try:
                status_block = self.page.locator("div.ant-row").filter(has_text="客户订舱下单时间").first
                status_block.wait_for(timeout=5000)
                trace_text = status_block.inner_text()
                latest_info, sail_time, arrive_time, sign_time, is_inspected = self.extract_latest_logistics_info(trace_text)
            except Exception as e:
                trace_text = ""
                latest_info = ""
                print(f"轨迹提取失败: {e}")

            # --- 判断状态 ---
            # 如果签收时间不为空，则为"已签收"，否则为"在途"
            status = "签收" if sign_time else "在途"
            latest_info = "Done" if status == "签收" else latest_info

            # --- 返回整合数据 ---
            return {
                "voyage_info": voyage_info,      # 船名航次
                "trace": trace_text,             # 完整轨迹
                "latest_info": latest_info,      # 最新轨迹
                "sail_time": sail_time,          # 开船时间
                "arrive_time": arrive_time,      # 到港时间
                "sign_time": sign_time,          # 签收时间
                "is_inspected": is_inspected,    # 是否被查验
                "status": status                 # 当前状态
            }

        except Exception as e:
            print(f"查询 {tracking_no} 出错: {e}")
            return None
        
def main():
    # --- 第一步：加载 .env 文件 ---
    # 读取 .env 文件中的配置到环境变量中
    load_dotenv()

    # --- 第二步：从环境变量中获取配置 ---
    username = os.getenv("DAINIFEI_USERNAME", "18922884510")
    password = os.getenv("DAINIFEI_PASSWORD", "ds18922884510")

    # 从 .env 读取其他配置
    headless = os.getenv("CRAWLER_HEADLESS", "false").lower() == "true"
    timeout = int(os.getenv("CRAWLER_TIMEOUT", "30")) * 1000 # 转换为毫秒

    if not username or not password:
        print("❌ 错误：未在 .env 文件中找到 DAINIFEI_USERNAME 或 DAINIFEI_PASSWORD")
        return

    print(f"ℹ️ 正在使用账号: {username} 初始化爬虫...")

    # --- 第三步：启动 Playwright 和爬虫逻辑 ---
    with sync_playwright() as p:
        # 使用从 .env 读取的参数来启动浏览器
        # headless=True 表示无头模式（不显示浏览器），False 表示有界面
        browser = p.chromium.launch(headless=headless)

        page = browser.new_page()

        try:
            # 1. 创建爬虫实例
            spider = DainifeiSpider(page, username, password)

            # 2. 登录
            spider.login()

            # 3. 搜索 (给出一个测试单号)
            tracking_no = "DSAU260100351"
            result = spider.search(tracking_no)

            if result:
                print("=== 查询结果 ===")
                print(f"船名航次: {result.get('voyage_info')}")
                print(f"最新状态: {result.get('latest_info')}")
                print(f"完整轨迹: \n{result.get('trace')}")
                print(f"开船时间: {result.get('sail_time')}")
                print(f"到港时间: {result.get('arrive_time')}")
                print(f"签收时间: {result.get('sign_time')}")
                print(f"是否查验: {result.get('is_inspected')}")
                print(f"当前状态: {result.get('status')}")
            else:
                print("查询失败")

        except Exception as e:
            print(f"运行出错: {e}")
        finally:
            # 浏览器保持打开或关闭，根据你的需求调整
            browser.close()

if __name__ == "__main__":
    main()