# SecureBox dashboard

A local Flask dashboard for the BeagleY-AI MQTT demo. It provides login,
displays live MQTT sensor readings and alerts, stores recent readings, displays
message history, and publishes commands/messages to `securebox/commands`.

## Run on Windows for development

```powershell
cd dashboard
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

Development credentials are `admin` / `securebox`.

Windows MQTT environment variables are configured with `$env:NAME="value"`:

```powershell
$env:SECUREBOX_USERNAME="your-name"
$env:SECUREBOX_PASSWORD="a-long-random-password"
$env:SECUREBOX_SECRET_KEY="a-long-random-secret"
$env:MQTT_HOST="127.0.0.1"
$env:MQTT_PORT="8883"
$env:MQTT_TOPIC="securebox/sensors"
$env:MQTT_COMMAND_TOPIC="securebox/commands"
$env:MQTT_TLS="1"
$env:MQTT_CA_CERT="C:/path/to/ca.crt"
python app.py
```

## Run directly on the BeagleY-AI

First configure the sensor application and MQTT broker using the instructions in
the repository root README. Then open a terminal on the board.

### 1. Start the sensor publisher

Use Terminal 1:

```bash
cd ~/Documents/SecureBox/firmware_beagley_ai
/usr/bin/python3 run_securebox.py
```

Leave this process running. Sensor data is published to `securebox/sensors` over
MQTT TLS on port 8883.

### 2. Start the dashboard

Use Terminal 2:

```bash
cd ~/Documents/SecureBox/dashboard
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

export MQTT_HOST="127.0.0.1"
export MQTT_PORT="8883"
export MQTT_TOPIC="securebox/sensors"
export MQTT_COMMAND_TOPIC="securebox/commands"
export MQTT_TLS="1"
export MQTT_CA_CERT="/etc/mosquitto/certs/securebox/ca.crt"

python3 app.py
```

### 3. Open it on the board

In Firefox or Chromium, visit:

```text
http://127.0.0.1:5000
```

For development, log in with:

```text
Username: admin
Password: securebox
```

### 4. View it from another computer

On the BeagleY-AI, run:

```bash
hostname -I
```

Then visit the board address on a computer connected to the same network:

```text
http://BOARD-IP:5000
```

Example:

```text
http://192.168.1.50:5000
```

The Flask server listens on all network interfaces, so this works when port 5000
is not blocked by the board firewall. Do not expose the dashboard directly to
the public internet without HTTPS and stronger authentication.

## Verify the services

```bash
curl http://127.0.0.1:5000/api/health
ss -ltn | grep 5000
ss -ltn | grep 8883
sudo systemctl status mosquitto
```

Press `Ctrl+C` in a terminal to stop the process running there.

## Important current limitation

The dashboard records and publishes commands to `securebox/commands`, but the
current BeagleY-AI sensor application has no subscriber for that topic. Messages
are therefore visible in the dashboard but cannot yet trigger actions on the
board. Before using alarm or device-control features, add a command subscriber
to the board application.

The MQTT defaults and TLS setup are described in the root README. Broker
credentials and ACL support are not included in this demo's certificate-only
Mosquitto configuration and should be added before production deployment.
