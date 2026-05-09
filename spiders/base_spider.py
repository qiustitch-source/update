# base_spider.py
# 爬虫抽象基类
# 定义了所有爬虫的通用接口：login、search、search_with_retry、safe_wait
# 所有爬虫都应继承此类，根据需要重写 needs_browser() 和 needs_login() 方法

from __future__ import annotations
from playwright.sync_api import Page
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class BaseSpider:
    """爬虫抽象基类：定义通用接口和重试机制
    所有爬虫都应继承此类并实现 login() 和 search() 方法
    """
    def __init__(self, **kwargs):
        """接受任意参数，子类按需使用"""
        self.page: Optional[Page] = kwargs.get('page')
        self.username: str = kwargs.get('username', '')
        self.password: str = kwargs.get('password', '')
        self.is_logged_in: bool = False

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

    def needs_browser(self) -> bool:
        """是否需要浏览器，默认 True
        API 爬虫和本地 Excel 策略应返回 False
        """
        return True

    def needs_login(self) -> bool:
        """是否需要登录，默认 True
        无需登录的爬虫应返回 False
        """
        return True

    def set_page(self, page):
        """设置 page 对象"""
        self.page = page