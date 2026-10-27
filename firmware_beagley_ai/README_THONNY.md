# SecureBox on BeagleY-AI (Linux + Thonny)

This replaces the old ESP32/MicroPython instructions. The BeagleY-AI itself
runs Linux Python 3 and reads the sensors through its 40-pin header. There is
no ESP32 and no firmware flashing/upload step.

## Architecture

```text
DHT11/DHT22 -- Linux DHT IIO driver --+
HC-SR04 ------------------------------+--> BeagleY-AI (Debian + Python)
Digital vibration module -------------+        |-- Thonny Shell
                                               +-- readings_mqtt.csv
```

The BeagleY-AI reads sensors locally, prints threshold alerts, saves a CSV,
and can publish each sample to an MQTT broker. A separate gateway, database,
or dashboard is not required.

## Wiring (BeagleY-AI 40-pin header)

The pin numbers below are **physical header positions**. GPIO line offsets are
the SoC controller offsets used by Linux/libgpiod; do not substitute the
Raspberry Pi BCM number in Python.

| Sensor | Sensor pin | BeagleY-AI connection |
|---|---|---|
| DHT11/DHT22 | VCC | 3.3 V, physical pin 1 or 17 |
|  | DATA | physical pin 7 (GPIO4 / main_gpio0 line 38) |
|  | GND | physical pin 6, 9, or another GND |
| HC-SR04 | VCC | 5 V, physical pin 2 or 4 |
|  | GND | GND, common with BeagleY-AI |
|  | TRIG | physical pin 11 (GPIO17 / main_gpio1 line 8) |
|  | ECHO | physical pin 13 (GPIO27 / main_gpio0 line 33), **through a divider** |
| Digital vibration module | VCC | 3.3 V if supported by that module |
|  | GND | common GND |
|  | DO/OUT | physical pin 15 (GPIO22 / main_gpio0 line 41) |

Use the BeagleY-AI pinout to verify the physical orientation before wiring.
With the board's 40-pin header on the right and HDMI on the left, pin 1 is the
top pin in the odd-numbered column.

**Voltage safety**

- BeagleY-AI GPIO is 3.3 V logic. Never connect the HC-SR04's 5 V ECHO
  directly to the board.
- A simple divider for ECHO is: sensor ECHO -> 2 kOhm resistor -> GPIO node;
  GPIO node -> 3.3 kOhm resistor -> GND.
- Keep all grounds common.
- Power a vibration-module output at 3.3 V where its datasheet allows it. If
  powered from 5 V, verify/shift its OUT voltage before connecting it.
- Bare 4-pin DHT sensors need a 4.7-10 kOhm DATA-to-3.3 V pull-up. A module
  board may already include one.

The sensor models are not confirmed yet. The pinout above assumes DHT11/22,
HC-SR04, and a digital-output vibration module such as SW-420. Check the
markings/datasheets before applying power; analog-only vibration modules need
an ADC and cannot be read from a GPIO input.

## Prepare Debian and Thonny

Run on the BeagleY-AI:

```bash
sudo apt update
sudo apt install python3-thonny python3-libgpiod gpiod mosquitto mosquitto-clients python3-paho-mqtt openssl
sudo systemctl enable --now mosquitto
cd ~/Documents/SecureBox
sudo sh setup_mqtt_tls.sh
```

Use Thonny's **system Python 3** interpreter on the BeagleY-AI. Do not select
MicroPython, an ESP32 interpreter, or a local laptop interpreter: GPIO is
available only to a Python process running on the board.

Check which GPIO chip nodes are the AM67A controllers:

```bash
gpiodetect
gpioinfo /dev/gpiochip0
gpioinfo /dev/gpiochip1
```

Update `GPIO_CHIP_MAIN0` and `GPIO_CHIP_MAIN1` in `config.py` to match the
controllers named `main_gpio0` and `main_gpio1` on your image. If the names
or chip ordering differ, do not guess—use the controller names shown by
`gpioinfo`.

The program uses the Debian `python3-libgpiod` v1 API. If GPIO access fails
with a permission error, check the permissions on `/dev/gpiochip*` and grant
the logged-in user the board image's GPIO-device access; do not leave the
application running as root as a permanent workaround.

## DHT driver requirement

