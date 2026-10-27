# SecureBox: Tamper-Evident Smart Storage Box Monitor

> **Architecture update (current workspace):** The old ESP32/MicroPython
> architecture below is historical and is not the active hardware design.
> The current target is a BeagleY-AI running Linux Python 3, with DHT,
> ultrasonic, and digital vibration sensors connected directly to its GPIO
> header. Follow [START_HERE.md](./START_HERE.md) and
> [firmware_beagley_ai/README_THONNY.md](./firmware_beagley_ai/README_THONNY.md)
> for current wiring and Thonny instructions. MQTT/backend integration is
> not currently implemented in this workspace.

### Historical ESP32 target: DHT22 + MPU6050 + IR | MQTT/TLS | HMAC | backend/dashboard

> **INSTRUCTIONS FOR THE CLI CODING AGENT (read this first)**
> You are building a complete, runnable demo project from this specification. The human will only *run and present* it.
> 1. Detect the host OS (Windows / Linux / macOS) first and adapt shell commands. Prefer cross-platform Python scripts over bash/PowerShell where possible.
> 2. Create **every file** listed in section 5 with working code. Do not leave TODOs or placeholders.
> 3. Follow the message format, topics, ports, GPIO pins and detection rules in this document **exactly**. They are the contract between firmware, gateway, API and dashboard.
> 4. Everything must be testable **without the ESP32** using `tools/fake_device.py`, so the backend can be verified before flashing hardware.
> 5. Keep code simple and commented. This is a student demo, so readability beats cleverness.
> 6. When finished, print the exact commands the human must run, in order (section 12), and run the acceptance checks in section 13.

---

## 1. Project Summary

**SecureBox** monitors a storage box (lab cabinet, locker, medicine box, or server-room drawer) and detects when someone **opens it**, **shakes or forces it**, or when its **environment goes abnormal**. It also protects the IoT system itself: every message from the ESP32 is encrypted (TLS), authenticated (username/password and HMAC), replay-protected (timestamp check), and firmware-attested (the device reports its firmware hash).

**Why this is simple:** one ESP32, three sensors, one protocol (MQTT over TLS), and one local Linux host for everything else. No cloud account is needed. The host can be an Odroid SBC with a monitor displaying the dashboard; a laptop can be used during development instead.

| Sensor | Measures | Used for |
|---|---|---|
| **DHT22** (or DHT11) | Temperature, humidity | Environment monitoring, statistical anomaly detection (z-score) |
| **MPU6050** | 3-axis acceleration and rotation | Movement, tilt, and shock detection |
| **Digital IR obstacle sensor** | Obstruction/presence state | Access/opening detection when aimed across the protected opening |

**Output actuator (no extra wiring):** the ESP32 onboard LED (GPIO 2) lights up as the alarm when the gateway sends a **signed command**.

---

## 2. Architecture

```
 PERCEPTION LAYER                NETWORK LAYER                     EDGE / GATEWAY LAYER
+-----------------------+     MQTT over TLS 1.2, port 8883      +----------------------------------+
| ESP32 (Wi-Fi)         |  user/pass + HMAC-SHA256 payload      | Mosquitto broker (TLS, ACL)      |
|  - DHT22  (GPIO 4)    | ------------------------------------> |   |                              |
|  - MPU6050 (I2C 21/22)|                                        |   v                              |
|  - IR     (GPIO 27)   | <------------------------------------ | Python gateway (gateway.py)      |
|  - LED    (GPIO 2)    |   signed alarm command (cmd topic)     |  - verify HMAC + replay window   |
+-----------------------+                                        |  - validate JSON schema          |
                                                                 |  - firmware fingerprint          |
                                                                 |  - anomaly detection             |
                                                                 |  - intrusion detection (IDS)     |
                                                                 +----------------+-----------------+
                                                                                  |
 CLOUD / APPLICATION LAYER                                                        v
+--------------------------------------------+     JSON/HTTP      +----------------------------+
| Streamlit dashboard (port 8501)            | <----------------> | Flask REST API (port 5000) |
| + tiny HTML/CSS/jQuery status page         |                    +-------------+--------------+
| (optional) Apache HTTPS reverse proxy :443 |                                  |
+--------------------------------------------+                                  v
                                                                  MongoDB (readings, alerts)
```

All server components run on **one local host**, preferably the Odroid SBC for an always-on demo. The host may be connected to a monitor showing the dashboard. The ESP32 joins the same Wi-Fi/LAN (phone hotspot or home router, *not* a network that isolates clients). Configure the ESP32 and broker certificate with the host's reachable LAN address, never `localhost`.

---

## 3. Hardware and Wiring

### 3.1 Bill of materials
- 1 x ESP32 DevKit (ESP32-WROOM-32, 30 or 38 pin)
- 1 x DHT22 (AM2302) module, or DHT11 (change one line in firmware)
- 1 x MPU6050 accelerometer/gyroscope breakout board
- 1 x digital IR obstacle/proximity sensor module with a 3.3 V-safe output
- Breadboard, jumper wires, micro-USB or USB-C cable (data cable, not charge-only)

