# shododesk
A vision-based robotic installation that transforms human interactions into dynamic visual compositions.

To run, simply run main.py.

REQUIREMENTS
opencv #pip install opencv-python
mediapipe #pip install mediapipe

GUIDE
- plug in the two USB sockets from the installation in to your device
- this should activate the camera module(ESP32, you should see the LED on the module blink)
- the camera module would release hot spot signal named 'HWP...'
- connect to the hot spot
- in 'send_to_arduino.py', remember to change 'MOTOR_SERIAL_PORT' and 'SERVO_SERIAL_PORT' to your corresponding port of your device
- now, run 'main.py'

POSSIBLE ISSUES
'UNABLE TO OPEN VIDEO STREAM': this should relate to "stream_url = 'http://192.168.5.1:81/stream'", try check the url ip
'[ERROR] UNABLE TO CONNECT...': this should relate to the ports that python is trying to access does not exist or is being occupied, change to the correct serial port
