import json
import math
import os

# ========== 输入输出配置 ==========
# 定义基础目录（当前脚本所在目录）
base_dir = os.path.dirname(os.path.abspath(__file__))

# 输入文件路径，假设上一段脚本的输出存放在 "input/filter_input" 文件夹中
input_path = os.path.join(base_dir, "input", "filter_input", "filtered_time_axis_contours.json")

# 输出文件存储目录（请根据需要修改），此处将输出保存到项目根目录下的 "arduino_input" 文件夹中
output_dir = os.path.join(base_dir, "arduino_input")
os.makedirs(output_dir, exist_ok=True)
# 输出文件前缀
output_prefix = os.path.join(output_dir, "converted_output_")

# ========== RDP简化相关配置 ==========
rdp_epsilon = 1.8

def perpendicular_distance(point, start, end):
    """RDP算法所需的垂距计算"""
    if start == end:
        return math.dist(point, start)
    (x0, y0) = point
    (x1, y1) = start
    (x2, y2) = end
    numerator = abs((y2 - y1)*x0 - (x2 - x1)*y0 + x2*y1 - y2*x1)
    denominator = math.sqrt((y2 - y1)**2 + (x2 - x1)**2)
    if denominator == 0:
        return 0.0
    return numerator / denominator

def rdp(points, epsilon):
    """Ramer-Douglas-Peucker 算法简化点集"""
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

def find_continuous_lines_from_connections(points_dict, connections):
    """根据 connections 提取连续线段"""
    adj = {}
    for c in connections:
        s, e = c["start"], c["end"]
        adj.setdefault(s, []).append(e)
        adj.setdefault(e, []).append(s)

    visited = set()
    lines = []
    all_points = list(points_dict.keys())

    for idx in all_points:
        if idx not in visited:
            stack = [idx]
            visited_comp = set()
            component_points = []
            while stack:
                node = stack.pop()
                if node in visited_comp:
                    continue
                visited_comp.add(node)
                component_points.append(node)
                for nb in adj.get(node, []):
                    if nb not in visited_comp:
                        stack.append(nb)
            visited.update(visited_comp)

            endpoints = [p for p in visited_comp if len(adj.get(p, [])) == 1]

            if len(endpoints) == 0:
                # 可能是环或单点
                if len(visited_comp) == 1:
                    single_point = list(visited_comp)[0]
                    lines.append([points_dict[single_point]])
                else:
                    # 环
                    start_ = list(visited_comp)[0]
                    line_order = [start_]
                    used = {start_}
                    current = start_
                    while True:
                        neighbors = [n for n in adj.get(current, []) if n not in used]
                        if not neighbors:
                            break
                        current = neighbors[0]
                        used.add(current)
                        line_order.append(current)
                        if current == start_:
                            break
                    lines.append([points_dict[i] for i in line_order])
            else:
                # 多条线段
                used_global = set()
                for ep in endpoints:
                    if ep not in used_global:
                        line_seg = [ep]
                        used_local = {ep}
                        cur = ep
                        while True:
                            nbs = [n for n in adj.get(cur, []) if n not in used_local]
                            if not nbs:
                                break
                            cur = nbs[0]
                            used_local.add(cur)
                            line_seg.append(cur)
                        used_global.update(line_seg)
                        lines.append([points_dict[i] for i in line_seg])
    return lines

def distance(p1, p2):
    """欧式距离"""
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def reorder_points_nearest_neighbor(points):
    """
    将点集按“最近邻”顺序排列。
    1. 找 (x 最小, y 最小) 作为起点
    2. 不断找距离当前点最近的点直到遍历完
    """
    if not points:
        return []
    start = sorted(points, key=lambda p: (p[0], p[1]))[0]
    ordered = [start]
    unvisited = set(points)
    unvisited.remove(start)
    current = start
    while unvisited:
        next_point = min(unvisited, key=lambda p: distance(current, p))
        ordered.append(next_point)
        unvisited.remove(next_point)
        current = next_point
    return ordered

def process_jawline_points(jawline_points):
    """
    1. 按y从小到大排序
    2. 保留后半段
    3. 用“最近邻”排序
    """
    if not jawline_points:
        return []
    jaw_sorted = sorted(jawline_points, key=lambda p: (p[1], p[0]))
    half_count = len(jaw_sorted) // 2
    kept_points = jaw_sorted[half_count:]
    ordered_line = reorder_points_nearest_neighbor(kept_points)
    return [ordered_line]

