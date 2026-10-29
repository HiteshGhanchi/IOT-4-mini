"""Read BeagleY-AI GPIO sensors and log readings for the SecureBox demo.

Runs with Linux Python 3. HC-SR04 and vibration inputs use libgpiod. Both
the Debian v1 and v2 Python APIs are supported. BMP280/BME280 temperature,
pressure, and optional humidity are read through Linux IIO.
"""

import csv
import glob
import json
import os
import ssl
import sys
import time
from datetime import datetime

import config


IIO_ROOT = "/sys/bus/iio/devices"
IIO_TEMPERATURE_FILE = "in_temp_input"
IIO_PRESSURE_FILE = "in_pressure_input"
IIO_HUMIDITY_FILE = "in_humidityrelative_input"
CSV_HEADER = [
    "timestamp", "temperature_c", "pressure_hpa", "humidity_percent",
    "bmp280_source", "bmp280_error", "distance_cm", "vibration", "alerts",
]


def _find_bmp280_device():
    configured = getattr(config, "BMP280_IIO_DEVICE", "")
    if configured:
        device = configured
        if not os.path.isfile(os.path.join(device, IIO_TEMPERATURE_FILE)):
            raise RuntimeError(
                "BMP280_IIO_DEVICE does not contain " + IIO_TEMPERATURE_FILE
            )
        return device

    for name_file in sorted(glob.glob(os.path.join(IIO_ROOT, "iio:device*", "name"))):
        device = os.path.dirname(name_file)
        try:
            with open(name_file, "r", encoding="ascii") as source:
                name = source.read().strip().lower()
        except OSError:
            continue
        if ("bmp280" in name or "bme280" in name) and os.path.isfile(
            os.path.join(device, IIO_TEMPERATURE_FILE)
        ):
            return device
    return None


def _read_iio_value(device, filename, scale=1000.0):
    with open(os.path.join(device, filename), "r", encoding="ascii") as source:
        return float(source.read().strip()) / scale


def _read_bmp280(device):
    if device is None:
        return None, None, None
    temperature = _read_iio_value(device, IIO_TEMPERATURE_FILE)
    pressure = None
    pressure_path = os.path.join(device, IIO_PRESSURE_FILE)
    if os.path.isfile(pressure_path):
        # IIO pressure data is in kPa; convert it to hPa.
        pressure = _read_iio_value(device, IIO_PRESSURE_FILE, 1.0) * 10.0
    humidity = None
    humidity_path = os.path.join(device, IIO_HUMIDITY_FILE)
    if os.path.isfile(humidity_path):
        humidity = _read_iio_value(device, IIO_HUMIDITY_FILE)
    return temperature, pressure, humidity


def _apply_bmp280_fallback(temperature, pressure, humidity, error=None):
    if temperature is not None:
        return temperature, pressure, humidity, "sensor", error
    if getattr(config, "BMP280_DEMO_FALLBACK_ENABLED", False):
        return config.BMP280_DEMO_TEMPERATURE_C, None, None, "demo", error
    return None, None, None, "unavailable", error


def _mqtt_payload(timestamp, temperature, pressure, humidity, bmp280_source,
                  bmp280_error, distance_cm, vibration, alerts):
    return json.dumps(
        {
            "timestamp": timestamp,
            "temperature_c": temperature,
            "pressure_hpa": pressure,
            "humidity_percent": humidity,
            "bmp280_source": bmp280_source,
            "bmp280_error": bmp280_error,
            "dht_source": bmp280_source,
            "dht_error": bmp280_error,
            "distance_cm": distance_cm,
            "vibration": vibration,
            "alerts": alerts,
        },
        separators=(",", ":"),
    )


