from flask import Flask, jsonify, render_template
from flask_cors import CORS
import time
import threading

try:
    import serial
except ImportError:
    serial = None

app = Flask(__name__)
CORS(app)

# Configuration - Change 'COM3' to your actual port (e.g., '/dev/ttyUSB0' on Linux)
SERIAL_PORT = 'COM3'
BAUD_RATE = 9600

# Thread lock for safe read/write of latest_data across threads
data_lock = threading.Lock()

# Global variable to store the latest data
latest_data = {
    "status": "device_not_connected"
}

# Tracks the last time valid data was received
last_data_time = None


def read_serial():
    global latest_data, last_data_time

    if serial is None:
        print("Error: pyserial not installed. Serial monitoring is disabled.")
        with data_lock:
            latest_data = {"status": "pyserial_missing"}
        return

    ser = None

    while True:
        try:
            if ser is None:
                # Attempt to open serial port
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
                print(f"Connected to {SERIAL_PORT}")

            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                print("RAW DATA:", line)

                if line:
                    # Expected format: heart_rate,temperature,latitude,longitude
                    parts = line.split(',')

                    if len(parts) == 4:
                        try:
                            hr   = float(parts[0])
                            temp = float(parts[1])
                            lat  = float(parts[2])
                            lon  = float(parts[3])

                            # Health Status Logic
                            # Danger if: HR < 50 or > 120, Temp > 38°C (fever) or < 35°C (hypothermia)
                            health_status = "normal"
                            if hr < 50 or hr > 120 or temp > 38 or temp < 35:
                                health_status = "danger"

                            with data_lock:
                                latest_data = {
                                    "heart_rate": round(hr),
                                    "temperature": round(temp, 1),
                                    "latitude": lat,
                                    "longitude": lon,
                                    "status": health_status
                                }

                            last_data_time = time.time()

                        except ValueError:
                            print("Invalid data received from serial")
                            with data_lock:
                                latest_data = {"status": "device_not_connected"}
                    else:
                        # Incorrect number of parts — bad packet
                        with data_lock:
                            latest_data = {"status": "device_not_connected"}

                else:
                    # Empty line received
                    with data_lock:
                        latest_data = {"status": "device_not_connected"}

            else:
                # No new data — check if device has gone silent for > 5 seconds
                if last_data_time and (time.time() - last_data_time > 5):
                    with data_lock:
                        latest_data = {"status": "device_not_connected"}

        except Exception as e:
            print(f"Serial error: {e}")
            with data_lock:
                latest_data = {"status": "device_not_connected"}
            if ser:
                ser.close()
            ser = None

        time.sleep(0.1)


# Start serial reading in a background thread
serial_thread = threading.Thread(target=read_serial, daemon=True)
serial_thread.start()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/data')
def get_data():
    with data_lock:
        return jsonify(latest_data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)