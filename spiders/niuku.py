import os
import re
import time
import json
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NiuKuSpider:
    def __init__(self, page=None, username='J12970B', password='WJ123'):
        """
        纽酷爬虫类：采用 API 接口调用方式。
        :param page: 为了保持结构一致留下的参数，实际 API 不使用 page 对象
        """
        self.username = username
        self.password = password
        self.token = None
        
        # API 终端配置
        self.BASE_URL = 'https://api.usniuku.com/portal/api/1.0/openApi'
        self.LOGIN_URL = f'{self.BASE_URL}/login'
        self.TRACK_URL = f'{self.BASE_URL}/findLogisticsTrack'
        self.DETAIL_URL = f'{self.BASE_URL}/getFirstLegOrderDetail'
        self.CACHE_FILE = 'niuku_token_cache.json'

    def _get_cached_token(self):
        """获取本地缓存的 Token"""
        if not os.path.exists(self.CACHE_FILE):
            return None, 0
        try:
            with open(self.CACHE_FILE, 'r') as f:
                data = json.load(f)
                return data.get('token'), data.get('timestamp', 0)
        except:
            return None, 0

    def _cache_token(self, token):
        """缓存 Token 到本地"""
        with open(self.CACHE_FILE, 'w') as f:
            json.dump({'token': token, 'timestamp': int(time.time())}, f)

    def login(self):
        """获取并验证登录 Token"""
        token, ts = self._get_cached_token()
        if token and (time.time() - ts) < 24 * 60 * 60:
            self.token = token
            logging.info("使用纽酷缓存 Token 成功")
            return True

        logging.info(f"正在登录纽酷账号: {self.username}")
        try:
            # 纽酷接口对请求头有时有校验，建议补全
            headers = {'Content-Type': 'application/json'}
            resp = requests.post(self.LOGIN_URL, json={
                'account': self.username,
                'password': self.password
            }, headers=headers, timeout=10)
            
            resp.raise_for_status()
            data = resp.json()
            
            if str(data.get('code')) == "200":
                # 确保 token 路径正确，部分接口可能直接在 data 下或 data['token']
                self.token = data.get('data', {}).get('token')
                if not self.token:
                    logging.error(f"登录响应成功但未找到 Token: {data}")
                    return False
                self._cache_token(self.token)
                logging.info("纽酷登录成功并缓存 Token")
                return True
            else:
                logging.error(f"纽酷登录失败。响应内容: {data}")
                return False
        except Exception as e:
            logging.error(f"纽酷登录接口异常: {e}")
            return False
    def search(self, tracking_no):
        """
        执行查询逻辑
        :param tracking_no: 客户单号 (clientNo)
        """
        if not self.token:
            if not self.login():
                return {"error": "登录失败", "status": "无权限"}

        logging.info(f"正在查询纽酷单号: {tracking_no}")
        try:
            headers = {'token': self.token, 'Content-Type': 'application/json'}

            # 1. 获取订单详情（提取船名航次、ETD、ETA）
            detail_resp = requests.post(self.DETAIL_URL, json={'clientNo': tracking_no}, headers=headers, timeout=10)
            detail_resp.raise_for_status()
            detail_json = detail_resp.json()

            # 2. 解析轨迹数据
            tracks = self._parse_tracks(detail_json)
            
            # 3. 解析详情数据（船名航次等）
            container_info = self._parse_container(detail_json)

            # 4. 提取关键时间节点
            sail_time, arrive_time, sign_time, is_inspected = self._extract_times_and_inspection(tracks)
            
            # 逻辑：如果没有实际开船时间，则使用 API 返回的预计 ETD
            if not sail_time and container_info['etd'] != 'N/A':
                sail_time = container_info['etd']
            if not arrive_time and container_info['eta'] != 'N/A':
                arrive_time = container_info['eta']

            # 5. 构造返回结构
            status = "签收" if sign_time else "在途"
            
            # 构造完整轨迹文本
            trace_text = "\n".join([f"{t['date']} : {t['content']}" for t in tracks])
            
            # 构造最新信息
            latest_info = ""
            if status == "签收":
                latest_info = "Done"
            elif tracks:
                latest_info = f"{tracks[0]['date']} {tracks[0]['content']}————（{datetime.now().strftime('%Y-%m-%d')}）"

            return {
                "trace": trace_text,
                "latest_info": latest_info,
                "sail_time": self._format_date(sail_time),
                "arrive_time": self._format_date(arrive_time),
                "sign_time":  self._format_date(sign_time),
                "is_inspected": is_inspected,
                "voyage_info": container_info['shipNo'] if container_info['shipNo'] != 'N/A' else "",
                "status": status
            }

        except Exception as e:
            logging.error(f"查询纽酷单号 {tracking_no} 出错: {e}")
            return {"error": str(e), "trace": "", "latest_info": "查询失败"}

    def _parse_tracks(self, response_json):
        """解析轨迹列表"""
        try:
            track_list = response_json.get('data', {}).get('logisticsTrackResponseList', [])
            result = []
            for track in track_list:
                result.append({
                    'date': track.get('date', 'N/A'),
                    'content': track.get('content', '无描述')
                })
            # 按时间倒序
            return sorted(result, key=lambda x: x['date'], reverse=True)
        except:
            return []

    def _parse_container(self, response_json):
        """解析集装箱/船舶详情"""
        data = response_json.get('data', {})
        container = data.get('openApiContainerResponse', {}) or {}
        return {
            'shipNo': container.get('shipNo', 'N/A'),
            'eta': container.get('eta', 'N/A'),
            'etd': container.get('etd', 'N/A'),
            'pol': container.get('pol', 'N/A'),
            'podEnd': container.get('podEnd', 'N/A'),
            'dispatchType': container.get('dispatchType', 'N/A')
        }

    def _extract_times_and_inspection(self, tracks):
        """从轨迹中提取开船、到港、签收、查验状态"""
        sail_time = ""
        arrive_time = ""
        sign_time = ""
        is_inspected = False
        
        for t in tracks:
            content = t['content']
            # 提取开船
            if not sail_time and '已开船' in content:
                sail_time = t['date']
            # 提取到港时间
            if not arrive_time and ('已到港' in content or '抵达' in content):
                arrive_time = t['date']
            # 提取签收
            if not sign_time and '已签收' in content:
                sign_time = t['date']
            # 提取查验
            if '查验' in content:
                is_inspected = True
                
        return sail_time, arrive_time, sign_time, is_inspected
    
    def _format_date(self, date_str):
        """
        统一格式化日期为 YYYY-MM-DD
        支持输入: '2026-01-22 14:30:00', '2026/01/22', '2026-01-22'
        """
        if not date_str or date_str == 'N/A':
            return ""
        
        date_str = str(date_str).strip()
        
        try:
            # 1. 尝试直接截取空格前的时间 (处理 2026-01-22 12:00:00 这种情况最快)
            if '-' in date_str and ' ' in date_str:
                return date_str.split(' ')[0]
            
            # 2. 如果是 2026/01/22 这种格式，替换斜杠
            if '/' in date_str:
                date_str = date_str.replace('/', '-')
                # 如果有时间部分，再次截取
                if ' ' in date_str:
                    date_str = date_str.split(' ')[0]
                return date_str

            # 3. 尝试使用 datetime 解析标准格式 (作为兜底验证)
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
            
        except ValueError:
            # 如果解析失败，尝试解析带时间的
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%Y-%m-%d")
            except:
                # 实在解析不了，返回原样或空
                return date_str if date_str else ""

