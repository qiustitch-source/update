
import os
import time
from dotenv import load_dotenv
import re
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, Playwright


class XinDaSpider:
    def __init__(self, page: Page, username, password):
        self.page = page
        self.username = username
        self.password = password
        self.is_logged_in = False

    def login(self):
        """执行登录逻辑（心达系统）"""
        print("正在登录心达物流系统...")
        self.page.goto("http://szxdgj.nextsls.com/tms/wos/login?redirect_url=%2Ftms%2Fwos")
        
        # 填写账号密码
        self.page.get_by_role("textbox", name="用户名").fill(self.username)
        self.page.get_by_role("textbox", name="密码").fill(self.password)
        
        # 点击登录
        self.page.get_by_role("button", name="登 录").click()

        try:
            # --- 判断登录成功：处理弹窗 ---
            # 源码中有 "×" 按钮，推测是欢迎弹窗
            try:
                close_btn = self.page.get_by_text("×")
                close_btn.wait_for(timeout=3000)
                close_btn.click()
                print("检测到并关闭了欢迎弹窗")
            except:
                print("未检测到欢迎弹窗")

            # --- 导航到运单页面 ---
            # 根据源码，菜单路径是 "发货运单工单" -> "运单"
            # 1. 点击一级菜单
            self.page.get_by_text("发货运单工单").click()
            time.sleep(1) # 等待二级菜单展开
            
            # 2. 点击二级菜单 "运单"
            order_menu = self.page.get_by_role("link", name=" 运单")
            order_menu.wait_for(timeout=10000)
            order_menu.click()
            
            print("登录并进入运单查询页成功")
            self.is_logged_in = True
            
        except Exception as e:
            print(f"登录或导航失败: {e}")
    
    @staticmethod
 

    def parse_logistics_data(raw_list):
        """
        通用物流数据解析器：
        1. 能够精准提取包含特殊符号（点号、括号、斜杠）的复杂船名。
        2. 确保在“已开船”状态下优先锁定正确的日期。
        """
        trace = []
        latest_info = ""
        sail_time = ""
        arrive_time = ""
        sign_time = ""
        voyage_info = ""
        current_year = datetime.now().year

        # --- 辅助函数：标准化日期 ---
        def standardize_date(text, base_year=current_year):
            if not text: return ""
            # 1. 优先匹配 YYYY-MM-DD
            long_match = re.search(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", text)
            if long_match:
                return f"{long_match.group(1)}-{int(long_match.group(2)):02d}-{int(long_match.group(3)):02d}"
            
            # 2. 匹配 MM-DD (利用负向环视防止误抓航次编号)
            short_match = re.search(r"(?<!\d)(\d{1,2})[-/\.](\d{1,2})(?!\d)", text)
            if short_match:
                m, d = int(short_match.group(1)), int(short_match.group(2))
                if 1 <= m <= 12 and 1 <= d <= 31:
                    try:
                        return datetime(base_year, m, d).strftime("%Y-%m-%d")
                    except: pass
            return ""

        # 数据预处理（严格保留原逻辑）
        if isinstance(raw_list, list) and raw_list:
            if ' ：' in raw_list[0]:
                trace = raw_list
            else:
                raw_str = raw_list[0]
                parts = raw_str.split('\n')
                if '#' in parts[0]:
                    parts = parts[1:]
                parts = [p.strip() for p in parts if p.strip()]
                for i in range(0, len(parts), 2):
                    if i + 1 < len(parts):
                        trace.append(f"{parts[i]} ：{parts[i + 1]}")

        if not trace: return [], "", "", "", "", ""
        # 记录最新状态
        latest_info = trace[0] + "————（" + datetime.now().strftime('%Y-%m-%d') + "）"

        for item in trace:
            content_part = item.split('：', 1)[1] if '：' in item else item
            try:
                log_year = int(item[:4])
            except:
                log_year = current_year

            # 1. 提取签收时间
            if not sign_time and any(kw in content_part.upper() for kw in ["已签收", "DELIVERED"]):
                sign_time = standardize_date(content_part, log_year)
                if not sign_time:
                    sign_time = standardize_date(item, log_year)
            # 2. 提取开船时间 (sail_time)
            # 改进点：优先识别明确带有“已开船”或“已离港”字样的行及其前面的日期
            if not sail_time or ("已开船" in content_part or "已离港" in content_part):
                # 模式 A: 匹配 "日期 已开船" 或 "日期 已离港"
                actual_match = re.search(r"(\d{1,2}[/\-\.]\d{1,2})\s*(?:已开船|已离港|已离境)", content_part)
                if actual_match:
                    sail_time = standardize_date(actual_match.group(1), log_year)
                # 模式 B: 匹配 ETD 标签或普通开船描述
                elif not sail_time:
                    etd_match = re.search(r"(?:ETD|开船|离港)[：:]?\s*([\d\-\./]+)", content_part, re.I)
                    if etd_match:
                        sail_time = standardize_date(etd_match.group(1), log_year)
                    else:
                        # 兜底：抓取该行第一个日期
                        general_date = re.search(r"(\d{1,2}[/\-\.]\d{1,2})", content_part)
                        if general_date:
                            sail_time = standardize_date(general_date.group(1), log_year)

            # 3. 提取到港时间 (arrive_time)
            if not arrive_time:
                # 优先匹配带有到港标识的日期
                eta_match = re.search(r"(?:ETA|到港|送仓)[：:]?\s*([\d\-\./]+)", content_part, re.I)
                if eta_match:
                    arrive_time = standardize_date(eta_match.group(1), log_year)
                else:
                    # 兜底：如果一行有多个日期，取第二个
                    all_dates = re.findall(r"(?<!\d)\d{1,2}[/\-]\d{1,2}(?!\d)", content_part)
                    if len(all_dates) >= 2:
                        arrive_time = standardize_date(all_dates[1], log_year)

            is_new_vessel = any(kw in content_part for kw in ["新船期", "新船名航次", "新的船名航次"]) 
            if not voyage_info or is_new_vessel:
                v_match = re.search(r"(?:新的船名航次|船名航次|航名航次|已装柜|VV|新船期)[：:，\s]+([a-zA-Z0-9\s\(\)/\.\-]+)", content_part)
                if v_match:
                    raw_v = v_match.group(1).strip()
                    clean_voyage = re.split(r"(?i)\s*(?:ETD|ETA|预计|,|，|(?<![a-zA-Z0-9])\d{1,2}[/\-]\d{1,2})", raw_v)[0].strip()
                    temp_voyage = clean_voyage.rstrip('。').strip()
                    
                    # 如果找到了有效船名，且它是“新”的，或者是第一次找到，则赋值
                    if temp_voyage:
                        voyage_info = temp_voyage
                        # 如果已经匹配到了明确的“新”船期，后续旧记录（如已装柜）将不再覆盖它
                        if is_new_vessel:
                            # 标记已锁定最新船名，防止被后续旧记录（如“已装柜”）覆盖
                            # 这里可以理解为：一旦从“新船期”拿到值，就不再进入这个 if
                            pass

        return trace, latest_info, sail_time, arrive_time, sign_time, voyage_info
    
    def search(self, tracking_no):
        """
        查询单个运单号。
        """
        if not self.is_logged_in:
            print("请先登录")
            return None

        print(f"正在查询: {tracking_no}")
        try:
            # 1. 填入单号并回车查询
            search_box = self.page.get_by_role("textbox", name="输入单号查询，多个请用“,”隔开")
            search_box.fill(tracking_no)
            search_box.press("Enter")
            
            # 等待列表刷新
            time.sleep(2) 

            # 2. 点击具体的单号（进入详情页）
            self.page.get_by_text(tracking_no).click()
            
            # 等待详情页加载
            time.sleep(3)

            # --- 数据提取逻辑 ---
            # 根据脚本，轨迹信息在 class="pod-route-info" 的元素中
            texts = []
            latest_info = ""
            sail_time = ""
            arrive_time = ""
            sign_time = ""
            voyage_info = ""
            is_inspected = False
            self.page.wait_for_load_state("networkidle", timeout=20000)
            result_locator = self.page.locator(".pod-route-info")
            
            if result_locator.count() > 0:
                texts = result_locator.all_inner_texts()
                self.page.keyboard.press("Escape")
                print(f"提取到的物流轨迹信息：\n{texts}")
            if texts:   
                trace, latest_info, sail_time, arrive_time, sign_time, voyage_info = self.parse_logistics_data(texts)
                # --- 判断是否被查验 ---
                is_inspected = any("查验" in item for item in trace)
                # --- 判断状态 ---
                # 如果签收时间不为空，则为"签收"，否则为"在途"
                status = "签收" if sign_time else "在途"
                latest_info = "Done" if status == "签收" else latest_info

                # --- 返回整合数据 ---
                return {
                    "voyage_info": voyage_info,      # 船名航次
                    "trace": trace,                  # 完整轨迹
                    "latest_info": latest_info,      # 最新轨迹
                    "sail_time": sail_time,          # 开船时间
                    "arrive_time": arrive_time,      # 到港时间
                    "sign_time": sign_time,          # 签收时间
                    "is_inspected": is_inspected,    # 是否被查验
                    "status": status                 # 当前状态
                }
            else:
                print("未找到轨迹信息节点 (.pod-route-info)")
                return {"error": "未找到轨迹", "trace": "", "latest_info": ""}
                        
        except Exception as e:
            print(f"查询 {tracking_no} 出错: {e}")
            return None


def main():
    # --- 第一步：加载 .env 文件  ---
    load_dotenv()

    # --- 第二步：从环境变量中获取配置 ---
    username = os.getenv("XINDA_USERNAME", "唯镜电子商务") # 提供默认值方便测试
    password = os.getenv("XINDA_PASSWORD", "A123456")
    headless = os.getenv("CRAWLER_HEADLESS", "false").lower() == "true"

    print(f"ℹ️ 正在使用账号: {username} 初始化爬虫...")

    # --- 第三步：启动 Playwright ---
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=50)
        context = browser.new_context()
        page = context.new_page()

        try:
            spider = XinDaSpider(page, username, password)
            spider.login()

            if spider.is_logged_in:
                # 使用测试单号
                testing_no = ["XD2602274801"]
                for tn in testing_no:
                    result = spider.search(tn)
                    if result:
                        print("=== 查询结果 ===")
                        print(f"单号: {tn}")
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