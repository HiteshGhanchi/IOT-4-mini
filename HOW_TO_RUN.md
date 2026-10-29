# SecureBox — How to Run and Demonstrate the Project

This guide explains how to run the complete SecureBox demonstration on the
BeagleY-AI, view the authenticated dashboard, observe MQTT messages, and explain
each component to a teacher.

## Board details

```text
BeagleY-AI IP address: 10.10.190.111
Username:             beagle
Dashboard URL:        http://10.10.190.111:5000
Project location:     ~/Documents/SecureBox

Dashboard login:
Username: admin
Password: securebox
```

The dashboard password is only a development credential and should be changed
before presenting an internet-connected deployment.

---

## 1. Connect to the BeagleY-AI

Run this from the Windows computer:

```powershell
ssh beagle@10.10.190.111
```

Enter the board password when prompted.

---

## 2. Start the MQTT broker

Mosquitto should normally run automatically in the background. Verify it before
starting the demo:

```bash
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
sudo systemctl status mosquitto --no-pager
```

The broker configuration has a TLS listener on localhost:

```text
Protocol: MQTT over TLS
Port:     8883
Address:  127.0.0.1
```

Confirm that it is listening:

```bash
ss -ltn | grep 8883
```

The expected output contains:

```text
127.0.0.1:8883
```

---

## 3. Observe MQTT messages live

Open Terminal 1 on the BeagleY-AI. Subscribe to the sensor topic with certificate
verification:

```bash
cd ~/Documents/SecureBox
mosquitto_sub \
  --cafile /etc/mosquitto/certs/securebox/ca.crt \
  -h 127.0.0.1 \
  -p 8883 \
  -t securebox/sensors \
  -v
```

This terminal shows every JSON sensor message received from the board. Keep this
terminal visible during the demonstration because it proves that MQTT is working.

Expected message content includes:

```text
securebox/sensors
{
  "timestamp": "...",
  "temperature_c": 29.5,
  "humidity_percent": null,
  "dht_source": "demo",
  "distance_cm": 0.0,
  "vibration": false,
  "alerts": []
}
```

`humidity_percent` may be `null` in MQTT because the physical DHT/humidity sensor
is unavailable. The dashboard creates and displays a slowly changing presentation
value from 32% to 41%, and labels it as a demo value.

---

## 4. Start the SecureBox sensor publisher

Open Terminal 2 on the BeagleY-AI:

```bash
cd ~/Documents/SecureBox/firmware_beagley_ai
/usr/bin/python3 run_securebox.py
```

Leave this terminal running. It:

- Reads the temperature, distance, and vibration sensors.
- Checks threshold values.
- Writes readings to the local CSV file.
- Creates alert messages.
- Publishes sensor data every five seconds to `securebox/sensors` using MQTT TLS.

The MQTT subscriber terminal should now begin showing JSON messages.

---

## 5. Start the dashboard

Open Terminal 3 on the BeagleY-AI:

```bash
cd ~/Documents/SecureBox/dashboard
source .venv/bin/activate 2>/dev/null || true
python3 app.py
```

The dashboard listens on port 5000 on all network interfaces:

```text
0.0.0.0:5000
```

If the virtual environment has not been created yet:

```bash
cd ~/Documents/SecureBox/dashboard
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py
```

---

## 6. View the dashboard

From a Windows or Linux computer on the same LAN, open:

```text
http://10.10.190.111:5000
```

The teacher can also open this address from the Beagle board itself:

```text
http://127.0.0.1:5000
```

Sign in with:

```text
Username: admin
Password: securebox
```

### What to show in the dashboard

1. **MQTT status pill** — displays `connected` when the dashboard can reach the
   broker.
2. **Temperature card** — changes when the sensor publisher sends a new value.
3. **Humidity card** — displays a slowly changing demo value between 32%
   and 41% and is marked as a demo value.
4. **Distance card** — displays ultrasonic distance measurements.
5. **Vibration card** — displays whether vibration is currently detected.
6. **Temperature chart** — shows recent MQTT readings.
7. **Recent alerts** — displays sensor threshold alerts.
8. **Message section** — records dashboard messages sent over MQTT.

To verify dashboard communication:

```bash
curl http://127.0.0.1:5000/api/health
```

Expected response:

```json
{"mqtt":"connected","ok":true}
```

---

