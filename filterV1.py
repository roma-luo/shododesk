import json
import os

# DEFINE BASE DIRECTORY (CURRENT SCRIPT DIRECTORY)
base_dir = os.path.dirname(os.path.abspath(__file__))

# INPUT FOLDER PATH (CONSISTENT WITH THE PREVIOUS SCRIPT, DEFAULT IS 'INPUT' FOLDER)
input_directory = os.path.join(base_dir, "input")  # USERS CAN MODIFY THIS PATH IF NEEDED

# SET INPUT FILE PATH, DEFAULT IS input/time_axis_contours.json
input_path = os.path.join(input_directory, "time_axis_contours.json")

# SET OUTPUT FOLDER PATH, DEFAULT IS input/filter_input
output_directory = os.path.join(input_directory, "filter_input")  # USERS CAN MODIFY THIS PATH IF NEEDED
os.makedirs(output_directory, exist_ok=True)  # CREATE OUTPUT DIRECTORY IF IT DOES NOT EXIST

# SET OUTPUT FILE PATH
output_path = os.path.join(output_directory, "filtered_time_axis_contours.json")

# SCALING FACTORS FOR EACH CATEGORY (ONLY SCALING IN THE Y DIRECTION)
scaling_factors = {
    "head": {"scale_y": 1.0},  # HEAD
    "body": {"scale_y": 1.0},  # BODY
    "legs": {"scale_y": 1.0}   # LEGS
}

def perpendicular_distance(point, start, end):
    """CALCULATE THE PERPENDICULAR DISTANCE FROM A POINT TO A LINE SEGMENT"""
    x1, y1 = start["x"], start["y"]
    x2, y2 = end["x"], end["y"]
    x0, y0 = point["x"], point["y"]

    if x1 == x2 and y1 == y2:
        return ((x0 - x1)**2 + (y0 - y1)**2)**0.5

    numerator = abs((y2 - y1)*x0 - (x2 - x1)*y0 + x2*y1 - y2*x1)
    denominator = ((y2 - y1)**2 + (x2 - x1)**2)**0.5
    return numerator / denominator

def rdp(points, epsilon):
    """SIMPLIFY A SET OF POINTS USING THE RAMER-DOUGLAS-PEUCKER ALGORITHM"""
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

# TOLERANCE FOR RDP ALGORITHM
rdp_epsilon = 1.8

if not os.path.exists(input_path):
    print(f"INPUT FILE {input_path} DOES NOT EXIST, PLEASE CHECK THE PATH.")
    exit()

with open(input_path, 'r') as f:
    data = json.load(f)

filtered_data = []

def scale_y_and_translate(points, scale_y, y_offset):
    """SCALE POINTS IN THE Y DIRECTION + TRANSLATE, BUT y_offset IS SET TO 0 HERE"""
    scaled_points = []
    for point in points:
        x = point["x"]
        y = point["y"] * scale_y + y_offset  # y_offset IS 0, MAINTAINING ORIGINAL Y VALUES
        scaled_points.append({"x": x, "y": y})
    return scaled_points

# ITERATE THROUGH JSON DATA (PROCESSING ONCE WITHOUT GLOBAL OFFSET)
for item in data:
    if item["type"] == "contour":
        categories = item.get("categories", {"head": [], "body": [], "legs": []})
        processed_categories = {}

        # NO NEED FOR max_y_previous OR global_y_shift, AS GLOBAL Y ALIGNMENT IS REMOVED
        global_min_y = float('inf')
        global_max_y = -float('inf')

        for category, points in categories.items():
            if not points:
                processed_categories[category] = []
                continue

            if category in scaling_factors:
                scale_y = scaling_factors[category]["scale_y"]
                # DO NOT COMPUTE y_offset, SET IT TO 0
                y_offset = 0

                # SCALE (WITHOUT TRANSLATION) POINT SET
                processed_points = scale_y_and_translate(points, scale_y, y_offset)

                # APPLY RDP SIMPLIFICATION TO HEAD, BODY, AND LEGS
                if category in ["head", "body", "legs"]:
                    processed_points = rdp(processed_points, rdp_epsilon)

                processed_categories[category] = processed_points

                # UPDATE GLOBAL MIN AND MAX Y VALUES
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
        # NON-"CONTOUR" DATA IS NOT PROCESSED FURTHER AND IS KEPT AS-IS
        filtered_data.append(item)

# SECOND GLOBAL OFFSET ADJUSTMENT REMOVED, AS IT IS NO LONGER NEEDED

# SAVE THE PROCESSED DATA TO A NEW JSON FILE
with open(output_path, 'w') as f:
    json.dump(filtered_data, f, indent=4)
    print(f"PROCESSED DATA SAVED TO {output_path}")
