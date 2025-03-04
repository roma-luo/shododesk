import json
import os

# 定义基础目录（当前脚本所在目录）
base_dir = os.path.dirname(os.path.abspath(__file__))

# 输入文件夹路径（与上一段脚本保持一致，默认为 'input' 文件夹）
input_directory = os.path.join(base_dir, "input")  # 用户如需修改，请调整此路径

# 设置输入文件路径，默认为 input/time_axis_contours.json
input_path = os.path.join(input_directory, "time_axis_contours.json")

# 设置输出文件夹路径，默认为 input/filter_input
output_directory = os.path.join(input_directory, "filter_input")  # 用户如需修改，请调整此路径
os.makedirs(output_directory, exist_ok=True)  # 如果输出目录不存在，则创建

# 设置输出文件路径
output_path = os.path.join(output_directory, "filtered_time_axis_contours.json")

# 各类别的缩放比例，仅缩放 y 方向
scaling_factors = {
    "head": {"scale_y": 1.0},  # 头部
    "body": {"scale_y": 1.0},  # 身体
    "legs": {"scale_y": 1.0}   # 腿部
}

def perpendicular_distance(point, start, end):
    """计算点 point 到线段 start-end 的垂直距离"""
    x1, y1 = start["x"], start["y"]
    x2, y2 = end["x"], end["y"]
    x0, y0 = point["x"], point["y"]

    if x1 == x2 and y1 == y2:
        return ((x0 - x1)**2 + (y0 - y1)**2)**0.5

    numerator = abs((y2 - y1)*x0 - (x2 - x1)*y0 + x2*y1 - y2*x1)
    denominator = ((y2 - y1)**2 + (x2 - x1)**2)**0.5
    return numerator / denominator

def rdp(points, epsilon):
    """使用 Ramer-Douglas-Peucker 算法对点集进行简化"""
    if len(points) < 3:
        return points

    start, end = points[0], points[-1]
    max_dist = 0.0
    index = 0
    for i in range(1, len(points)-1):
        dist = perpendicular_distance(points[i], start, end)
        if dist > max_dist:
            index = i
            max_dist = dist

    if max_dist > epsilon:
        left = rdp(points[:index+1], epsilon)
        right = rdp(points[index:], epsilon)
        return left[:-1] + right
    else:
        return [start, end]

# RDP 算法公差
rdp_epsilon = 1.8

if not os.path.exists(input_path):
    print(f"输入文件 {input_path} 不存在，请检查路径。")
    exit()

with open(input_path, 'r') as f:
    data = json.load(f)

filtered_data = []

def scale_y_and_translate(points, scale_y, y_offset):
    """对点列表进行 y 方向缩放 + 平移，但这里我们不再进行 y_offset 位移，直接传入 y_offset=0"""
    scaled_points = []
    for point in points:
        x = point["x"]
        y = point["y"] * scale_y + y_offset  # 此处 y_offset 为 0，不改变原有 y 逻辑
        scaled_points.append({"x": x, "y": y})
    return scaled_points

# 遍历 JSON 数据（只处理一遍，不再进行全局偏移）
for item in data:
    if item["type"] == "contour":
        categories = item.get("categories", {"head": [], "body": [], "legs": []})
        processed_categories = {}

        # 无需 max_y_previous 和 global_y_shift，直接不对 y 进行整体对齐
        global_min_y = float('inf')
        global_max_y = -float('inf')

        for category, points in categories.items():
            if not points:
                processed_categories[category] = []
                continue

            if category in scaling_factors:
                scale_y = scaling_factors[category]["scale_y"]
                # 不计算 y_offset，直接使用 0
                y_offset = 0

                # 缩放（不平移）点集
                processed_points = scale_y_and_translate(points, scale_y, y_offset)

                # 对 head、body、legs 执行 RDP 简化
                if category in ["head", "body", "legs"]:
                    processed_points = rdp(processed_points, rdp_epsilon)

                processed_categories[category] = processed_points

                # 更新全局最小值与最大值
                cat_min_y = min(p["y"] for p in processed_points)
                cat_max_y = max(p["y"] for p in processed_points)
                if cat_min_y < global_min_y:
                    global_min_y = cat_min_y
                if cat_max_y > global_max_y:
                    global_max_y = cat_max_y
            else:
                processed_categories[category] = points
                if points:
                    cat_min_y = min(p["y"] for p in points)
                    cat_max_y = max(p["y"] for p in points)
                    if cat_min_y < global_min_y:
                        global_min_y = cat_min_y
                    if cat_max_y > global_max_y:
                        global_max_y = cat_max_y

        contour_item = {
            "type": "contour",
            "categories": processed_categories,
            "height_info": {
                "min_y": global_min_y if global_min_y != float('inf') else None,
                "max_y": global_max_y if global_max_y != -float('inf') else None
            }
        }

        filtered_data.append(contour_item)

    else:
        # 非 "contour" 类型数据不做额外处理，直接保持原样
        filtered_data.append(item)

# 不再进行第二遍全局偏移，因已移除该逻辑

# 保存处理后的数据到新的 JSON 文件
with open(output_path, 'w') as f:
    json.dump(filtered_data, f, indent=4)
    print(f"处理后的数据已保存到 {output_path}")
