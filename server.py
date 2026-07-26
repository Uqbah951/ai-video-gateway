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
# 3. ENDPOINTS & PROFESSIONAL UI
# ---------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Video Gateway | Dashboard</title>
        <style>
            :root { background: #090d16; color: #f1f5f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { margin: 0; padding: 30px; display: flex; justify-content: center; }
            .container { width: 100%; max-width: 750px; }
            .card { background: #111827; border: 1px solid #1f2937; padding: 25px; border-radius: 14px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); margin-bottom: 20px; }
            h1 { color: #38bdf8; font-size: 24px; margin-top: 0; display: flex; justify-content: space-between; align-items: center; }
            .badge { background: #059669; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
            label { display: block; margin-bottom: 8px; font-weight: 600; color: #94a3b8; font-size: 14px; }
            input, textarea { width: 100%; padding: 12px; background: #1f2937; border: 1px solid #374151; color: white; border-radius: 8px; box-sizing: border-box; margin-bottom: 15px; font-size: 14px; }
            input:focus, textarea:focus { outline: none; border-color: #38bdf8; }
            button { background: #2563eb; color: white; border: none; padding: 12px 20px; font-size: 15px; font-weight: bold; border-radius: 8px; cursor: pointer; width: 100%; transition: background 0.2s; }
            button:hover { background: #1d4ed8; }
            code { background: #1f2937; padding: 4px 8px; border-radius: 4px; color: #f43f5e; font-family: monospace; }
            .result-box { margin-top: 15px; background: #0f172a; border: 1px solid #334155; padding: 15px; border-radius: 8px; display: none; font-size: 14px; word-break: break-all; }
            .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px; }
            .info-item { background: #1f2937; padding: 12px; border-radius: 8px; }
            .info-item span { display: block; font-size: 12px; color: #94a3b8; margin-bottom: 4px; }
            .info-item strong { color: #f8fafc; font-size: 15px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h1>AI Video Gateway <span class="badge">Live</span></h1>
                <p style="color: #94a3b8; margin-top: -5px;">High-performance asynchronous AI rendering pipeline</p>
                
                <div class="info-grid">
                    <div class="info-item">
                        <span>Active Test API Key</span>
                        <strong><code>sk_live_test123</code></strong>
                    </div>
                    <div class="info-item">
                        <span>Generation Cost</span>
                        <strong>15 Credits / Video</strong>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3 style="margin-top: 0; color: #f8fafc;">Generate 3-Min AI Video</h3>
                <form id="videoForm">
                    <label for="apiKey">API Key</label>
                    <input type="text" id="apiKey" value="sk_live_test123" required>
                    
                    <label for="prompt">Video Scene Prompt</label>
                    <textarea id="prompt" rows="3" placeholder="Describe your 3-minute video concept (e.g., Cinematic drone shot flying over a futuristic green sci-fi city)..." required></textarea>
                    
                    <button type="submit" id="submitBtn">Start Video Generation Job</button>
                </form>

                <div id="resultBox" class="result-box">
                    <p><strong>Status:</strong> <span id="jobStatus" style="color: #fbbf24;">Processing...</span></p>
                    <p><strong>Job ID:</strong> <span id="jobIdText"></span></p>
                    <div id="videoContainer" style="margin-top: 10px; display: none;">
                        <video id="videoOutput" controls style="width: 100%; border-radius: 6px; margin-top: 8px;"></video>
                    </div>
                </div>
            </div>
            
            <div style="text-align: center; color: #64748b; font-size: 13px;">
                <a href="/admin/keys?secret=markaz_secure_2026" target="_blank" style="color: #38bdf8; text-decoration: none;">Admin Keys & Credits Panel</a>
            </div>
        </div>

        <script>
            document.getElementById('videoForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                const apiKey = document.getElementById('apiKey').value;
                const prompt = document.getElementById('prompt').value;
                const btn = document.getElementById('submitBtn');
                const resultBox = document.getElementById('resultBox');
                const jobStatus = document.getElementById('jobStatus');
                const jobIdText = document.getElementById('jobIdText');
                const videoContainer = document.getElementById('videoContainer');
                const videoOutput = document.getElementById('videoOutput');

                btn.disabled = true;
                btn.textContent = "Submitting Job...";
                resultBox.style.display = "block";
                videoContainer.style.display = "none";
                jobStatus.textContent = "Queued on server...";
                jobIdText.textContent = "Initializing...";

                try {
                    const response = await fetch('/v1/generate-video', {
                        method: 'POST',
                        headers: {
                            'Authorization': apiKey,
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ prompt: prompt, duration: "3min" })
                    });

                    const data = await response.json();
                    if (!response.ok) {
                        alert(data.error || "Failed to start generation");
                        btn.disabled = false;
                        btn.textContent = "Start Video Generation Job";
                        return;
                    }

                    const jobId = data.job_id;
                    jobIdText.textContent = jobId;
                    btn.textContent = "Processing Background Job...";

                    // Poll job status every 3 seconds
                    const interval = setInterval(async () => {
                        const statusRes = await fetch(`/v1/status/${jobId}`);
                        const statusData = await statusRes.json();

                        if (statusData.status === "completed") {
                            clearInterval(interval);
                            jobStatus.textContent = "Completed Successfully!";
                            jobStatus.style.color = "#34d399";
                            btn.disabled = false;
                            btn.textContent = "Start Video Generation Job";
                            
                            if (statusData.video_url) {
                                videoOutput.src = statusData.video_url;
                                videoContainer.style.display = "block";
                            }
                        } else {
                            jobStatus.textContent = "Processing with GPU worker...";
                        }
                    }, 3000);

                } catch (err) {
                    alert("Network error: " + err.message);
                    btn.disabled = false;
                    btn.textContent = "Start Video Generation Job";
                }
            });
        </script>
    </body>
    </html>
    """, 200

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
    time.sleep(4) # Simulate render time
    # Sample public MP4 video link for UI testing
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
