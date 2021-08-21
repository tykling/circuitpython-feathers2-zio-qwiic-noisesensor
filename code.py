import json
import wifi
import socketpool
import board
import time
import ssl
import socketpool
import wifi
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from config import Config

i2c = board.I2C()
wifi.radio.connect(Config.wifi_ssid)

def connected(client, userdata, flags, rc):
    # This function will be called when the client is connected
    # successfully to the broker.
    print("Connected to mqtt")


def disconnected(client, userdata, rc):
    # This method is called when the client is disconnected
    print("Disconnected from mqtt")


def message(client, topic, message):
    # This method is called when a topic the client is subscribed to
    # has a new message.
    print("New message on topic {0}: {1}".format(topic, message))

# Create a socket pool
pool = socketpool.SocketPool(wifi.radio)

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
while True:
    # Poll the message queue
    mqtt_client.loop()

    # get sensor value
    while not i2c.try_lock():
        pass
    i2c.writeto_then_readfrom(0x38, bytearray([0x05]), noiselevel)
    i2c.unlock()
    value = noiselevel[1] << 8 | noiselevel[0]
    #print("got raw value: %s which is decimal %s" % (noiselevel, value))

    # Send mqtt message
    mqtt_client.publish(Config.mqtt_topic, json.dumps({"noiselevel": value}))
    time.sleep(5)