def process_nose_points(nose_points):
    """
    1. 按y从小到大排序
    2. 若 >=3 点, 取第3个; 若 >=7 点, 取第7个
    3. 用最近邻排序
    """
    if not nose_points:
        return []
    nose_sorted = sorted(nose_points, key=lambda p: (p[1], p[0]))
    kept_nose_points = []
    if len(nose_sorted) >= 3:
        kept_nose_points.append(nose_sorted[2])
    if len(nose_sorted) >= 7:
        kept_nose_points.append(nose_sorted[6])
    if not kept_nose_points:
        return []
    ordered_line = reorder_points_nearest_neighbor(kept_nose_points)
    return [ordered_line]

# 绕原点 (0,0) 做 -90° 旋转 (顺时针 90°)
def rotate_minus_90(x, y):
    """
    x' =  y
    y' = -x
    """
    return (y, -x)

def process_one_person(full_contour_points, facial_feature_lines, nose_line, person_index, dist_range):
    """
    处理单个“人”的轮廓 & 五官线条，输出到一个 json 文件。
    dist_range = (max_y - min_y) 用来决定笔深度(1/2/3)。
    """
    # === 1) 对 full_contour 做 RDP（可能是一条或多条线） ===
    simplified_full = [rdp(line, rdp_epsilon) for line in full_contour_points]

    # 将线条分别打上标签
    labeled_lines = []
    for line in simplified_full:
        labeled_lines.append(("full", line))
    for line in facial_feature_lines:
        labeled_lines.append(("feat", line))
    if nose_line:
        for line in nose_line:
            labeled_lines.append(("nose", line))

    if not labeled_lines:
        # 如果无人数据
        output_path = f"{output_prefix}{person_index}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return

    # === 2) -90° 旋转 ===
    rotated_lines = []
    for (cat, line) in labeled_lines:
        new_line = [rotate_minus_90(px, py) for (px, py) in line]
        rotated_lines.append((cat, new_line))

    # === 3) 计算 bounding box, 缩放到 [0, <=250] ===
    all_points = []
    for (cat, line) in rotated_lines:
        all_points.extend(line)

    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    width = max_x - min_x
    height = max_y - min_y
    scale = 1.0
    max_dim = max(width, height)
    if max_dim > 250:
        scale = 250.0 / max_dim

    def stage1_transform(px, py):
        x_s = (px - min_x) * scale
        y_s = (py - min_y) * scale
        return (x_s, y_s)

    lines_stage1 = []
    for (cat, line) in rotated_lines:
        transformed_line = [stage1_transform(x, y) for (x, y) in line]
        lines_stage1.append((cat, transformed_line))

    # === 4) 倾斜补偿(此处设为 0 度以示例) ===
    tilt_deg = 0.0
    tilt_slope = math.tan(math.radians(tilt_deg))

    def tilt_transform(px, py):
        return (px, py - px * tilt_slope)

    lines_stage2 = []
    for (cat, line) in lines_stage1:
        new_line = [tilt_transform(x, y) for (x, y) in line]
        lines_stage2.append((cat, new_line))

    # === 5) 再次 bounding box: 平移到 x∈[-112.5,...], y∈[25,...] ===
    all_points2 = []
    for (cat, line) in lines_stage2:
        all_points2.extend(line)

    xs2 = [p[0] for p in all_points2]
    ys2 = [p[1] for p in all_points2]
    min_x2 = min(xs2)
    min_y2 = min(ys2)

    def stage2_transform(px, py):
        x_shifted = px - min_x2 - 100
        y_shifted = py - min_y2 + 30
        return (round(x_shifted, 1), round(y_shifted, 1))

    lines_final = []
    for (cat, line) in lines_stage2:
        final_line = [stage2_transform(x, y) for (x, y) in line]
        lines_final.append((cat, final_line))

    # === 6) 根据 dist_range 分档位 => pen_depth(1/2/3) ===
    # 大于200 => 1, 100~200 => 2, 小于100 => 3
    if dist_range > 200:
        pen_depth = 1
    elif dist_range >= 100:
        pen_depth = 2
    else:
        pen_depth = 3

    print(f"[DEBUG] person_index={person_index}, dist_range={dist_range}, pen_depth={pen_depth}")

    # === 7) 组装 final_points 输出 JSON ===
    final_points = []
    for i, (cat, line) in enumerate(lines_final):
        if not line:
            continue
        if cat == "full":
            if len(line) == 1:
                x0, y0 = line[0]
                final_points.append({"x": x0, "y": y0, "updown": 0})
            else:
                x0, y0 = line[0]
                final_points.append({"x": x0, "y": y0, "updown": pen_depth})
                for (xm, ym) in line[1:-1]:
                    final_points.append({"x": xm, "y": ym, "updown": pen_depth})
                x_end, y_end = line[-1]
                final_points.append({"x": x_end, "y": y_end, "updown": 0})
        elif cat == "feat":
            for (xx, yy) in line:
                final_points.append({"x": xx, "y": yy, "updown": pen_depth})
            last_x, last_y = line[-1]
            final_points.append({"x": last_x, "y": last_y, "updown": 0})
        elif cat == "nose":
            for (xx, yy) in line:
                final_points.append({"x": xx, "y": yy, "updown": pen_depth})
            last_x, last_y = line[-1]
            final_points.append({"x": last_x, "y": last_y, "updown": 0})
            final_points.append({"x": 50.0, "y": 50.0, "updown": 0})

    # === 8) 在生成完所有点后，额外添加指令 ===
    #  1. x=-250, y=50, updown=0
    #  2. x=-250, y=50, updown=1
    #  3. x=-250, y=50, updown=0
    final_points.append({"x": -250.0, "y": 50.0, "updown": 0})
    final_points.append({"x": -250.0, "y": 50.0, "updown": 1})
    final_points.append({"x": -250.0, "y": 50.0, "updown": 1})
    final_points.append({"x": -250.0, "y": 50.0, "updown": 0})

    # === 写出 JSON 文件 ===
    output_path = f"{output_prefix}{person_index}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_points, f, ensure_ascii=False, indent=2)

