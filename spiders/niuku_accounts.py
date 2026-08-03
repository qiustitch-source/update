import logging
from typing import Callable, Iterable, Optional


TRACKING_SIGNAL_KEYS = (
    "trace",
    "latest_info",
    "sail_time",
    "arrive_time",
    "sign_time",
    "voyage_info",
)


def normalize_niuku_accounts(
    primary_user: Optional[str],
    primary_pwd: Optional[str],
    extra_accounts: Optional[dict],
    *,
    strict: bool = False,
):
    """Build an ordered NiuKu account list with the legacy account first."""
    accounts = []
    if primary_user and primary_pwd:
        accounts.append({
            "key": "primary",
            "user": str(primary_user).strip(),
            "pwd": str(primary_pwd).strip(),
        })

    for key, cred in (extra_accounts or {}).items():
        if not isinstance(cred, dict):
            if strict:
                raise ValueError(f"NIUKU_EXTRA_ACCOUNTS.{key} must be an object")
            continue

        user = cred.get("user") or cred.get("username") or cred.get("account")
        pwd = cred.get("pwd") or cred.get("password")
        if not user or not pwd:
            if strict:
                raise ValueError(f"NIUKU_EXTRA_ACCOUNTS.{key} must include user and pwd")
            continue

        accounts.append({
            "key": str(key).strip(),
            "user": str(user).strip(),
            "pwd": str(pwd).strip(),
        })

    return accounts


def niuku_result_has_tracking(result) -> bool:
    if not result or result.get("error"):
        return False

    return any(str(result.get(key) or "").strip() for key in TRACKING_SIGNAL_KEYS)


def query_niuku_with_accounts(
    tracking_no: str,
    accounts: Iterable[dict],
    spider_factory: Callable[[dict], object],
    *,
    logger: Optional[logging.Logger] = None,
):
    """Try the primary NiuKu account first, then fall back through extras."""
    for account in accounts:
        account_key = account.get("key") or account.get("user") or "unknown"
        spider = spider_factory(account)

        if spider.needs_login() and not getattr(spider, "is_logged_in", False):
            spider.login()

        result = spider.search_with_retry(tracking_no)
        if niuku_result_has_tracking(result):
            if logger:
                logger.info("纽酷单号 %s 使用账号 [%s] 查询到物流", tracking_no, account_key)
            return result, account

        if logger:
            logger.info("纽酷单号 %s 在账号 [%s] 未查询到有效物流", tracking_no, account_key)

    return None, None