class MqttPublisher:
    def __init__(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as error:
            raise RuntimeError(
                "Python MQTT client is missing. Install the OS package "
                "'python3-paho-mqtt'."
            ) from error

        self._mqtt = mqtt
        if hasattr(mqtt, "CallbackAPIVersion"):
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=config.MQTT_CLIENT_ID,
            )
        else:
            self._client = mqtt.Client(client_id=config.MQTT_CLIENT_ID)
        if config.MQTT_TLS_ENABLED:
            self._client.tls_set(
                ca_certs=config.MQTT_TLS_CA_CERT,
                cert_reqs=ssl.CERT_REQUIRED,
            )
            print(
                "[TLS] enabled; verifying broker certificate with %s"
                % config.MQTT_TLS_CA_CERT
            )
        else:
            print("[TLS] DISABLED")
        self._tls_verified = not config.MQTT_TLS_ENABLED
        self._reported_tls_unverified = False
        self._client.on_connect = self._on_connect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._reported_disconnected = False
        print(
            "[MQTT] connecting to %s:%s, topic=%s"
            % (config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT,
               config.MQTT_TOPIC)
        )
        self._client.connect_async(
            config.MQTT_BROKER_HOST,
            config.MQTT_BROKER_PORT,
            keepalive=60,
        )
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if getattr(reason_code, "is_failure", reason_code != 0):
            self._tls_verified = False
            print("[MQTT] connection failed: %s" % reason_code)
            return

        print("[MQTT] connected")
        if config.MQTT_TLS_ENABLED:
            connection = client.socket()
            if connection is None or not connection.getpeercert():
                self._tls_verified = False
                print("[TLS] ERROR: broker certificate was not verified")
                return
            cipher = connection.cipher()
            self._tls_verified = True
            self._reported_tls_unverified = False
            print(
                "[TLS] VERIFIED | protocol=%s | cipher=%s"
                % (
                    connection.version(),
                    cipher[0] if cipher else "unknown",
                )
            )

    def publish(self, payload):
        if config.MQTT_TLS_ENABLED and not self._tls_verified:
            if not self._reported_tls_unverified:
                print("[MQTT] TLS peer not verified; sample not sent")
                self._reported_tls_unverified = True
            return

        if not self._client.is_connected():
            if not self._reported_disconnected:
                print("[MQTT] broker unavailable; reconnecting, sample not sent")
                self._reported_disconnected = True
            return

        self._reported_disconnected = False
        info = self._client.publish(
            config.MQTT_TOPIC,
            payload,
            qos=config.MQTT_QOS,
        )
        if info.rc != self._mqtt.MQTT_ERR_SUCCESS:
            print("[MQTT] publish rejected (error code %s)" % info.rc)
            return

        try:
            info.wait_for_publish(timeout=config.MQTT_PUBLISH_TIMEOUT_SECONDS)
        except RuntimeError as error:
            print("[MQTT] publish failed: %s" % error)
            return
        if not info.is_published():
            print("[MQTT] publish timed out; delivery not confirmed")
            return
        print("[MQTT] published to %s" % config.MQTT_TOPIC)

    def close(self):
        self._client.disconnect()
        self._client.loop_stop()


