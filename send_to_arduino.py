import serial
import time
import json
import os
import math

# ========== 配置部分，按需修改 ==========
# (1) 舵机 Arduino 串口 (绘图)
SERVO_SERIAL_PORT = 'COM6'  # 用户请根据实际情况修改
SERVO_BAUD_RATE = 9600      # 用户请根据实际情况修改

# (2) 马达 A,B Arduino 串口 (卷纸)
MOTOR_SERIAL_PORT = 'COM3'  # 用户请根据实际情况修改
MOTOR_BAUD_RATE   = 9600    # 用户请根据实际情况修改

# (3) 读取 .json 文件的文件夹
# 修改为项目根目录下的 "arduino_input" 文件夹，该文件夹应与前一脚本的输出路径一致
base_dir = os.path.dirname(os.path.abspath(__file__))
JSON_DIR_PATH = os.path.join(base_dir, "arduino_input")  # 用户如需调整路径，请修改此处

def open_serial(port, baud_rate):
    """
    打开串口的辅助函数
    """
    try:
        print(f"[INFO] connecting to port {port} (baud_rate {baud_rate})...")
        ard = serial.Serial(port, baud_rate, timeout=1)
        time.sleep(2)  # 等待 Arduino 初始化
        print(f"[INFO] successfully connected to {port}")
        return ard
    except serial.SerialException as e:
        print(f"[ERROR] unable to connect {port}: {e}")
        exit(1)

def send_command_to_servo(servo_arduino, x, y, updown):
    """
    给舵机系统的 Arduino 发送 JSON + 'R' 格式指令。
    使用 readline() 来读取一整行返回。
    """
    try:
        data = {"x": x, "y": y, "updown": updown}
        cmd_str = json.dumps(data) + "R"
        print(f"[SERVO] command: {cmd_str}")
        servo_arduino.write(cmd_str.encode())

        # 使用 readline() 读取 Arduino 响应
        response = servo_arduino.readline()
        resp_decoded = response.decode(errors='ignore').strip()
        print(f"[SERVO] Arduino return: {resp_decoded}")

    except serial.SerialException as e:
        print(f"[ERROR] fail to send data - {e}")
        servo_arduino.close()
        exit(1)

def roll_paper_with_motor():
    """
    固定让马达 A、B、D 旋转 3 秒（不再计算卷纸时间）
    """
    print(f"[MOTOR] We will rotate motors A,B,D for 3s using 'AB 3'.")
    # 打开马达端口
    motor_arduino = open_serial(MOTOR_SERIAL_PORT, MOTOR_BAUD_RATE)
    ab_cmd = "AB 4\n"  # 固定旋转 4 秒
    motor_arduino.write(ab_cmd.encode('utf-8'))
    print(f"[MOTOR] command sent: {ab_cmd.strip()}")

    finished = False
    while not finished:
        line = motor_arduino.readline().decode('utf-8').strip()
        if line:
            print(f"[MOTOR] Arduino return: {line}")
            if line == "Done":
                finished = True

    motor_arduino.close()
    print("[MOTOR] done rolling, closing port now.")

def main():
    # 打开舵机 Arduino 串口
    servo_arduino = open_serial(SERVO_SERIAL_PORT, SERVO_BAUD_RATE)

    # 获取所有 .json 文件
    json_files = [f for f in os.listdir(JSON_DIR_PATH) if f.endswith(".json")]
    json_files.sort()

    try:
        for json_file in json_files:
            file_path = os.path.join(JSON_DIR_PATH, json_file)
            print(f"[MAIN] reading file: {file_path}")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    drawing_data = json.load(f)
            except FileNotFoundError:
                print(f"[ERROR] cannot find file {file_path}")
                continue
            except json.JSONDecodeError:
                print(f"[ERROR] JSON file format wrong: {file_path}")
                continue

            # 逐点发送给舵机 Arduino
            for point in drawing_data:
                x = point["x"]
                y = point["y"]
                up = point["updown"]
                send_command_to_servo(servo_arduino, x, y, up)
                time.sleep(2)  # 可选的延迟

            print("[MAIN] done handling file, waiting for 3s...")
            time.sleep(3)

            # *** 卷纸动作：固定旋转 3 秒 ***
            print("[MAIN] Rolling paper for 3 seconds.")
            roll_paper_with_motor()

        print("[MAIN] All JSON files completed")

    finally:
        # 关闭舵机串口
        print("[MAIN] closing servo port...")
        servo_arduino.close()
        print("[MAIN] servo port closed.")

        # 删除所有的 .json 文件
        for jf in json_files:
            jfpath = os.path.join(JSON_DIR_PATH, jf)
            try:
                os.remove(jfpath)
                print(f"[MAIN] file deleted: {jfpath}")
            except OSError as e:
                print(f"[ERROR] fail to delete file: {jfpath}, error: {e}")

if __name__ == "__main__":
    main()