### 3.2 GPIO pin map (use exactly these)

| Sensor / part | Sensor pin | ESP32 pin | Notes |
|---|---|---|---|
| **DHT22** | VCC (+) | **3V3** | Use 3.3V, not 5V |
| | DATA (OUT) | **GPIO 4** | Module boards have a built-in pull-up. For a bare 4-pin DHT22, add a **10 kΩ resistor between DATA and 3V3** |
| | GND (-) | **GND** | |
| **MPU6050** | VCC | **3V3** | Confirm breakout supports 3.3 V logic |
| | GND | **GND** | Common ground |
| | SDA | **GPIO 21** | ESP32 I2C data |
| | SCL | **GPIO 22** | ESP32 I2C clock |
| **Digital IR sensor** | VCC | **3V3** | Confirm the board's output is 3.3 V safe |
| | GND | **GND** | Common ground |
| | OUT/DO | **GPIO 27** | Configure active polarity in MicroPython `config.py` |
| **Alarm LED** | onboard LED | **GPIO 2** | Already on the board, no wiring |

Pins to **avoid**: GPIO 0, 12, 15 (boot strapping), GPIO 6-11 (internal flash), GPIO 1 and 3 (USB serial).

### 3.3 Wiring diagram (text)

```
                +---------------------+
                |        ESP32        |
   DHT22 DATA --| GPIO 4        3V3   |-- sensor VCC (3.3 V only)
   MPU6050 SDA -| GPIO 21      GND   |-- all sensor GND
   MPU6050 SCL -| GPIO 22             |
   IR OUT/DO ---| GPIO 27             |
                | GPIO 2 (LED)  USB   |-- host (power + flashing)
                +---------------------+
```
Tip: connect the 3V3 pin to the breadboard's red rail and GND to the blue rail, then plug all three sensors into the rails.

### 3.4 Sensor sanity notes
- DHT22 needs at least 2 seconds between reads. The firmware publishes every **5 seconds**.
- The IR sensor is a simple digital obstacle/presence sensor; mount it so its detection path changes when the lid or protected opening moves. Set `IR_ACTIVE_LEVEL` to match the board's active output polarity.
- The MPU6050 is sampled over I2C at 20 Hz. Firmware counts movement events from acceleration changes or angular-rate thresholds and reports the latest acceleration in g.
- LiDAR and ultrasonic sensors are possible future alternatives, but their models and interfaces differ. They are not supported by the current MicroPython firmware. For a common HC-SR04, its 5 V ECHO must not be connected directly to an ESP32 GPIO.

---

## 4. Software Requirements

| Component | Version / note |
|---|---|
| Python | 3.10+ |
| Mosquitto | 2.x (with `mosquitto_passwd`) |
| MongoDB | Community server or container where supported; verify availability for the selected Odroid model/OS/CPU architecture before choosing Odroid as the database host |
| ESP32 firmware | MicroPython for ESP32, uploaded with Thonny; the present firmware does not use PlatformIO |
| OpenSSL | For generating certificates |
| Apache 2.4 | **Optional** (section 9) |
| Python packages (`requirements.txt`) | `paho-mqtt>=2.0`, `pymongo`, `flask`, `flask-cors`, `python-dotenv`, `streamlit>=1.37`, `requests`, `pandas`, `altair`, `aiocoap` (optional) |

---

## 5. Repository Layout (create all of these)

```
securebox/
├── README.md                    # short run guide (copy of section 12)
├── .env.example                 # all settings (section 6)
├── .gitignore                   # .env, certs/*.key, firmware/include/secrets.h, __pycache__
├── requirements.txt
├── certs/
│   └── gen_certs.py             # creates CA + broker cert with IP SAN (section 7.1)
├── mosquitto/
│   ├── mosquitto.conf           # TLS listener, no anonymous, ACL (section 7.2)
│   └── acl                      # topic permissions (section 7.3)
├── firmware_micropython/
│   ├── main.py                  # ESP32 MicroPython firmware
│   ├── umqtt_simple.py          # MQTT client
│   ├── config.py.example        # copy to config.py and edit locally
│   └── README_THONNY.md         # upload instructions
├── gateway/
│   ├── gateway.py               # MQTT subscriber + validation + detection + DB (section 8.2)
│   ├── security.py              # HMAC sign/verify helpers, replay check
│   └── ids_logwatch.py          # tails mosquitto log for auth failures (section 8.2.6)
├── api/
│   ├── app.py                   # Flask REST API (section 8.3)
│   └── static/status.html       # small HTML + CSS + jQuery page (section 8.4)
├── dashboard/
│   └── app.py                   # Streamlit dashboard (section 8.5)
├── apache/
│   └── securebox.conf           # OPTIONAL HTTPS reverse proxy (section 9)
├── coap/
│   └── coap_status.py           # OPTIONAL tiny CoAP server (section 9)
└── tools/
    ├── gen_secrets.py           # reads .env + certs/ca.crt -> firmware/include/secrets.h
    ├── setup_broker.py          # creates Mosquitto password file from .env
    ├── fake_device.py           # simulated ESP32 + attack modes (section 10)
    └── run_all.py               # starts gateway, API, logwatch, dashboard together
```

