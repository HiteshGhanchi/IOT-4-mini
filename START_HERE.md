# SecureBox: BeagleY-AI setup

The active hardware target is **BeagleY-AI running Linux**. The sensors wire
directly to the BeagleY-AI GPIO header; there is no ESP32.

## Architecture

```text
DHT11/DHT22 -- Linux IIO sensor driver --+
HC-SR04 ----------------------------------+--> BeagleY-AI (Debian + Python)
Digital vibration sensor ----------------+        |-- Console + CSV
                                                   +-- MQTT over TLS --> Mosquitto
```

For complete first-time setup, MQTT/TLS instructions, and the two-terminal
demo, start with the root [README.md](./README.md). The longer hardware and
Thonny guide is [firmware_beagley_ai/README_THONNY.md](./firmware_beagley_ai/README_THONNY.md).

## Wiring

This example assumes DHT11/22, HC-SR04, and a digital vibration module such as
SW-420. The sensor models are not confirmed—check the markings and datasheets
before connecting power.

| Sensor pin | BeagleY-AI header |
|---|---|
| DHT VCC | 3.3 V, physical pin 1 or 17 |
| DHT DATA | physical pin 7 (GPIO4; SoC main_gpio0 line 38) |
| DHT GND | GND |
| HC-SR04 VCC | 5 V, physical pin 2 or 4 |
| HC-SR04 TRIG | physical pin 11 (GPIO17; main_gpio1 line 8) |
| HC-SR04 ECHO | physical pin 13 (GPIO27; main_gpio0 line 33), via divider |
| HC-SR04 GND | GND |
| Vibration VCC | 3.3 V if the module supports it |
| Vibration DO/OUT | physical pin 15 (GPIO22; main_gpio0 line 41) |
| Vibration GND | GND |

All grounds must be common. GPIO uses 3.3 V logic: **never connect a 5 V
HC-SR04 ECHO directly to the BeagleY-AI**. Use a divider: sensor ECHO -> 2 kOhm
resistor -> GPIO node; GPIO node -> 3.3 kOhm resistor -> GND. If the vibration
board is powered at 5 V, confirm its output is 3.3 V safe or add level
shifting. A bare 4-pin DHT needs a 4.7-10 kOhm DATA-to-3.3 V pull-up.

## Install and run

On the BeagleY-AI Debian system:

```bash
sudo apt update
sudo apt install python3-thonny python3-libgpiod gpiod mosquitto mosquitto-clients python3-paho-mqtt openssl
sudo systemctl enable --now mosquitto
cd ~/Documents/SecureBox
sudo sh setup_mqtt_tls.sh
```

1. Copy `firmware_beagley_ai/config.py.example` to
   `firmware_beagley_ai/config.py`.
2. Run `gpiodetect` and `gpioinfo /dev/gpiochip0` / `gpioinfo /dev/gpiochip1`.
   Set `GPIO_CHIP_MAIN0` and `GPIO_CHIP_MAIN1` to the actual controller device
   paths shown for `main_gpio0` and `main_gpio1`.
3. Run Thonny **on the BeagleY-AI** and select its system Python 3 interpreter.
   The code does not get flashed to a microcontroller.
4. Open `firmware_beagley_ai/main.py` and press **Run**. Readings/alerts appear
   in the Shell; the CSV is written beside `main.py`. Stop with Ctrl+C.

The GPIO starter uses Debian's libgpiod v1 API. The DHT is read using the
Linux DHT11/DHT22 IIO kernel driver because Python userspace timing is not
reliable enough for DHT pulse decoding. If the OS image has not enabled that
driver and a device-tree node for the DHT DATA GPIO, temperature/humidity
will be reported unavailable; ultrasonic and vibration logging continue.
The exact DHT overlay depends on the installed Debian/kernel image.

See [firmware_beagley_ai/README_THONNY.md](./firmware_beagley_ai/README_THONNY.md)
for the full pin guide, setup checks, and troubleshooting.

## Run the dashboard on the board

With the Mosquitto broker and sensor program configured, open two terminals.

Terminal 1:

```bash
cd ~/Documents/SecureBox/firmware_beagley_ai
/usr/bin/python3 run_securebox.py
```

Terminal 2:

```bash
cd ~/Documents/SecureBox/dashboard
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py
```

Then open `http://127.0.0.1:5000` on the board. Sign in with `admin` /
`securebox`, and replace those development credentials before deployment. To
open it from another computer on the same network, run `hostname -I` on the
board and visit `http://BOARD-IP:5000`.

Dashboard messages are currently published to `securebox/commands`. The sensor
program does not yet process that topic, so device actions require a command
subscriber to be added before those controls can work.
