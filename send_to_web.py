# -*- coding: utf-8 -*-
import json
import math
import os
import random
import shutil
import datetime

# ========== 配置部分 ==========

# 1) 原始输入文件
INPUT_JSON_PATH = r"C:\Users\romal\Documents\MArc-Tokyo\Studio\2.0_coding\input\filter_input\filtered_time_axis_contours.json"

# 2) 输出给“viewer-affiliated”的系列文件所在目录 (Arduino 已生成)
ARDUINO_OUTPUT_FOLDER = r"C:\Users\romal\Documents\MArc-Tokyo\Studio\5.0_arduino_input"

# 3) 网站端 uploads 目录，在此下创建时间戳文件夹
WEB_UPLOADS_FOLDER = r"C:\Users\romal\PycharmProjects\obj_api\uploads"

# 4) 弯曲时的一些参数
X_OFFSET_INCREMENT = 639.0     # contour 间的 x 偏移
MAX_LENGTH = 80.0              # 若两点距离超过这个值 => 断线
DIVISION_LENGTH = 8.0          # 导出 JSON 时，每隔多少距离采样一个点
FLIP_Z_IN_EXPORT = True        # 导出时是否对 Z 坐标做 -Z

# 5) 弯曲半径：现在逻辑由脚本**自动**计算
# BEND_RADIUS = scaling_factor * (500 - min_diff)
# scaling_factor ∈ [1.5, 2.0]

# 6) 输出主文件名 (给"viewer"用)
VIEWER_OUTPUT_NAME = "bent_reconstructed.json"

# ========== 几何辅助函数 ==========

def distance_3d(p1, p2):
    """三维点间距"""
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)

def subdivide_by_length(polyline, dist_step):
    """
    将 polyline(点列表) 按指定距离做均匀采样(类似 DivideByLength)。
    返回新的点列表。
    """
    if len(polyline) < 2:
        return polyline[:]

    out_points = []
    lengths = []
    total_len = 0.0
    for i in range(len(polyline)-1):
        seg_len = distance_3d(polyline[i], polyline[i+1])
        lengths.append(seg_len)
        total_len += seg_len

    if total_len == 0:
        return [polyline[0]]

    accumulated = 0.0
    current_target = 0.0
    step = dist_step

    out_points.append(polyline[0])  # 第一个点
    for i, seg_len in enumerate(lengths):
        p_start = polyline[i]
        p_end   = polyline[i+1]
        if seg_len > 0:
            dir_vec = (
                (p_end[0] - p_start[0]) / seg_len,
                (p_end[1] - p_start[1]) / seg_len,
                (p_end[2] - p_start[2]) / seg_len
            )
        else:
            dir_vec = (0,0,0)

        start_dist = accumulated
        end_dist   = accumulated + seg_len

        while current_target <= end_dist:
            if current_target >= start_dist:
                ratio = 0.0
                if seg_len != 0:
                    ratio = (current_target - start_dist)/seg_len
                px = p_start[0] + ratio*(p_end[0] - p_start[0])
                py = p_start[1] + ratio*(p_end[1] - p_start[1])
                pz = p_start[2] + ratio*(p_end[2] - p_start[2])
                new_pt = (px, py, pz)
                if distance_3d(new_pt, out_points[-1])>1e-9:
                    out_points.append(new_pt)
            current_target += step

        accumulated += seg_len

    # 确保终点包含
    if distance_3d(out_points[-1], polyline[-1])>1e-9:
        out_points.append(polyline[-1])
    return out_points


def bend_2d_to_cylinder(polylines, radius):
    """
    将若干 2D (x,y,0) 的折线“卷”到圆柱表面：
    - 先统计 overall min_x, max_x
    - (x - min_x)/(max_x - min_x) * 2π => θ
    - newX = radius*cos(θ), newZ = radius*sin(θ), newY = y
    """
    if not polylines:
        return []

    all_x = []
    for pl in polylines:
        for (x,y,z) in pl:
            all_x.append(x)

    if not all_x:
        return polylines

    min_x = min(all_x)
    max_x = max(all_x)
    if abs(max_x - min_x) < 1e-9:
        return polylines

    bent_result = []
    for pl in polylines:
        new_pl = []
        for (x,y,z) in pl:
            theta = (x - min_x)/(max_x - min_x) * 2.0*math.pi
            newX = radius*math.cos(theta)
            newZ = radius*math.sin(theta)
            newY = y
            new_pl.append((newX, newY, newZ))
        bent_result.append(new_pl)
    return bent_result


