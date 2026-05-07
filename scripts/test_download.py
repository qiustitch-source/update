"""
test_download.py - 钉钉文件下载功能测试

从钉钉群聊自动下载 Excel 文件。
仅依赖 pyautogui + pyperclip + ctypes，不依赖 pywinauto/pywin32。

使用前：
  1. 钉钉桌面客户端已打开并登录（版本 8.x）
  2. 程序会自动最小化所有窗口，只保留钉钉在前台
  3. 运行后不要动鼠标键盘，除非紧急停止（鼠标甩到左上角）
"""

import os
import sys
import time
import shutil
import logging
import subprocess
import ctypes
from ctypes import wintypes
import pyperclip
import pyautogui

pyautogui.FAILSAFE = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== 配置区 ==========
DINGTALK_PATH = r"C:\Program Files (x86)\DingDing\main\current\Dingtalk.exe"
GROUP_NAME = "仓库-运营协作群"
FILE_NAME = "发货流程表2026.V1.xlsx"
SAVE_DIR = r"C:\Users\25a04\Desktop\货代更新"
# ============================

# Windows 鼠标事件常量
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def countdown(seconds, reason=""):
    """倒计时等待"""
    if reason:
        logger.info(f"{reason}（等待 {seconds} 秒）")
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"\r  倒计时: {i}s ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r                \n")
    sys.stdout.flush()


def prepare_environment():
    """脚本启动时调用一次：最小化所有窗口，然后恢复钉钉到前台"""
    logger.info("正在最小化其他窗口...")
    subprocess.run(
        ['powershell', '-Command',
         '(New-Object -ComObject Shell.Application).MinimizeAll()'],
        capture_output=True, timeout=5
    )
    time.sleep(1)
    # os.startfile 对已运行的程序会激活/恢复其窗口
    os.startfile(DINGTALK_PATH)
    time.sleep(3)
    logger.info("钉钉已恢复到前台")


def focus_dingtalk():
    """强制激活钉钉到前台（三种方式叠加，确保可靠）"""
    # 方式1: os.startfile 恢复已运行的钉钉实例（最可靠）
    os.startfile(DINGTALK_PATH)
    time.sleep(0.5)
    # 方式2: ctypes 查找钉钉窗口并置顶
    # 遍历顶级窗口，找到标题包含"钉钉"的窗口
    hwnd = ctypes.windll.user32.FindWindowW(None, "钉钉")
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)


def click_instant(x, y):
    """瞬移鼠标并左键点击（ctypes SetCursorPos，不经过中间像素）"""
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def click_without_cursor_move(x, y):
    """不移动鼠标光标，直接向坐标处窗口发送点击消息（PostMessage）"""
    point = wintypes.POINT(int(x), int(y))
    hwnd = ctypes.windll.user32.WindowFromPoint(point)
    if not hwnd:
        return False
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    rel_x = int(x) - rect.left
    rel_y = int(y) - rect.top
    lparam = (rel_y << 16) | (rel_x & 0xFFFF)
    ctypes.windll.user32.PostMessageW(hwnd, 0x0201, 1, lparam)   # WM_LBUTTONDOWN
    time.sleep(0.05)
    ctypes.windll.user32.PostMessageW(hwnd, 0x0202, 0, lparam)   # WM_LBUTTONUP
    return True


# ========== 主流程步骤 ==========

def step1_activate_dingtalk():
    """Step 1: 启动/激活钉钉"""
    logger.info("=" * 40)
    logger.info("Step 1: 激活钉钉窗口")
    logger.info("=" * 40)

    if not os.path.exists(DINGTALK_PATH):
        logger.error(f"钉钉路径不存在: {DINGTALK_PATH}")
        sys.exit(1)

    os.startfile(DINGTALK_PATH)
    countdown(5, "等待钉钉启动")
    focus_dingtalk()
    countdown(2, "等待钉钉窗口置前")
    logger.info("钉钉已在前台")


def step2_enter_group():
    """Step 2: 搜索并进入群聊"""
    logger.info("=" * 40)
    logger.info(f"Step 2: 搜索群聊 [{GROUP_NAME}]")
    logger.info("=" * 40)

    focus_dingtalk()
    time.sleep(0.5)

    # 钉钉 8.x 搜索快捷键 Ctrl+Shift+F
    pyautogui.hotkey('ctrl', 'shift', 'f')
    countdown(2, "等待搜索框弹出")

    # 输入群名
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.3)
    pyperclip.copy(GROUP_NAME)
    pyautogui.hotkey('ctrl', 'v')
    countdown(2, "等待搜索结果加载")

    # 按回车进入搜索结果
    pyautogui.press('enter')
    countdown(2, "等待进入群聊")
    pyautogui.press('enter')
    countdown(2, "确认进入群聊")
    logger.info("搜索群聊操作完成")