## 7. Show MQTT independently

For a strong teacher demonstration, arrange the presentation screen into three
sections:

1. The browser showing the SecureBox dashboard.
2. Terminal 1 showing live MQTT JSON from `mosquitto_sub`.
3. Terminal 2 showing readings and alerts printed by the sensor program.

Explain the complete data flow:

```text
DHT / ultrasonic / vibration sensors
                |
                v
      SecureBox Python program
                |
                v
      MQTT JSON publication over TLS
                |
                v
       Local Mosquitto broker :8883
          /                    \
         v                      v
   mosquitto_sub            Flask dashboard
                             API subscription
                                  |
                                  v
                             Browser :5000
```

---

## 8. Demonstrate a new sensor reading

Look at Terminal 2 while triggering or approaching the ultrasonic sensor. The
physical sensor behavior should appear in the terminal and the dashboard
updates automatically every three seconds.

For vibration, gently move the vibration sensor or demonstrate the configured
sensor module according to its safe operating instructions. Do not touch
unprotected wiring or expose bare GPIO connections.

Do not claim that the humidity is real. It is intentionally presented as a
dashboard demonstration fallback.

---

## 9. Commands and messages

The dashboard sends messages to:

```text
securebox/commands
```

View those messages live by opening Terminal 4:

```bash
mosquitto_sub \
  --cafile /etc/mosquitto/certs/securebox/ca.crt \
  -h 127.0.0.1 \
  -p 8883 \
  -t securebox/commands \
  -v
```

Type a message in the dashboard, then press **Send**. Its MQTT message should
appear in this terminal.

Example published payload:

```json
{
  "timestamp": "2026-10-28T...",
  "action": "message",
  "message": "SecureBox presentation message",
  "from": "admin"
}
```

The current board sensor program does not yet subscribe to or process this
command topic. This means the dashboard sends and records the message, and MQTT
shows that it was delivered, but the board does not perform an alarm or device
action yet.

---

## 10. Suggested presentation script

> “SecureBox is a local IoT monitoring system. The physical sensors are read by
a Python application running directly on the BeagleY-AI. The readings are
published as JSON through MQTT over TLS to a local Mosquitto broker. The Flask
backend subscribes to those MQTT readings, stores recent history, enforces login,
and exposes them through an API. The browser dashboard retrieves that API and
shows live sensor cards, alerts, charts, and message controls.”

Then show:

1. Sensor terminal running.
2. MQTT subscriber receiving live JSON.
3. Dashboard login page and successful login.
4. Dashboard cards updating.
5. Presentation humidity demonstration explanation.
6. Sending a dashboard MQTT message and observing it in the subscriber terminal.
7. Dashboard health and broker status checks.

---

## 11. Troubleshooting

### Dashboard does not open

```bash
cd ~/Documents/SecureBox/dashboard
python3 app.py
curl http://127.0.0.1:5000/api/health
ss -ltn | grep 5000
```

### MQTT status does not become connected

```bash
sudo systemctl status mosquitto --no-pager
ss -ltn | grep 8883
tail -50 /tmp/securebox-dashboard.log
```

Restart services:

```bash
sudo systemctl restart mosquitto
```

Then restart the sensor publisher and dashboard.

### Sensor terminal shows errors

```bash
gpiodetect
gpioinfo /dev/gpiochip2
gpioinfo /dev/gpiochip3
cat ~/Documents/SecureBox/firmware_beagley_ai/config.py
```

Verify wiring and GPIO controller paths. Never connect the ultrasonic ECHO wire
directly to a 3.3 V GPIO pin: the HC-SR04 ECHO output is 5 V and requires a
resistor divider or level shifter.

### Certificate error

```bash
ls -l /etc/mosquitto/certs/securebox
sudo sh ~/Documents/SecureBox/firmware_beagley_ai/setup_mqtt_tls.sh
sudo systemctl restart mosquitto
```

This certificate setup regenerates the local MQTT certificates. Restart both the
sensor publisher and dashboard afterward.

---

## 12. Stop the demonstration

Press `Ctrl+C` in each running terminal:

1. Dashboard terminal.
2. Sensor publisher terminal.
3. MQTT sensor subscriber terminal.
4. MQTT command subscriber terminal, if running.

The Mosquitto broker may remain running as a system service.

```bash
sudo systemctl status mosquitto
```
