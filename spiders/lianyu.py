import os
import re
import logging
from datetime import datetime

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from spiders.base_spider import BaseSpider

logger = logging.getLogger(__name__)


class LianyuSpider(BaseSpider):
    """联宇物流（坤云）爬虫"""

    LOGIN_URL = "https://client.kunyun.link-trans.com/user/login?redirect=%252Fonline%252Fbulk-cargo"
    SEARCH_URL = "https://client.kunyun.link-trans.com/order/bulk-cargo"

    def login(self):
        logger.info("正在登录联宇物流...")
        self.page.goto(self.LOGIN_URL)
        self.page.get_by_role("textbox", name="请输入账号").fill(self.username)
        self.page.get_by_role("textbox", name="密码").fill(self.password)
        self.page.get_by_role("button", name="立即登录").click()

        try:
            self.page.wait_for_url("**/online/**", timeout=15000)
            logger.info("登录成功")
            self.is_logged_in = True
        except Exception:
            logger.warning("登录后未跳转到预期页面，请检查账号密码")
            self.is_logged_in = False

    def _open_bulk_cargo_page(self):
        self.page.goto(self.SEARCH_URL)
        try:
            self.page.get_by_role("button", name="搜 索").wait_for(
                state="visible", timeout=15000
            )
        except Exception:
            pass
        self.page.wait_for_timeout(800)

    def _select_search_field(self):
        selects = self.page.locator(".ant-select:not(.ant-select-disabled)")
        for i in range(selects.count()):
            sel = selects.nth(i)
            sel.click()
            self.page.wait_for_timeout(300)
            option = self.page.locator(".ant-select-item").filter(has_text="系统SO号").first
            if option.is_visible(timeout=1500):
                option.click()
                logger.info("已选择搜索字段：系统SO号")
                self.page.wait_for_timeout(300)
                return
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(200)
        raise RuntimeError("未找到包含 '系统SO号' 选项的搜索字段选择器")

    def _get_value_select(self):
        field = self.page.locator(".ant-select").filter(has_text="系统SO号").first
        return field.locator("xpath=following-sibling::div[contains(@class, 'ant-select')][1]")

    def _input_tracking_no(self, tracking_no: str):
        value_select = self._get_value_select()
        value_select.wait_for(state="visible", timeout=5000)
        value_select.click()
        value_input = value_select.locator("input.ant-select-selection-search-input").first
        if value_input.count() == 0:
            value_input = value_select.locator("input").first
        value_input.click()
        value_input.fill(tracking_no)
        self.page.wait_for_timeout(500)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(300)
        self.page.keyboard.press("Escape")
        logger.info(f"已输入运单号: {tracking_no}")

    def _click_search_button(self):
        self.page.get_by_role("button", name="搜 索").click()
        logger.info("已点击搜索")

    def _click_accepted_tab(self):
        tab = self.page.locator(".ant-tabs-tab").filter(has_text="已受理").first
        if tab.count() == 0:
            tab = self.page.get_by_text("已受理", exact=True).first
        tab.click()
        logger.info("已点击已受理")
        self.page.wait_for_timeout(1500)

    def _click_route_button(self):
        """点击 button.routeClass 打开路由轨迹弹窗"""
        btn = self.page.locator("button.routeClass").first
        btn.wait_for(state="visible", timeout=10000)
        btn.click()
        logger.info("已点击路由信息按钮")
        self.safe_wait("text=路由轨迹", timeout=10000)

    @staticmethod
    def _parse_nodes(text):
        def norm(s):
            return s.replace("/", "-").strip() if s else ""

        def find_preschedule():
            # 预配船期用于兜底：没有实际开船/到港节点时，再取这里的 ETD/ETA
            m = re.search(
                r"预配船期[:：]\s*(.*?)\s+ETD[:：]\s*(\d{4}-\d{1,2}-\d{1,2})"
                r"(?:\s+ETA[:：]\s*(\d{4}-\d{1,2}-\d{1,2}))?",
                text,
            )
            if not m:
                return "", "", ""
            return m.group(1).strip(), m.group(2), m.group(3) or ""

        date_pat = r"(\d{4}/\d{1,2}/\d{1,2})\s+星期[一二三四五六日天]"
        keywords = [
            "货物已签收", "开船时间", "出口报关放行", "货物已装柜",
            "转运中心已收货", "订单已受理", "订单已下单",
            "到港时间", "清关已放行", "查验放行", "出口查验",
        ]
        timeline = {}
        # 联宇轨迹是“日期在前、节点在后”，这里按真实页面结构提取节点日期
        for kw in keywords:
            m = re.search(date_pat + r"\s+" + re.escape(kw), text)
            if m:
                timeline[kw] = norm(m.group(1))

        voyage_info = ""
        m = re.search(r"船名航次[:：]\s*([^\n]+)", text)
        if m:
            voyage_info = m.group(1).strip()
        preschedule_voyage, etd, eta = find_preschedule()
        if not voyage_info:
            voyage_info = preschedule_voyage

        sail_time = timeline.get("开船时间", "")
        arrive_time = timeline.get("到港时间", "")
        sign_time = timeline.get("货物已签收", "")
        # 实际节点优先；页面没有实际节点时，才使用预配船期中的预计 ETD/ETA
        if not sail_time and etd:
            sail_time = etd
        if not arrive_time and eta:
            arrive_time = eta

        is_inspected = "查验" in text

        process_order = [
            "订单已下单", "订单已受理", "转运中心已收货", "货物已装柜",
            "出口报关放行", "开船时间", "货物已签收",
        ]
        latest_info = ""
        for step in process_order:
            if step in timeline:
                latest_info = f"{step} {timeline[step]} ————（{datetime.now().strftime('%Y-%m-%d')}）"

        return {
            "voyage_info": voyage_info,
            "sail_time": sail_time,
            "arrive_time": arrive_time,
            "sign_time": sign_time,
            "is_inspected": is_inspected,
            "latest_info": latest_info,
        }

    @staticmethod
    def _format_trace(text):
        # 将弹窗里的多行轨迹整理为“一条日期 + 多个描述”的单行事件，便于写回 Excel
        date_line_pat = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}\s+星期[一二三四五六日天]$")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        events = []
        current_date = ""
        current_items = []

        for line in lines:
            if date_line_pat.match(line):
                if current_date and current_items:
                    events.append((current_date, current_items))
                current_date = line
                current_items = []
                continue
            if current_date:
                current_items.append(line)

        if current_date and current_items:
            events.append((current_date, current_items))

        return "\n".join(
            f"{event_date} ： {' ，'.join(items)}"
            for event_date, items in events
        )

    @staticmethod
    def _get_latest_trace(trace):
        for line in trace.splitlines():
            line = line.strip()
            if line:
                return line
        return ""

    def search(self, tracking_no: str):
        if not self.is_logged_in:
            return None
        logger.info(f"正在查询联宇运单: {tracking_no}")
        try:
            self._open_bulk_cargo_page()
            self._select_search_field()
            self._input_tracking_no(tracking_no)
            self._click_search_button()
            self.page.wait_for_timeout(1500)
            self._click_accepted_tab()

            # 点击路由信息按钮
            self._click_route_button()

            # 定位弹窗
            modal = self.page.locator(
                ".ant-modal-content, .ant-drawer-content"
            ).filter(has_text="路由轨迹").first
            modal.wait_for(timeout=8000)

            # 等待 "网络请求中..." 消失
            try:
                self.page.locator(
                    ".ant-modal-content, .ant-drawer-content"
                ).filter(has_text="网络请求中").wait_for(state="hidden", timeout=15000)
            except Exception:
                logger.warning("等待物流数据加载超时")
            self.page.wait_for_timeout(800)

            trace_text = modal.inner_text()
            formatted_trace = self._format_trace(trace_text)
            parsed = self._parse_nodes(trace_text)
            trace = formatted_trace or trace_text

            status = "签收" if parsed["sign_time"] else "在途"
            # 签收货件按现有业务规则写 Done；在途货件取完整轨迹第一条作为最新物流
            if status == "签收":
                latest_info = "Done"
            else:
                latest_trace = self._get_latest_trace(trace)
                latest_info = (
                    f"{latest_trace}  ————（{datetime.now().strftime('%Y-%m-%d')}）"
                    if latest_trace
                    else parsed["latest_info"]
                )

            return {
                "voyage_info": parsed["voyage_info"],
                "trace": trace,
                "latest_info": latest_info,
                "sail_time": parsed["sail_time"],
                "arrive_time": parsed["arrive_time"],
                "sign_time": parsed["sign_time"],
                "is_inspected": parsed["is_inspected"],
                "status": status,
            }
        except Exception as e:
            logger.error(f"查询联宇 {tracking_no} 出错: {e}")
            return None
        finally:
            # 无论成功失败，关闭可能残留的弹窗，避免影响下一次查询
            try:
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
            except Exception:
                pass


def main():
    load_dotenv()
    username = os.getenv("LIANYU_USERNAME", "")
    password = os.getenv("LIANYU_PASSWORD", "")
    headless = os.getenv("CRAWLER_HEADLESS", "false").lower() == "true"

    if not username or not password:
        print("❌ 未在 .env 中找到 LIANYU_USERNAME / LIANYU_PASSWORD")
        return

    print(f"ℹ️ 正在使用账号: {username} 初始化爬虫...")

    test_list = [
        "990260400016726",
        "990260400016733",
        "990260400101220",
        "990260500088078",
        "990260500086572",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            spider = LianyuSpider(page=page, username=username, password=password)
            spider.login()
            for tracking_no in test_list:
                print(f"\n{'=' * 50}")
                print(f"当前单号: {tracking_no}")
                print("=" * 50)
                result = spider.search(tracking_no)
                if result:
                    print(f"船名航次: {result.get('voyage_info')}")
                    print(f"最新状态: {result.get('latest_info')}")
                    print(f"完整轨迹:\n{result.get('trace')}")
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
            browser.close()


if __name__ == "__main__":
    main()
