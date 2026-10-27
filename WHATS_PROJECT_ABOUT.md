# What is SecureBox?

SecureBox is a local monitor for a storage box/cabinet. In the current
hardware version, a **BeagleY-AI running Linux** reads a DHT temperature and
humidity sensor, an ultrasonic distance sensor, and a digital vibration
sensor directly from its GPIO header.

```text
DHT (Linux IIO) ----+
Ultrasonic GPIO ----+--> BeagleY-AI / Python 3
Vibration GPIO -----+        |-- Thonny Shell readings and alerts
                            +-- local CSV history
```

There is no ESP32 in this architecture. Thonny runs Python on the
BeagleY-AI; this is not MicroPython firmware and is not uploaded to a
microcontroller.

## Current implementation

- [START_HERE.md](./START_HERE.md) — quick wiring and setup.
- [firmware_beagley_ai/main.py](./firmware_beagley_ai/main.py) — Linux Python
  reader for the sensors, local alerts, and CSV logging.
- [firmware_beagley_ai/config.py.example](./firmware_beagley_ai/config.py.example)
  — configurable GPIO chip paths, line offsets, and thresholds.
- [firmware_beagley_ai/README_THONNY.md](./firmware_beagley_ai/README_THONNY.md)
  — full BeagleY-AI/Thonny guide.

Ultrasonic and digital vibration sensors use the BeagleY-AI GPIO header through
libgpiod. DHT11/22 uses Linux's DHT IIO kernel driver so that sensor pulse
timing is handled by the kernel instead of Python userspace. If the installed
OS image does not expose a DHT IIO device, its kernel/Device Tree setup must
be completed; the application reports missing DHT data rather than inventing
values.

The current first stage prints readings and threshold alerts in Thonny and
appends them to CSV. MQTT security, gateway, database, API, and dashboard
components are not present in this workspace and are intentionally not
required to test the sensors.

## Hardware safety and assumptions

The wiring guide assumes DHT11/22, HC-SR04, and a digital-output vibration
module (for example SW-420). Exact module variants still need to be checked.
BeagleY-AI GPIO is 3.3 V logic. In particular, HC-SR04 ECHO is 5 V and needs
a resistor divider/level shifter; never connect it directly to the board.
An analog-only vibration sensor needs an ADC rather than a GPIO input.

See [SECUREBOX_PROJECT.md](./SECUREBOX_PROJECT.md) for the original ESP32
target specification. Its ESP32 pin map and firmware sections are historical
and must not be used for this BeagleY-AI setup.