# ========== 解析 JSON: 包括 polylines 和 height_info ==========

def parse_filtered_json(json_file, x_offset_increment, max_seg_length):
    """
    解析 filtered_time_axis_contours.json，返回：
      1) polylines: [(x,y,z), ...] 的若干折线
      2) min_diff_in_height: 所有 "height_info" 中 (max_y-min_y) 的最小值
    """

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 用于存储折线
    polylines = []
    contour_index = 0
    current_x_offset = 0.0

    # 用于收集 height_info 的差值
    height_diffs = []

    for item in data:
        # 先看是否有 height_info
        hi = item.get("height_info")
        if hi and "min_y" in hi and "max_y" in hi:
            diff = hi["max_y"] - hi["min_y"]
            height_diffs.append(diff)

        typ = item.get("type", "")
        if typ == "contour":
            x_offset = contour_index * x_offset_increment
            contour_index += 1
            current_x_offset = x_offset

            cats = item.get("categories", {})
            for cat_name, points_list in cats.items():
                if not isinstance(points_list, list):
                    continue

                offset_points = []
                for p in points_list:
                    px = p["x"] + x_offset
                    py = p["y"]
                    offset_points.append((px, py, 0.0))

                # 断线逻辑
                if len(offset_points) < 2:
                    continue
                seg_buf = [offset_points[0]]
                for i_pt in range(1, len(offset_points)):
                    dist_ = distance_3d(seg_buf[-1], offset_points[i_pt])
                    if dist_ <= max_seg_length:
                        seg_buf.append(offset_points[i_pt])
                    else:
                        if len(seg_buf) > 1:
                            polylines.append(seg_buf[:])
                        seg_buf = [offset_points[i_pt]]
                if len(seg_buf) > 1:
                    polylines.append(seg_buf)

        elif typ == "facial_features":
            x_offset = current_x_offset
            categories = item.get("categories", {})

            # 收集 jawline/nose 用于附加处理
            jawline_pts = []
            nose_pts = []

            for feature_key, feature_data in categories.items():
                if isinstance(feature_data, dict):
                    pts_map = {}
                    for p in feature_data.get("points", []):
                        idx = p["index"]
                        px = p["x"] + x_offset
                        py = p["y"]
                        pts_map[idx] = (px, py, 0.0)

                        if feature_key == "jawline":
                            jawline_pts.append((px, py, 0.0))
                        elif feature_key == "nose":
                            nose_pts.append((px, py, 0.0))

                    # connections => 两点线
                    for conn in feature_data.get("connections", []):
                        s = conn["start"]
                        e = conn["end"]
                        if s in pts_map and e in pts_map:
                            dist_ = distance_3d(pts_map[s], pts_map[e])
                            if dist_ <= max_seg_length:
                                polylines.append([pts_map[s], pts_map[e]])

                elif isinstance(feature_data, list):
                    # 不做额外处理
                    pass

            # 额外处理下颌线
            if jawline_pts:
                jaw_sorted = sorted(jawline_pts, key=lambda p: p[1])  # 按 y 排序
                half_count = len(jaw_sorted)//2
                kept = jaw_sorted[half_count:]
                for i_pt, pt in enumerate(kept):
                    min_d = float('inf')
                    closest = None
                    for j_pt, other in enumerate(kept):
                        if i_pt != j_pt:
                            d_ = distance_3d(pt, other)
                            if d_ < min_d:
                                min_d = d_
                                closest = other
                    if closest is not None:
                        polylines.append([pt, closest])

            # 额外处理鼻子
            if nose_pts:
                nose_sorted = sorted(nose_pts, key=lambda p: p[1])
                selected = []
                if len(nose_sorted)>=3:
                    selected.append(nose_sorted[2])
                if len(nose_sorted)>=7:
                    selected.append(nose_sorted[6])
                for i_pt, pt in enumerate(selected):
                    min_d = float('inf')
                    closest = None
                    for j_pt, other in enumerate(selected):
                        if i_pt != j_pt:
                            d_ = distance_3d(pt, other)
                            if d_ < min_d:
                                min_d = d_
                                closest = other
                    if closest:
                        polylines.append([pt, closest])

    # 计算 min_diff_in_height
    if height_diffs:
        min_diff = min(height_diffs)
    else:
        min_diff = 0.0

    return polylines, min_diff