DHT signaling is timing-sensitive. Python polling on a general Linux process
can miss its short pulses, so this code intentionally reads DHT through the
Linux kernel's DHT11/DHT22 IIO driver rather than bit-banging in Thonny.

Check whether the image already exposes a DHT IIO device:

```bash
for f in /sys/bus/iio/devices/iio:device*/name; do
    [ -f "$f" ] && printf '%s: ' "$f" && cat "$f"
done
```

If a DHT device is present, the script discovers it automatically. If not,
the image needs the kernel `dht11` driver and a device-tree node for the DHT
data GPIO (physical pin 7). The exact overlay procedure depends on the
BeagleY-AI Debian/kernel image. Until that is enabled, the script reports
the failed sensor read. For presentations, `config.py` enables a clearly
labelled **simulated** 29.5 C temperature fallback by default; humidity
remains unavailable. This value is not measured by the sensor. Set
`DHT_DEMO_FALLBACK_ENABLED = False` to disable the fallback.

## MQTT demo

The first-time setup above installs Mosquitto and configures a TLS listener
bound only to `127.0.0.1:8883`. In `config.py`, use host `127.0.0.1`, port
`8883`, set `MQTT_TLS_ENABLED = True`, and set the trusted CA path to
`/etc/mosquitto/certs/securebox/ca.crt`. The example config has these values.
The demo publishes JSON every sampling interval to `securebox/sensors`.
Subscribe in a second terminal with certificate verification enabled:

```bash
mosquitto_sub --cafile /etc/mosquitto/certs/securebox/ca.crt -h 127.0.0.1 -p 8883 -t securebox/sensors -v
```

After connecting, the application prints `[TLS] VERIFIED` with the negotiated
protocol and cipher. It verifies the broker certificate; no insecure
verification bypass is used.
Each message includes `dht_source` (`sensor`, `simulated`, or `unavailable`)
and `dht_error`; when the demo fallback is used, `temperature_c` is 29.5 and
`humidity_percent` is `null`. Console output and the CSV also identify
simulated readings. The updated CSV includes source/error columns and is
written to `readings_mqtt.csv`, leaving an older `readings.csv` untouched.

This starter's broker is local to the board. To allow remote subscribers,
configure an authenticated TLS listener and certificates for the real
hostname; do not expose this local demo listener to the network.

## Run from Thonny

1. If `config.py` does not exist, copy `config.py.example` to `config.py`.
   Otherwise preserve its GPIO settings and add the DHT/MQTT settings from
   the example; set `CSV_FILE = "readings_mqtt.csv"` to keep the older CSV.
2. Verify the chip paths, active level, fallback label, and MQTT/TLS broker in
   `config.py`.
3. Open `main.py` in Thonny running on the BeagleY-AI.
4. Choose the board's system Python 3 interpreter and press **Run**.
5. Watch sensor readings and alerts in the Shell. Stop with **Ctrl+C**.
6. Open `firmware_beagley_ai/readings_mqtt.csv` for the recorded data.

The script samples every 5 seconds by default. Thresholds and CSV location are
in `config.py`.

## Troubleshooting

- `Python libgpiod is missing`: install `python3-libgpiod` and select system
  Python in Thonny.
- `This starter uses libgpiod v1`: use the Debian package, not the pip v2 API.
- GPIO line busy or invalid: verify the chip-to-controller mapping and that
  the header pin is muxed as GPIO and not owned by another device.
- DHT IIO device not found: check the DHT driver/device-tree setup above.
- Kernel log says `Only 70-79 signal edges detected`: the DHT response is
  incomplete, so no temperature/humidity can be decoded. Check DATA on
  physical pin 7, common ground, 3.3 V power, the DATA pull-up (4.7-10 kOhm
  for a bare sensor), sensor type, and short wiring. This is a signal/wiring
  issue; the demo fallback does not repair the sensor reading.
- HC-SR04 always says no echo: verify TRIG/ECHO, common ground, object range,
  and that the divider is installed in the ECHO path.
- Vibration never changes: verify the module has a digital `DO/OUT` pin and
  set `VIBRATION_ACTIVE_LEVEL` to match its output polarity.

Official references:

- [BeagleY-AI documentation](https://docs.beagleboard.org/boards/beagley/ai/)
- [BeagleY-AI pinout](https://pinout.beagley.ai/)
