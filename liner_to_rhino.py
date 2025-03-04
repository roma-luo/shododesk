import cv2
import mediapipe as mp
import numpy as np
import json
import os
import time
import requests
import serial

# -------------------------------
# 基础路径设置（建议使用相对路径）
base_dir = os.path.dirname(os.path.abspath(__file__))

# 输出文件保存目录（如需修改，请自行调整）
output_directory = os.path.join(base_dir, "input")  # 用户可修改保存目录路径
os.makedirs(output_directory, exist_ok=True)

# -------------------------------
# 定义参数
pixel_to_mm = 1
horizontal_speed = 0
frame_interval = 1
capture_interval = 5  # 此处保留，但不再使用自动拍照

# -------------------------------
# 初始化 MediaPipe 模块
mp_selfie_segmentation = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
mp_face_mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1)

# 导入官方连接常量
from mediapipe.python.solutions.face_mesh_connections import (
    FACEMESH_FACE_OVAL,
    FACEMESH_LEFT_EYE,
    FACEMESH_RIGHT_EYE,
    FACEMESH_LEFT_EYEBROW,
    FACEMESH_RIGHT_EYEBROW
)

# 自定义内嘴唇索引
FACEMESH_INNER_LIPS = frozenset([
    (78, 95), (95, 88), (88, 178), (178, 87), (87, 14),
    (14, 317), (317, 402), (402, 318), (318, 324), (324, 308),
    (308, 78),
    (95, 78), (88, 95), (178, 88), (87, 178), (14, 87),
    (317, 14), (402, 317), (318, 402), (324, 318), (308, 324)
])
inner_lips_indices = set([pt for connection in FACEMESH_INNER_LIPS for pt in connection])

# -------------------------------
# 初始化时间轴和轮廓数据
time_axis_data = []
current_x_position = 0

def classify_points(points, frame_height):
    categories = {
        "head": [],
        "body": [],
        "legs": []
    }
    for point in points:
        x, y = point["x"], point["y"]
        if y < frame_height * 0.3:
            categories["head"].append({"x": x, "y": y})
        elif frame_height * 0.3 <= y < frame_height * 0.7:
            categories["body"].append({"x": x, "y": y})
        else:
            categories["legs"].append({"x": x, "y": y})
    return categories

# -------------------------------
# 摄像头及设备配置（请根据自己设备修改以下设置）
# 替换为 ESP32-S3 流地址，若有需要，请修改为你设备对应的地址
stream_url = "http://192.168.5.1:81/stream"  # 用户可修改设备流地址

# 设置分辨率的 URL，若有需要，请修改设备 IP 地址或参数
framesize_val = 11
control_url = f"http://192.168.5.1/control?var=framesize&val={framesize_val}"
try:
    response = requests.get(control_url)
    if response.status_code == 200:
        print("分辨率设置为 HD(1280x720) 成功!")
    else:
        print(f"分辨率设置失败，HTTP状态码: {response.status_code}")
except Exception as e:
    print(f"设置分辨率时出现异常: {e}")

time.sleep(1)

cap = cv2.VideoCapture(stream_url)
if not cap.isOpened():
    print("无法打开视频流")
    exit()

print("Initializing the stream, please wait...")
time.sleep(2)
print("Recognition started, please stay stable...")

last_capture_time = time.time()
last_update_time = time.time()

json_path = os.path.join(output_directory, "time_axis_contours.json")

# -------------------------------
# 打开 Arduino 串口 & 自动发送 "C"
# 请修改串口端口号为你实际使用的端口（例如 Windows 下 "COM3" 或 Linux 下 "/dev/ttyUSB0"）
try:
    ser = serial.Serial("COM3", 9600, timeout=0.5)  # 用户请根据实际情况修改串口端口
    time.sleep(2)
    print("[Python] 串口已打开，等待 Arduino 通信...")

    ser.write(b"C\n")
    print("[Python] 已发送 'C' 指令给 Arduino，触发马达 C 流程")

except Exception as e:
    print(f"无法打开串口: {e}")
    ser = None

