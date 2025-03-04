import json
import math
import os

# ========== INPUT OUTPUT CONFIGURATION ==========
# DEFINE BASE DIRECTORY (CURRENT SCRIPT DIRECTORY)
base_dir = os.path.dirname(os.path.abspath(__file__))

# INPUT FILE PATH, ASSUMING THE PREVIOUS SCRIPT'S OUTPUT IS STORED IN THE "INPUT/FILTER_INPUT" FOLDER
input_path = os.path.join(base_dir, "input", "filter_input", "filtered_time_axis_contours.json")

# OUTPUT FILE STORAGE DIRECTORY (MODIFY IF NEEDED), HERE THE OUTPUT IS SAVED IN THE "ARDUINO_INPUT" FOLDER AT THE PROJECT ROOT
output_dir = os.path.join(base_dir, "arduino_input")
os.makedirs(output_dir, exist_ok=True)
# OUTPUT FILE PREFIX
output_prefix = os.path.join(output_dir, "converted_output_")

# ========== RDP SIMPLIFICATION CONFIGURATION ==========
rdp_epsilon = 1.8

def perpendicular_distance(point, start, end):
    """CALCULATE THE PERPENDICULAR DISTANCE REQUIRED FOR THE RDP ALGORITHM"""
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
    """RAMER-DOUGLAS-PEUCKER ALGORITHM TO SIMPLIFY A SET OF POINTS"""
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
    """EXTRACT CONTINUOUS LINES BASED ON CONNECTIONS"""
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
                # POSSIBLY A LOOP OR SINGLE POINT
                if len(visited_comp) == 1:
                    single_point = list(visited_comp)[0]
                    lines.append([points_dict[single_point]])
                else:
                    # LOOP
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
                # MULTIPLE LINE SEGMENTS
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
    """EUCLIDEAN DISTANCE"""
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def reorder_points_nearest_neighbor(points):
    """
    REORDER A SET OF POINTS USING THE "NEAREST NEIGHBOR" METHOD.
    1. FIND THE POINT WITH THE SMALLEST (X, Y) AS THE STARTING POINT
    2. CONTINUOUSLY FIND THE NEAREST POINT TO THE CURRENT POINT UNTIL ALL POINTS ARE VISITED
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
    1. SORT BY Y IN ASCENDING ORDER
    2. KEEP THE SECOND HALF
    3. REORDER USING NEAREST NEIGHBOR METHOD
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
    1. SORT BY Y IN ASCENDING ORDER
    2. IF >=3 POINTS, TAKE THE 3RD; IF >=7 POINTS, TAKE THE 7TH
    3. REORDER USING NEAREST NEIGHBOR METHOD
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

# ROTATE AROUND THE ORIGIN (0,0) BY -90° (CLOCKWISE 90°)
def rotate_minus_90(x, y):
    """
    X' = Y
    Y' = -X
    """
    return (y, -x)

def process_one_person(full_contour_points, facial_feature_lines, nose_line, person_index, dist_range):
    """
    PROCESS THE CONTOUR & FACIAL FEATURE LINES FOR A SINGLE PERSON, AND OUTPUT TO A JSON FILE.
    dist_range = (max_y - min_y) IS USED TO DETERMINE PEN DEPTH (1/2/3).
    """
    # === 1) APPLY RDP TO full_contour (POSSIBLY ONE OR MULTIPLE LINES) ===
    simplified_full = [rdp(line, rdp_epsilon) for line in full_contour_points]

    # LABEL THE LINES
    labeled_lines = []
    for line in simplified_full:
        labeled_lines.append(("full", line))
    for line in facial_feature_lines:
        labeled_lines.append(("feat", line))
    if nose_line:
        for line in nose_line:
            labeled_lines.append(("nose", line))

    if not labeled_lines:
        # IF NO DATA FOR THE PERSON
        output_path = f"{output_prefix}{person_index}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return

    # === 2) ROTATE -90° ===
    rotated_lines = []
    for (cat, line) in labeled_lines:
        new_line = [rotate_minus_90(px, py) for (px, py) in line]
        rotated_lines.append((cat, new_line))

    # === 3) CALCULATE BOUNDING BOX, SCALE TO [0, <=250] ===
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

    # === 4) TILT COMPENSATION (SET TO 0° AS AN EXAMPLE) ===
    tilt_deg = 0.0
    tilt_slope = math.tan(math.radians(tilt_deg))

    def tilt_transform(px, py):
        return (px, py - px * tilt_slope)

    lines_stage2 = []
    for (cat, line) in lines_stage1:
        new_line = [tilt_transform(x, y) for (x, y) in line]
        lines_stage2.append((cat, new_line))

    # === 5) SECOND BOUNDING BOX: TRANSLATE TO X∈[-112.5,...], Y∈[25,...] ===
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

    # === 6) DETERMINE PEN DEPTH BASED ON dist_range => pen_depth (1/2/3) ===
    # GREATER THAN 200 => 1, 100~200 => 2, LESS THAN 100 => 3
    if dist_range > 200:
        pen_depth = 1
    elif dist_range >= 100:
        pen_depth = 2
    else:
        pen_depth = 3

    print(f"[DEBUG] person_index={person_index}, dist_range={dist_range}, pen_depth={pen_depth}")

    # === 7) ASSEMBLE final_points FOR JSON OUTPUT ===
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

    # === 8) AFTER ALL POINTS ARE GENERATED, ADD EXTRA COMMANDS ===
    #  1. x=-250, y=50, updown=0
    #  2. x=-250, y=50, updown=1
    #  3. x=-250, y=50, updown=0
    final_points.append({"x": -250.0, "y": 50.0, "updown": 0})
    final_points.append({"x": -250.0, "y": 50.0, "updown": 1})
    final_points.append({"x": -250.0, "y": 50.0, "updown": 1})
    final_points.append({"x": -250.0, "y": 50.0, "updown": 0})

    # === WRITE THE JSON FILE ===
    output_path = f"{output_prefix}{person_index}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_points, f, ensure_ascii=False, indent=2)

def main():
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    shapes = data
    person_index = 1

    # RECORD DATA FOR THE CURRENT PERSON
    dist_range_for_person = 0.0
    current_full_contour_lines = []
    current_facial_feature_lines = []
    nose_final_line = None

    got_full = False
    got_face = False

    # ITERATE THROUGH JSON: FIND "contour" => height_info, "full_contour" => FULL BODY POINTS, "facial_features" => FACIAL FEATURES
    for shape in shapes:
        shape_type = shape.get("type")

        if shape_type == "contour":
            # IN THE SECOND SCRIPT, ONLY height_info WAS WRITTEN FOR "contour"
            # HERE WE READ min_y, max_y => dist_range_for_person
            height_info = shape.get("height_info", {})
            min_y = height_info.get("min_y")
            max_y = height_info.get("max_y")
            if (min_y is not None) and (max_y is not None):
                dist_range_for_person = max_y - min_y
            else:
                dist_range_for_person = 0

        elif shape_type == "full_contour":
            # READ FULL BODY CONTOUR
            fc_points = shape.get("points", [])
            if fc_points:
                coords = [(p["x"], p["y"]) for p in fc_points]
                current_full_contour_lines = [coords]
            else:
                current_full_contour_lines = []
            got_full = True

        elif shape_type == "facial_features":
            # FACIAL FEATURES
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
                    # OTHER FACIAL FEATURES => GENERATE LINES USING CONNECTIONS
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

            # PROCESS JAWLINE
            if jawline_points:
                jawline_line = process_jawline_points(jawline_points)
                feature_lines_temp.extend(jawline_line)

            # PROCESS NOSE
            if nose_points:
                nose_line = process_nose_points(nose_points)
                if nose_line:
                    nose_final_line = nose_line

            current_facial_feature_lines = feature_lines_temp
            got_face = True

        # ONCE BOTH full_contour AND facial_features ARE READY => OUTPUT
        if got_full and got_face:
            process_one_person(
                current_full_contour_lines,
                current_facial_feature_lines,
                nose_final_line,
                person_index,
                dist_range_for_person
            )
            person_index += 1

            # RESET
            dist_range_for_person = 0.0
            current_full_contour_lines = []
            current_facial_feature_lines = []
            nose_final_line = None
            got_full = False
            got_face = False

    print("[MAIN] ALL DONE. JSON FILES SAVED IN:", output_prefix)

if __name__ == "__main__":
    main()
