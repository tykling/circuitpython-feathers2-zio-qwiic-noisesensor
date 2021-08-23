import json
import os
import ssl
import time

import adafruit_minimqtt.adafruit_minimqtt as MQTT
import adafruit_requests
import board
import feathers2
import microcontroller
import socketpool
import wifi
from microcontroller import watchdog as w
from watchdog import WatchDogMode

from config import Config

VERSION = "2.3"
UPDATEURL = "https://raw.githubusercontent.com/tykling/circuitpython-feathers2-zio-qwiic-noisesensor/main/code.py"

# configure watchdog
w.timeout = 10
w.mode = WatchDogMode.RESET
w.feed()

# initiate I2C
i2c = board.I2C()

# Create a socket pool
pool = socketpool.SocketPool(wifi.radio)

# prepare requests
requests = adafruit_requests.Session(pool, ssl.create_default_context())

def check_for_update():
    print("Checking for updates at %s" % UPDATEURL)
    new_code = requests.get(UPDATEURL)
    with open("/code.py") as f:
        current_code = f.read()

    if new_code.text != current_code:
        # write the new code to storage
        with open("/new_code.py", "w") as f:
            f.write(new_code.text)
        # switch to using the new code
        os.rename("/code.py", "/old_code.py")
        os.rename("/new_code.py", "/code.py")
        print("wrote new code to /code.py and saved the old in old_code.py, rebooting")
        # reboot so we start using the new code
        microcontroller.reset()
    else:
        print("current /code.py is identical with the one on github, no update needed")
        return time.time()


def connect_wifi():
    wifi.radio.connect(Config.wifi_ssid)
    print("got wifi IP: %s" % wifi.radio.ipv4_address)


def connected(client, userdata, flags, rc):
    print("Connected to mqtt")


def disconnected(client, userdata, rc):
    print("Disconnected from mqtt")


def message(client, topic, message):
    print("New message on topic {0}: {1}".format(topic, message))

def blink_led():
    feathers2.led_set(True)
    time.sleep(0.1)
    feathers2.led_set(False)

connect_wifi()

# do an initial update check
updatetime = check_for_update()

# Set up a MiniMQTT Client
mqtt_client = MQTT.MQTT(
    broker=Config.mqtt_broker_hostname,
    port=Config.mqtt_broker_port,
    socket_pool=pool,
    ssl_context=ssl.create_default_context(),
)

# Setup the callback methods above
mqtt_client.on_connect = connected
mqtt_client.on_disconnect = disconnected
mqtt_client.on_message = message

# Connect the client to the MQTT broker.
print("Connecting to mqtt broker...")
mqtt_client.connect()

noiselevel = bytearray(2)
sendtime = 0
readings = []
try:
    while True:
        # check for updates?
        if time.time() > updatetime + 3600:
            # more than an hour has passed
            updatetime = check_for_update()
        # get sensor value
        while not i2c.try_lock():
            pass
        i2c.writeto_then_readfrom(0x38, bytearray([0x05]), noiselevel)
        i2c.unlock()
        value = noiselevel[1] << 8 | noiselevel[0]
        readings.append(value)
        # print("got raw value: %s which is decimal %s" % (noiselevel, value))

        # is it time to send?
        if time.time() > sendtime + Config.send_interval_seconds:
            message = {
                "metadata": {
                    "version": VERSION,
                },
                "min": min(readings),
                "max": max(readings),
                "avg": sum(readings) / len(readings),
                "readings": readings,
                "noiselevel": max(readings),
            }
            if not mqtt_client.ping():
                print("not connected to mqtt, rebooting")
                microcontroller.reset()
            print("sending message to mqtt: %s" % message)
            mqtt_client.publish(Config.mqtt_topic, json.dumps(message))

            # record time and reset readings
            sendtime = time.time()
            readings = []

        # feed the dog, blink the LED, and sleep for a bit
        w.feed()
        blink_led()
        time.sleep(Config.sensor_interval_seconds)
except Exception as E:
    print("got exception, rebooting in 5s: %s" % E)
    time.sleep(5)
    microcontroller.reset()
