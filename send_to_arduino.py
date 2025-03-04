import serial
import time
import json
import os
import math

# ========== CONFIGURATION SECTION, MODIFY AS NEEDED ==========
# (1) SERVO ARDUINO SERIAL PORT (DRAWING)
SERVO_SERIAL_PORT = 'COM6'  # USERS SHOULD MODIFY ACCORDING TO ACTUAL SETUP
SERVO_BAUD_RATE = 9600      # USERS SHOULD MODIFY ACCORDING TO ACTUAL SETUP

# (2) MOTOR A, B ARDUINO SERIAL PORT (PAPER ROLLING)
MOTOR_SERIAL_PORT = 'COM3'  # USERS SHOULD MODIFY ACCORDING TO ACTUAL SETUP
MOTOR_BAUD_RATE   = 9600    # USERS SHOULD MODIFY ACCORDING TO ACTUAL SETUP

# (3) FOLDER FOR READING .JSON FILES
# MODIFY TO THE "ARDUINO_INPUT" FOLDER AT THE PROJECT ROOT; THIS FOLDER SHOULD MATCH THE OUTPUT PATH OF THE PREVIOUS SCRIPT
base_dir = os.path.dirname(os.path.abspath(__file__))
JSON_DIR_PATH = os.path.join(base_dir, "arduino_input")  # MODIFY THIS PATH IF NECESSARY

def open_serial(port, baud_rate):
    """
    OPEN SERIAL PORT HELPER FUNCTION
    """
    try:
        print(f"[INFO] CONNECTING TO PORT {port} (BAUD_RATE {baud_rate})...")
        ard = serial.Serial(port, baud_rate, timeout=1)
        time.sleep(2)  # WAIT FOR ARDUINO INITIALIZATION
        print(f"[INFO] SUCCESSFULLY CONNECTED TO {port}")
        return ard
    except serial.SerialException as e:
        print(f"[ERROR] UNABLE TO CONNECT {port}: {e}")
        exit(1)

def send_command_to_servo(servo_arduino, x, y, updown):
    """
    SEND JSON + 'R' FORMAT COMMAND TO THE SERVO SYSTEM ARDUINO.
    USE READLINE() TO READ A COMPLETE LINE RESPONSE.
    """
    try:
        data = {"x": x, "y": y, "updown": updown}
        cmd_str = json.dumps(data) + "R"
        print(f"[SERVO] COMMAND: {cmd_str}")
        servo_arduino.write(cmd_str.encode())

        # USE READLINE() TO READ ARDUINO RESPONSE
        response = servo_arduino.readline()
        resp_decoded = response.decode(errors='ignore').strip()
        print(f"[SERVO] ARDUINO RETURN: {resp_decoded}")

    except serial.SerialException as e:
        print(f"[ERROR] FAIL TO SEND DATA - {e}")
        servo_arduino.close()
        exit(1)

def roll_paper_with_motor():
    """
    FIXEDLY ROTATE MOTORS A, B, D FOR 3 SECONDS (PAPER ROLLING, NO CALCULATION OF ROLLING TIME)
    """
    print(f"[MOTOR] WE WILL ROTATE MOTORS A, B, D FOR 3S USING 'AB 3'.")
    # OPEN MOTOR PORT
    motor_arduino = open_serial(MOTOR_SERIAL_PORT, MOTOR_BAUD_RATE)
    ab_cmd = "AB 4\n"  # FIXED ROTATION FOR 4 SECONDS
    motor_arduino.write(ab_cmd.encode('utf-8'))
    print(f"[MOTOR] COMMAND SENT: {ab_cmd.strip()}")

    finished = False
    while not finished:
        line = motor_arduino.readline().decode('utf-8').strip()
        if line:
            print(f"[MOTOR] ARDUINO RETURN: {line}")
            if line == "Done":
                finished = True

    motor_arduino.close()
    print("[MOTOR] DONE ROLLING, CLOSING PORT NOW.")

def main():
    # OPEN SERVO ARDUINO SERIAL PORT
    servo_arduino = open_serial(SERVO_SERIAL_PORT, SERVO_BAUD_RATE)

    # GET ALL .JSON FILES
    json_files = [f for f in os.listdir(JSON_DIR_PATH) if f.endswith(".json")]
    json_files.sort()

    try:
        for json_file in json_files:
            file_path = os.path.join(JSON_DIR_PATH, json_file)
            print(f"[MAIN] READING FILE: {file_path}")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    drawing_data = json.load(f)
            except FileNotFoundError:
                print(f"[ERROR] CANNOT FIND FILE {file_path}")
                continue
            except json.JSONDecodeError:
                print(f"[ERROR] JSON FILE FORMAT WRONG: {file_path}")
                continue

            # SEND POINTS TO SERVO ARDUINO ONE BY ONE
            for point in drawing_data:
                x = point["x"]
                y = point["y"]
                up = point["updown"]
                send_command_to_servo(servo_arduino, x, y, up)
                time.sleep(2)  # OPTIONAL DELAY

            print("[MAIN] DONE HANDLING FILE, WAITING FOR 3S...")
            time.sleep(3)

            # *** PAPER ROLLING ACTION: FIXED ROTATION FOR 3 SECONDS ***
            print("[MAIN] ROLLING PAPER FOR 3 SECONDS.")
            roll_paper_with_motor()

        print("[MAIN] ALL JSON FILES COMPLETED")

    finally:
        # CLOSE SERVO SERIAL PORT
        print("[MAIN] CLOSING SERVO PORT...")
        servo_arduino.close()
        print("[MAIN] SERVO PORT CLOSED.")

        # DELETE ALL .JSON FILES
        for jf in json_files:
            jfpath = os.path.join(JSON_DIR_PATH, jf)
            try:
                os.remove(jfpath)
                print(f"[MAIN] FILE DELETED: {jfpath}")
            except OSError as e:
                print(f"[ERROR] FAIL TO DELETE FILE: {jfpath}, ERROR: {e}")

if __name__ == "__main__":
    main()