# -------------------------------
# 主循环
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Unable to read the video stream")
            break

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        segmentation_results = mp_selfie_segmentation.process(rgb_frame)
        face_results = mp_face_mesh.process(rgb_frame)

        # Segmentation mask
        mask = segmentation_results.segmentation_mask > 0.5
        mask_8bit = (mask * 255).astype(np.uint8)

        # 显示分割掩码及实时画面
        cv2.imshow("Segmentation Mask", mask_8bit)
        cv2.imshow("Real-Time Frame", frame)

        current_time = time.time()

        # 保留“水平移动线”逻辑
        if current_time - last_update_time >= frame_interval:
            current_x_position += horizontal_speed
            time_axis_data.append({"type": "line", "x": current_x_position, "y": 0})
            last_update_time = current_time

        # ========== 串口交互：C_STEP / Done ==========
        if ser and ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            if line == "C_STEP":
                print("[Python] 收到 Arduino 'C_STEP' -> 等1.5秒以便聚焦")
                time.sleep(1.5)

                print("[Python] 开始拍照+解析...")
                output_image = frame.copy()

                # 人体轮廓检测
                contours, _ = cv2.findContours(mask_8bit, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest_contour = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(largest_contour) > 500:
                        scaled_contour = [
                            {
                                "x": float(pt[0][0]) * pixel_to_mm + current_x_position,
                                "y": float(pt[0][1]) * pixel_to_mm
                            }
                            for pt in largest_contour
                        ]
                        cats = classify_points(scaled_contour, frame.shape[0])
                        time_axis_data.append({
                            "type": "contour",
                            "categories": cats
                        })
                        time_axis_data.append({
                            "type": "full_contour",
                            "points": scaled_contour
                        })
                        cv2.drawContours(output_image, [largest_contour], -1, (0, 255, 0), 2)
                        print(f"Human contour captured, {len(scaled_contour)} points")

                # 人脸特征检测
                if face_results.multi_face_landmarks:
                    for face_landmarks in face_results.multi_face_landmarks:
                        facial_features = {
                            "eyebrows": {"points": [], "connections": []},
                            "eyes": {"points": [], "connections": []},
                            "nose": {"points": [], "connections": []},
                            "mouth": {"points": [], "connections": []},
                            "jawline": {"points": [], "connections": []}
                        }

                        eyebrow_indices = set([idx for c in (FACEMESH_LEFT_EYEBROW | FACEMESH_RIGHT_EYEBROW) for idx in c])
                        eye_indices = set([idx for c in (FACEMESH_LEFT_EYE | FACEMESH_RIGHT_EYE) for idx in c])
                        jawline_indices = set([idx for c in FACEMESH_FACE_OVAL for idx in c])
                        nose_indices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

                        for idx, landmark in enumerate(face_landmarks.landmark):
                            x = int(landmark.x * frame.shape[1])
                            y = int(landmark.y * frame.shape[0])
                            point = {"x": x + current_x_position, "y": y}

                            if idx in eyebrow_indices:
                                facial_features["eyebrows"]["points"].append({"index": idx, **point})
                            elif idx in eye_indices:
                                facial_features["eyes"]["points"].append({"index": idx, **point})
                            elif idx in jawline_indices:
                                facial_features["jawline"]["points"].append({"index": idx, **point})
                            elif idx in nose_indices:
                                facial_features["nose"]["points"].append({"index": idx, **point})
                            elif idx in inner_lips_indices:
                                facial_features["mouth"]["points"].append({"index": idx, **point})

                            cv2.circle(output_image, (x, y), 2, (255, 0, 0), -1)

                        def draw_and_record_connections(img, connections, feature_key, color=(0, 255, 0)):
                            for (start_idx, end_idx) in connections:
                                sp = face_landmarks.landmark[start_idx]
                                ep = face_landmarks.landmark[end_idx]
                                x1, y1 = int(sp.x * frame.shape[1]), int(sp.y * frame.shape[0])
                                x2, y2 = int(ep.x * frame.shape[1]), int(ep.y * frame.shape[0])
                                cv2.line(img, (x1, y1), (x2, y2), color, 1)
                                facial_features[feature_key]["connections"].append({"start": start_idx, "end": end_idx})

                        draw_and_record_connections(output_image, FACEMESH_LEFT_EYE, "eyes", color=(0, 255, 0))
                        draw_and_record_connections(output_image, FACEMESH_RIGHT_EYE, "eyes", color=(0, 255, 0))
                        draw_and_record_connections(output_image, FACEMESH_LEFT_EYEBROW, "eyebrows", color=(255, 0, 255))
                        draw_and_record_connections(output_image, FACEMESH_RIGHT_EYEBROW, "eyebrows", color=(255, 0, 255))
                        draw_and_record_connections(output_image, FACEMESH_INNER_LIPS, "mouth", color=(0, 0, 255))

                        time_axis_data.append({
                            "type": "facial_features",
                            "categories": facial_features
                        })
                        print(f"Facial features captured, points: {sum(len(v['points']) for v in facial_features.values())}")

                # 保存图像
                image_path = os.path.join(output_directory, f"frame_{int(time.time())}.png")
                cv2.imwrite(image_path, output_image)
                print(f"Annotated image saved: {image_path}")

                # 保存 JSON 数据
                with open(json_path, 'w') as f:
                    json.dump(time_axis_data, f, indent=4)
                    print(f"Data saved to {json_path}")

                # 延迟 1 秒后发送 CONTINUE 信号
                time.sleep(1.0)
                ser.write(b"CONTINUE\n")
                print("[Python] 已回传 CONTINUE, Arduino 可进行下一段旋转")

            elif line == "Done":
                print("[Python] 收到 Arduino 'Done'，马达 C 动作完成，准备退出。")
                break

        # 用户可随时按 'q' 键退出
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Program exited by user")
            break

except KeyboardInterrupt:
    print("Program interrupted by user")

finally:
    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()

    if ser:
        ser.close()
        print("[Python] 串口已关闭")

    print("Camera (stream) resources released")