def step3_open_file_tab():
    """Step 3: 点击群文件标签"""
    logger.info("=" * 40)
    logger.info("Step 3: 打开群文件面板")
    logger.info("=" * 40)

    focus_dingtalk()
    time.sleep(0.5)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_tab_img = os.path.join(script_dir, "..", "assets", "file_tab_btn.png")

    if os.path.exists(file_tab_img):
        try:
            location = pyautogui.locateOnScreen(file_tab_img, confidence=0.8)
            if location:
                center = pyautogui.center(location)
                pyautogui.click(center)
                logger.info(f"已通过截图识别点击'文件'标签，坐标: {center}")
                countdown(3, "等待文件面板加载")
                return True
            else:
                logger.warning("截图文件存在但未在屏幕上找到匹配")
        except Exception as e:
            logger.warning(f"截图识别失败: {e}")
    else:
        logger.info("未找到 file_tab_btn.png 截图，跳过截图识别")

    # 备用：键盘导航
    logger.info("尝试通过键盘导航到'文件'标签...")
    focus_dingtalk()
    time.sleep(0.3)
    screen_w, _ = pyautogui.size()
    pyautogui.click(screen_w // 3, _ := pyautogui.size()[1] // 2)
    time.sleep(0.5)
    for _ in range(8):
        pyautogui.press('tab')
        time.sleep(0.1)
    pyautogui.press('right')
    time.sleep(0.3)
    pyautogui.press('enter')
    countdown(3, "等待文件面板加载")
    return True


def step4_find_and_download():
    """Step 4: 搜索文件并下载"""
    logger.info("=" * 40)
    logger.info(f"Step 4: 查找并下载文件 [{FILE_NAME}]")
    logger.info("=" * 40)

    os.makedirs(SAVE_DIR, exist_ok=True)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_file = os.path.join(SAVE_DIR, FILE_NAME)
    default_download = os.path.join(os.path.expanduser("~"), "Downloads")
    search_btn_pos = None

    # --- 4.1 点击"搜索"按钮 ---
    logger.info("4.1 查找并点击'搜索'按钮...")
    focus_dingtalk()
    time.sleep(0.5)

    search_btn_img = os.path.join(script_dir, "..", "assets", "search_btn.png")
    search_clicked = False

    if os.path.exists(search_btn_img):
        for conf in [0.8, 0.7, 0.6]:
            try:
                location = pyautogui.locateOnScreen(search_btn_img, confidence=conf)
                if location:
                    center = pyautogui.center(location)
                    search_btn_pos = (center.x, center.y)
                    pyautogui.click(center)
                    logger.info(f"已点击'搜索'按钮 (confidence={conf})，坐标: {center}")
                    countdown(2, "等待搜索框出现")
                    search_clicked = True
                    break
            except Exception as e:
                logger.warning(f"截图识别 confidence={conf} 失败: {e}")

    if not search_clicked:
        logger.info("尝试通过 Tab 键导航到搜索输入框...")
        focus_dingtalk()
        time.sleep(0.3)
        for _ in range(5):
            pyautogui.press('tab')
            time.sleep(0.15)
        countdown(1, "等待搜索框聚焦")

    # --- 4.2 输入文件名搜索 ---
    logger.info("4.2 输入文件名进行搜索...")
    # 点击搜索输入框区域，确保光标聚焦到输入框
    if search_btn_pos:
        pyautogui.click(search_btn_pos[0], search_btn_pos[1] + 15)
    else:
        screen_w, _ = pyautogui.size()
        pyautogui.click(screen_w // 2, 170)
    time.sleep(0.5)

    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.3)
    pyperclip.copy(FILE_NAME)
    pyautogui.hotkey('ctrl', 'v')
    countdown(3, "等待搜索结果加载")
    logger.info(f"已输入文件名: {FILE_NAME}")

    # --- 4.3 点击搜索结果 ---
    logger.info("4.3 点击搜索结果...")
    focus_dingtalk()
    time.sleep(0.3)

    if search_btn_pos:
        result_x = search_btn_pos[0]
        result_y = search_btn_pos[1] + 80
    else:
        screen_w, _ = pyautogui.size()
        result_x = screen_w // 2
        result_y = 280

    logger.info(f"点击搜索结果，坐标: ({result_x}, {result_y})")
    pyautogui.click(result_x, result_y)
    time.sleep(0.8)

    # --- 4.4 右键菜单选择"下载" ---
    # 策略：右键后不移动鼠标，用两种方式尝试点击菜单项
    # 方式1: PostMessage（光标完全不动，菜单不会消失）
    # 方式2: click_instant 瞬移点击（备用）
    # 覆盖菜单出现在右下/左下两种情况

    # 菜单偏移量：(x偏移, y偏移)
    # y: 第1项≈20px, 第2项≈48px, 第3项≈76px
    menu_offsets = [
        (50, 48),    # 右下 第2项
        (-50, 48),   # 左下 第2项
        (50, 20),    # 右下 第1项
        (-50, 20),   # 左下 第1项
        (50, 76),    # 右下 第3项
        (-50, 76),   # 左下 第3项
    ]

    for ox, oy in menu_offsets:
        # 关闭残留弹窗
        pyautogui.press('escape')
        time.sleep(0.3)

        # 聚焦钉钉，重新选中文件
        focus_dingtalk()
        time.sleep(0.5)
        pyautogui.click(result_x, result_y)
        time.sleep(0.5)

        # 右键打开菜单
        pyautogui.rightClick(result_x, result_y)
        time.sleep(1)

        # 方式1: PostMessage（光标不动）
        tx, ty = result_x + ox, result_y + oy
        ok = click_without_cursor_move(tx, ty)
        logger.info(f"PostMessage 点击 ({tx},{ty}) 偏移({ox},{oy}) = {ok}")
        time.sleep(2)

        # 检查下载
        for cp in [target_file, os.path.join(default_download, FILE_NAME)]:
            if os.path.exists(cp):
                if cp != target_file:
                    shutil.copy2(cp, target_file)
                logger.info(f"文件下载成功: {target_file} ({os.path.getsize(target_file)} bytes)")
                return True

        # 方式1没成功，关闭弹窗，重新右键，用方式2瞬移点击
        pyautogui.press('escape')
        time.sleep(0.3)
        focus_dingtalk()
        time.sleep(0.5)
        pyautogui.click(result_x, result_y)
        time.sleep(0.5)
        pyautogui.rightClick(result_x, result_y)
        time.sleep(1)
        click_instant(tx, ty)
        logger.info(f"瞬移点击 ({tx},{ty}) 偏移({ox},{oy})")
        time.sleep(2)

        # 再次检查下载
        for cp in [target_file, os.path.join(default_download, FILE_NAME)]:
            if os.path.exists(cp):
                if cp != target_file:
                    shutil.copy2(cp, target_file)
                logger.info(f"文件下载成功: {target_file} ({os.path.getsize(target_file)} bytes)")
                return True

        logger.info(f"偏移({ox},{oy}) 未命中下载，继续尝试...")

    # 所有偏移都没成功，尝试处理另存为对话框
    logger.info("尝试处理另存为对话框...")
    try:
        focus_dingtalk()
        time.sleep(0.3)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.3)
        pyperclip.copy(target_file)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(1)
        pyautogui.press('enter')
        countdown(3, "等待文件保存")
        pyautogui.press('left')
        time.sleep(0.3)
        pyautogui.press('enter')
        countdown(2, "确认覆盖")
        if os.path.exists(target_file):
            logger.info(f"文件下载成功: {target_file} ({os.path.getsize(target_file)} bytes)")
            return True
    except Exception as e:
        logger.warning(f"处理另存为对话框失败: {e}")

    # 最后检查
    countdown(5, "最后检查下载状态")
    for cp in [target_file, os.path.join(default_download, FILE_NAME)]:
        if os.path.exists(cp):
            if cp != target_file:
                shutil.copy2(cp, target_file)
            logger.info(f"文件下载成功: {target_file} ({os.path.getsize(target_file)} bytes)")
            return True

    logger.error("自动下载未能完成")
    logger.info(f"请手动下载，保存到: {target_file}")
    return False


