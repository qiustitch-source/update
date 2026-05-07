"""
dingtalk_automation.py - 钉钉桌面自动化工具

功能：通过 pywinauto + pyautogui 控制钉钉桌面客户端，实现：
  1. 从钉钉群聊自动下载 Excel 文件
  2. 调用主流程处理 Excel（爬取物流数据、更新状态）
  3. 将处理后的 Excel 上传回钉钉群聊覆盖原文件

使用前提：
  - 钉钉桌面客户端已安装并登录
  - 屏幕分辨率固定（坐标依赖分辨率，建议 1920x1080）
  - 需要 pywinauto、pyautogui、pyperclip 已安装

注意：
  - 此文件独立于主流程（main.py），单独运行
  - 由于公司钉钉未企业认证，无法通过 API 下载/上传文件，因此使用桌面自动化
  - 钉钉客户端版本更新可能导致 UI 变化，需要重新调试坐标
"""

import os
import time
import logging
import subprocess
import pyperclip
import pyautogui
from pywinauto import Application

from config import FILE_PATHS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== 用户需要根据实际环境修改的配置 ==========

# 钉钉安装路径
DINGTALK_PATH = r"C:\Program Files (x86)\DingDing\main\current\Dingtalk.exe"

# 目标群聊名称
GROUP_NAME = "仓库-运营协作群"

# 目标文件名（在群文件中的文件名）
FILE_NAME = "发货流程表2026.V1.xlsx"

# 主 Excel 文件路径（从 config.py 获取）
MAIN_EXCEL_PATH = FILE_PATHS['main_excel']

# 主 Excel 所在目录（下载和上传都在这个目录操作）
EXCEL_DIR = os.path.dirname(MAIN_EXCEL_PATH) if MAIN_EXCEL_PATH else "."

# "上传为新版本"按钮截图路径（需要用户手动截取钉钉弹出的按钮截图）
# 截图方法：钉钉检测到同名文件时弹出提示框，截取"上传为新版本"按钮的截图
# 截图保存为 assets/ 目录下的 update_version_btn.png
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_BTN_IMAGE = os.path.join(SCRIPT_DIR, "assets", "update_version_btn.png")

# ========== 等待时间配置（秒） ==========
WAIT_DINGTALK_START = 8       # 钉钉启动等待时间
WAIT_SEARCH = 2               # 搜索等待时间
WAIT_FILE_PANEL = 3           # 文件面板加载等待
WAIT_DOWNLOAD = 5             # 文件下载等待
WAIT_UPLOAD = 3               # 文件上传等待
WAIT_DIALOG = 2               # 对话框弹出等待


def setup_dingtalk():
    """唤起并连接钉钉窗口"""
    try:
        app = Application(backend="uia").connect(title_re="钉钉", class_name="StandardFrame")
        logger.info("已连接到钉钉窗口")
    except Exception:
        logger.info("未找到钉钉窗口，正在启动钉钉...")
        os.startfile(DINGTALK_PATH)
        time.sleep(WAIT_DINGTALK_START)
        app = Application(backend="uia").connect(title_re="钉钉", class_name="StandardFrame")
        logger.info("钉钉已启动并连接")

    main_win = app.window(title_re="钉钉")
    main_win.set_focus()
    return main_win


def enter_group(main_win, group_name):
    """搜索并进入指定群聊"""
    logger.info(f"正在搜索群聊: {group_name}")

    # Ctrl+F 打开搜索
    main_win.type_keys('^f')
    time.sleep(WAIT_SEARCH)

    # 粘贴群名
    pyperclip.copy(group_name)
    main_win.type_keys('^v')
    time.sleep(WAIT_SEARCH)

    # 按回车进入群聊
    main_win.type_keys('{ENTER}')
    time.sleep(WAIT_SEARCH)
    logger.info(f"已进入群聊: {group_name}")


