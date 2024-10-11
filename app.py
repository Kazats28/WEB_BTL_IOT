from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
import threading
import time
from datetime import datetime

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
current_gas_ppm = 0
is_turn_on = False
current_time = datetime.now()

def getting_ppm_data():
    global gas_ppm
    global is_turn_on
    global current_gas_ppm
    global current_time
    while True:
        if is_turn_on:
            current_gas_ppm = gas_ppm
            current_time = datetime.now()
        time.sleep(1)
# Gửi dữ liệu gas_ppm lên MongoDB mỗi 10 giây
def store_ppm_data():
    global gas_ppm
    global is_turn_on
    while True:
        if is_turn_on:
            ppm_collection.insert_one({
                "ppm": gas_ppm,
                "timestamp": datetime.now()
            })
        time.sleep(60)  # Lưu dữ liệu mỗi 60 giây

def change_is_turn_on():
    global is_turn_on
    global last_ping
    while True:
        if time.time() - last_ping > 5:
            is_turn_on = False
        else:
            is_turn_on = True
        time.sleep(1)

# Khởi chạy luồng cho việc lưu ppm liên tục
threading.Thread(target=getting_ppm_data, daemon=True).start()
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
    data = request.get_json()  # Lấy dữ liệu JSON từ request
    if data and 'ppm' in data:
        last_ping = time.time()
        gas_ppm = float(data['ppm'])  # Chuyển đổi giá trị ppm từ chuỗi thành số thực
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

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
    # Prepare the data in JSON format for the frontend
    data = [
        {
            'ppm': current_gas_ppm,
            'time': current_time.strftime('%H:%M:%S')  # Format timestamp as HH:MM:SS
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
    return jsonify({'ppm': gas_ppm})

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