# ========== 入口 ==========
if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  钉钉文件下载测试")
    print("=" * 50)
    print(f"  目标群聊: {GROUP_NAME}")
    print(f"  目标文件: {FILE_NAME}")
    print(f"  保存目录: {SAVE_DIR}")
    print()
    print("  注意事项：")
    print("  - 程序会自动最小化其他窗口，只保留钉钉")
    print("  - 运行期间不要动鼠标键盘")
    print("  - 紧急停止：鼠标快速甩到屏幕左上角")
    print("=" * 50)
    print()

    countdown(10, "准备时间，请确保只打开钉钉")

    try:
        prepare_environment()
        step1_activate_dingtalk()
        step2_enter_group()
        step3_open_file_tab()
        success = step4_find_and_download()

        print()
        if success:
            print("=" * 50)
            print("  [OK] 下载测试完成！文件已成功下载")
            print("=" * 50)
        else:
            print("=" * 50)
            print("  [FAIL] 下载测试失败，请根据日志排查")
            print("=" * 50)

    except pyautogui.FailSafeException:
        logger.warning("鼠标移到左上角，脚本已安全停止")
    except KeyboardInterrupt:
        logger.info("用户中断 (Ctrl+C)")
    except Exception as e:
        logger.error(f"测试出错: {e}")
        raise
