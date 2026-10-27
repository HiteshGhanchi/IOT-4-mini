# SecureBox on BeagleY-AI (Linux + Thonny)

This replaces the old ESP32/MicroPython instructions. The BeagleY-AI itself
runs Linux Python 3 and reads the sensors through its 40-pin header. There is
no ESP32 and no firmware flashing/upload step.

## Architecture

```text
DHT11/DHT22 -- Linux DHT IIO driver --+
HC-SR04 ------------------------------+--> BeagleY-AI (Debian + Python)
Digital vibration module -------------+        |-- Thonny Shell
                                               +-- readings.csv
```

This starter stage is local-only: live readings, threshold alerts, and a
CSV log. MQTT, a gateway, a database, and a dashboard are deliberately not
required; the workspace does not currently contain those backend programs.

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
sudo apt install python3-thonny python3-libgpiod gpiod
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
BeagleY-AI Debian/kernel image. Until that is enabled, the script clearly
reports unavailable temperature/humidity and continues logging the other
sensors. It does not fabricate readings.

## Run from Thonny

1. Copy `config.py.example` to `config.py`.
2. Verify the chip paths, active level, and physical sensor models in
   `config.py`.
3. Open `main.py` in Thonny running on the BeagleY-AI.
4. Choose the board's system Python 3 interpreter and press **Run**.
5. Watch sensor readings and alerts in the Shell. Stop with **Ctrl+C**.
6. Open `firmware_beagley_ai/readings.csv` for the recorded data.

The script samples every 5 seconds by default. Thresholds and CSV location are
in `config.py`.

## Troubleshooting

- `Python libgpiod is missing`: install `python3-libgpiod` and select system
  Python in Thonny.
- `This starter uses libgpiod v1`: use the Debian package, not the pip v2 API.
- GPIO line busy or invalid: verify the chip-to-controller mapping and that
  the header pin is muxed as GPIO and not owned by another device.
- DHT IIO device not found: check the DHT driver/device-tree setup above.
- HC-SR04 always says no echo: verify TRIG/ECHO, common ground, object range,
  and that the divider is installed in the ECHO path.
- Vibration never changes: verify the module has a digital `DO/OUT` pin and
  set `VIBRATION_ACTIVE_LEVEL` to match its output polarity.

Official references:

- [BeagleY-AI documentation](https://docs.beagleboard.org/boards/beagley/ai/)
- [BeagleY-AI pinout](https://pinout.beagley.ai/)