---

## 6. Configuration (`.env.example`)

```ini
# --- Network ---
BROKER_HOST=192.168.1.50        # Odroid/laptop LAN IP (ESP32 connects here); must match cert SAN.
BROKER_PORT=8883
WIFI_SSID=YourWiFiName
WIFI_PASS=YourWiFiPassword

# --- MQTT accounts (generated by tools/setup_broker.py if left as CHANGE_ME) ---
DEVICE_ID=esp32-01
DEVICE_USER=esp32-01
DEVICE_PASS=CHANGE_ME
GATEWAY_USER=gateway
GATEWAY_PASS=CHANGE_ME

# --- Crypto ---
HMAC_KEY_HEX=CHANGE_ME          # 64 hex chars (32 bytes). Generated by gen_secrets.py if CHANGE_ME.
REPLAY_WINDOW_SEC=60

# --- Firmware fingerprint ---
FW_ALLOWLIST=                   # comma-separated version-derived fingerprints; empty = learn mode

# --- Detection rules ---
PUBLISH_INTERVAL_SEC=5
Z_THRESHOLD=3.0
Z_WINDOW=30                     # samples in the rolling window; need >= 10 before z-score is used
TEMP_MAX=35.0
TEMP_MIN=5.0
HUM_MAX=85.0
IR_ACTIVE_LEVEL=0               # digital level that means the IR sensor detects an obstruction
MOTION_EVENTS_ALERT=2           # movement events in one publish interval = tamper
MOTION_ACCEL_DELTA_G=0.35       # acceleration delta threshold used by the firmware
MOTION_GYRO_THRESHOLD_DPS=80.0  # angular-rate threshold used by the firmware
MOTION_DEBOUNCE_MS=250          # minimum separation between movement events
OFFLINE_AFTER_SEC=20
AUTH_FAIL_BURST=3               # failures within 60s -> brute-force alert

# --- Services ---
MONGO_URI=mongodb://localhost:27017
MONGO_DB=securebox
API_HOST=127.0.0.1
API_PORT=5000
API_KEY=CHANGE_ME               # required header X-API-Key for write endpoints (generated if CHANGE_ME)
MOSQUITTO_LOG=./mosquitto/mosquitto.log
```

---

## 7. Security Setup

### 7.1 TLS certificates (`certs/gen_certs.py`)
The script reads `BROKER_HOST` from `.env` and runs OpenSSL (equivalent commands below). **The IP must be in the Subject Alternative Name or the ESP32 will reject the broker.**

```bash
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 -subj "/CN=SecureBox-CA" -out ca.crt
openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/CN=<BROKER_HOST>" -out server.csr
echo "subjectAltName=IP:<BROKER_HOST>" > san.ext
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365 -sha256 -extfile san.ext
```
Only `ca.crt` is placed on the ESP32 (it needs to trust the CA, not hold private keys). If the laptop's IP changes (hotspot), regenerate certs and re-flash.

### 7.2 `mosquitto/mosquitto.conf`
```
per_listener_settings true
listener 8883
cafile      <abs path>/certs/ca.crt
certfile    <abs path>/certs/server.crt
keyfile     <abs path>/certs/server.key
tls_version tlsv1.2
allow_anonymous false
password_file <abs path>/mosquitto/passwd
acl_file      <abs path>/mosquitto/acl
log_dest file <abs path>/mosquitto/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
connection_messages true
```
No plain port 1883 listener exists (hardening). `tools/setup_broker.py` fills in absolute paths and creates the password file with `mosquitto_passwd -c -b`.

### 7.3 `mosquitto/acl` (least privilege access control)
```
user esp32-01
topic write securebox/esp32-01/data
topic write securebox/esp32-01/status
topic read  securebox/esp32-01/cmd

user gateway
topic read  securebox/+/data
topic read  securebox/+/status
topic write securebox/+/cmd
```
The device cannot read other devices' data or publish commands. The gateway cannot be impersonated without its password.

### 7.4 Security controls summary

