import unittest

from spiders.niuku_accounts import (
    normalize_niuku_accounts,
    query_niuku_with_accounts,
)


class FakeSpider:
    def __init__(self, result):
        self.result = result
        self.is_logged_in = False
        self.login_calls = 0
        self.searches = []

    def needs_login(self):
        return True

    def login(self):
        self.login_calls += 1
        self.is_logged_in = True
        return True

    def search_with_retry(self, tracking_no):
        self.searches.append(tracking_no)
        return self.result


class NiuKuAccountTests(unittest.TestCase):
    def test_primary_account_is_first_then_extra_accounts(self):
        accounts = normalize_niuku_accounts(
            primary_user="main_user",
            primary_pwd="main_pwd",
            extra_accounts={
                "backup_a": {"user": "backup_user", "pwd": "backup_pwd"},
            },
        )

        self.assertEqual(["primary", "backup_a"], [account["key"] for account in accounts])
        self.assertEqual("main_user", accounts[0]["user"])
        self.assertEqual("backup_pwd", accounts[1]["pwd"])

    def test_query_uses_backup_when_primary_has_no_tracking(self):
        accounts = [
            {"key": "primary", "user": "main_user", "pwd": "main_pwd"},
            {"key": "backup_a", "user": "backup_user", "pwd": "backup_pwd"},
        ]
        spiders = {
            "primary": FakeSpider({"trace": "", "latest_info": "", "status": "在途"}),
            "backup_a": FakeSpider({"trace": "2026-07-15 : 已开船", "latest_info": "已开船"}),
        }

        result, account = query_niuku_with_accounts(
            "STAR-001",
            accounts,
            lambda account_config: spiders[account_config["key"]],
        )

        self.assertEqual("backup_a", account["key"])
        self.assertEqual("已开船", result["latest_info"])
        self.assertEqual(["STAR-001"], spiders["primary"].searches)
        self.assertEqual(["STAR-001"], spiders["backup_a"].searches)

    def test_query_stops_when_primary_has_tracking(self):
        accounts = [
            {"key": "primary", "user": "main_user", "pwd": "main_pwd"},
            {"key": "backup_a", "user": "backup_user", "pwd": "backup_pwd"},
        ]
        spiders = {
            "primary": FakeSpider({"trace": "2026-07-15 : 已开船", "latest_info": "已开船"}),
            "backup_a": FakeSpider({"trace": "backup should not run", "latest_info": "backup"}),
        }

        result, account = query_niuku_with_accounts(
            "STAR-002",
            accounts,
            lambda account_config: spiders[account_config["key"]],
        )

        self.assertEqual("primary", account["key"])
        self.assertEqual("已开船", result["latest_info"])
        self.assertEqual(["STAR-002"], spiders["primary"].searches)
        self.assertEqual([], spiders["backup_a"].searches)


if __name__ == "__main__":
    unittest.main()