def download_file_from_group(main_win, file_name, save_dir):
    """
    从当前群聊的文件面板下载指定文件

    操作流程：
      1. 点击群右上角的"文件"图标（需要根据实际 UI 定位）
      2. 在文件列表中搜索目标文件
      3. 右键点击文件 → 另存为 → 指定路径

    注意：此函数中的坐标操作依赖钉钉版本和屏幕分辨率，
         如果执行失败需要手动调试坐标。
    """
    logger.info("正在打开群文件面板...")

    # --- Step 1: 打开群文件面板 ---
    # 方法A: 通过 Tab 键导航到"文件"按钮（尝试按几次 Tab 到达工具栏）
    # 方法B: 如果知道"文件"按钮的坐标，直接点击
    #
    # 以下使用方法A：按 Tab 键 + Enter 尝试导航
    # 如果你的钉钉版本有"文件"快捷入口，可以取消下面的注释
    #
    # pyautogui.press('tab')  # 导航到工具栏
    # pyautogui.press('tab')
    # pyautogui.press('enter')
    # time.sleep(WAIT_FILE_PANEL)

    # --- Step 2: 在文件面板中搜索文件 ---
    # 假设文件面板已打开，使用 Ctrl+F 搜索
    main_win.type_keys('^f')
    time.sleep(1)
    pyperclip.copy(file_name)
    main_win.type_keys('^v')
    time.sleep(WAIT_SEARCH)

    # --- Step 3: 选中搜索结果并右键另存为 ---
    # 按一次 Tab 让焦点跳到搜索结果列表
    pyautogui.press('tab')
    time.sleep(1)

    # 右键点击第一项
    pyautogui.rightClick()
    time.sleep(WAIT_DIALOG)

    # 按 'a' 键选择"另存为"（钉钉右键菜单中"另存为"的快捷键）
    # 注意：不同钉钉版本快捷键可能不同，需要实际测试
    pyautogui.press('a')
    time.sleep(WAIT_DIALOG)

    # --- Step 4: 在"另存为"对话框中输入路径 ---
    try:
        save_as_win = Application(backend="win32").connect(title="另存为", timeout=5)
        save_path = os.path.join(save_dir, file_name)
        save_as_win.window(title="另存为").type_keys(save_path)
        time.sleep(1)
        save_as_win.window(title="另存为").type_keys('{ENTER}')
        time.sleep(WAIT_DOWNLOAD)

        # 如果文件已存在，弹窗提示覆盖，按 'y' 确认
        pyautogui.press('y')
        time.sleep(1)

        logger.info(f"文件已下载到: {save_path}")
        return True
    except Exception as e:
        logger.error(f"下载文件失败（可能'另存为'对话框未出现）: {e}")
        logger.error("请手动下载文件后继续，或检查钉钉版本是否更新了 UI")
        return False


def run_main_pipeline():
    """调用主流程处理 Excel 文件"""
    logger.info("正在调用主流程处理 Excel...")

    try:
        # 导入并执行主流程
        from database import init_db
        from main import load_excel_to_db, process_crawlers, analyze_logistics_exceptions, send_notifications
        from excel_handler import read_and_update_excel
        from notice import DingTalkRobot
        from config import DINGTALK_CONFIG

        # Step 1: 初始化数据库并导入 Excel
        init_db()
        load_excel_to_db(MAIN_EXCEL_PATH)

        # Step 2: 创建钉钉机器人实例，执行爬虫
        bot = DingTalkRobot(DINGTALK_CONFIG['app_key'], DINGTALK_CONFIG['app_secret'], DINGTALK_CONFIG['robot_code'])
        process_crawlers(bot=bot)

        # Step 3: 异常分析和通知
        us_list, others, inspections, delations = analyze_logistics_exceptions()
        send_notifications(us_list, others, inspections, delations, bot=bot)

        # Step 4: 写回 Excel
        read_and_update_excel(MAIN_EXCEL_PATH, '发货数据详情')

        logger.info("主流程处理完成！")
        return True

    except Exception as e:
        logger.error(f"主流程执行失败: {e}")
        return False


