#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Johan Kanflo (github.com/kanflo)
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

#
# proxclient subscribes to the MQTT topic /adsb/radar/json and calculates the
# distance to the nearest aircraft and publishes data to /adsb/proximity/json
#

import paho.mqtt.client as mosquitto
import Queue
import time
import argparse
from threading import *
import logging
import sys
try:
  import remotelogger
except ImportError:
  print "remotelogger module not found, install from github.com/kanflo/python-remotelogger"
  sys.exit(1)
import socket
import calendar, datetime
import json
import traceback
import math
import signal
import random
import bing
import bingconfig
import planeimg

max_receiver_distance = 374000 # Meters
min_receiver_distance = 10000 # Meters

# Used for tracking the nearest aircraft
minTrackingDistance = 999999
trackingICAO24 = None

gQuitting = False
gImageDB = None
gCurImage = None

log = logging.getLogger(__name__)


def deg2rad(deg):
  return deg * (math.pi/180)

def receiverBearing(lat, lon):
  global args
  lat1, lon1 = args.lat, args.lon
  lat2, lon2 = lat, lon

  rlat1 = math.radians(lat1)
  rlat2 = math.radians(lat2)
  rlon1 = math.radians(lon1)
  rlon2 = math.radians(lon2)
  dlon = math.radians(lon2-lon1)

  b = math.atan2(math.sin(dlon)*math.cos(rlat2),math.cos(rlat1)*math.sin(rlat2)-math.sin(rlat1)*math.cos(rlat2)*math.cos(dlon)) # bearing calc
  bd = math.degrees(b)
  br,bn = divmod(bd+360,360) # the bearing remainder and final bearing

  return bn

def latLonDistance(lat1, lon1, lat2, lon2):
  R = 6371 # Radius of the earth in km
  dLat = deg2rad(lat2-lat1)  # deg2rad below
  dLon = deg2rad(lon2-lon1)
  a = math.sin(dLat/2) * math.sin(dLat/2) + math.cos(deg2rad(lat1)) * math.cos(deg2rad(lat2)) * math.sin(dLon/2) * math.sin(dLon/2)
  c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
  d = R * c * 1000 #  Distance in m
  return d


def receiverDistance(lat, lon, altitude):
  global args
  distance = latLonDistance(lat, lon, args.lat, args.lon)
  return float("{0:.3f}".format(distance))

def copyMessage(data):
    j = {}
    j['loggedDate'] = data["loggedDate"]
    j['time'] = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
    j['icao24'] = data["icao24"]
    j['altitude'] = data["altitude"]
    j['lat'] = data["lat"]
    j['lon'] = data["lon"]
    j['distance'] = float(data["distance"]/1000)
    j['callsign'] = data["callsign"]

    j['operator'] = data["operator"]
    j['speed'] = data["groundSpeed"]
    j['vspeed'] = data["verticalRate"]
    j['heading'] = data["track"]
    j['bearing'] = int(round(data["bearing"]))

    # You never know what the data might contain :)
    if "type" in data:
      j['type'] = data["type"]
    if "registration" in data:
      j['registration'] = data["registration"]
    if "image" in data:
      j['image'] = data["image"]
    if "copyright" in data:
      j['copyright'] = data["copyright"]
    if "origin" in data:
      j["origin"] = data["origin"]
    if "destination" in data:
      j["destination"] = data["destination"]
    return j

def sendProx(mosq, data):
    global args
    j = copyMessage(data)
    retain = False
    mosq.publish(args.prox, json.dumps(j), 0, retain)

def sendLost(mosq, data):
    global args
    j = copyMessage(data)
    j["lost"] = True
    retain = False
    mosq.publish(args.prox, json.dumps(j), 0, retain)

def proxyCheck(mosq, data):
  global min_receiver_distance
  global max_receiver_distance
  global minTrackingDistance
  global trackingICAO24
  global args
  global gImageDB
  global gCurImage

  lat = data["lat"]
  lon = data["lon"]
  altitude = data["altitude"]
  icao24 = data["icao24"]
  lost = data["lost"]

  if lat and lon:
    distance = receiverDistance(lat, lon, altitude)
    bearing = receiverBearing(lat, lon)
    data["distance"] = distance
    data["bearing"] = bearing

    if distance < minTrackingDistance:
      minTrackingDistance = distance
      if icao24 != trackingICAO24:
        if trackingICAO24:
          log.debug("Giving up %s, tracking %s", trackingICAO24, icao24)
        else:
          log.debug("Tracking %s", icao24)
        trackingICAO24 = icao24
  # TODO: Lookup images here?
        planeimage = gImageDB.find(trackingICAO24)
        if planeimage:
          gCurImage = planeimage.image
        elif data and data["operator"] and data["type"] and data["registration"]:
          searchTerm = "%s %s %s" % (data["operator"], data["type"], data["registration"])

          if args.no_images:
            imageUrls = None
          else:
            imageUrls = bing.imageSearch(searchTerm, {"minWidth":1024, "minHeight":768})

          if imageUrls and data:
            gCurImage = imageUrls[0]
            log.debug("Added url %s for %s", gCurImage, icao24)
            gImageDB.add(trackingICAO24, gCurImage)

    data["image"] = gCurImage
    if trackingICAO24 == icao24:
      if lost:
        log.debug("Lost %s", icao24)
        trackingICAO24 = None
        minTrackingDistance = 999999
        sendLost(mosq, data)
      else:
        minTrackingDistance = distance
        log.debug(" pos:%2f, %2f @ %dft distance:%d bearing:%d" % (lat, lon, altitude, distance, bearing))
        sendProx(mosq, data)

    if distance < min_receiver_distance:
      log.info("New min range for %s at %d", icao24, distance)
      min_receiver_distance = distance
    if distance > max_receiver_distance:
      log.info("New max range for %s at %d", icao24, distance)
      max_receiver_distance = distance


