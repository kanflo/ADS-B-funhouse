#!/usr/bin/env python
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

import socket, select
import paho.mqtt.client as mosquitto
import argparse
from threading import *
import json
import sbs1
import icao24
import sys, logging
try:
  import remotelogger
except ImportError:
  print "remotelogger module not found, install from github.com/kanflo/python-remotelogger"
  sys.exit(1)
import datetime, calendar
import signal
import thread, threading
import random
import time
import re
import errno

gQuitting = False
gPlaneDBs = []

log = logging.getLogger(__name__)


# http://stackoverflow.com/questions/1165352/fast-comparison-between-two-python-dictionary
class DictDiffer(object):
  """
  Calculate the difference between two dictionaries as:
  (1) items added
  (2) items removed
  (3) keys same in both but changed values
  (4) keys same in both and unchanged values
  """
  def __init__(self, current_dict, past_dict):
    self.current_dict, self.past_dict = current_dict, past_dict
    self.set_current, self.set_past = set(current_dict.keys()), set(past_dict.keys())
    self.intersect = self.set_current.intersection(self.set_past)
  def added(self):
    return self.set_current - self.intersect 
  def removed(self):
    return self.set_past - self.intersect 
  def changed(self):
    return set(o for o in self.intersect if self.past_dict[o] != self.current_dict[o])
  def unchanged(self):
    return set(o for o in self.intersect if self.past_dict[o] == self.current_dict[o])

class Observation(object):
  def __init__(self, sbs1Message):
    log.debug("%s appeared" % sbs1Message.icao24)
    self.icao24 = sbs1Message.icao24
    self.loggedDate = sbs1Message.loggedDate
    self.callsign = sbs1Message.callsign
    self.altitude = sbs1Message.altitude
    self.groundSpeed = sbs1Message.groundSpeed
    self.track = sbs1Message.track
    self.lat = sbs1Message.lat
    self.lon = sbs1Message.lon
    self.verticalRate = sbs1Message.verticalRate
    self.operator = None
    self.type = None
    self.lost = False
    self.updated = True
    for db in gPlaneDBs:
      plane = db.find(self.icao24)
      if plane:
        self.registration = plane.registration
        self.type = plane.type
        self.operator = plane.operator
        break
    if not plane:
        log.debug("icao24 %s not found in any data base" % (self.icao24))

  def update(self, sbs1Message):
    self.loggedDate = sbs1Message.loggedDate
    oldData = dict(self.__dict__)
    if sbs1Message.icao24:
      self.icao24 = sbs1Message.icao24
    if sbs1Message.callsign and self.callsign != sbs1Message.callsign:
      self.callsign = sbs1Message.callsign
    if sbs1Message.altitude:
      self.altitude = sbs1Message.altitude
    if sbs1Message.groundSpeed:
      self.groundSpeed = sbs1Message.groundSpeed
    if sbs1Message.track:
      self.track = sbs1Message.track
    if sbs1Message.lat:
      self.lat = sbs1Message.lat
    if sbs1Message.lon:
      self.lon = sbs1Message.lon
    if sbs1Message.verticalRate:
      self.verticalRate = sbs1Message.verticalRate
    if not self.verticalRate:
      self.verticalRate = 0

    for db in gPlaneDBs:
      plane = db.find(self.icao24)
      if plane:
        self.registration = plane.registration
        self.type = plane.type
        self.operator = plane.operator
        break
    if not plane:
        log.debug("icao24 %s not found in any data base" % (self.icao24))


    # Check if observation was updated
    newData = dict(self.__dict__)
    del oldData["loggedDate"]
    del newData["loggedDate"]
    d = DictDiffer(oldData, newData)
    self.updated = len(d.changed()) > 0


  def isPresentable(self):
    return self.altitude and self.groundSpeed and self.track and self.lat and self.lon


  def dump(self):
    log.debug("> %s %s - %s %s, trk:%s spd:%s alt:%s %s, %s" % (self.icao24, self.callsign, self.operator, self.type, self.track, self.groundSpeed, self.altitude, self.lat, self.lon))

   
  def dict(self):
    d =  dict(self.__dict__)
    if d["verticalRate"] == None:
      d["verticalRate"] = 0;
    if "lastAlt" in d:
      del d["lastAlt"]
    if "lastLat" in d:
      del d["lastLat"]
    if "lastLon" in d:
      del d["lastLon"]
    d["loggedDate"] = "%s" % (d["loggedDate"])
    return d


