import os
import sqlite3
import threading
import time
import uuid
import requests
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

DB_NAME = "database.db"

# ---------------------------------------------------------
# 1. DATABASE INITIALIZATION
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            api_key TEXT PRIMARY KEY,
            email TEXT,
            credits INTEGER DEFAULT 100
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            api_key TEXT,
            status TEXT,
            video_url TEXT
        )
    ''')
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (api_key, email, credits)
        VALUES ('sk_live_test123', 'testuser@example.com', 500)
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# 2. API KEY & CREDIT VERIFICATION HELPER
# ---------------------------------------------------------
def verify_and_deduct_credits(cost=15):
    api_key = request.headers.get("Authorization")
    
    if not api_key:
        return None, jsonify({"error": "Missing API Key in Authorization header"}), 401
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT credits FROM users WHERE api_key = ?", (api_key,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return None, jsonify({"error": "Invalid API Key"}), 403
        
    current_credits = user[0]
    if current_credits < cost:
        conn.close()
        return None, jsonify({"error": "Insufficient credits", "credits_remaining": current_credits}), 402
        
    new_credits = current_credits - cost
    cursor.execute("UPDATE users SET credits = ? WHERE api_key = ?", (new_credits, api_key))
    conn.commit()
    conn.close()
    
    return api_key, new_credits, 200

# ---------------------------------------------------------
# 3. ENDPOINTS & UI
# ---------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

@app.route('/v1/generate-video', methods=['POST'])
def generate_video():
    api_key, credit_or_error, status_code = verify_and_deduct_credits(15)
    if status_code != 200:
        return credit_or_error, status_code
        
    remaining_credits = credit_or_error
    data = request.get_json() or {}
    
    job_id = str(uuid.uuid4())
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO jobs (job_id, api_key, status, video_url) VALUES (?, ?, ?, ?)",
                   (job_id, api_key, "processing", None))
    conn.commit()
    conn.close()
    
    threading.Thread(target=mock_runpod_handler, args=(job_id, data)).start()
    
    return jsonify({
        "message": "Video generation started",
        "job_id": job_id,
        "credits_remaining": remaining_credits
    }), 200

@app.route('/webhook', methods=['POST'])
def webhook_receiver():
    data = request.get_json() or {}
    job_id = data.get("job_id")
    status = data.get("status")
    video_url = data.get("video_url")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = ?, video_url = ? WHERE job_id = ?",
                   (status, video_url, job_id))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "received"}), 200

@app.route('/v1/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT status, video_url FROM jobs WHERE job_id = ?", (job_id,))
    job = cursor.fetchone()
    conn.close()
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
        
    return jsonify({
        "job_id": job_id,
        "status": job[0],
        "video_url": job[1]
    }), 200

def mock_runpod_handler(job_id, job_input):
    time.sleep(4)
    video_url = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
    
    port = int(os.environ.get("PORT", 5000))
    try:
        requests.post(f"http://127.0.0.1:{port}/webhook", json={
            "job_id": job_id,
            "status": "completed",
            "video_url": video_url
        })
    except Exception as e:
        print(f"Webhook error: {e}")

@app.route('/admin/keys', methods=['GET'])
def admin_view_keys():
    secret = request.args.get('secret')
    if secret != "markaz_secure_2026":
        return "Unauthorized. Provide correct secret key.", 403

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT api_key, email, credits FROM users")
    users = cursor.fetchall()
    conn.close()

    html = """
    <html>
    <head><title>Admin Panel</title><style>body{background:#090d16;color:#fff;font-family:sans-serif;padding:30px;}table{width:100%;border-collapse:collapse;margin-top:20px;}th,td{border:1px solid #334155;padding:12px;text-align:left;}th{background:#1e293b;}</style></head>
    <body>
        <h2>Live API Keys & User Accounts</h2>
        <table>
            <tr><th>API Key</th><th>Email</th><th>Credits</th></tr>
    """
    for user in users:
        html += f"<tr><td><code>{user[0]}</code></td><td>{user[1]}</td><td>{user[2]}</td></tr>"
    html += "</table></body></html>"
    return html

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
