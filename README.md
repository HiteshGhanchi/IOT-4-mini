# SecureBox

SecureBox is a BeagleY-AI demo that reads GPIO-connected sensors, prints
readings and threshold alerts, logs samples to CSV, and publishes JSON over
MQTT. No cloud account is used; the MQTT broker and message display run
locally on the BeagleY-AI.

## What runs where

```text
DHT11 + HC-SR04 + vibration sensor
              |
              v
       BeagleY-AI / Python
         |            |
         v            v
 readings_mqtt.csv   MQTT over TLS
                         |
                         v
                local Mosquitto broker
                         |
                         v
                mosquitto_sub terminal
```

The application samples every five seconds. JSON is published to
`securebox/sensors`. The console displays the verified TLS protocol and cipher
after connecting; the subscriber terminal shows each MQTT message.

## Hardware and software

- BeagleY-AI running the BeagleBoard.org Debian image.
- DHT11/DHT22 data on physical header pin 7, with 3.3 V power, common ground,
  and a DATA pull-up if required by the sensor.
- HC-SR04 TRIG on physical pin 11; ECHO on physical pin 13 through a
  5 V-to-3.3 V divider. **Never connect 5 V ECHO directly to GPIO.**
- Digital vibration sensor output on physical pin 15.
- Debian packages: `python3-thonny`, `python3-libgpiod`, `gpiod`, `mosquitto`,
  `mosquitto-clients`, `python3-paho-mqtt`, and `openssl`.

Verify the pinout and sensor datasheets before wiring. BeagleY-AI GPIO uses
3.3 V logic.

## First-time setup on the BeagleY-AI

Copy the contents of `firmware_beagley_ai` onto the board at
`~/Documents/SecureBox` (or use the existing `~/Documents/SecureBox` folder).
Keep its board-specific `config.py`; do not overwrite it blindly with the
example file. Merge the MQTT/TLS settings from `config.py.example` if
`config.py` already exists. The application code is Python running on Linux,
not firmware to flash to the board.

Open a terminal on the board:

```bash
cd ~/Documents/SecureBox
sudo apt update
sudo apt install python3-thonny python3-libgpiod gpiod mosquitto mosquitto-clients python3-paho-mqtt openssl
sudo systemctl enable --now mosquitto
sudo sh setup_mqtt_tls.sh
```

The TLS setup script creates a local certificate authority and broker
certificate, configures Mosquitto to accept TLS on `127.0.0.1:8883`, then
restarts the broker. The broker is restricted to the board itself; this
starter setup does not expose an unauthenticated MQTT listener to the LAN.
Keep the CA private key off the board. The script deletes its temporary CA
private key after issuing the server certificate. Rerunning the script
generates a new local CA/certificate and restarts Mosquitto.

The MQTT client validates the broker certificate against
`/etc/mosquitto/certs/securebox/ca.crt` and connects by `127.0.0.1`, which is
included in the certificate. No insecure TLS verification bypass is used.

## Run and observe the demo

Use **two terminals on the BeagleY-AI**.

Terminal 1 subscribes using TLS and verifies the broker certificate:

```bash
mosquitto_sub --cafile /etc/mosquitto/certs/securebox/ca.crt -h 127.0.0.1 -p 8883 -t securebox/sensors -v
```

Terminal 2 starts SecureBox:

```bash
cd ~/Documents/SecureBox
/usr/bin/python3 run_securebox.py
```

The application prints readings and a `[TLS] VERIFIED` status including the
negotiated TLS version and cipher. The subscriber prints the JSON payload.
Press **Ctrl+C** in the application terminal to stop it.

Readings are appended to `readings_mqtt.csv`. Each message and CSV row has a
`dht_source` field. If the physical DHT cannot be read, the configured demo
fallback may publish a **demo** temperature; it is labelled as
`demo`, and humidity remains unavailable. Do not treat demo readings
as measurements. Set `DHT_DEMO_FALLBACK_ENABLED = False` in `config.py` to
disable that fallback.

## Configuration and troubleshooting

- Preserve the board-specific GPIO chip paths already in `config.py`.
- MQTT/TLS settings are in `config.py`; the example is
  [firmware_beagley_ai/config.py.example](./firmware_beagley_ai/config.py.example).
- Check the broker with `systemctl status mosquitto`.
- Check the TLS listener with
  `ss -ltn | grep 8883`; it should show `127.0.0.1:8883`.
- If certificate verification fails, confirm that the app uses host
  `127.0.0.1` and that the configured CA file exists and is readable.
- If the DHT driver reports incomplete signal edges or times out, check the
  sensor model, DATA on physical pin 7, common ground, 3.3 V power, and the
  DATA pull-up. A software fallback does not repair the sensor signal.