| Layer | Control | Defends against |
|---|---|---|
| Transport | TLS 1.2 on port 8883, device validates broker via CA cert | Eavesdropping, man-in-the-middle, rogue broker |
| Authentication | Per-client MQTT username/password, no anonymous | Unauthorized clients |
| Message integrity | HMAC-SHA256 over a canonical string | Forged or tampered payloads |
| Replay protection | Timestamp must be newer than the last accepted one and within +/-60 s of gateway clock | Replayed old messages |
| Authorization | Mosquitto ACL | A compromised device publishing to other topics |
| Firmware fingerprint | Device reports a version-derived build fingerprint; a future gateway can compare it to an allowlist | Changed/unrecognized firmware version (not cryptographic proof of the running image) |
| Command authentication | Alarm commands signed with HMAC and timestamped | Fake alarm commands |
| API | API key for write endpoints, bound to localhost | Unauthorized API use |
| IDS | Gateway + log watcher alerts | Brute force, forgery, tampering |

---

## 8. Component Specifications

### 8.0 The data contract (used by everything)

**Topics**
- `securebox/esp32-01/data`: device -> gateway, every 5 s
- `securebox/esp32-01/status`: device -> gateway, retained. Payload `online` on connect, **Last Will** payload `offline`
- `securebox/esp32-01/cmd`: gateway -> device (signed command)

**Data payload (JSON)** The current MicroPython firmware publishes:
```json
{"dev":"esp32-01","ts":1761556800,"seq":42,"temp":27.5,"hum":55.2,"ir":0,"ax":0.01,"ay":-0.02,"az":1.00,"motion":0,"fw":"9f2c1a...32hex","sig":"<64 hex chars>"}
```
`ts` is Unix epoch seconds (the ESP32 gets it via NTP), `seq` is a counter since boot, `ir` is normalized to 1 when the configured IR active level is detected, `ax`/`ay`/`az` are MPU6050 acceleration values in g, `motion` is the number of detected movement events since the previous publish, and `fw` is the MicroPython build fingerprint.

**Canonical string for the HMAC** (avoids JSON key-order problems; both sides must build it identically):
```
"<dev>|<ts>|<seq>|<temp %.1f>|<hum %.1f>|<ir>|<ax %.2f>|<ay %.2f>|<az %.2f>|<motion>|<fw>"
sig = hex( HMAC-SHA256( key = bytes.fromhex(HMAC_KEY_HEX), msg = canonical string ) )
```
All readings in the payload are signed, including the IR state, acceleration, and movement-event count.
Compare signatures with `hmac.compare_digest` on the gateway.

**Command payload** (gateway -> device)
```json
{"cmd":"alarm","state":1,"ts":1761556801,"sig":"..."}
```
Canonical string: `"CMD|alarm|<state>|<ts>"` (the `CMD|` prefix prevents a data signature from being reused as a command signature). The device verifies the HMAC and that `|now - ts| <= 60`, then sets the GPIO 2 LED to `state`.

### 8.1 ESP32 firmware (`firmware_micropython/main.py`)
The implementation currently present uses MicroPython on an ESP32 and is
uploaded with Thonny.

1. DHT data is on GPIO 4; IR output is on GPIO 27; MPU6050 SDA/SCL are GPIO
   21/22; the onboard alarm LED is GPIO 2. IR active polarity and MPU I2C
   address are configured in `firmware_micropython/config.py`.
2. The MPU6050 is initialized over I2C and sampled every 50 ms. Firmware counts
   movement events when acceleration delta or gyro magnitude crosses its
   configured threshold, with a configurable debounce.
3. The firmware connects to Wi-Fi, synchronizes time through NTP, and refuses
   insecure MQTT TLS. The broker CA certificate is uploaded as `ca.crt`.
4. It connects to MQTT using the device credentials, sets a retained Last Will
   (`offline`), publishes retained `online`, subscribes to the command topic,
   and reconnects with a 5-second backoff.
5. Every 5 seconds it reads DHT temperature/humidity, includes the normalized
   IR state, MPU6050 acceleration and movement-event count, signs all fields
   using the data canonical string in section 8.0, and publishes JSON.
6. On an alarm command, it validates the HMAC and timestamp window before
   controlling GPIO 2. Serial output runs at 115200 baud.
7. MicroPython does not provide a portable hash of the running flash image;
   the firmware reports a version-derived 32-hex build fingerprint instead.
   Change `FW_VERSION` when intentionally changing the firmware.

### 8.2 Gateway (`gateway/gateway.py`, `gateway/security.py`)
Uses `paho-mqtt` (Callback API v2) with TLS (`tls_set(ca_certs=...)`), username `gateway`.

1. **Subscribe** to `securebox/+/data` and `securebox/+/status`.
2. **Validation pipeline** for each data message, in this order (stop and raise an alert at the first failure, and do **not** store the reading):
   1. Parse JSON; check required keys and types (`dev` str, `ts` int, `seq` int, `temp`, `hum` float, `ir` int in 0..1, `ax`, `ay`, `az` float, `motion` int >= 0, `fw` str, `sig` str). Failure -> alert `BAD_FORMAT` (medium).
   2. Recompute HMAC and compare. Failure -> alert `BAD_HMAC` (high).
   3. Replay check: `abs(now - ts) <= REPLAY_WINDOW_SEC` and `ts > last_ts[dev]`. Failure -> alert `REPLAY` (high).
   4. Firmware fingerprint check: if `FW_ALLOWLIST` is empty, run in **learn mode** (print the fingerprint and add it for this session). Otherwise `fw` must be in the list, else alert `FW_MISMATCH` (high), still store the reading flagged `fw_ok=false`. This is a version-derived fingerprint, not a cryptographic measurement of flash contents.
