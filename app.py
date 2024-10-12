from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
import threading
import time
from datetime import datetime
import pytz


app = Flask(__name__)

# Kết nối đến MongoDB
username = "User_All"
password = "ZqudTpzBIAhwmlru"
cluster_name = "cluster0.zmfwqij"
db_name = "gas_monitoring"
connection_string = f"mongodb+srv://{username}:{password}@{cluster_name}.mongodb.net/{db_name}?retryWrites=true&w=majority"
client = MongoClient(connection_string)

db = client.gas_monitoring
settings_collection = db.settings
ppm_collection = db.gas_data

last_ping = time.time()
gas_ppm = 0
is_turn_on = False

laos_tz = pytz.timezone('Asia/Ho_Chi_Minh')

# Gửi dữ liệu gas_ppm lên MongoDB mỗi 10 giây
def store_ppm_data():
    global gas_ppm
    global is_turn_on
    while True:
        if gas_ppm != 0 and is_turn_on:
            ppm_collection.insert_one({
                "ppm": gas_ppm,
                "timestamp": datetime.now()
            })
        time.sleep(60)  # Lưu dữ liệu mỗi 60 giây

def change_is_turn_on():
    global is_turn_on
    global last_ping
    global gas_ppm
    while True:
        if time.time() - last_ping > 5:
            is_turn_on = False
            gas_ppm = 0
        else:
            is_turn_on = True
        time.sleep(1)

# Khởi chạy luồng cho việc lưu ppm liên tục
threading.Thread(target=change_is_turn_on, daemon=True).start()
threading.Thread(target=store_ppm_data, daemon=True).start()

# Lấy giá trị từ MongoDB
def get_settings():
    settings = settings_collection.find_one()
    return settings if settings else {}

# Route để nhận dữ liệu từ ESP32
@app.route('/data', methods=['POST'])
def receive_data():
    global gas_ppm
    global last_ping
    data = request.data.decode('utf-8')  # Lấy dữ liệu dạng plain text
    if data:
        try:
            gas_ppm = gas_ppm + int(data)  # Chuyển đổi giá trị thành số nguyên
            last_ping = time.time()  # Cập nhật thời gian ping
            return "success", 200  # Trả về trạng thái thành công
        except ValueError:
            return "Invalid data format", 400  # Trả về lỗi nếu dữ liệu không hợp lệ
    return "No data received", 400  # Trả về lỗi nếu không có dữ liệu

# Route để cập nhật dữ liệu lên ESP32
@app.route('/update', methods=['GET'])
def update():
    settings = get_settings()  # Lấy cài đặt từ MongoDB
    return jsonify({
        "low_threshold": settings.get('low_threshold', 200),
        "high_threshold": settings.get('high_threshold', 800),
        "low_alert": settings.get('low_alert', False),
        "high_alert": settings.get('high_alert', False)
    })

# Route để render giao diện chính
@app.route('/')
def index():
    settings = get_settings()  # Lấy cài đặt từ MongoDB
    return render_template('index.html',
                           low_threshold=settings.get('low_threshold', 200),
                           high_threshold=settings.get('high_threshold', 800),
                           low_alert=settings.get('low_alert', False),
                           high_alert=settings.get('high_alert', False))

@app.route('/get_gas_data')
def get_gas_data():
    global laos_tz
    # Prepare the data in JSON format for the frontend
    data = [
        {
            'ppm': gas_ppm,
            'time': datetime.now(laos_tz).strftime('%H:%M:%S')  # Format timestamp as HH:MM:SS
        }
    ]
    return jsonify(data)

@app.route('/get_gas_history')
def get_gas_history():
    # Query the last 10 entries sorted by timestamp in descending order
    history = list(ppm_collection.find({}, {'ppm': 1, 'timestamp': 1}).sort('timestamp', -1).limit(60))

    # Reverse the list to show the oldest first
    history.reverse()

    # Prepare the data in JSON format for the frontend
    data = [
        {
            'ppm': entry['ppm'],
            'time': entry['timestamp'].strftime('%H:%M:%S')  # Format timestamp as HH:MM:SS
        }
        for entry in history
    ]

    return jsonify(data)

@app.route('/get_ppm')
def get_ppm():
    return str(gas_ppm)  # Return gas_ppm as a plain text string

@app.route('/get_status')
def get_status():
    return jsonify({'is_turn_on': is_turn_on})


@app.route('/update_thresholds', methods=['POST'])
def update_thresholds():
    data = request.get_json()
    low_threshold = int(data.get('low_threshold', 200))  # Mặc định là 200 nếu không có dữ liệu
    high_threshold = int(data.get('high_threshold', 800))  # Mặc định là 800 nếu không có dữ liệu

    # Cập nhật vào MongoDB
    settings_collection.update_one({}, {"$set": {
        "low_threshold": low_threshold,
        "high_threshold": high_threshold
    }}, upsert=True)

    return jsonify({"status": "success"}), 200

@app.route('/update_alerts', methods=['POST'])
def update_alerts():
    data = request.get_json()
    low_alert = data.get('low_alert', False)  # Mặc định là False nếu không có dữ liệu
    high_alert = data.get('high_alert', False)  # Mặc định là False nếu không có dữ liệu

    # Cập nhật vào MongoDB
    settings_collection.update_one({}, {"$set": {
        "low_alert": low_alert,
        "high_alert": high_alert
    }}, upsert=True)

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