def cleanObservations(observations, timeoutSec, mqttc):
  global args
  removed = []
  now = datetime.datetime.now()
  for icao24 in observations:
    lastSeen = observations[icao24].loggedDate
    if lastSeen:
      lookDiff = now - lastSeen
      diffSeconds = (lookDiff.days * 86400 + lookDiff.seconds)
      if diffSeconds > timeoutSec:
        removed.append(icao24)

  for icao24 in removed:
    observations[icao24].lost = True
    observations[icao24].updated = True
    d = observations[icao24].dict()
    d["lost"] = True
    mqttc.publish("/adsb/%s/json" % args.radar_name, json.dumps(d), 0, False) # Retain)
    del observations[icao24]
    log.debug("%s lost", icao24)

  return observations

def mqttOnConnect(mosq, obj, rc):
  log.info("MQTT Connect: %s" % (str(rc)))

def mqttOnDisconnect(mosq, obj, rc):
  global gQuitting
  log.info("MQTT Disconnect: %s" % (str(rc)))
  if not gQuitting:
    while not mqttConnect():
      time.sleep(10)
      log.info("Attempting MQTT reconnect")
    log.info("MQTT connected")

def mqttOnMessage(mosq, obj, msg):
  try:
    data = json.loads(msg.payload)
  except Exception as e:
    log.error("JSON load failed for '%s'", msg.payload)
  proxyCheck(mosq, data)


def mqttOnPublish(mosq, obj, mid):
    pass


def mqttOnSubscribe(mosq, obj, mid, granted_qos):
  log.debug("Subscribed")


def mqttOnLog(mosq, obj, level, string):
  log.debug("log:"+string)


def mqttThread():
  global gQuitting
  try:
    mqttc.loop_forever()
    gQuitting = True
    log.info("MQTT thread exiting")
    gQuitting = True
  except Exception as e:
    log.error("MQTT thread got exception: %s" % (e))
    print traceback.format_exc()
    gQuitting = True
    log.info("MQTT disconnect")
    mqttc.disconnect();

def mqttConnect():
  global args
  global mqttc
  try:
    mqttc = mosquitto.Mosquitto("adsbclient-%d" % (random.randint(0, 65535)))
    mqttc.on_message = mqttOnMessage
    mqttc.on_connect = mqttOnConnect
    mqttc.on_disconnect = mqttOnDisconnect
    mqttc.on_publish = mqttOnPublish
    mqttc.on_subscribe = mqttOnSubscribe

    if args.mqtt_user and args.mqtt_password:
      mqttc.username_pw_set(args.mqtt_user, password = args.mqtt_password)

    mqttc.connect(args.mqtt_host, args.mqtt_port, 60)

    thread = Thread(target = mqttThread)
    thread.setDaemon(True)
    thread.start()
    return True
  except socket.error, e:
    return False

  log.info("MQTT wierdness")

def loggingInit(level):
  log = logging.getLogger(__name__)

  # Initialize remote logging
  logger = logging.getLogger()
  logger.setLevel(level)
  remotelogger.init(logger = logger, appName = "adsbclient", subSystem = None, host = "midi.local", level = logging.DEBUG)

  if 1:
    # Log to stdout
    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def signal_handler(signal, frame):
  global gQuitting
  global mqttc
  log.info("Quitting due to ctrl-c")
  gQuitting = True
  mqttc.disconnect();
  sys.exit(0)


