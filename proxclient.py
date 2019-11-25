#!/usr/bin/env python3
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

import time
import argparse
from threading import *
import logging
import sys
import remotelogger
import socket
import calendar, datetime
import json
import traceback
import math
import signal
import random
import bing
import planeimg
import planedb
import mqtt_wrapper

prox_timeout = 30
last_xmit_time = time.time()

max_receiver_distance = 374000 # Meters
min_receiver_distance = 10000 # Meters

# Used for tracking the nearest aircraft
cur_tracking_distance = 999999
cur_icao24 = None

# If the current observation is blacklisted by Bing, don't hammer...
blacklisted = None

# Keeping track of current route
cur_route = None

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
    if "route" in data:
      j['route'] = data["route"]

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
    if "counter" in data:
      j["counter"] = data["counter"]
    return j

def sendProx(bridge, data):
    global last_xmit_time
    j = copyMessage(data)
    retain = False
    last_xmit_time = time.time()
    bridge.publish(args.prox, json.dumps(j), 0, retain)

def sendLost(bridge, data):
    j = copyMessage(data)
    j["lost"] = True
    retain = False
    bridge.publish(args.prox, json.dumps(j), 0, retain)

# @todo: don't search for
#
#    Bluebird Nordic Boeing 737 4Q8SF TF-BBM
#
# but rather
#
#    "Bluebird Nordic" "Boeing 737" "TF-BBM"
#
# or
#
#    "Bluebird Nordic" "TF-BBM"
#
# or
#
#    "Bluebird Nordic" Boeing "TF-BBM"

def image_search(plane):
  img_url = None
  # Bing sometimes refuses to search for "Scandinavian Airlines System" :-/
  op = plane["operator"].replace("Scandinavian Airlines System", "SAS")
  searchTerm = "%s %s %s" % (op, plane["type"], plane["registration"])
  log.info("Searching for %s", searchTerm)
  imageUrls = bing.imageSearch(searchTerm)
  if imageUrls:
    img_url = imageUrls[0]
    log.info("Added url %s for %s", img_url, plane['icao24'])
    for k in plane:
      log.info("%20s : %s" % (k, plane[k]))
    plane['image'] = img_url
    if not planedb.update_aircraft(plane['icao24'], {'image' : img_url}):
      sys.error("Failed to update image")

  else:
    log.error("Image search came up short for %s, blacklisted?" % (plane['icao24']))
  return img_url


def proxyCheck(bridge, data):
  global min_receiver_distance
  global max_receiver_distance
  global cur_tracking_distance
  global cur_icao24
  global args
  global blacklisted
  global cur_route

  if not data:
    return

  lat = data["lat"]
  lon = data["lon"]

  if lat and lon:
    altitude = data["altitude"]
    icao24 = data["icao24"]
    lost = data["lost"]
    distance = receiverDistance(lat, lon, altitude)
    bearing = receiverBearing(lat, lon)
    data["distance"] = distance
    data["bearing"] = bearing
    # Is this the plane we're tracking or is it one that is closer?
    if icao24 == cur_icao24 or distance < cur_tracking_distance:
      plane = planedb.lookup_aircraft(icao24)
      if not plane:
        return
      img_url = plane['image']
      if not img_url and blacklisted != cur_icao24:
        if data["operator"] and data["type"] and data["registration"]:
          img_url = image_search(data)
          if not img_url: # Don't try again for this plane
            blacklisted = icao24

      if img_url: # Only track planes with images
        data["image"] = img_url
        if icao24 != cur_icao24:
          log.info("Giving up %s (%d), tracking %s (%d)", cur_icao24, cur_tracking_distance, icao24, distance)
          cur_route = None
          cur_icao24 = icao24
        cur_tracking_distance = distance
        if "counter" in data:
          counter = data["counter"]
        else:
          counter = 0
        log.info("[%-10s] %s: pos:%2f, %2f @ %dft distance:%d bearing:%d" % (counter, icao24, lat, lon, altitude, distance, bearing))
        if not cur_route:
          route = planedb.lookup_route(data['callsign'])
          if route:
            src = planedb.lookup_airport(route['src_iata'])
            dst = planedb.lookup_airport(route['dst_iata'])
            if src and dst:
              src.pop('id', None)
              src.pop('added_on', None)
              src.pop('updated_on', None)
              dst.pop('id', None)
              dst.pop('added_on', None)
              dst.pop('updated_on', None)
              cur_route = {'origin' : src, 'destination' : dst}
        if cur_route:
          data['route'] = cur_route

        sendProx(bridge, data)

    if distance < min_receiver_distance:
      log.info("New min range for %s at %d", icao24, distance)
      min_receiver_distance = distance
    if distance > max_receiver_distance:
      log.info("New max range for %s at %d", icao24, distance)
      max_receiver_distance = distance


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


class mybridge(mqtt_wrapper.bridge):
    def msg_process(self, msg):
        j = json.loads(msg.payload.decode('utf-8'))
        proxyCheck(self, j)

def main():
  global args
  global cur_icao24
  global cur_tracking_distance
  global cur_route

  parser = argparse.ArgumentParser()
  parser.add_argument('-m', '--mqtt-host', help="MQTT broker hostname", default='127.0.0.1')
  parser.add_argument('-p', '--mqtt-port', type=int, help="MQTT broker port number", default=1883)
  parser.add_argument('-u', '--mqtt-user', help="MQTT broker user")
  parser.add_argument('-a', '--mqtt-password', help="MQTT broker password")
  parser.add_argument('-R', '--radar', help="MQTT radar topic to subscribe to", default='/adsb/radar/json')
  parser.add_argument('-P', '--prox', help="MQTT proximity topic to publish to", default='/adsb/proximity/json')
  parser.add_argument('-pdb', '--planedb', dest='pdb_host', help="Plane database host")
  parser.add_argument('-l', '--lat', type=float, help="Latitude of radar")
  parser.add_argument('-L', '--lon', type=float, help="Longitude of radar")
  parser.add_argument('-v', '--verbose', dest='verbose',  action="store_true", help="Verbose output")
  parser.add_argument('-o', '--logger', dest='log_host', help="Remote log host")

  args = parser.parse_args()

  if not args.lat and not args.lon:
    print("You really need to tell me where you are located (--lat and --lon)")
    sys.exit(1)

  if args.pdb_host:
    planedb.init(args.pdb_host)

  if args.verbose:
    loggingInit(logging.DEBUG, args.log_host)
  else:
    loggingInit(logging.INFO, args.log_host)
  log.info("Proxclient started")

  bridge = mybridge(host = args.mqtt_host, mqtt_topic = args.radar, port = args.mqtt_port, client_id = "proxclient-%d" % (random.randint(0, 65535)), user_id = args.mqtt_user, password = args.mqtt_password)
  while True:
    bridge.looping()
    if last_xmit_time and time.time() - last_xmit_time > prox_timeout and cur_icao24:
      log.warning("Timeout, giving up on %s" % cur_icao24)
      cur_route = None
      cur_icao24 = None
      cur_tracking_distance = 999999

# Ye ol main
main()