def main():
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    shapes = data
    person_index = 1

    # 记录当前人的数据
    dist_range_for_person = 0.0
    current_full_contour_lines = []
    current_facial_feature_lines = []
    nose_final_line = None

    got_full = False
    got_face = False

    # 遍历 JSON： 找 "contour" => height_info, "full_contour" => 全身点, "facial_features" => 五官
    for shape in shapes:
        shape_type = shape.get("type")

        if shape_type == "contour":
            # 在第二段脚本里, 只对 "contour" 写入了 height_info
            # 所以这里读取 min_y, max_y => dist_range_for_person
            height_info = shape.get("height_info", {})
            min_y = height_info.get("min_y")
            max_y = height_info.get("max_y")
            if (min_y is not None) and (max_y is not None):
                dist_range_for_person = max_y - min_y
            else:
                dist_range_for_person = 0

        elif shape_type == "full_contour":
            # 读取全身轮廓
            fc_points = shape.get("points", [])
            if fc_points:
                coords = [(p["x"], p["y"]) for p in fc_points]
                current_full_contour_lines = [coords]
            else:
                current_full_contour_lines = []
            got_full = True

        elif shape_type == "facial_features":
            # 面部五官
            jawline_points = []
            nose_points = []
            feature_lines_temp = []
            nose_final_line = None

            categories_dict = shape.get("categories", {})
            for cat_name, cat_data in categories_dict.items():
                points_list = cat_data.get("points", [])
                connections = cat_data.get("connections", [])
                points_dict = {p["index"]: (p["x"], p["y"]) for p in points_list}

                if cat_name == "jawline":
                    for p in points_list:
                        jawline_points.append((p["x"], p["y"]))
                elif cat_name == "nose":
                    for p in points_list:
                        nose_points.append((p["x"], p["y"]))
                else:
                    # 其他五官 => 用 connections 生成线段
                    if connections:
                        cat_lines = find_continuous_lines_from_connections(points_dict, connections)
                        feature_lines_temp.extend(cat_lines)
                    else:
                        if len(points_list) == 1:
                            p = points_list[0]
                            feature_lines_temp.append([(p["x"], p["y"])])
                        elif len(points_list) > 1:
                            coords = [(p["x"], p["y"]) for p in points_list]
                            feature_lines_temp.append(coords)

            # 处理下颌线
            if jawline_points:
                jawline_line = process_jawline_points(jawline_points)
                feature_lines_temp.extend(jawline_line)

            # 处理鼻子
            if nose_points:
                nose_line = process_nose_points(nose_points)
                if nose_line:
                    nose_final_line = nose_line

            current_facial_feature_lines = feature_lines_temp
            got_face = True

        # 一旦 full_contour + facial_features 都就绪 => 输出
        if got_full and got_face:
            process_one_person(
                current_full_contour_lines,
                current_facial_feature_lines,
                nose_final_line,
                person_index,
                dist_range_for_person
            )
            person_index += 1

            # 重置
            dist_range_for_person = 0.0
            current_full_contour_lines = []
            current_facial_feature_lines = []
            nose_final_line = None
            got_full = False
            got_face = False

    print("[MAIN] All done. JSON files saved in:", output_prefix)

if __name__ == "__main__":
    main()