class BeagleGpio:
    def __init__(self):
        try:
            import gpiod
        except ImportError as error:
            raise RuntimeError(
                "Python libgpiod is missing. Install the OS package "
                "'python3-libgpiod' and use that system Python in Thonny."
            ) from error

        self._gpiod = gpiod
        self._gpiod_v2 = not hasattr(gpiod, "LINE_REQ_DIR_IN")

        self._main0 = None
        self._main1 = None
        self._trigger = None
        self._echo = None
        self._vibration = None
        self._trigger_request = None
        self._echo_request = None
        self._vibration_request = None

        try:
            self._main0 = gpiod.Chip(config.GPIO_CHIP_MAIN0)
            self._main1 = gpiod.Chip(config.GPIO_CHIP_MAIN1)

            if self._gpiod_v2:
                direction = gpiod.line.Direction
                value = gpiod.line.Value
                self._trigger_request = self._main1.request_lines(
                    consumer="securebox-ultrasonic-trigger",
                    config={
                        config.ULTRASONIC_TRIGGER_OFFSET: gpiod.LineSettings(
                            direction=direction.OUTPUT,
                            output_value=value.INACTIVE,
                        )
                    },
                )
                self._echo_request = self._main0.request_lines(
                    consumer="securebox-ultrasonic-echo",
                    config={
                        config.ULTRASONIC_ECHO_OFFSET: gpiod.LineSettings(
                            direction=direction.INPUT,
                        )
                    },
                )
                self._vibration_request = self._main0.request_lines(
                    consumer="securebox-vibration",
                    config={
                        config.VIBRATION_OFFSET: gpiod.LineSettings(
                            direction=direction.INPUT,
                        )
                    },
                )
            else:
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
        if self._gpiod_v2:
            return (
                self._vibration_request.get_value(config.VIBRATION_OFFSET)
                == (
                    self._gpiod.line.Value.ACTIVE
                    if config.VIBRATION_ACTIVE_LEVEL
                    else self._gpiod.line.Value.INACTIVE
                )
            )
        return self._vibration.get_value() == config.VIBRATION_ACTIVE_LEVEL

    def read_distance_cm(self):
        if self._gpiod_v2:
            inactive = self._gpiod.line.Value.INACTIVE
            active = self._gpiod.line.Value.ACTIVE
            set_trigger = lambda value: self._trigger_request.set_value(
                config.ULTRASONIC_TRIGGER_OFFSET, value
            )
            read_echo = lambda: (
                self._echo_request.get_value(config.ULTRASONIC_ECHO_OFFSET)
                == active
            )
        else:
            inactive = 0
            active = 1
            set_trigger = self._trigger.set_value
            read_echo = lambda: self._echo.get_value() == 1

        set_trigger(inactive)
        time.sleep(0.000002)
        set_trigger(active)
        time.sleep(0.000010)
        set_trigger(inactive)

        timeout_ns = int(config.ECHO_TIMEOUT_SECONDS * 1_000_000_000)
        wait_started = time.monotonic_ns()
        while not read_echo():
            if time.monotonic_ns() - wait_started >= timeout_ns:
                return None

        pulse_started = time.monotonic_ns()
        while read_echo():
            if time.monotonic_ns() - pulse_started >= timeout_ns:
                return None
        pulse_seconds = (time.monotonic_ns() - pulse_started) / 1_000_000_000
        return pulse_seconds * 34300.0 / 2.0

    def close(self):
        for request in (
            self._vibration_request,
            self._echo_request,
            self._trigger_request,
        ):
            if request is not None:
                try:
                    request.release()
                except OSError:
                    pass
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
    if not needs_header:
        with open(path, "r", newline="", encoding="utf-8") as source:
            existing_header = next(csv.reader(source), [])
        if existing_header != CSV_HEADER:
            raise RuntimeError(
                "CSV header in %s is from an older format. Preserve the old "
                "file and set CSV_FILE in config.py to a new filename."
                % path
            )
    with open(path, "a", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        if needs_header:
            writer.writerow(CSV_HEADER)
        writer.writerow(row)


def main():
    bmp280_device = _find_bmp280_device()
    if bmp280_device is None:
        print(
            "[BMP280] No BMP280/BME280 IIO device found; checking the "
            "configured demo fallback."
        )
    else:
        print("[BMP280] IIO device: %s" % bmp280_device)

    gpio = BeagleGpio()
    mqtt_publisher = None
    try:
        if config.MQTT_ENABLED:
            mqtt_publisher = MqttPublisher()
        csv_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), config.CSV_FILE
        )
        print("[GPIO] ready; writing readings to %s" % csv_path)
        print("Press Ctrl+C in Thonny to stop.")

        while True:
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            bmp280_error = None
            try:
                temperature, pressure, humidity = _read_bmp280(bmp280_device)
            except (OSError, ValueError) as error:
                temperature, pressure, humidity = None, None, None
                bmp280_error = "%s: %s" % (type(error).__name__, error)

            temperature, pressure, humidity, bmp280_source, bmp280_error = (
                _apply_bmp280_fallback(
                    temperature, pressure, humidity, bmp280_error
                )
            )
            if bmp280_source == "demo":
                print(
                    "[BMP280] SENSOR VALUE UNAVAILABLE; using demo fallback "
                    "%.1f C (not a sensor measurement)%s"
                    % (
                        temperature,
                        ": " + bmp280_error if bmp280_error else "",
                    )
                )
            elif bmp280_source == "unavailable":
                print(
                    "[BMP280] reading unavailable%s"
                    % (": " + bmp280_error if bmp280_error else "")
                )
            if humidity is None:
                print("[BMP280] humidity unavailable: BMP280 does not measure humidity")

            distance_cm = gpio.read_distance_cm()
            if distance_cm is None:
                print("[ULTRASONIC] no echo; check wiring and sensor range")

            vibration = gpio.read_vibration()
            alerts = _alerts(temperature, humidity, distance_cm, vibration)
            distance_text = "--" if distance_cm is None else "%.1f cm" % distance_cm
            temp_text = "--" if temperature is None else "%.1f C" % temperature
            pressure_text = "--" if pressure is None else "%.1f hPa" % pressure
            humidity_text = "--" if humidity is None else "%.1f%%" % humidity
            alert_text = ", ".join(alerts) if alerts else "none"
            if bmp280_source == "demo":
                temp_text += " (DEMO)"

            print(
                "%s | temp=%s pressure=%s hum=%s bmp280_source=%s distance=%s "
                "vibration=%s | alerts=%s"
                % (timestamp, temp_text, pressure_text, humidity_text,
                   bmp280_source, distance_text,
                   "YES" if vibration else "no", alert_text)
            )
            _append_csv(
                csv_path,
                [
                    timestamp,
                    "" if temperature is None else "%.2f" % temperature,
                    "" if pressure is None else "%.2f" % pressure,
                    "" if humidity is None else "%.2f" % humidity,
                    bmp280_source,
                    bmp280_error or "",
                    "" if distance_cm is None else "%.2f" % distance_cm,
                    int(vibration),
                    "; ".join(alerts),
                ],
            )
            if mqtt_publisher is not None:
                mqtt_publisher.publish(
                    _mqtt_payload(
                        timestamp,
                        temperature,
                        pressure,
                        humidity,
                        bmp280_source,
                        bmp280_error,
                        distance_cm,
                        vibration,
                        alerts,
                    )
                )
            time.sleep(config.SAMPLE_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping SecureBox reader.")
    finally:
        gpio.close()
        if mqtt_publisher is not None:
            mqtt_publisher.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("[ERROR] %s" % error, file=sys.stderr)
        raise
