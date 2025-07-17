from flask import Flask, render_template, request
from db import get_dashboard_data

app = Flask(__name__)

@app.route("/")
def home():
    return "<h3>🛠️ Web3 FileBot Dashboard<br><br>Use <code>/dashboard/&lt;your_telegram_id&gt;</code> to view your storage.</h3>"

@app.route("/dashboard/<user_id>")
def dashboard(user_id):
    user, files = get_dashboard_data(user_id)
    if not user:
        return "User not found."

    name, points = user
    total_size = sum(f[2] for f in files)
    file_list = [{
        "name": f[0],
        "cid": f[1],
        "size": round(f[2] / 1024, 2),
        "link": f"https://{f[1]}.ipfs.dweb.link"
    } for f in files]

    return render_template("dashboard.html",
                           name=name,
                           user_id=user_id,
                           points=points,
                           used_size_mb=round(total_size / (1024 * 1024), 2),
                           files=file_list)

if __name__ == "__main__":
    app.run(port=5000)
