# 物流追踪自动化系统

跨境电商物流追踪自动化工具，自动从多个货代平台爬取物流状态，更新 Excel 数据并推送钉钉通知。

## 功能特性

- **多货代支持**：覆盖 8 家货代，包含网页爬取、API 调用、本地 Excel 三种数据获取方式
- **自动状态更新**：爬取开船、到港、签收等关键节点，自动写入 Excel
- **异常检测**：自动识别延期（>5天）、查验、延误三类异常
- **钉钉通知**：状态变更和异常汇总通过钉钉机器人私聊推送至对应负责人
- **桌面快捷运行**：支持双击 .bat 文件一键执行

## 支持的货代

| 货代 | 数据获取方式 | 技术方案 |
|------|-------------|---------|
| 袋你飞 | 网页爬取 | Playwright（Angular SPA） |
| 海桥 | 网页爬取 | Playwright + 滑块验证码 |
| 心达 | 网页爬取 | Playwright |
| 丛林鸟 | 网页爬取 | Playwright |
| 易派 (E-Express) | 网页爬取 | Playwright（frameset 页面） |
| 纽酷 | REST API | HTTP + JWT Token 缓存 |
| 辰舟 | 本地 Excel | openpyxl + 背景色判断 |
| 欧杰 | 本地 Excel | openpyxl |

## 技术栈

- **Python 3.9+**
- **Playwright** — 浏览器自动化
- **PostgreSQL** — 临时数据缓存
- **pandas + openpyxl** — Excel 读写
- **钉钉机器人 API** — 消息推送
- **requests** — HTTP 请求
- **pywinauto + pyautogui** — 钉钉桌面自动化

## 项目结构

├── main.py                # 主入口，编排全流程
├── config.py              # 配置中心，从 .env 加载
├── database.py            # 数据库操作（建表、查询、更新）
├── excel_handler.py       # Excel 读写
├── notice.py              # 钉钉机器人消息推送
├── dingtalk_automation.py # 钉钉桌面自动化（上传/下载文件）
├── spiders/
│   ├── base_spider.py     # 爬虫基类（统一接口）
│   ├── dainifei.py        # 袋你飞
│   ├── haiqiao.py         # 海桥
│   ├── xinda.py           # 心达
│   ├── junglebird.py      # 丛林鸟
│   ├── yipai.py           # 易派 (E-Express)
│   ├── niuku.py           # 纽酷（API 模式）
│   └── local_strategies.py # 辰舟/欧杰（本地 Excel）
├── docs/                  # 项目文档
└── requirements.txt       # 依赖清单


## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
2. 配置环境变量
复制 .env.example 为 .env，填写以下配置：


# 数据库
DB_HOST=localhost
DB_PORT=5432
DB_NAME=tracking
DB_USER=postgres
DB_PASSWORD=your_password

# 钉钉机器人
DINGTALK_APP_KEY=your_app_key
DINGTALK_APP_SECRET=your_app_secret
DINGTALK_ROBOT_CODE=your_robot_code

# 货代账号
DAINIFEI_USERNAME=xxx
DAINIFEI_PASSWORD=xxx
# ... 其他货代账号

# 文件路径
MAIN_EXCEL_PATH=D:\path\to\发货数据详情.xlsx
CHENZHOU_FILE_PATH=D:\path\to\辰舟.xlsx
OUJIE_FILE_PATH=D:\path\to\欧杰.xlsx

# 业务配置（JSON 格式）
MANAGER_MAPPING={"张三":"user_id_1","李四":"user_id_2"}
US_SITE_MANAGER=["user_id_1"]
3. 运行

python main.py
或双击桌面 run_logistics.bat 快捷方式。

工作流程

Excel 数据导入 → 数据库缓存 → 按货代分组爬取 → 状态对比更新 → 异常分析 → 钉钉通知 → 数据写回 Excel
扩展新货代
在 spiders/ 下新建文件，继承 BaseSpider
实现 login() 和 search(tracking_no) 方法
在 main.py 的 SPIDER_FACTORY 中注册
在 .env 中添加账号配置

License
Private — 内部使用
