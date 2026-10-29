import json
import math
import os
import sqlite3
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

ROOT = Path(__file__).resolve().parent
DB_FILE = ROOT / "securebox.db"

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECUREBOX_SECRET_KEY", "change-this-secret-key")
app.config.update(
    MQTT_HOST=os.getenv("MQTT_HOST", "127.0.0.1"),
    MQTT_PORT=int(os.getenv("MQTT_PORT", "8883")),
    MQTT_TOPIC=os.getenv("MQTT_TOPIC", "securebox/sensors"),
    MQTT_COMMAND_TOPIC=os.getenv("MQTT_COMMAND_TOPIC", "securebox/commands"),
    MQTT_TLS=os.getenv("MQTT_TLS", "1") == "1",
    MQTT_CA_CERT=os.getenv("MQTT_CA_CERT", "/etc/mosquitto/certs/securebox/ca.crt"),
)

latest_reading = None
mqtt_status = "connecting"
recent_messages = []
message_lock = threading.Lock()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def db():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with db() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at TEXT NOT NULL,
            topic TEXT NOT NULL,
            action TEXT NOT NULL,
            text TEXT NOT NULL
        )""")
        username = os.getenv("SECUREBOX_USERNAME", "admin")
        password = os.getenv("SECUREBOX_PASSWORD", "securebox")
        if not connection.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )


init_db()


mqtt_client = None


def dashboard_reading(reading):
    """Add the presentation-only humidity used when the physical sensor is unavailable."""
    if not reading:
        return None
    displayed = dict(reading)
    if displayed.get("humidity_percent") is None:
        cycle_seconds = 600
        phase = (time.time() % cycle_seconds) / cycle_seconds * 2 * math.pi
        displayed["humidity_percent"] = round(36.5 + 4.5 * math.sin(phase), 1)
        displayed["humidity_source"] = "demo"
    return displayed


def mqtt_new_client():
    if mqtt is None:
        return None
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="securebox-dashboard")
    else:
        client = mqtt.Client(client_id="securebox-dashboard")
    if app.config["MQTT_TLS"] and os.path.isfile(app.config["MQTT_CA_CERT"]):
        client.tls_set(ca_certs=app.config["MQTT_CA_CERT"], cert_reqs=ssl.CERT_REQUIRED)
    return client


mqtt_client = mqtt_new_client()


def mqtt_callbacks(client):
    global mqtt_status, latest_reading

    def on_connect(_client, _userdata, _flags, reason_code, _properties=None):
        global mqtt_status
        reason_value = getattr(reason_code, "value", reason_code)
        mqtt_status = "connected" if reason_value == 0 else "connection error"
        if reason_value == 0:
            _client.subscribe(app.config["MQTT_TOPIC"], qos=1)

    def on_disconnect(_client, _userdata, _reason_code, _properties=None):
        global mqtt_status
        mqtt_status = "offline"

    def on_message(_client, _userdata, message):
        global latest_reading
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        payload["received_at"] = utc_now()
        latest_reading = payload
        with db() as connection:
            connection.execute(
                "INSERT INTO readings (received_at, payload) VALUES (?, ?)",
                (payload["received_at"], json.dumps(payload)),
            )
            connection.execute(
                "DELETE FROM readings WHERE id NOT IN (SELECT id FROM readings ORDER BY id DESC LIMIT 100)"
            )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message


if mqtt_client:
    mqtt_callbacks(mqtt_client)


def mqtt_worker():
    global mqtt_status
    while True:
        try:
            if mqtt_client is None or mqtt is None:
                mqtt_status = "paho-mqtt not installed"
                time.sleep(5)
                continue
            mqtt_status = "connecting"
            mqtt_client.connect(app.config["MQTT_HOST"], app.config["MQTT_PORT"], keepalive=30)
            mqtt_client.loop_forever(retry_first_connection=True)
        except Exception as error:
            mqtt_status = "offline: " + str(error)
            time.sleep(5)


threading.Thread(target=mqtt_worker, daemon=True).start()


def login_required(view):
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as connection:
            user = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["username"] = username
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", username=session["username"])


@app.route("/api/state")
@login_required
def api_state():
    history = []
    with db() as connection:
        rows = connection.execute("SELECT payload FROM readings ORDER BY id DESC LIMIT 24").fetchall()
    for row in reversed(rows):
        try:
            history.append(json.loads(row["payload"]))
        except json.JSONDecodeError:
            pass
    with db() as connection:
        messages = connection.execute("SELECT sent_at, topic, action, text FROM messages ORDER BY id DESC LIMIT 20").fetchall()
    displayed_latest = dashboard_reading(latest_reading)
    displayed_history = [dashboard_reading(reading) for reading in history]
    return jsonify({
        "mqtt": mqtt_status,
        "latest": displayed_latest,
        "history": displayed_history,
        "messages": [dict(row) for row in messages],
    })


@app.route("/api/message", methods=["POST"])
@login_required
def api_message():
    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "message")).strip().lower()[:30] or "message"
    text = str(data.get("text", "")).strip()[:500]
    if not text:
        return jsonify({"error": "Message cannot be empty."}), 400
    if mqtt_client is None:
        return jsonify({"error": "MQTT client is unavailable."}), 503

    payload = {
        "timestamp": utc_now(),
        "action": action,
        "message": text,
        "from": session["username"],
    }
    result = mqtt_client.publish(app.config["MQTT_COMMAND_TOPIC"], json.dumps(payload), qos=1)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        return jsonify({"error": "Could not publish the message."}), 503
    with db() as connection:
        connection.execute(
            "INSERT INTO messages (sent_at, topic, action, text) VALUES (?, ?, ?, ?)",
            (payload["timestamp"], app.config["MQTT_COMMAND_TOPIC"], action, text),
        )
    return jsonify({"ok": True, "payload": payload})


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "mqtt": mqtt_status})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", "0") == "1")
