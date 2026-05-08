# base_spider.py
# 爬虫抽象基类
# 定义了所有 Playwright 爬虫的通用接口：login、search、search_with_retry、safe_wait
# 所有基于 Playwright 的爬虫（袋你飞、海桥、心达、丛林鸟、易派）都应继承此类

from playwright.sync_api import Page
import logging

logger = logging.getLogger(__name__)

class BaseSpider:
    """爬虫抽象基类：定义通用接口和重试机制
    所有基于 Playwright 的爬虫都应继承此类并实现 login() 和 search() 方法
    """
    def __init__(self, page: Page, username: str = "", password: str = ""):
        self.page = page
        self.username = username
        self.password = password
        self.is_logged_in = False

    def login(self):
        """子类必须实现登录逻辑"""
        raise NotImplementedError("子类必须实现 login 方法")

    def search(self, tracking_no: str):
        """子类必须实现查询逻辑"""
        raise NotImplementedError("子类必须实现 search 方法")

    def search_with_retry(self, tracking_no: str, max_retries: int = 3):
        """带重试的查询，失败时自动重试
        默认重试 3 次，每次重试会记录日志
        """
        for attempt in range(max_retries):
            try:
                result = self.search(tracking_no)
                if result:
                    return result
                logger.warning(f"查询 {tracking_no} 返回空结果，第 {attempt + 1} 次尝试")
            except Exception as e:
                logger.warning(f"查询 {tracking_no} 第 {attempt + 1} 次失败: {e}")
        logger.error(f"查询 {tracking_no} 在 {max_retries} 次尝试后仍失败")
        return None

    def safe_wait(self, selector: str, timeout: int = 10000):
        """封装动态等待，替代 time.sleep"""
        try:
            self.page.wait_for_selector(selector, timeout=timeout, state="visible")
            return True
        except Exception:
            logger.warning(f"等待元素超时: {selector}")
            return False