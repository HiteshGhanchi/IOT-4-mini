# SecureBox — Quick Presentation Commands

Run these commands before the teacher demonstration.

## Terminal 1 — MQTT sensor messages

```bash
mosquitto_sub --cafile /etc/mosquitto/certs/securebox/ca.crt -h 127.0.0.1 -p 8883 -t securebox/sensors -v
```

## Terminal 2 — Sensor program

```bash
cd ~/Documents/SecureBox/firmware_beagley_ai
/usr/bin/python3 run_securebox.py
```

## Terminal 3 — Dashboard

```bash
cd ~/Documents/SecureBox/dashboard
source .venv/bin/activate
python3 app.py
```

## Terminal 4 — Dashboard command messages

```bash
mosquitto_sub --cafile /etc/mosquitto/certs/securebox/ca.crt -h 127.0.0.1 -p 8883 -t securebox/commands -v
```

## Browser

From another computer:

```text
http://10.10.190.111:5000
```

Login: `admin` / `securebox`

## Explain

1. Sensor Python publishes MQTT JSON over TLS.
2. Mosquitto receives it on port 8883.
3. Dashboard receives it and displays cards, chart, alerts and messages.
4. Humidity is a presentation demo from 32% to 41%, marked clearly on the UI.
5. Dashboard commands are visible through MQTT but are not yet handled by the sensor program.
