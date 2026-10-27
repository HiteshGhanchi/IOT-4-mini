# SecureBox demo copy on the BeagleY-AI

Run this presentation copy on the Beagle itself:

```bash
cd ~/Documents/SecureBox
/usr/bin/python3 run_securebox.py
```

The program reads:

- DHT11/DHT22 through Linux IIO on physical header pin 7
- HC-SR04 TRIG on physical pin 11 and ECHO on physical pin 13
- Digital vibration `DO` on physical pin 15

It prints readings and threshold alerts every five seconds and writes
`readings.csv` beside the code. Stop it with Ctrl+C.

The current BeagleY-AI configuration uses `/dev/gpiochip2` for `main_gpio0`
and `/dev/gpiochip3` for `main_gpio1`. Check `gpiodetect` if the OS image is
changed. GPIO inputs are 3.3 V only. HC-SR04 ECHO must be level-shifted when
the sensor is powered at 5 V.

For the DHT module, connect `VCC` to 3.3 V, `DATA` to physical pin 7, and
`GND` to physical pin 6. The DHT device-tree overlay is already installed and
enabled on this board. A valid read can be tested directly with:

```bash
cat /sys/bus/iio/devices/iio:device0/name
cat /sys/bus/iio/devices/iio:device0/in_temp_input
cat /sys/bus/iio/devices/iio:device0/in_humidityrelative_input
```

Values are milli-units, for example `25000` means 25 C and `55000` means 55%.