3. **Store** valid readings in MongoDB `readings`:
   `{dev, ts, received_at, seq, temp, hum, ir, ax, ay, az, motion, fw, fw_ok, flags:[...]}`
4. **Detection rules** (each creates a document in `alerts`):

| Rule | Condition | Alert type | Severity |
|---|---|---|---|
| Temperature statistical anomaly | Rolling window of last `Z_WINDOW` temps has >= 10 samples and `abs(z) > Z_THRESHOLD` where `z=(x-mean)/std` (skip if std < 0.05) | `TEMP_ANOMALY` | medium |
| Temperature threshold | `temp > TEMP_MAX` or `temp < TEMP_MIN` | `TEMP_THRESHOLD` | medium |
| High humidity | `hum > HUM_MAX` | `HUMIDITY_HIGH` | low |
| Protected opening obstructed | `ir == 1` (IR module is mounted/configured so its active state indicates access) | `INTRUSION_IR` | high |
| Tamper / forced movement | `motion >= MOTION_EVENTS_ALERT` in one interval | `TAMPER_MOTION` | high |
| Minor movement | `1 <= motion < MOTION_EVENTS_ALERT` | `MOTION_DETECTED` | low |
| Device offline | Status `offline` received (Last Will) or no data for `OFFLINE_AFTER_SEC` | `DEVICE_OFFLINE` | medium |

   Rate-limit: do not re-raise the same alert type for the same device more than once every 15 s (avoid flooding).
5. **Active response:** when a **high** severity alert is raised, publish a signed command `alarm state=1` to `securebox/<dev>/cmd` (LED on). Publish `state=0` after 30 s with no high alerts.
6. **IDS log watcher** (`ids_logwatch.py`, separate process): tails `MOSQUITTO_LOG`, matches lines containing `not authorised`, `Bad username or password`, `bad user name`, or `certificate unknown` and `unknown ca`. Writes alert `AUTH_FAIL` (medium). If >= `AUTH_FAIL_BURST` failures occur within 60 s, writes `BRUTE_FORCE` (high). Extract the client IP from the log line when present.
7. Log every decision to the console with clear tags like `[OK]`, `[ALERT]`, `[REJECT]` so the demo is easy to narrate.
8. Create indexes: `readings(dev, ts)`, `alerts(ts)`.

`alerts` document: `{ts, received_at, dev, type, severity, message, details:{...}}`.

### 8.3 REST API (`api/app.py`, Flask, port 5000)
All responses are JSON. Enable CORS. Read endpoints are open on localhost, write endpoints need header `X-API-Key`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{status:"ok", mongo:true/false}` |
| GET | `/api/latest` | Newest reading plus device online/offline state and current IR/motion state |
| GET | `/api/readings?limit=200` | Newest first, max 1000 |
| GET | `/api/alerts?limit=50&severity=high` | Newest first, optional severity filter |
| GET | `/api/stats` | min / max / avg / std for temp and hum over the last 100 readings, counts of alerts by type and severity |
| POST | `/api/command` (API key) | Body `{"cmd":"alarm","state":0}`; the API stores a command request in the `commands` collection and the gateway (polls every 2 s) signs and publishes it. This lets the dashboard "Silence alarm" button work without the API holding the HMAC key |
| POST | `/api/clear_alerts` (API key) | Deletes alerts (for demo reset) |

Serve `api/static/status.html` at `/` (or `/status`).

### 8.4 Mini web page (`api/static/status.html`): HTML + CSS + jQuery
A single file, jQuery loaded from `https://code.jquery.com/jquery-3.7.1.min.js`. A small card layout styled with CSS showing the latest temperature, humidity, IR state, MPU movement count, device status, and the last 5 alerts. Uses `$.getJSON("/api/latest")` and `$.getJSON("/api/alerts?limit=5")` every 3 seconds. Red border when the newest alert is high severity. About 60 lines. (This covers the HTML/CSS/jQuery syllabus item. The main UI is Streamlit.)

### 8.5 Streamlit dashboard (`dashboard/app.py`)
Run: `streamlit run dashboard/app.py`. Read all data via the Flask API with `requests` (so the HTTP + JSON path is genuinely used). Use `st.set_page_config(layout="wide")` and refresh with `@st.fragment(run_every=5)`. Keep it **minimal**:

