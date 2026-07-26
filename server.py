import os
import sqlite3
import threading
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
            video_url TEXT,
            runpod_job_id TEXT
        )
    ''')
    
    # Safely upgrade existing databases without breaking them
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN runpod_job_id TEXT")
    except sqlite3.OperationalError:
        pass # Column already exists
    
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
    
    # Send to the real RunPod function instead of the mock
    threading.Thread(target=real_runpod_handler, args=(job_id, data)).start()
    
    return jsonify({
        "message": "Video generation started",
        "job_id": job_id,
        "credits_remaining": remaining_credits
    }), 200

@app.route('/webhook', methods=['POST'])
def webhook_receiver():
    # RunPod will call this URL and we pull our internal job_id from the query parameters
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "Missing job_id"}), 400
        
    data = request.get_json() or {}
    
    # RunPod sends statuses like "COMPLETED", "FAILED", "IN_PROGRESS"
    runpod_status = data.get("status")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if runpod_status == "COMPLETED":
        # Adjust "video_url" below based on what exact key your RunPod AI returns in its output dict
        output = data.get("output", {})
        video_url = output.get("video_url") or output.get("url")
        
        cursor.execute("UPDATE jobs SET status = ?, video_url = ? WHERE job_id = ?",
                       ("completed", video_url, job_id))
                       
    elif runpod_status in ["FAILED", "CANCELLED"]:
        cursor.execute("UPDATE jobs SET status = ? WHERE job_id = ?",
                       ("failed", job_id))
                       
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

# ---------------------------------------------------------
# 4. REAL RUNPOD INTEGRATION
# ---------------------------------------------------------
def real_runpod_handler(job_id, job_input):
    runpod_api_key = os.environ.get("RUNPOD_API_KEY")
    endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID")
    base_url = os.environ.get("BASE_URL") # e.g., https://your-app.onrender.com
    
    if not all([runpod_api_key, endpoint_id, base_url]):
        print("ERROR: Missing RunPod Environment Variables.")
        conn = sqlite3.connect(DB_NAME)
        conn.execute("UPDATE jobs SET status = 'failed' WHERE job_id = ?", (job_id,))
        conn.commit()
        conn.close()
        return

    url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
    headers = {
        "Authorization": f"Bearer {runpod_api_key}",
        "Content-Type": "application/json"
    }
    
    # We pass our webhook URL containing our internal job_id
    # so RunPod knows exactly where to send the finished data.
    payload = {
        "input": {
            "prompt": job_input.get("prompt", "cinematic drone shot")
            # Add other model-specific inputs here (width, height, frames, etc.)
        },
        "webhook": f"{base_url}/webhook?job_id={job_id}"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        runpod_data = response.json()
        
        # Save RunPod's unique ID to our database just in case we need it later
        runpod_job_id = runpod_data.get("id")
        conn = sqlite3.connect(DB_NAME)
        conn.execute("UPDATE jobs SET runpod_job_id = ? WHERE job_id = ?", (runpod_job_id, job_id))
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Failed to communicate with RunPod: {e}")
        conn = sqlite3.connect(DB_NAME)
        conn.execute("UPDATE jobs SET status = 'failed' WHERE job_id = ?", (job_id,))
        conn.commit()
        conn.close()

# ---------------------------------------------------------
# 5. ADMIN PANEL
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
