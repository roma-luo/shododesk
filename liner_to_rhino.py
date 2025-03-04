import cv2
import mediapipe as mp
import numpy as np
import json
import os
import time
import requests
import serial

# -------------------------------
# BASE DIRECTORY SETUP (RECOMMENDED TO USE RELATIVE PATHS)
base_dir = os.path.dirname(os.path.abspath(__file__))

# OUTPUT FILE SAVE DIRECTORY (MODIFY IF NEEDED)
output_directory = os.path.join(base_dir, "input")  # USERS CAN MODIFY THE SAVE DIRECTORY PATH
os.makedirs(output_directory, exist_ok=True)

# -------------------------------
# DEFINE PARAMETERS
pixel_to_mm = 1
horizontal_speed = 0
frame_interval = 1
capture_interval = 5  # THIS IS KEPT BUT AUTO CAPTURE IS NO LONGER USED

# -------------------------------
# INITIALIZE MEDIAPIPE MODULES
mp_selfie_segmentation = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
mp_face_mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1)

# IMPORT OFFICIAL CONNECTION CONSTANTS
from mediapipe.python.solutions.face_mesh_connections import (
    FACEMESH_FACE_OVAL,
    FACEMESH_LEFT_EYE,
    FACEMESH_RIGHT_EYE,
    FACEMESH_LEFT_EYEBROW,
    FACEMESH_RIGHT_EYEBROW
)

# CUSTOM INNER LIPS INDEX
FACEMESH_INNER_LIPS = frozenset([
    (78, 95), (95, 88), (88, 178), (178, 87), (87, 14),
    (14, 317), (317, 402), (402, 318), (318, 324), (324, 308),
    (308, 78),
    (95, 78), (88, 95), (178, 88), (87, 178), (14, 87),
    (317, 14), (402, 317), (318, 402), (324, 318), (308, 324)
])
inner_lips_indices = set([pt for connection in FACEMESH_INNER_LIPS for pt in connection])

# -------------------------------
# INITIALIZE TIME AXIS AND CONTOUR DATA
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
# CAMERA AND DEVICE CONFIGURATION (MODIFY SETTINGS ACCORDING TO YOUR DEVICE)
# REPLACE WITH ESP32-S3 STREAM URL, MODIFY AS NEEDED FOR YOUR DEVICE
stream_url = "http://192.168.5.1:81/stream"  # USERS CAN MODIFY THE DEVICE STREAM URL

# URL FOR SETTING RESOLUTION, MODIFY DEVICE IP OR PARAMETERS IF NEEDED
framesize_val = 11
control_url = f"http://192.168.5.1/control?var=framesize&val={framesize_val}"
try:
    response = requests.get(control_url)
    if response.status_code == 200:
        print("RESOLUTION SET TO HD(1280x720) SUCCESSFULLY!")
    else:
        print(f"FAILED TO SET RESOLUTION, HTTP STATUS CODE: {response.status_code}")
except Exception as e:
    print(f"EXCEPTION OCCURRED WHILE SETTING RESOLUTION: {e}")

time.sleep(1)

cap = cv2.VideoCapture(stream_url)
if not cap.isOpened():
    print("UNABLE TO OPEN VIDEO STREAM")
    exit()

print("INITIALIZING THE STREAM, PLEASE WAIT...")
time.sleep(2)
print("RECOGNITION STARTED, PLEASE STAY STABLE...")

last_capture_time = time.time()
last_update_time = time.time()

json_path = os.path.join(output_directory, "time_axis_contours.json")

# -------------------------------
# OPEN ARDUINO SERIAL PORT & AUTO SEND "C"
# MODIFY THE SERIAL PORT ACCORDING TO YOUR DEVICE (E.G., "COM3" FOR WINDOWS OR "/DEV/TTYUSB0" FOR LINUX)
try:
    ser = serial.Serial("COM3", 9600, timeout=0.5)  # USERS SHOULD MODIFY THE SERIAL PORT ACCORDING TO THEIR SETUP
    time.sleep(2)
    print("[PYTHON] SERIAL PORT OPENED, WAITING FOR ARDUINO COMMUNICATION...")

    ser.write(b"C\n")
    print("[PYTHON] SENT 'C' COMMAND TO ARDUINO TO TRIGGER MOTOR C PROCESS")

except Exception as e:
    print(f"UNABLE TO OPEN SERIAL PORT: {e}")
    ser = None

# -------------------------------
# MAIN LOOP
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("UNABLE TO READ THE VIDEO STREAM")
            break

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        segmentation_results = mp_selfie_segmentation.process(rgb_frame)
        face_results = mp_face_mesh.process(rgb_frame)

        # SEGMENTATION MASK
        mask = segmentation_results.segmentation_mask > 0.5
        mask_8bit = (mask * 255).astype(np.uint8)

        # DISPLAY SEGMENTATION MASK AND REAL-TIME FRAME
        cv2.imshow("Segmentation Mask", mask_8bit)
        cv2.imshow("Real-Time Frame", frame)

        current_time = time.time()

        # KEEP "HORIZONTAL MOVEMENT LINE" LOGIC
        if current_time - last_update_time >= frame_interval:
            current_x_position += horizontal_speed
            time_axis_data.append({"type": "line", "x": current_x_position, "y": 0})
            last_update_time = current_time

        # ========== SERIAL INTERACTION: C_STEP / Done ==========
        if ser and ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            if line == "C_STEP":
                print("[PYTHON] RECEIVED 'C_STEP' FROM ARDUINO -> WAITING 1.5 SECONDS FOR FOCUS")
                time.sleep(1.5)

                print("[PYTHON] STARTING CAPTURE + PROCESSING...")
                output_image = frame.copy()

                # HUMAN CONTOUR DETECTION
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
                        print(f"HUMAN CONTOUR CAPTURED, {len(scaled_contour)} POINTS")

                # SAVE IMAGE
                image_path = os.path.join(output_directory, f"frame_{int(time.time())}.png")
                cv2.imwrite(image_path, output_image)
                print(f"ANNOTATED IMAGE SAVED: {image_path}")

                # SAVE JSON DATA
                with open(json_path, 'w') as f:
                    json.dump(time_axis_data, f, indent=4)
                    print(f"DATA SAVED TO {json_path}")

                # DELAY 1 SECOND THEN SEND CONTINUE SIGNAL
                time.sleep(1.0)
                ser.write(b"CONTINUE\n")
                print("[PYTHON] SENT 'CONTINUE', ARDUINO CAN PROCEED TO NEXT ROTATION")

            elif line == "Done":
                print("[PYTHON] RECEIVED 'Done' FROM ARDUINO, MOTOR C ACTION COMPLETED, EXITING.")
                break

        # USERS CAN EXIT BY PRESSING 'Q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("PROGRAM EXITED BY USER")
            break

except KeyboardInterrupt:
    print("PROGRAM INTERRUPTED BY USER")

finally:
    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()

    if ser:
        ser.close()
        print("[PYTHON] SERIAL PORT CLOSED")

    print("CAMERA (STREAM) RESOURCES RELEASED")
