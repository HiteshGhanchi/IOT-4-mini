# SecureBox demo copy on the BeagleY-AI

Run this presentation copy on the Beagle itself:

```bash
cd ~/Documents/SecureBox
/usr/bin/python3 run_securebox.py
```

The program reads:

- BMP280/BME280 through Linux IIO on I2C: SDA pin 3, SCL pin 5
- HC-SR04 TRIG on physical pin 11 and ECHO on physical pin 13
- Digital vibration `DO` on physical pin 15

It prints readings and threshold alerts every five seconds and writes
`readings_mqtt.csv` beside the code. Demo fallback is disabled by default;
BMP280 failures are reported as unavailable. Stop it with Ctrl+C.

For MQTT, install and start the local broker and Python client once:

```bash
sudo apt update
sudo apt install mosquitto mosquitto-clients python3-paho-mqtt openssl
sudo systemctl enable --now mosquitto
cd ~/Documents/SecureBox
sudo sh setup_mqtt_tls.sh
```

Preserve the GPIO values in the existing `config.py`, and add/update these
settings before launching:

```python
BMP280_DEMO_FALLBACK_ENABLED = False
BMP280_DEMO_TEMPERATURE_C = 29.5
BMP280_IIO_DEVICE = ""
CSV_FILE = "readings_mqtt.csv"
MQTT_ENABLED = True
MQTT_BROKER_HOST = "127.0.0.1"
MQTT_BROKER_PORT = 8883
MQTT_TOPIC = "securebox/sensors"
MQTT_CLIENT_ID = "securebox-beagle"
MQTT_QOS = 1
MQTT_PUBLISH_TIMEOUT_SECONDS = 5
MQTT_TLS_ENABLED = True
MQTT_TLS_CA_CERT = "/etc/mosquitto/certs/securebox/ca.crt"
```

In another terminal, watch messages while the app runs:

```bash
mosquitto_sub --cafile /etc/mosquitto/certs/securebox/ca.crt -h 127.0.0.1 -p 8883 -t securebox/sensors -v
```

Messages identify BMP280/BME280 readings as `sensor`, `demo`, or `unavailable`.
The demo fallback also includes the sensor's read error for transparent
demonstration. The app prints `[TLS] VERIFIED` with the negotiated protocol
and cipher after it validates the broker certificate.

The current BeagleY-AI configuration uses `/dev/gpiochip2` for `main_gpio0`
and `/dev/gpiochip3` for `main_gpio1`. Check `gpiodetect` if the OS image is
changed. GPIO inputs are 3.3 V only. HC-SR04 ECHO must be level-shifted when
the sensor is powered at 5 V.

For the environmental sensor, connect its `VCC/VIN` to 3.3 V, `GND` to ground,
`SDA` to physical pin 3, and `SCL` to physical pin 5. No series resistor is
required on a normal 3.3 V breakout. Use 5 V only if the module explicitly
supports regulated 5 V input. A BMP280 does not measure humidity; use BME280
if humidity is required.

Check the sensor directly with:

```bash
i2cdetect -y 1
cat /sys/bus/iio/devices/iio:device*/name
cat /sys/bus/iio/devices/iio:device*/in_temp_input
cat /sys/bus/iio/devices/iio:device*/in_pressure_input
```

Values are milli-units, for example `25000` means 25 C and `55000` means 55%.