def upload_and_cover(main_win, file_path):
    """
    将处理后的文件上传到钉钉群聊并覆盖原文件

    操作流程：
      1. 在钉钉群聊输入框中粘贴文件
      2. 钉钉检测到同名文件会弹出"上传为新版本"提示
      3. 点击"上传为新版本"按钮

    注意：需要 update_version_btn.png 截图文件才能自动识别按钮
    """
    logger.info("正在上传文件并覆盖...")

    # --- Step 1: 确保焦点在钉钉群聊 ---
    main_win.set_focus()
    time.sleep(1)

    # --- Step 2: 打开文件资源管理器并复制文件 ---
    # 用资源管理器打开并选中文件
    subprocess.Popen(f'explorer /select,"{file_path}"')
    time.sleep(2)

    # 等资源管理器出现后，按 Ctrl+C 复制选中的文件
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(1)

    # --- Step 3: 回到钉钉，粘贴文件到聊天输入框 ---
    main_win.set_focus()
    time.sleep(1)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(WAIT_UPLOAD)

    # --- Step 4: 处理"上传为新版本"弹窗 ---
    if os.path.exists(UPLOAD_BTN_IMAGE):
        # 有截图文件，尝试图像识别
        btn_location = pyautogui.locateOnScreen(UPLOAD_BTN_IMAGE, confidence=0.8)
        if btn_location:
            center = pyautogui.center(btn_location)
            pyautogui.click(center)
            logger.info("已点击'上传为新版本'按钮（图像识别）")
        else:
            logger.warning("未识别到'上传为新版本'按钮，尝试按回车确认...")
            pyautogui.press('enter')
    else:
        # 没有截图文件，提示用户
        logger.warning(f"缺少按钮截图文件: {UPLOAD_BTN_IMAGE}")
        logger.warning("请手动点击'上传为新版本'按钮，或截取按钮截图后重试")
        logger.warning("截图方法：钉钉弹出同名文件提示时，截取'上传为新版本'按钮")
        input("处理完成后按回车继续...")

    time.sleep(WAIT_UPLOAD)
    logger.info("文件上传完成！")


# ========== 主执行流程 ==========
if __name__ == "__main__":
    print("=" * 50)
    print("  钉钉桌面自动化 - 物流更新全流程")
    print("=" * 50)
    print()
    print("流程说明：")
    print("  1. 自动从钉钉群下载 Excel 文件")
    print("  2. 执行物流爬取和更新（主流程）")
    print("  3. 将更新后的 Excel 上传回钉钉群覆盖")
    print()

    # 检查钉钉路径是否存在
    if not os.path.exists(DINGTALK_PATH):
        logger.error(f"钉钉路径不存在: {DINGTALK_PATH}")
        logger.error("请修改 dingtalk_automation.py 中的 DINGTALK_PATH 为你的钉钉安装路径")
        exit(1)

    # 检查主 Excel 路径
    if not MAIN_EXCEL_PATH:
        logger.error("未配置 MAIN_EXCEL_PATH，请检查 .env 文件")
        exit(1)

    try:
        # ===== Step 1: 连接钉钉 =====
        logger.info("===== Step 1: 连接钉钉 =====")
        dw = setup_dingtalk()

        # ===== Step 2: 进入群聊 =====
        logger.info("===== Step 2: 进入群聊 =====")
        enter_group(dw, GROUP_NAME)

        # ===== Step 3: 下载文件 =====
        logger.info("===== Step 3: 下载文件 =====")
        download_ok = download_file_from_group(dw, FILE_NAME, EXCEL_DIR)
        if not download_ok:
            logger.warning("自动下载失败，请手动下载 Excel 文件到以下路径后继续：")
            logger.warning(f"  {MAIN_EXCEL_PATH}")
            input("下载完成后按回车继续...")

        # ===== Step 4: 确认文件存在 =====
        if not os.path.exists(MAIN_EXCEL_PATH):
            logger.error(f"Excel 文件不存在: {MAIN_EXCEL_PATH}")
            logger.error("请确认文件已下载到正确位置")
            exit(1)

        # ===== Step 5: 执行主流程 =====
        logger.info("===== Step 4: 执行物流更新主流程 =====")
        pipeline_ok = run_main_pipeline()
        if not pipeline_ok:
            logger.error("主流程执行失败，跳过上传步骤")
            exit(1)

        # ===== Step 6: 上传覆盖 =====
        logger.info("===== Step 5: 上传文件到钉钉 =====")
        upload_and_cover(dw, MAIN_EXCEL_PATH)

        logger.info("=" * 50)
        logger.info("  全部流程执行完毕！")
        logger.info("=" * 50)

    except KeyboardInterrupt:
        logger.info("用户中断执行")
    except Exception as e:
        logger.error(f"执行过程中出错: {e}")
        raise