1. **Header** with the project title and a status badge: ONLINE (green) / OFFLINE (red), plus a **security badge**: "Secure channel: TLS 1.2 | HMAC verified | Firmware OK/MISMATCH".
2. **KPI row** (`st.metric`): Temperature (with delta from previous), Humidity, IR state (with "Opening: CLEAR/OBSTRUCTED"), MPU movement events, Active alerts in last 10 min.
3. **Charts:** (a) temperature and humidity line chart, with anomaly points marked in red (Altair layer using readings whose `flags` contain `TEMP_ANOMALY`); (b) acceleration axes (`ax`, `ay`, `az`) over time; (c) movement events as a bar chart.
4. **Analytics expander:** min / max / mean / std table from `/api/stats`, and the rolling z-score of temperature.
5. **Alerts table:** newest 15 alerts, colour rows by severity (high = red, medium = orange, low = yellow). Show an **alerts-by-type** bar chart.
6. **Sidebar:** buttons "Silence alarm" (POST `/api/command`, state 0) and "Clear alerts", plus the API URL and key (from env), and a refresh-interval note.

---

## 9. Optional Extras (only if time remains; each is under 10 minutes)

**9.1 Apache HTTPS reverse proxy (`apache/securebox.conf`).** Enable `mod_ssl`, `mod_proxy`, `mod_proxy_http`, `mod_proxy_wstunnel`, `mod_rewrite`, `mod_headers`. VirtualHost `*:443` using a certificate signed by the project CA (SAN = local host IP), `ServerTokens Prod`, `Header always set X-Content-Type-Options nosniff`, `ProxyPass /api http://127.0.0.1:5000/api`, and proxy `/` (with WebSocket upgrade: `RewriteRule /(.*) ws://127.0.0.1:8501/$1`) to Streamlit on port 8501. Port 80 redirects to 443. Start Streamlit with `--server.address 127.0.0.1` when proxying. If Apache is hard to install on the host OS, run it in Docker (`httpd:2.4`) or document the config only.

**9.2 CoAP endpoint (`coap/coap_status.py`).** With `aiocoap`, expose `GET coap://<laptop>:5683/status` returning the latest reading as JSON (read from MongoDB). This demonstrates the third protocol. Explain in the report that CoAP **over DTLS (UDP 5684)** is the secure variant, and that MQTT-over-TLS is used in this project because TLS/TCP is supported natively on ESP32 with `WiFiClientSecure`.

**9.3 Secure boot demonstration (documentation, no eFuse burning).** Do **not** burn eFuses on the only board (irreversible). Show the ESP-IDF `menuconfig` screens (*Security features -> Enable hardware Secure Boot in bootloader; Enable flash encryption on boot*) in screenshots, explain the chain of trust (ROM bootloader -> signed second-stage bootloader -> signed app), and demonstrate the related application-level controls: the version-derived `fw` fingerprint allowlist and signed commands. These controls are not hardware secure boot and do not prove the contents of flash.

---

## 10. Simulation and Attack Tools (`tools/fake_device.py`)

A Python MQTT client that behaves exactly like the ESP32 so the backend can be tested and the security demo can be shown even without hardware. It reuses the same canonical string/HMAC code. Usage:

```
python tools/fake_device.py --mode normal       # realistic temp ~26 C, ir=0, motion=0, valid HMAC
python tools/fake_device.py --mode heat         # temperature climbs by +1 C every cycle (TEMP_ANOMALY, TEMP_THRESHOLD)
python tools/fake_device.py --mode open         # IR state becomes active (INTRUSION_IR)
python tools/fake_device.py --mode shake        # motion events exceed threshold (TAMPER_MOTION)
python tools/fake_device.py --mode badhmac      # valid-looking payload with wrong signature (BAD_HMAC)
python tools/fake_device.py --mode replay       # re-sends an old captured message (REPLAY)
python tools/fake_device.py --mode badfw        # unknown firmware hash (FW_MISMATCH)
python tools/fake_device.py --mode badpass      # connects with a wrong password (AUTH_FAIL via log watcher)
python tools/fake_device.py --mode bruteforce   # 5 wrong passwords in a row (BRUTE_FORCE)
```
Each mode prints what it is doing and which alert the audience should expect. The `normal` mode must use the real device credentials so it can replace the ESP32 in tests (use a different `dev` id only if the real device is running at the same time).

`tools/run_all.py` starts the gateway, API, log watcher and Streamlit as subprocesses, prints the URLs, and shuts everything down on Ctrl+C. Mosquitto and MongoDB are started separately by the human (section 12).

---

## 11. Syllabus Coverage Map (for the report and viva)

