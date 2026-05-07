import requests
import json
import logging

from config import DINGTALK_CONFIG

logger = logging.getLogger(__name__)


class DingTalkRobot:
    def __init__(self, app_key, app_secret, robot_code):
        self.app_key = app_key
        self.app_secret = app_secret
        self.robot_code = robot_code
        self.token = self._get_token()

    def _get_token(self):
        """获取 Access Token"""
        url = "https://oapi.dingtalk.com/gettoken"
        params = {'appkey': self.app_key, 'appsecret': self.app_secret}
        res = requests.get(url, params=params).json()
        token = res.get('access_token')
        if not token:
            logger.error(f"获取钉钉 Token 失败: {res}")
        return token

    def send_private_message(self, user_id, content):
        """给指定用户发送单聊 Markdown 消息"""
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
        result = response.json()
        if result.get('code') and result.get('code') != '0':
            logger.error(f"钉钉消息发送失败: {result}")
        return result


def main():
    bot = DingTalkRobot(DINGTALK_CONFIG['app_key'], DINGTALK_CONFIG['app_secret'], DINGTALK_CONFIG['robot_code'])
    result = bot.send_private_message('39696335541171342', "## 物流更新测试\n\n发货流程表已更新，请及时查看。")
    print("发送结果:", result)

if __name__ == '__main__':
    main()