def adsbThread():
  global gQuitting
  global mqttc
  global args
  sock = None
  connWarn = False
  observations = {}
  socketTimeoutSec = 5
  cleanIntervalSec = 5
  cleanTimeoutSec = 30 # Clean observations when we have no updates in this time

  if args.basestationdb:
    gPlaneDBs.append(icao24.PlaneDB(args.basestationdb))
  if args.myplanedb:
    gPlaneDBs.append(icao24.PlaneDB(args.myplanedb))


  lastClean = datetime.datetime.utcnow()
  nextClean = datetime.datetime.utcnow() + datetime.timedelta(seconds=cleanIntervalSec)

  while 1:
    if sock == None:
      try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((args.dump1090_host, args.dump1090_port))
        log.info("ADSB connected")
        sock.settimeout(socketTimeoutSec)
        connWarn = False
      except socket.error as e:
        if not connWarn:
          logging.critical("Failed to connect to ADSB receiver on %s:%s, retrying : %s" % (args.dump1090_host, args.dump1090_port, e))
          connWarn = True
        sock = None
        time.sleep(10)
    else:
      if datetime.datetime.utcnow() > nextClean:
        observations = cleanObservations(observations, cleanTimeoutSec, mqttc)
        lastClean = datetime.datetime.utcnow()
        nextClean = datetime.datetime.utcnow() + datetime.timedelta(seconds=cleanIntervalSec)
      try:
        data = sock.recv(512)
      except socket.error, e:
        err = e.args[0]
        if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
          logging.critical("No data available")
          print ''
          sock = None
          time.sleep(10)
        else:
          logging.critical("Error occured : %s" % (e))
          sock = None
          time.sleep(10)
      else:
        m = sbs1.SBS1Message(data)
        if m.isValid:
          if m.icao24 in observations:
            observations[m.icao24].update(m)
          else:
            observations[m.icao24] = Observation(m)
          if observations[m.icao24].isPresentable() and observations[m.icao24].updated:
            mqttc.publish("/adsb/%s/json" % args.radar_name, json.dumps(observations[m.icao24].dict()), 0, False) # Retain)
            observations[m.icao24].updated = False
            observations[m.icao24].dump()


def adsbConnect():
    thread = Thread(target = adsbThread)
    thread.setDaemon(True)
    thread.start()

def main():
  global args
  parser = argparse.ArgumentParser(description='This is my description')

  parser.add_argument('-r', '--radar-name', help="name of radar, used as topic string /adsb/<radar>/json", default='radar')
  parser.add_argument('-m', '--mqtt-host', help="MQTT broker hostname", default='127.0.0.1')
  parser.add_argument('-p', '--mqtt-port', type=int, help="MQTT broker port number (default 1883)", default=1883)
  parser.add_argument('-u', '--mqtt-user', help="MQTT broker user")
  parser.add_argument('-a', '--mqtt-password', help="MQTT broker password")
  parser.add_argument('-H', '--dump1090-host', help="dump1090 hostname", default='127.0.0.1')
  parser.add_argument('-P', '--dump1090-port', type=int, help="dump1090 port number (default 30003)", default=30003)
  parser.add_argument('-v', '--verbose',  action="store_true", help="Verbose output")
  parser.add_argument('-bdb', '--basestationdb', help="BaseStation SQLite DB (download from http://planebase.biz/bstnsqb)", nargs='?')
  parser.add_argument('-mdb', '--myplanedb', help="Your own SQLite DB with the same structure as BaseStation.sqb where you can add planes missing from BaseStation db", nargs='?')

  args = parser.parse_args()

  signal.signal(signal.SIGINT, signal_handler)
  if args.verbose:
    loggingInit(logging.DEBUG)
  else:
    loggingInit(logging.INFO)

  mqttConnect()
  adsbConnect()

  numThreads = threading.active_count()
  while numThreads == threading.active_count():
    time.sleep(0.1)
  log.critical("Exiting")


# Ye ol main
main()
