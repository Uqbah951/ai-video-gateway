import os
import sqlite3
import threading
import time
import uuid
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_NAME = "database.db"

# ---------------------------------------------------------
# 1. DATABASE INITIALIZATION
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Table for users and their API keys
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            api_key TEXT PRIMARY KEY,
            email TEXT,
            credits INTEGER DEFAULT 100
        )
    ''')
    
    # Table for tracking asynchronous jobs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            api_key TEXT,
            status TEXT,
            video_url TEXT
        )
    ''')
    
    # Insert a test API key so you can test immediately!
    cursor.execute('''
        INSERT OR IGNORE INTO users (api_key, email, credits)
        VALUES ('sk_live_test123', 'testuser@example.com', 500)
    ''')
    
    conn.commit()
    conn.close()

# Run database setup on startup
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
    
    # Check if key exists and check balance
    cursor.execute("SELECT credits FROM users WHERE api_key = ?", (api_key,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return None, jsonify({"error": "Invalid API Key"}), 403
        
    current_credits = user[0]
    if current_credits < cost:
        conn.close()
        return None, jsonify({"error": "Insufficient credits", "credits_remaining": current_credits}), 402
        
    # Deduct credits and save
    new_credits = current_credits - cost
    cursor.execute("UPDATE users SET credits = ? WHERE api_key = ?", (new_credits, api_key))
    conn.commit()
    conn.close()
    
    return api_key, new_credits, 200


# ---------------------------------------------------------
# 3. ENDPOINTS
# ---------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "service": "AI Video Gateway",
        "endpoints": {
            "generate_video": "/v1/generate-video (POST)",
            "check_status": "/v1/status/<job_id> (GET)"
        }
    }), 200


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
    
    print(f"\n[API GATEWAY] 🔔 Webhook received! Job {job_id} updated to '{status}'.")
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


# ---------------------------------------------------------
# 4. MOCK GPU WORKER
# ---------------------------------------------------------
def mock_runpod_handler(job_id, job_input):
    print(f"\n[GPU WORKER] 🚀 Processing job: {job_id}")
    time.sleep(3) 
    
    video_url = "https://your-real-s3-bucket.s3.amazonaws.com/rendered_output.mp4"
    
    port = int(os.environ.get("PORT", 5000))
    try:
        requests.post(f"http://127.0.0.1:{port}/webhook", json={
            "job_id": job_id,
            "status": "completed",
            "video_url": video_url
        })
    except Exception as e:
        print(f"[GPU WORKER] Webhook delivery failed: {e}")


# ---------------------------------------------------------
# 5. ADMIN ROUTE
# ---------------------------------------------------------
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

    html = "<h2>Live API Keys & Users</h2><table border='1' cellpadding='8'><tr><th>API Key</th><th>Email</th><th>Credits</th></tr>"
    for user in users:
        html += f"<tr><td><code>{user[0]}</code></td><td>{user[1]}</td><td>{user[2]}</td></tr>"
    html += "</table>"
    return html


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
    
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
    
    print(f"\n[API GATEWAY] 🔔 Webhook received! Job {job_id} updated to '{status}'.")
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


# ---------------------------------------------------------
# 4. MOCK GPU WORKER
# ---------------------------------------------------------
def mock_runpod_handler(job_id, job_input):
    print(f"\n[GPU WORKER] 🚀 Processing job: {job_id}")
    time.sleep(3) # Simulate render time
    
    video_url = "https://your-real-s3-bucket.s3.amazonaws.com/rendered_output.mp4"
    
    # Send webhook back to gateway
    import requests
    try:
        requests.post("http://127.0.0.1:5000/webhook", json={
            "job_id": job_id,
            "status": "completed",
            "video_url": video_url
        })
    except Exception as e:
        print(f"[GPU WORKER] Webhook delivery failed: {e}")

import os
@app.route('/admin/keys', methods=['GET'])
def admin_view_keys():
    # Simple security check using an admin secret in the URL parameters or headers
    # e.g., your-app.onrender.com/admin/keys?secret=my_secret_pass
    secret = request.args.get('secret')
    if secret != "markaz_secure_2026":
        return "Unauthorized. Provide correct secret key.", 403

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, api_key, credits FROM users")
    users = cursor.fetchall()
    conn.close()

    html = "<h2>Live API Keys & Users</h2><table border='1' cellpadding='8'><tr><th>ID</th><th>Username</th><th>API Key</th><th>Credits</th></tr>"
    for user in users:
        html += f"<tr><td>{user[0]}</td><td>{user[1]}</td><td><code>{user[2]}</code></td><td>{user[3]}</td></tr>"
    html += "</table>"
    return html

if __name__ == '__main__':
    # Render assigns a port dynamically via os.environ.get("PORT")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
