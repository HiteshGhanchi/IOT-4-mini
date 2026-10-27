"""Read BeagleY-AI GPIO sensors and log readings for the SecureBox demo.

Runs with Linux Python 3. HC-SR04 and vibration inputs use libgpiod v1.
The DHT sensor is read through the Linux IIO DHT11/DHT22 kernel driver, which
handles the sensor's timing-sensitive signal outside Python userspace.
"""

import csv
import glob
import os
import sys
import time
from datetime import datetime

import config


IIO_ROOT = "/sys/bus/iio/devices"
IIO_TEMPERATURE_FILE = "in_temp_input"
IIO_HUMIDITY_FILE = "in_humidityrelative_input"


def _find_dht_device():
    if config.DHT_IIO_DEVICE:
        device = config.DHT_IIO_DEVICE
        if not os.path.isfile(os.path.join(device, IIO_TEMPERATURE_FILE)):
            raise RuntimeError(
                "DHT_IIO_DEVICE does not contain " + IIO_TEMPERATURE_FILE
            )
        return device

    for name_file in sorted(glob.glob(os.path.join(IIO_ROOT, "iio:device*", "name"))):
        device = os.path.dirname(name_file)
        try:
            with open(name_file, "r", encoding="ascii") as source:
                name = source.read().strip().lower()
        except OSError:
            continue
        if ("dht" in name and
                os.path.isfile(os.path.join(device, IIO_TEMPERATURE_FILE)) and
                os.path.isfile(os.path.join(device, IIO_HUMIDITY_FILE))):
            return device
    return None


def _read_iio_value(device, filename):
    with open(os.path.join(device, filename), "r", encoding="ascii") as source:
        # The Linux DHT IIO driver exposes temperature and relative humidity
        # in milli-units (for example 23500 = 23.5 C, 51000 = 51.0%).
        return int(source.read().strip()) / 1000.0


def _read_dht(device):
    if device is None:
        return None, None
    temperature = _read_iio_value(device, IIO_TEMPERATURE_FILE)
    humidity = _read_iio_value(device, IIO_HUMIDITY_FILE)
    return temperature, humidity


class BeagleGpio:
    def __init__(self):
        try:
            import gpiod
        except ImportError as error:
            raise RuntimeError(
                "Python libgpiod is missing. Install the OS package "
                "'python3-libgpiod' and use that system Python in Thonny."
            ) from error

        if not hasattr(gpiod, "LINE_REQ_DIR_IN"):
            raise RuntimeError(
                "This starter uses the libgpiod v1 Python API. Install the "
                "Debian python3-libgpiod package (v1), not the v2 pip API."
            )

        self._main0 = None
        self._main1 = None
        self._trigger = None
        self._echo = None
        self._vibration = None

        try:
            self._main0 = gpiod.Chip(config.GPIO_CHIP_MAIN0)
            self._main1 = gpiod.Chip(config.GPIO_CHIP_MAIN1)

            self._trigger = self._main1.get_line(config.ULTRASONIC_TRIGGER_OFFSET)
            self._trigger.request(
                consumer="securebox-ultrasonic-trigger",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_val=0,
            )

            self._echo = self._main0.get_line(config.ULTRASONIC_ECHO_OFFSET)
            self._echo.request(
                consumer="securebox-ultrasonic-echo",
                type=gpiod.LINE_REQ_DIR_IN,
            )

            self._vibration = self._main0.get_line(config.VIBRATION_OFFSET)
            self._vibration.request(
                consumer="securebox-vibration",
                type=gpiod.LINE_REQ_DIR_IN,
            )
        except Exception:
            self.close()
            raise

    def read_vibration(self):
        return self._vibration.get_value() == config.VIBRATION_ACTIVE_LEVEL

    def read_distance_cm(self):
        self._trigger.set_value(0)
        time.sleep(0.000002)
        self._trigger.set_value(1)
        time.sleep(0.000010)
        self._trigger.set_value(0)

        timeout_ns = int(config.ECHO_TIMEOUT_SECONDS * 1_000_000_000)
        wait_started = time.monotonic_ns()
        while self._echo.get_value() == 0:
            if time.monotonic_ns() - wait_started >= timeout_ns:
                return None

        pulse_started = time.monotonic_ns()
        while self._echo.get_value() == 1:
            if time.monotonic_ns() - pulse_started >= timeout_ns:
                return None
        pulse_seconds = (time.monotonic_ns() - pulse_started) / 1_000_000_000
        return pulse_seconds * 34300.0 / 2.0

    def close(self):
        for line in (self._vibration, self._echo, self._trigger):
            if line is not None:
                try:
                    line.release()
                except OSError:
                    pass
        for chip in (self._main1, self._main0):
            if chip is not None:
                try:
                    chip.close()
                except OSError:
                    pass


def _alerts(temperature, humidity, distance_cm, vibration):
    alerts = []
    if vibration:
        alerts.append("vibration detected")
    if distance_cm is not None and distance_cm <= config.DISTANCE_ALERT_CM:
        alerts.append("object within %.1f cm" % config.DISTANCE_ALERT_CM)
    if temperature is not None:
        if temperature < config.TEMPERATURE_MIN_C:
            alerts.append("temperature below limit")
        elif temperature > config.TEMPERATURE_MAX_C:
            alerts.append("temperature above limit")
    if humidity is not None and humidity > config.HUMIDITY_MAX_PERCENT:
        alerts.append("humidity above limit")
    return alerts


def _append_csv(path, row):
    needs_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        if needs_header:
            writer.writerow(
                ["timestamp", "temperature_c", "humidity_percent",
                 "distance_cm", "vibration", "alerts"]
            )
        writer.writerow(row)


def main():
    dht_device = _find_dht_device()
    if dht_device is None:
        print(
            "[DHT] No DHT IIO device found. Temperature/humidity will be "
            "blank until the Linux DHT11/DHT22 kernel driver is enabled and "
            "bound to the data GPIO."
        )
    else:
        print("[DHT] IIO device: %s" % dht_device)

    gpio = BeagleGpio()
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.CSV_FILE)
    print("[GPIO] ready; writing readings to %s" % csv_path)
    print("Press Ctrl+C in Thonny to stop.")

    try:
        while True:
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            try:
                temperature, humidity = _read_dht(dht_device)
            except (OSError, ValueError) as error:
                temperature, humidity = None, None
                print("[DHT] read failed: %s" % error)

            distance_cm = gpio.read_distance_cm()
            if distance_cm is None:
                print("[ULTRASONIC] no echo; check wiring and sensor range")

            vibration = gpio.read_vibration()
            alerts = _alerts(temperature, humidity, distance_cm, vibration)
            distance_text = "--" if distance_cm is None else "%.1f cm" % distance_cm
            temp_text = "--" if temperature is None else "%.1f C" % temperature
            humidity_text = "--" if humidity is None else "%.1f%%" % humidity
            alert_text = ", ".join(alerts) if alerts else "none"

            print(
                "%s | temp=%s hum=%s distance=%s vibration=%s | alerts=%s"
                % (timestamp, temp_text, humidity_text, distance_text,
                   "YES" if vibration else "no", alert_text)
            )
            _append_csv(
                csv_path,
                [
                    timestamp,
                    "" if temperature is None else "%.2f" % temperature,
                    "" if humidity is None else "%.2f" % humidity,
                    "" if distance_cm is None else "%.2f" % distance_cm,
                    int(vibration),
                    "; ".join(alerts),
                ],
            )
            time.sleep(config.SAMPLE_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping SecureBox reader.")
    finally:
        gpio.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("[ERROR] %s" % error, file=sys.stderr)
        raise