def mqttOnConnect(mosq, obj, rc):
  global args
  mosq.subscribe(args.radar, 0)
  log.debug("MQTT Connect: %s" % (str(rc)))

def mqttOnDisconnect(mosq, obj, rc):
  global gQuitting
  log.debug("MQTT Disconnect: %s" % (str(rc)))
  if not gQuitting:
    while not mqttConnect():
      time.sleep(10)
      log.debug("Attempting MQTT reconnect")
    log.debug("MQTT connected")

def mqttOnMessage(mosq, obj, msg):
  data = None
  try:
    data = json.loads(msg.payload)
  except Exception as e:
    log.error("JSON load failed for '%s'", msg.payload)
  if data != None:
    proxyCheck(mosq, data)


def mqttOnPublish(mosq, obj, mid):
# log.debug("mid: "+str(mid)))
    pass


def mqttOnSubscribe(mosq, obj, mid, granted_qos):
  log.debug("Subscribed")


def mqttOnLog(mosq, obj, level, string):
  log.debug("log:"+string)


def mqttThread():
  global gQuitting
  global gImageDB
  if args.imagedb:
    gImageDB = planeimg.ImageDB(args.imagedb)
  while not gQuitting:
    try:
      mqttc.loop_forever()
      log.debug("MQTT thread exiting")
    except Exception as e:
      log.error("MQTT thread got exception: %s" % (e))
      print traceback.format_exc()
      log.info("MQTT disconnect")
      mqttc.disconnect();

def mqttConnect():
  global mqttc
  global args
  try:
    mqttc = mosquitto.Mosquitto("proxclient-%d" % (random.randint(0, 65535)))
    mqttc.on_message = mqttOnMessage
    mqttc.on_connect = mqttOnConnect
    mqttc.on_disconnect = mqttOnDisconnect
    mqttc.on_publish = mqttOnPublish
    mqttc.on_subscribe = mqttOnSubscribe
    #mqttc.on_log = mqttOnLog # Uncomment to enable debug messages
    mqttc.connect(args.mqtt_host, args.mqtt_port, 60)

    thread = Thread(target = mqttThread)
    thread.start()
    return True
  except socket.error, e:
    return False

  log.debug("MQTT wierdness")


def loggingInit(level, log_host):
  log = logging.getLogger(__name__)

  # Initialize remote logging
  logger = logging.getLogger()
  logger.setLevel(level)
  if log_host != None:
    remotelogger.init(logger = logger, appName = "radarprox", subSystem = None, host = log_host, level = level)

  # Log to stdout
  ch = logging.StreamHandler(sys.stdout)
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  ch.setFormatter(formatter)
  logger.addHandler(ch)

def signal_handler(signal, frame):
  global gQuitting
  global mqttc
  print "ctrl-c"
  gQuitting = True
  mqttc.disconnect();
  sys.exit(0)

def main():
  global gQuitting
  global mqttc
  global args
  parser = argparse.ArgumentParser()
  parser.add_argument('-m', '--mqtt-host', help="MQTT broker hostname", default='127.0.0.1')
  parser.add_argument('-p', '--mqtt-port', type=int, help="MQTT broker port number", default=1883)
  parser.add_argument('-R', '--radar', help="MQTT radar topic to subscribe to", default='/adsb/radar/json')
  parser.add_argument('-P', '--prox', help="MQTT proximity topic to publish to", default='/adsb/proximity/json')
  parser.add_argument('-idb', '--imagedb', help="SQLite plane image database")
  parser.add_argument('-r', '--rlog-host', help="Remote logging host")
  parser.add_argument('-l', '--lat', type=float, help="Latitude of radar")
  parser.add_argument('-L', '--lon', type=float, help="Longitude of radar")
  parser.add_argument('-v', '--verbose', dest='verbose',  action="store_true", help="Verbose output")
  parser.add_argument('-g', '--no-images', dest='no_images',  action="store_true", help="Skip image search")
  parser.add_argument('-o', '--logger', dest='log_host', help="Remote log host")

  args = parser.parse_args()
  if bingconfig.key == None:
    if not args.no_images:
      print "You really need to specify a Bing API key or --no-images"
      sys.exit(1)

  bing.setKey(bingconfig.key)

  if not args.lat and not args.lon:
    print "You really need to tell me where you are located (--lat and --lon)"
    sys.exit(1)
  if not args.imagedb:
    print "You need to tell me where to store aircraft image info (--imagedb DB)"
    sys.exit(1)
  try:
    signal.signal(signal.SIGINT, signal_handler)
    if args.verbose:
      loggingInit(logging.DEBUG, args.log_host)
    else:
      loggingInit(logging.INFO, args.log_host)
    log.info("Proxclient started")
    mqttConnect()
    while not gQuitting:
      time.sleep(1)
  except Exception as e:
    log.error("Mainloop got exception: %s" % (e))
    print traceback.format_exc()
    gQuitting = True
  log.info("MQTT disconnect")
  mqttc.disconnect();

# Ye ol main
main()