| Syllabus topic | Where it appears in this project |
|---|---|
| IoT architecture and design principles | Section 2: 4-layer model (perception, network, edge/gateway, cloud/application); modular, loosely coupled via MQTT topics |
| IoT devices, gateways, networking | ESP32 (device, Wi-Fi), Odroid SBC running Linux with Python gateway + broker (edge), TCP/IP over Wi-Fi |
| HTTP, MQTT, CoAP | MQTT (device to gateway), HTTP/JSON (API to dashboard), CoAP endpoint (9.2) and a comparison table in the report |
| IoT communication security | TLS channel, HMAC, replay protection, ACL (section 7.4) |
| Cryptography and authentication | RSA-2048 certificates, SHA-256, HMAC-SHA256, pre-shared key, username/password |
| TLS/SSL and DTLS | TLS 1.2 on port 8883 with certificate validation on the ESP32; DTLS (UDP 5684) explained for CoAP |
| Secure boot and firmware security | Version-derived firmware fingerprint allowlist, signed commands, secure boot + flash encryption chain explained (9.3) |
| Access control and device hardening | Mosquitto ACL, no anonymous access, no plain-text port, least privilege, API key, localhost binding, CA-only on device |
| IoT application development | Firmware + gateway + API + dashboard |
| Apache/HTTP server | Apache HTTPS reverse proxy (9.1) and the Flask HTTP server |
| MongoDB/database | `readings`, `alerts`, `commands` collections |
| HTML, CSS and jQuery based UI | `status.html` (8.4); Streamlit as the main minimal dashboard |
| JSON-based data processing | MQTT payloads, API responses, MongoDB documents, schema validation |
| IoT data acquisition and management | Sensor sampling, movement-event aggregation, publish cycle, ingestion pipeline, storage and indexing |
| Data analytics and visualization | KPIs, min/max/mean/std, rolling z-score, charts in Streamlit |
| Anomaly detection | Z-score on temperature, environmental thresholds, IR state, MPU6050 motion events |
| Cloud computing and XaaS | Mapping below |
| IoT monitoring and intrusion detection | Alerts collection, log watcher, brute-force detection, forged/replayed message detection |

**XaaS mapping (for the report).** *Today:* services run on a local Odroid SBC (private edge), or a laptop during development. *Cloud deployment option:* move Mosquitto + gateway + API + MongoDB to a VM = **IaaS**; run the API/dashboard on managed platforms with a compatible database service = **PaaS**; the Streamlit dashboard as consumed by an end user = **SaaS**; the device-to-cloud data service as a whole = **IoTaaS / Data-as-a-Service**.

**Threat model (short, for the report).**

| Threat | Example attack | Mitigation here |
|---|---|---|
| Eavesdropping | Wireshark on the Wi-Fi | TLS |
| Spoofing | Fake device publishes false data | Password + HMAC |
| Tampering | Edited payload | HMAC |
| Replay | Resent old "all normal" message | Timestamp window + monotonic `ts` |
| Rogue broker | Attacker AP with fake broker | Device validates CA + SAN |
| Brute force | Guessing MQTT passwords | Log-based IDS, alerting |
| Malicious firmware | Modified code on the device | Attestation hash mismatch alert |
| Physical tamper | Protected opening obstructed or box moved | IR obstacle sensor + MPU6050 detection |
| Privilege abuse | Device publishing commands | ACL |

---

## 12. Target Run Guide

The backend and tools below are specified but are not present in the current
workspace. The commands describe the intended completed demo and cannot be run
until those backend files have been implemented. The ESP32 firmware that is
present can be prepared with the Thonny steps in `START_HERE.md`.

```bash
# 0. One-time setup
cd securebox
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # then edit BROKER_HOST, WIFI_SSID, WIFI_PASS

# 1. Security material
python certs/gen_certs.py                               # CA + broker cert with IP SAN
python tools/setup_broker.py                            # passwords, HMAC key, password file, mosquitto.conf, acl
# Configure firmware_micropython/config.py from config.py.example and upload
# it, main.py, umqtt_simple.py, and certs/ca.crt using Thonny.

# 2. Start infrastructure (separate terminals)
mosquitto -c mosquitto/mosquitto.conf -v
# MongoDB: running locally or: docker start mongo

# 3. Start the backend + dashboard
python tools/run_all.py                                 # gateway + API + log watcher + Streamlit
#   Dashboard: http://localhost:8501     Mini page: http://localhost:5000
# For an Odroid display, open the dashboard in the Odroid's local browser.

# 4. Test WITHOUT hardware first
python tools/fake_device.py --mode normal

# 5. Flash the real ESP32
# Open firmware_micropython/main.py in Thonny and upload it with the other
# required device files as described in START_HERE.md.
# Allow inbound TCP 8883 in the host firewall. Stop fake_device before the board runs.
```

---

## 13. Acceptance Checks (the agent must run these and report PASS/FAIL)