def export_to_buffergeometry_json(polylines, out_file, division_len=8.0, flip_z=True):
    """
    将多条折线 => 做“等距细分” => 输出 three.js BufferGeometry JSON。
    如果 flip_z=True，则对输出点的 Z 坐标做取反(类似 GH 里的 -Z)。
    """
    vertices = []
    indices  = []
    cur_idx_base = 0

    for pl in polylines:
        subdiv = subdivide_by_length(pl, division_len)
        if len(subdiv)<2:
            continue

        for i, p in enumerate(subdiv):
            px, py, pz = p
            if flip_z:
                pz = -pz
            vertices.append((px, py, pz))

            if i>0:
                indices.append([cur_idx_base + i - 1, cur_idx_base + i])

        cur_idx_base += len(subdiv)

    float_array = []
    for (x,y,z) in vertices:
        float_array.extend([x,y,z])

    index_array = []
    for pair in indices:
        index_array.extend(pair)

    json_data = {
        "metadata": {
            "type": "BufferGeometry",
            "version": 4.5
        },
        "data": {
            "attributes": {
                "position": {
                    "itemSize": 3,
                    "type": "Float32Array",
                    "array": float_array
                }
            },
            "index": {
                "type": "Uint16Array",
                "array": index_array
            }
        }
    }

    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"导出完成：{out_file}")


def main():
    # 1) 解析 JSON => 得到 2D 折线 & min_diff_in_height
    polylines_2d, min_diff_in_height = parse_filtered_json(
        INPUT_JSON_PATH,
        x_offset_increment=X_OFFSET_INCREMENT,
        max_seg_length=MAX_LENGTH
    )

    if not polylines_2d:
        print("未解析到任何线，脚本结束。")
        return

    # 2) 动态计算 BEND_RADIUS
    #    scaling_factor ∈ [1.5, 2.0]
    scaling_factor = random.uniform(1.5, 2.0)
    BEND_RADIUS = scaling_factor * (500.0 - min_diff_in_height)
    print(f"min_diff_in_height = {min_diff_in_height}, scaling_factor = {scaling_factor:.2f}, BEND_RADIUS = {BEND_RADIUS:.2f}")

    # 3) 弯曲到圆柱
    bent_polylines = bend_2d_to_cylinder(polylines_2d, BEND_RADIUS)

    # 4) 准备输出目录：以时间戳命名的新文件夹
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_folder = os.path.join(WEB_UPLOADS_FOLDER, now_str)
    os.makedirs(out_folder, exist_ok=True)
    print(f"已创建输出文件夹：{out_folder}")

    # 5) 复制 "viewer-affiliated" 需要的 splitted JSON (Arduino 输出) 到这个文件夹
    if os.path.isdir(ARDUINO_OUTPUT_FOLDER):
        for fname in os.listdir(ARDUINO_OUTPUT_FOLDER):
            if fname.lower().endswith(".json"):
                src_path = os.path.join(ARDUINO_OUTPUT_FOLDER, fname)
                dst_path = os.path.join(out_folder, fname)
                shutil.copy2(src_path, dst_path)
                print(f"复制 {src_path} -> {dst_path}")
    else:
        print(f"警告：Arduino 输出目录不存在：{ARDUINO_OUTPUT_FOLDER}")

    # 6) 导出“viewer”所需的主 3D JSON
    out_json_path = os.path.join(out_folder, VIEWER_OUTPUT_NAME)
    export_to_buffergeometry_json(
        bent_polylines,
        out_json_path,
        division_len=DIVISION_LENGTH,
        flip_z=FLIP_Z_IN_EXPORT
    )

    print("全部处理完成！")


if __name__ == "__main__":
    main()