# --- 主函数：用于本地测试 ---
def main():
    # 加载环境变量
    load_dotenv()
    
    # 从 .env 获取配置
    username = os.getenv("NIUKU_USERNAME",'J12970B')
    password = os.getenv("NIUKU_PASSWORD",'WJ123')
    
    if not username or not password:
        print("❌ 错误: 请在 .env 文件中配置 NIUKU_USERNAME 和 NIUKU_PASSWORD")
        return

    # 初始化爬虫（API 模式不需要传入 Playwright 的 page，但为了保持类接口统一，构造函数接收它）
    spider = NiuKuSpider(username=username, password=password)
    
    # 执行登录
    if spider.login():
        # 测试查询单号
        test_no = "STAR-VW5GQWDNDN6KY" 
        result = spider.search(test_no)
        
        if "error" not in result:
            print("\n" + "="*50)
            print(f"📊 纽酷查询结果 [{test_no}]")
            print("-" * 50)
            print(f"最新信息: {result['latest_info']}")
            print(f"状态:     {result['status']}")
            print(f"开船时间: {result['sail_time']}")
            print(f"到港时间: {result['arrive_time']}")
            print(f"签收时间: {result['sign_time']}")
            print(f"船名航次: {result['voyage_info']}")
            print(f"是否查验: {result['is_inspected']}")
            print("-" * 50)
            print(f"完整轨迹:\n{result['trace']}")
        else:
            print(f"❌ 查询失败: {result.get('error')}")

if __name__ == "__main__":
    main()