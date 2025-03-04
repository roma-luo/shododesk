import subprocess
import os
import sys

python_path = sys.executable

base_dir = os.path.dirname(os.path.abspath(__file__))

liner_to_rhino_script = os.path.join(base_dir, "liner_to_rhino.py")
filter_script = os.path.join(base_dir, "filterV1.py")
print_filter_script = os.path.join(base_dir, "filterV2.py")
send_to_web_script = os.path.join(base_dir, "send_to_web.py")
process_to_arduino = os.path.join(base_dir, "send_to_arduino.py")

try:

    print("run liner_to_rhino.py...")
    subprocess.run([python_path, liner_to_rhino_script], check=True)


    print("run filterV1.py...")
    subprocess.run([python_path, filter_script], check=True)


    print("run filterV2.py...")
    subprocess.run([python_path, print_filter_script], check=True)


    # print("run send_to_web.py...")
    # subprocess.run([python_path, send_to_web_script], check=True)


    print("run send_to_arduino.py...")
    subprocess.run([python_path, process_to_arduino], check=True)

    print("all scripts being processed")

except subprocess.CalledProcessError as e:
    print(f"error: {e}")