1. `openssl s_client -connect <BROKER_HOST>:8883 -CAfile certs/ca.crt` shows a verified certificate.
2. Anonymous publish is rejected: `mosquitto_pub -h <ip> -p 8883 --cafile certs/ca.crt -t test -m hi` fails.
3. `fake_device.py --mode normal` -> readings appear in MongoDB and in `/api/latest`, and in Streamlit.
4. Modes `heat`, `open`, `shake` each produce the expected alert type within 20 s.
5. `badhmac`, `replay` and `badfw` readings are **not** stored as valid readings, and alerts appear.
6. `badpass` produces `AUTH_FAIL`; `bruteforce` produces `BRUTE_FORCE`.
7. A high-severity alert makes the gateway publish a signed `alarm` command, and `fake_device` (or the ESP32) accepts it. A command with a bad signature is rejected by the device.
8. `GET /api/health`, `/api/readings`, `/api/alerts`, `/api/stats` all return valid JSON.
9. Stopping the device (unplug, or Ctrl+C on fake_device) triggers `DEVICE_OFFLINE`.
10. No secret (`.env`, `*.key`, `secrets.h`) is tracked by git.

---

## 14. Demo Script for the Presentation (about 6 minutes)

| Step | Action | What the audience sees | Say |
|---|---|---|---|
| 1 | Show the wired ESP32 and Serial Monitor | Live values and `[PUB]` lines | "Three sensors on one ESP32, publishing every 5 seconds over MQTT with TLS" |
| 2 | Open the Streamlit dashboard | Live KPIs and charts, ONLINE badge | "Data flows ESP32 -> broker -> gateway -> MongoDB -> Flask API -> Streamlit" |
| 3 | Move an object into the IR sensor path at the protected opening | `INTRUSION_IR` alert, onboard LED turns on | "The IR sensor detected a change at the protected opening. The gateway sent a signed alarm command back" |
| 4 | Tap or tilt the box with the MPU6050 mounted on it | `TAMPER_MOTION` alert | "The accelerometer/gyroscope detected repeated movement" |
| 5 | Breathe on or warm the DHT22 | `TEMP_ANOMALY` appears on chart | "Z-score above 3 against a rolling window" |
| 6 | Run `fake_device.py --mode badhmac` and `--mode replay` | Rejected, red alerts | "Forged and replayed messages are rejected and logged as intrusions" |
| 7 | Run `fake_device.py --mode bruteforce` | `BRUTE_FORCE` alert | "The IDS correlates failed logins" |
| 8 | Change `FW_VERSION`, re-flash | `FW_MISMATCH` alert | "The gateway detects an unrecognized firmware version fingerprint" |
| 9 | Show Wireshark filtered to port 8883 | Encrypted TLS application data | "An attacker on the network sees only ciphertext" |
| 10 | Show the mini jQuery page and the architecture/XaaS slide | | "Same API serves a plain HTML/jQuery client" |

---

## 15. Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| ESP32 prints `TLS connect failed` | Host IP not in cert SAN, wrong time, or wrong CA | Regenerate certs for the current host IP, upload the new CA to the ESP32, and check the NTP sync log line |
| Broker unreachable | Firewall or client isolation | Open TCP 8883, use a phone hotspot |
| DHT returns NaN | Missing pull-up, loose wire, wrong `DHTTYPE` | Check pin 4 and the 10k pull-up, set DHT11 vs DHT22 correctly |
| IR never triggers `INTRUSION_IR` | Wrong active polarity, aim, or sensor sensitivity | Check raw `ir`, adjust `IR_ACTIVE_LEVEL`, aim it across the opening |
| MPU6050 not detected | Wrong I2C wiring or address | Check SDA GPIO 21, SCL GPIO 22, common ground, and address `0x68`/`0x69` |
| Motion alerts fire continuously or never fire | MPU thresholds inappropriate for mounting/usage | Secure the MPU6050 and tune motion thresholds in `config.py` |
| Every message shows `BAD_HMAC` | Key mismatch or number formatting | Re-run `gen_secrets.py` and re-flash; check `%.1f` formatting on both sides |
| `REPLAY` alerts on a healthy device | Laptop clock off by more than 60 s, or ESP32 NTP not synced | Sync laptop time, check NTP |
| MQTT messages truncated or dropped | PubSubClient default buffer is 256 bytes | `client.setBufferSize(512)` |

---

## 16. Report Outline (suggested)

1. Abstract and problem statement
2. Objectives
3. System architecture (diagram from section 2) and layer description
4. Hardware design: BOM, GPIO table, wiring diagram, sensor datasheet notes
5. Communication design: protocol comparison table (HTTP vs MQTT vs CoAP, TCP vs UDP, TLS vs DTLS), topics and payloads
6. Security design: threat model, controls, key and certificate management, secure boot discussion
7. Software design: firmware flow chart, gateway pipeline, database schema, API table, UI screenshots
8. Analytics: anomaly detection method (z-score formula, thresholds, baseline learning), results
9. Testing and results: acceptance checks, attack demonstrations, screenshots
10. Cloud and XaaS deployment mapping
11. Limitations (pre-shared key stored in flash, version-derived firmware fingerprint is not a flash measurement, single device) and future work (flash encryption and secure boot on production boards, mutual TLS with per-device certificates, OTA with signed images, CoAP over DTLS, ML-based anomaly detection)
12. Conclusion and references
