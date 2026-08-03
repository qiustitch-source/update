# 物流追踪自动化系统

跨境电商物流追踪自动化工具。项目会从发货流程表导入货件数据，按货代查询最新物流状态，写入 PostgreSQL 临时表，发送钉钉通知，并将最新结果回写到 Excel。

## 功能特性

- **多货代支持**：覆盖 8 家货代，包含网页爬取、API 调用、本地 Excel 三种数据获取方式
- **自动状态更新**：爬取完整路径、最新路径、船名航次、开船、到港、签收、查验等关键字段
- **旧表对比**：对比旧发货流程表中的最新状态，记录变化字段和写入字段
- **异常检测**：自动识别延期（>5 天）、查验、延误三类异常
- **钉钉通知**：状态变更和异常汇总通过钉钉机器人私聊推送至对应负责人
- **日志追踪**：按货代分组打印每票货件的查询结果、状态对比、通知对象和通知内容

## 支持的货代

| 货代 | 数据获取方式 | 技术方案 |
| --- | --- | --- |
| 袋你飞 | 网页爬取 | Playwright（Angular SPA） |
| 海桥 | 网页爬取 | Playwright + 滑块验证码 |
| 心达 | 网页爬取 | Playwright |
| 丛林鸟 | 网页爬取 | Playwright |
| 易派 / E-Express | 网页爬取 | Playwright（frameset 页面） |
| 联宇 / 联宇物流 | 网页爬取 | Playwright（坤云平台） |
| 纽酷 | REST API | HTTP + JWT Token 缓存 |
| 辰舟 | 本地 Excel | openpyxl + 背景色判断 |

## 技术栈

- Python 3.9+
- Playwright
- PostgreSQL
- pandas + openpyxl
- 钉钉机器人 API
- requests

## 项目结构

```text
updata_Logistics/
├── main.py                   # 主入口，编排全流程
├── config.py                 # 配置中心，从 .env 加载
├── database.py               # 数据库操作（建表、查询、更新）
├── excel_handler.py          # Excel 读写
├── notice.py                 # 钉钉机器人消息推送
├── requirements.txt          # 依赖清单
├── docs/                     # 项目文档
└── spiders/
    ├── base_spider.py        # 爬虫基类
    ├── dainifei.py           # 袋你飞
    ├── haiqiao.py            # 海桥
    ├── xinda.py              # 心达
    ├── junglebird.py         # 丛林鸟
    ├── yipai.py              # 易派
    ├── lianyu.py             # 联宇
    ├── niuku.py              # 纽酷（API 模式）
    └── local_strategies.py   # 辰舟（本地 Excel）
```

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置环境变量

在项目根目录创建 `.env`，填写数据库、钉钉、文件路径和货代账号。`.env` 已被 `.gitignore` 忽略，不应提交到仓库。

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=tracking
DB_USER=postgres
DB_PASSWORD=your_password

DINGTALK_APP_KEY=your_app_key
DINGTALK_APP_SECRET=your_app_secret
DINGTALK_ROBOT_CODE=your_robot_code

MAIN_EXCEL_PATH=D:\path\to\发货数据详情.xlsx
CHENZHOU_FILE_PATH=D:\path\to\辰舟.xlsx

MANAGER_MAPPING={"张三":"user_id_1","李四":"user_id_2"}
US_SITE_MANAGER=["user_id_1"]

LIANYU_USERNAME=xxx
LIANYU_PASSWORD=xxx
```

其他货代账号同样在 `.env` 中配置，例如 `HAIQIAO_USERNAME`、`HAIQIAO_PASSWORD`。

### 3. 运行

```powershell
python main.py
```

## 工作流程

1. 初始化数据库
2. 从 Excel 导入货件数据
3. 按货代分组查询物流
4. 对比旧状态并发送负责人通知
5. 分析延期、查验、延误异常
6. 发送异常汇总通知
7. 将数据库中的最新结果回写 Excel

## 输出日志

运行日志会同时输出到控制台和 `logs/app.log`。日志目录已被忽略，不会提交到 Git。

每票货件会打印：

- 完整路径
- 最新路径
- 船名航次
- 开船时间
- 到港时间
- 签收时间
- 是否被查验
- 当前状态
- 与旧发货流程表的状态对比
- 实际写入数据库的字段
- 负责人通知对象和通知内容

## 扩展新货代

1. 在 `spiders/` 下新增爬虫文件
2. 继承 `BaseSpider`
3. 实现 `login()` 和 `search(tracking_no)`
4. 在 `main.py` 的 `SPIDER_FACTORY` 中注册
5. 在 `config.py` / `.env` 中补充账号配置

## 文档

- `docs/01_项目概述与业务背景.md`：业务背景和货代列表
- `docs/02_项目逻辑分析.md`：主流程、数据库模型和爬虫策略
- `docs/03_需求文档.md`：PRD 与流程图
- `docs/联宇获取物流流程.docx`：联宇平台流程记录

## License

Private - 内部使用
