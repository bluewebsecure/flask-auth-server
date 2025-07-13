from flask import Flask, request, jsonify
from datetime import datetime
from threading import Lock
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
sessions = {}
lock = Lock()

# === Google Sheet Setup ===
SHEET_NAME = "auth_usage_log"          # 📌 Your sheet name
WORKSHEET_NAME = "CodeAuthLogs"          # 📌 Your tab name
CREDENTIALS_FILE = "credentials.json"  # 📌 JSON file

def get_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    return sheet

def log_to_sheet(code, ip, action="add"):
    try:
        sheet = get_google_sheet()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([code, ip, action, now])
    except Exception as e:
        print(f"❌ Failed to log to sheet: {e}")

# === Flask Routes ===
@app.route('/check_code_usage', methods=['POST'])
def check_code_usage():
    data = request.json
    code = data.get("code")
    ip = data.get("ip")
    max_users = int(data.get("max_users", 1))

    if not code or not ip:
        return jsonify({"valid": False, "reason": "Missing fields"}), 400

    try:
        sheet = get_google_sheet()
        rows = sheet.get_all_values()[1:]  # skip header

        # Filter rows for this code and action = add
        active_ips = set()
        for row in rows:
            if len(row) < 4: continue
            row_code, row_ip, action, _ = row
            if row_code == code:
                if action == "add":
                    active_ips.add(row_ip)
                elif action == "remove":
                    active_ips.discard(row_ip)

        if ip in active_ips:
            return jsonify({"valid": True, "already_logged_in": True})
        elif len(active_ips) >= max_users:
            return jsonify({"valid": False, "reason": "Max users reached"}), 403
        else:
            return jsonify({"valid": True, "already_logged_in": False})

    except Exception as e:
        return jsonify({"valid": False, "reason": str(e)}), 500


@app.route('/add_code_usage', methods=['POST'])
def add_code_usage():
    data = request.json
    code = data.get("code")
    ip = data.get("ip")

    if not code or not ip:
        return jsonify({"success": False, "reason": "Missing fields"}), 400

    with lock:
        sessions.setdefault(code, []).append({"ip": ip, "timestamp": datetime.now().isoformat()})
        log_to_sheet(code, ip, "add")
        return jsonify({"success": True})

@app.route('/remove_code_usage', methods=['POST'])
def remove_code_usage():
    data = request.json
    code = data.get("code")
    ip = data.get("ip")

    if not code or not ip:
        return jsonify({"success": False, "reason": "Missing fields"}), 400

    with lock:
        if code in sessions:
            sessions[code] = [s for s in sessions[code] if s["ip"] != ip]
        log_to_sheet(code, ip, "remove")
        return jsonify({"success": True})

@app.route('/status', methods=['GET'])
def status():
    return jsonify(sessions)

if __name__ == "__main__":
    app.run(port=5000)
