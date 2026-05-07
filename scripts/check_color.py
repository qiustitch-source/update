import openpyxl

def check_cell_color(file_path, sheet_name, cell_address, target_hex_color):
    """
    检查指定单元格的底色是否为目标颜色
    :param target_hex_color: 16进制颜色代码，例如 'FFFF0000' (纯红)
    """
    # 加载工作簿
    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet = wb[sheet_name]
    cell = sheet[cell_address]
    # 处理合并单元格的情况：如果返回的是元组，取第一个元素
    if isinstance(cell, tuple):
        cell = cell[0]
    
    # 获取单元格填充颜色对象
    fill = cell.fill
    
    # 获取颜色值 (start_color 是填充的主要颜色)
    # 注意：Excel 颜色通常带 Alpha 通道（前两位），如 FFFFFFFF
    current_color = fill.start_color.index
    
    print(f"单元格 {cell_address} 的当前颜色代码为: {current_color}")
    
    if current_color == target_hex_color:
        return True
    else:
        return False

# 示例调用
file = r"C:\Users\25a04\Desktop\货代更新\【唯镜】物流状态更新模版——辰舟.xlsx"
# 假设我们要检查 A1 单元格是否为黄色 (黄色通常是 'FFFFFF00' 或 '00000000' 视索引而定)
is_match = check_cell_color(file, "唯镜录系统模板", "H38", "FFFFFF00")
print(f"颜色匹配结果: {is_match}")