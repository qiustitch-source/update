# notice.py
# 钉钉机器人消息发送模块
# 功能：通过钉钉机器人 API 发送私聊消息，支持 Token 延迟初始化和自动刷新

import requests
import json
import logging

from config import DINGTALK_CONFIG

logger = logging.getLogger(__name__)


class DingTalkRobot:
    """钉钉机器人类：用于发送钉钉私聊消息
    采用延迟初始化策略：只在第一次发送消息时才获取 Token，避免网络问题导致程序启动失败
    """
    def __init__(self, app_key, app_secret, robot_code):
        self.app_key = app_key
        self.app_secret = app_secret
        self.robot_code = robot_code
        self._token = None  # 延迟初始化，只在需要时才获取

    @property
    def token(self):
        """延迟初始化 Token：只在第一次访问时获取"""
        if self._token is None:
            self._token = self._get_token()
        return self._token

    @token.setter
    def token(self, value):
        self._token = value

    def _get_token(self):
        """获取 Access Token
        调用钉钉 API 获取 access_token，用于后续消息发送
        """
        url = "https://oapi.dingtalk.com/gettoken"
        params = {'appkey': self.app_key, 'appsecret': self.app_secret}
        res = requests.get(url, params=params).json()
        token = res.get('access_token')
        if not token:
            logger.error(f"获取钉钉 Token 失败: {res}")
        return token

    def send_private_message(self, user_id, content):
        """给指定用户发送单聊 Markdown 消息
        如果 Token 过期（返回 40014/42001 错误），自动刷新 Token 并重试一次
        """
        result = self._do_send(user_id, content)
        # 如果返回 token 过期错误，刷新后重试一次
        if result.get('code') and str(result.get('code')) in ('40014', '42001', 'InvalidAuthentication'):
            logger.info("钉钉 Token 已过期，正在刷新...")
            self.token = self._get_token()
            result = self._do_send(user_id, content)
        if result.get('code') and result.get('code') != '0':
            logger.error(f"钉钉消息发送失败: {result}")
        return result

    def _do_send(self, user_id, content):
        """实际发送请求"""
        url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        headers = {
            'x-acs-dingtalk-access-token': self.token,
            'Content-Type': 'application/json'
        }
        payload = {
            "robotCode": self.robot_code,
            "userIds": [user_id],
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps({
                "title": "物流状态通知",
                "text": content
            })
        }
        response = requests.post(url, json=payload, headers=headers)
        return response.json()


def main():
    bot = DingTalkRobot(DINGTALK_CONFIG['app_key'], DINGTALK_CONFIG['app_secret'], DINGTALK_CONFIG['robot_code'])
    result = bot.send_private_message('39696335541171342', "## 物流更新测试\n\n发货流程表已更新，请及时查看。")
    print("发送结果:", result)

if __name__ == '__main__':
    main()