- For CSVs created by an older version, the application writes to
  `readings_mqtt.csv` so the earlier `readings.csv` stays intact.

For wiring and the longer Thonny guide, see
[firmware_beagley_ai/README_THONNY.md](./firmware_beagley_ai/README_THONNY.md).

## Complete run and demonstration guide

For a detailed teacher-presentation guide covering the broker, MQTT subscribers,
sensor publisher, dashboard, browser, message commands, and troubleshooting, see
[HOW_TO_RUN.md](./HOW_TO_RUN.md). A shorter command-only guide is available in
[HOW_TO_DEMO_QUICK.md](./HOW_TO_DEMO_QUICK.md).

## Run the authenticated web dashboard on the BeagleY-AI

### Device already prepared in the lab

The SecureBox project is installed on the board at `10.10.190.111` under
`~/Documents/SecureBox`. The live sensor publisher, dashboard, Mosquitto broker,
and local MQTT TLS listener are currently running. To open the dashboard, visit
`http://10.10.190.111:5000` from another computer on the LAN, or
`http://127.0.0.1:5000` directly on the board.

### Prepare the dashboard for the first run

```bash
cd ~/Documents/SecureBox/dashboard
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### Start the authenticated web dashboard on the BeagleY-AI

The dashboard is in [dashboard/](./dashboard/). It shows live MQTT readings, alerts, recent history, and publishes messages or commands to `securebox/commands`.

Complete the BeagleY-AI sensor and MQTT setup above, then use two terminals on the board. Leave both running while presenting the demo.

### Terminal 1: sensor program and MQTT publisher

```bash
cd ~/Documents/SecureBox/firmware_beagley_ai
/usr/bin/python3 run_securebox.py
```

### Terminal 2: dashboard

```bash
cd ~/Documents/SecureBox/dashboard
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py
```

Open Firefox or Chromium on the board at:

```text
http://127.0.0.1:5000
```

Development login:

```text
Username: admin
Password: securebox
```

Set strong credentials and a Flask secret before a real deployment:

```bash
export SECUREBOX_USERNAME="your-username"
export SECUREBOX_PASSWORD="a-long-random-password"
export SECUREBOX_SECRET_KEY="a-long-random-secret"
export MQTT_HOST="127.0.0.1"
export MQTT_PORT="8883"
export MQTT_TOPIC="securebox/sensors"
export MQTT_COMMAND_TOPIC="securebox/commands"
export MQTT_TLS="1"
export MQTT_CA_CERT="/etc/mosquitto/certs/securebox/ca.crt"
python3 app.py
```

### View the dashboard from another computer

Find the BeagleY-AI IP address:

```bash
hostname -I
```

From another device on the same network, open:

```text
http://BEAGLE_IP_ADDRESS:5000
```

For example: `http://192.168.1.50:5000`. The dashboard binds to `0.0.0.0`, so it is reachable on the LAN. Do not expose port 5000 directly to the internet: this demo login is not suitable for internet-facing deployment without HTTPS, secure session cookies, rate limiting, and proper MQTT authentication.

### Useful checks

```bash
curl http://127.0.0.1:5000/api/health
ss -ltn | grep 5000
ss -ltn | grep 8883
sudo systemctl status mosquitto
```

Press `Ctrl+C` in either terminal to stop that process.

## Record a demo video on Linux

To demonstrate the dashboard, sensors, and commands, install FFmpeg on the
board and use an available USB camera:

```bash
sudo apt update
sudo apt install ffmpeg
ls /dev/video*
ffmpeg -f v4l2 -framerate 30 -video_size 1280x720 -i /dev/video0 -c:v libx264 -pix_fmt yuv420p ~/SecureBox-demo.mp4
```

Press `Ctrl+C` to stop recording. If a USB microphone is connected, list its
recording device first:

```bash
arecord -l
```

Then record camera video and audio together, replacing `hw:1,0` with the number
shown by `arecord -l`:

```bash
ffmpeg -f v4l2 -framerate 30 -video_size 1280x720 -i /dev/video0 -f alsa -i hw:1,0 -c:v libx264 -pix_fmt yuv420p -c:a aac ~/SecureBox-demo.mp4
```

For a presentation recording made from the BeagleY-AI desktop without a
camera, phone-based screen recording is often more reliable on this Debian
image. Show the running dashboard, MQTT sensor terminal, and one live
sensor event in the same recording.

### Current messaging limitation

Dashboard commands and messages are published to `securebox/commands`. The BeagleY-AI sensor application currently does not subscribe to this topic, so sent messages are recorded and visible in the dashboard but are not yet processed by the board. Implement a subscriber in the sensor application before using this screen for alarm or device-control commands.
