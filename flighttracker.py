#!/usr/bin/env python3
#
# Copyright (c) 2020 Johan Kanflo (github.com/kanflo)
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

from typing import *
import socket
import argparse
import threading
import sys
import os
import logging
import logging
import coloredlogs
from datetime import datetime, timedelta
import time
import sbs1
from planedb import *
import utils
import mqtt_wrapper


# Clean out observations this often
OBSERVATION_CLEAN_INTERVAL = 30
# Socket read timeout
DUMP1090_SOCKET_TIMEOUT = 60

args = None

counter = 0

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
    """
    This class keeps track of the observed flights around us.
    """
    __icao24 = None
    __loggedDate = None
    __callsign = None
    __altitude = None
    __altitudeTime = None
    __groundSpeed = None
    __track = None
    __lat = None
    __lon = None
    __latLonTime = None
    __verticalRate = None
    __operator = None
    __registration = None
    __type = None
    __updated = None
    __route = None
    __image_url = None
    __planedb_nagged = False  # Used in case the icao24 is unknown and we only want to log this once
    __planedb_unknown = False
    __planedb_unknown_nagged = False

    def __init__(self, sbs1msg):
        logging.info("%s appeared" % sbs1msg["icao24"])
        self.__icao24 = sbs1msg["icao24"]
        self.__loggedDate = datetime.utcnow()  # sbs1msg["loggedDate"]
        self.__callsign = sbs1msg["callsign"]
        self.__altitude = sbs1msg["altitude"]
        self.__altitudeTime = datetime.utcnow()
        self.__groundSpeed = sbs1msg["groundSpeed"]
        self.__track = sbs1msg["track"]
        self.__lat = sbs1msg["lat"]
        self.__lon = sbs1msg["lon"]
        self.__latLonTime = datetime.utcnow()
        self.__verticalRate = sbs1msg["verticalRate"]
        self.__operator = None
        self.__registration = None
        self.__type = None
        self.__updated = True
        if args.pdb_host:
            plane = planedb.lookup_aircraft_icao24(self.__icao24)
            if plane:
                self.__registration = plane["registration"]
                self.__type = plane["manufacturer"] + " " + plane["model"]
                self.__operator = plane["operator"]
                self.__image_url = plane["image"]
                if self.__image_url is None or len(self.__image_url) < 2:
                    self.__image_url = utils.image_search(self.__icao24, self.__operator, self.__type, self.__registration)
            else:
                self.__planedb_unknown = True
                if not self.__planedb_nagged:
                    self.__planedb_nagged = True
                    logging.error("icao24 %s not found in the database" % (self.__icao24))

    def update(self, sbs1msg):
        oldData = dict(self.__dict__)
        self.__loggedDate = datetime.utcnow()
        if sbs1msg["icao24"]:
            self.__icao24 = sbs1msg["icao24"]
        if sbs1msg["callsign"] and self.__callsign != sbs1msg["callsign"]:
            self.__callsign = sbs1msg["callsign"].rstrip()
        if sbs1msg["altitude"]:
            self.__altitude = sbs1msg["altitude"]
            self.__altitudeTime = datetime.utcnow()
        if sbs1msg["groundSpeed"]:
            self.__groundSpeed = sbs1msg["groundSpeed"]
        if sbs1msg["track"]:
            self.__track = sbs1msg["track"]
        if sbs1msg["lat"]:
            self.__lat = sbs1msg["lat"]
            self.__latLonTime = datetime.utcnow()
        if sbs1msg["lon"]:
            self.__lon = sbs1msg["lon"]
            self.__latLonTime = datetime.utcnow()
        if sbs1msg["verticalRate"]:
            self.__verticalRate = sbs1msg["verticalRate"]
        if not self.__verticalRate:
            self.__verticalRate = 0
        if sbs1msg["generatedDate"]:
            self.__generatedDate = sbs1msg["generatedDate"]
        #if sbs1msg["loggedDate"]:
        #    self.__loggedDate = sbs1msg["loggedDate"]

        if args.pdb_host:
            plane = planedb.lookup_aircraft_icao24(self.__icao24)
            if plane:
                self.__registration = plane['registration']
                self.__type = plane['manufacturer'] + " " + plane['model']
                self.__operator = plane['operator']
            else:
                if not self.__planedb_nagged:
                    self.__planedb_nagged = True
                    self.__planedb_unknown = True
                    logging.error("icao24 %s not found in the database" % (self.__icao24))
            if self.__callsign and not self.__route:
                route = planedb.lookup_route(self.__callsign)
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
                        self.__route = {'origin' : src, 'destination' : dst}
                    else:
                        self.__route = {}
                else:
                    self.__route = {}

        # Check if observation was updated
        newData = dict(self.__dict__)
        del oldData["_Observation__loggedDate"]
        del newData["_Observation__loggedDate"]
        d = DictDiffer(oldData, newData)
        self.__updated = len(d.changed()) > 0

    def getIcao24(self) -> str:
        return self.__icao24

    def getLat(self) -> float:
        return self.__lat

    def getLon(self) -> float:
        return self.__lon

    def isUpdated(self) -> bool:
        return self.__updated

    def getLoggedDate(self) -> datetime:
        return self.__loggedDate

    def getGroundSpeed(self) -> float:
        return self.__groundSpeed

    def getHeading(self) -> float:
        return self.__track

    def getAltitude(self) -> float:
        return self.__altitude

    def getType(self) -> str:
        return self.__type

    def getRegistration(self) -> str:
        return self.__registration

    def getOperator(self) -> str:
        return self.__operator

    def getRoute(self) -> str:
        return self.__route

    def getImageUrl(self) -> str:
        return self.__image_url

    def isPresentable(self) -> bool:
        return self.__altitude and self.__groundSpeed and self.__track and self.__lat and self.__lon and self.__image_url

    def dump(self):
        """Dump this observation on the console
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        logging.debug("> %s  %s %-7s - trk:%3d spd:%3d alt:%5d (%5d) %.4f, %.4f" % (now, self.__icao24, self.__callsign, self.__track, self.__groundSpeed, self.__altitude, self.__verticalRate, self.__lat, self.__lon))

    def isKnown(self) -> bool:
        """Return True if this plane is known in the database

        Returns:
            bool: True if plane is known, False otherwise
        """
        return not self.__planedb_unknown

    def isKnownNagged(self) -> bool:
        """If the plane is unknown, return False __once__. Why on earth is this?
           Well, the function is used for determining if we should publish an MQTT
           topic about the unknown aircraft. We do not want to spam each an every time
           we receive an update on an unknown aircraft so we need to filter this somehow.
           This is a feeble attempt at doing so...

        Returns:
            bool: True if plane is known or we have called this function several times
                  False if the plans is unknown and this is the first time we call the function
        """
        if not self.__planedb_unknown_nagged:
            self.__planedb_unknown_nagged = True
            return not self.__planedb_unknown
        else:
            return True

    def json(self, bearing: int, distance: int) -> str:
        """Return JSON representation of this observation

        Arguments:
            bearing {int} -- bearing to observation in degrees
            distance {int} -- distance to observation in meters

        Returns:
            str -- JSON string
        """
        if self.__route is None:
            route = "\"\""
        else:
            route = "%s" % self.__route
            route = route.replace("'", "\"")

        if self.__callsign is None:
            callsign = "\"\""
        else:
            callsign = "\"%s\"" % self.__callsign

        distance = distance / 1000
        global counter
        counter += 1
        return '{"vspeed": %d, "time": %d, "lat": %.5f, "lon": %.5f, "distance": %.5f, "image": "%s", "altitude": %d, "speed": %d, "icao24": "%s", "registration": "%s", "heading": %d, "operator": "%s", "bearing": %d, "loggedDate": "%s", "type": "%s", "callsign": %s, "route" : %s, "counter": %d}' % \
            (self.__verticalRate, time.time(), self.__lat, self.__lon, distance, self.__image_url, self.__altitude, self.__groundSpeed, self.__icao24, self.__registration, self.__track, self.__operator, bearing, self.__loggedDate, self.__type, callsign, route, counter)


    def dict(self):
        d =  dict(self.__dict__)
        if d["_Observation__verticalRate"] == None:
            d["verticalRate"] = 0
        if "_Observation__lastAlt" in d:
            del d["lastAlt"]
        if "_Observation__lastLat" in d:
            del d["lastLat"]
        if "_Observation__lastLon" in d:
            del d["lastLon"]
        d["loggedDate"] = "%s" % (d["_Observation__loggedDate"])
        return d


class FlightTracker(object):
    __dump1090_host: str = ""
    __dump1090_port: int = 0
    __mqtt_broker: str = ""
    __mqtt_port: int = 0
    __latitude: float = 0
    __longitude: float = 0
    __dump1090_sock: socket.socket = None
    __mqtt_bridge = None
    __observations: Dict[str, str] = {}
    __tracking_icao24: str = None
    __tracking_distance: int = 999999999
    __next_clean: datetime = None
    __has_nagged: bool = False
    __unknown_aircraft_topic: str = None

    def __init__(self, dump1090_host: str, mqtt_broker: str, latitude: float, longitude: float, proximity_topic: str, dump1090_port: int = 30003, mqtt_port: int = 1883, unknown_aircraft_topic: str = None):
        """Initialize the flight tracker

        Arguments:
            dump1090_host {str} -- Name or IP of dump1090 host
            mqtt_broker {str} -- Name or IP of dump1090 MQTT broker
            latitude {float} -- Latitude of receiver
            longitude {float} -- Longitude of receiver
            proximity_topic {str} -- MQTT topic for proximity reports
            unknown_aircraft_topic {str} -- MQTT topic for unknown aircraft reports

        Keyword Arguments:
            dump1090_port {int} -- Override the dump1090 raw port (default: {30003})
            mqtt_port {int} -- Override the MQTT default port (default: {1883})
        """
        self.__dump1090_host = dump1090_host
        self.__dump1090_port = dump1090_port
        self.__mqtt_broker = mqtt_broker
        self.__mqtt_port = mqtt_port
        self.__latitude = latitude
        self.__longitude = longitude
        self.__sock = None
        self.__observations = {}
        self.__next_clean = datetime.utcnow() + timedelta(seconds=OBSERVATION_CLEAN_INTERVAL)
        self.__prox_topic = proximity_topic
        self.__unknown_aircraft_topic = unknown_aircraft_topic


    def dump1090Connect(self) -> bool:
        """If not connected, connect to the dump1090 host

        Returns:
            bool -- True if we are connected
        """
        if self.__dump1090_sock == None:
            try:
                if not self.__has_nagged:
                    logging.info("Connecting to dump1090 host on %s:%s" % (self.__dump1090_host, self.__dump1090_port))
                self.__dump1090_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.__dump1090_sock.connect((self.__dump1090_host, self.__dump1090_port))
                logging.info("ADSB connected")
                self.__dump1090_sock.settimeout(DUMP1090_SOCKET_TIMEOUT)
                self.__has_nagged = False
                return True
            except socket.error as e:
                if not self.__has_nagged:
                    logging.critical("Failed to connect to ADSB receiver on %s:%s, retrying : %s" % (self.__dump1090_host, self.__dump1090_port, e))
                    self.__has_nagged = True
                self.__dump1090_sock = None
                time.sleep(5)
            return False
        else:
            return True


    def dump1090Close(self):
        """Close connection to dump1090 host.
        """
        try:
            self.__dump1090_sock.close()
        except socket.error:
            pass
        self.__dump1090_sock = None
        self.__has_nagged = False


    def dump1090Read(self) -> str:
        """Read a line from the dump1090 host. If the host went down, close the socket and return None

        Returns:
            str -- An SBS1 message or None if disconnected or timeout

        Yields:
            str -- An SBS1 message or None if disconnected or timeout
        """
        try:
            try:
                buffer = self.__dump1090_sock.recv(4096)
            except ConnectionResetError:
                logging.warning("Connection reset")
                self.dump1090Close()
                yield None
            except socket.error:
                logging.warning("Socket error")
                self.dump1090Close()
                yield None
            if buffer is None:
                self.dump1090Close()
                return None
            buffer = buffer.decode("utf-8")
            buffering = True
            if buffer == "":
                self.dump1090Close()
                return None
            while buffering:
                if "\n" in buffer:
                    (line, buffer) = buffer.split("\r\n", 1)
                    yield line
                else:
                    try:
                        more = self.__dump1090_sock.recv(4096)
                    except ConnectionResetError:
                        logging.warning("Connection reset")
                        self.dump1090Close()
                        yield None
                    except socket.error:
                        logging.warning("Socket error")
                        self.dump1090Close()
                        yield None
                    if not more:
                        buffering = False
                    else:
                        try:
                            more = more.decode("utf-8")
                        except AttributeError:
                            pass
                        if more == "":
                            self.dump1090Close()
                            return None
                        buffer += more
            if buffer:
                yield buffer
        except socket.timeout:
            yield None


    def __publish_thread(self):
        """
        MQTT publish closest observation every second, more often if the plane is closer
        """
        while True:
            if not self.__tracking_icao24:
                time.sleep(1)
            else:
                if not self.__tracking_icao24 in self.__observations:
                    self.__tracking_icao24 is None
                    continue
                cur = self.__observations[self.__tracking_icao24]
                if cur is None:
                    continue
                (lat, lon) = utils.calc_travel(cur.getLat(), cur.getLon(), cur.getLoggedDate(), cur.getGroundSpeed(), cur.getHeading())
                distance = utils.coordinate_distance(self.__latitude, self.__longitude, lat, lon)
                # Round off to nearest 100 meters
                distance = round(distance/100) * 100
                bearing = utils.bearing(self.__latitude, self.__longitude, lat, lon)

                # @todo: update altitude
                # altitude = sbs1["altitude"]

                retain = False
                self.__mqtt_bridge.client.publish(self.__prox_topic, cur.json(bearing, distance), 0, retain)
                logging.info("%s at %5d brg %3d alt %5d trk %3d spd %3d %s" % (cur.getIcao24(), distance, bearing, cur.getAltitude(), cur.getHeading(), cur.getGroundSpeed(), cur.getType()))

                if distance < 3000:
                    time.sleep(0.25)
                elif distance < 6000:
                    time.sleep(0.5)
                else:
                    time.sleep(1)


    def updateTrackingDistance(self):
        """Update distance to aircraft being tracked
        """
        cur = self.__observations[self.__tracking_icao24]
        self.__tracking_distance = utils.coordinate_distance(self.__latitude, self.__longitude, cur.getLat(), cur.getLon())


    def run(self):
        """Run the flight tracker.
        """
        logging.info("Connecting to MQTT broker on %s:%s" % (self.__mqtt_broker, self.__mqtt_port))
        self.__mqtt_bridge = mqtt_wrapper.bridge(host = self.__mqtt_broker, port = self.__mqtt_port, mqtt_topic = "foobar", client_id = "FlightTracker-%d" % (os.getpid())) # TOOD: , user_id = args.mqtt_user, password = args.mqtt_password)
        threading.Thread(target = self.__publish_thread, daemon = True).start()

        while True:
            logging.info("Connecting to dump1090")
            if not self.dump1090Connect():
                continue
            for data in self.dump1090Read():
                if data is None:
                    break
                self.cleanObservations()
                m = sbs1.parse(data)
                if m:
                    icao24 = m["icao24"]
                    if icao24 == "000000":  # "Ghost data" sometimes received by dump1090, ignore
                        continue
                    if icao24 in self.__observations:
                        self.__observations[icao24].update(m)
                    else:
                        self.__observations[icao24] = Observation(m)

                    if self.__observations[icao24].isPresentable():
                        if not self.__tracking_icao24:
                            self.__tracking_icao24 = icao24
                            self.updateTrackingDistance()
                            logging.info("Tracking %s at %d" % (self.__tracking_icao24, self.__tracking_distance))
                        elif self.__tracking_icao24 == icao24:
                            self.updateTrackingDistance()
                        else:
                            distance = utils.coordinate_distance(self.__latitude, self.__longitude, self.__observations[icao24].getLat(), self.__observations[icao24].getLon())
                            if distance < self.__tracking_distance:
                                self.__tracking_icao24 = icao24
                                self.__tracking_distance = distance
                                logging.info("Now tracking %s at %d" % (self.__tracking_icao24, self.__tracking_distance))
                    if not self.__observations[icao24].isKnownNagged() and self.__unknown_aircraft_topic is not None:
                        self.__mqtt_bridge.client.publish(self.__unknown_aircraft_topic, icao24)


    def selectNearestObservation(self):
        """Select nearest presentable aircraft
        """
        self.__tracking_icao24 = None
        self.__tracking_distance = 999999999
        for icao24 in self.__observations:
            if not self.__observations[icao24].isPresentable():
                continue
            distance = utils.coordinate_distance(self.__latitude, self.__longitude, self.__observations[icao24].getLat(), self.__observations[icao24].getLon())
            if distance < self.__tracking_distance:
                self.__tracking_icao24 = icao24
                self.__tracking_distance = distance
        if self.__tracking_icao24 is None:
            logging.info("Found nothing to track")
        else:
            logging.info("Found new tracking %s at %d" % (self.__tracking_icao24, self.__tracking_distance))


    def cleanObservations(self):
        """Clean observations for planes not seen in a while
        """
        now = datetime.utcnow()
        if now > self.__next_clean:
            cleaned = []
            for icao24 in self.__observations:
#                logging.info("[%s] %s -> %s : %s" % (icao24, self.__observations[icao24].getLoggedDate(), self.__observations[icao24].getLoggedDate() + timedelta(seconds=OBSERVATION_CLEAN_INTERVAL), now))
                if self.__observations[icao24].getLoggedDate() + timedelta(seconds=OBSERVATION_CLEAN_INTERVAL) < now:
                    logging.info("%s disappeared" % (icao24))
                    if icao24 == self.__tracking_icao24:
                        self.__tracking_icao24 = None
                    cleaned.append(icao24)

            for icao24 in cleaned:
                del self.__observations[icao24]
            if self.__tracking_icao24 is None:
                self.selectNearestObservation()

            self.__next_clean = now + timedelta(seconds=OBSERVATION_CLEAN_INTERVAL)


def main():
    global args
    global logging
    parser = argparse.ArgumentParser(description='A Dump 1090 to MQTT bridge')

    parser.add_argument('-r', '--radar-name', help="name of radar, used as topic string /adsb/<radar>/json", default='radar')
    parser.add_argument('-l', '--lat', type=float, help="Latitude of radar")
    parser.add_argument('-L', '--lon', type=float, help="Longitude of radar")
    parser.add_argument('-m', '--mqtt-host', help="MQTT broker hostname", default='127.0.0.1')
    parser.add_argument('-p', '--mqtt-port', type=int, help="MQTT broker port number (default 1883)", default=1883)
    parser.add_argument('-u', '--mqtt-user', help="MQTT broker user")
    parser.add_argument('-a', '--mqtt-password', help="MQTT broker password")
    parser.add_argument('-H', '--dump1090-host', help="dump1090 hostname", default='127.0.0.1')
    parser.add_argument('-P', '--dump1090-port', type=int, help="dump1090 port number (default 30003)", default=30003)
    parser.add_argument('-pdb', '--planedb', dest='pdb_host', help="Plane database host")
    parser.add_argument('-x', '--prox', dest='prox_topic', help="MQTT proximity topic", default="/adsb/proximity/json")
    parser.add_argument('-n', '--unk', dest='unknown_topic', help="MQTT unknown aircraft topic", default="/adsb/unknown")
    parser.add_argument('-v', '--verbose',  action="store_true", help="Verbose output")

    args = parser.parse_args()

    if not args.lat and not args.lon:
        print("You really need to tell me where you are located (--lat and --lon)")
        sys.exit(1)

    level = logging.DEBUG if args.verbose else logging.INFO

    styles = {'critical': {'bold': True, 'color': 'red'}, 'debug': {'color': 'green'}, 'error': {'color': 'red'}, 'info': {'color': 'white'}, 'notice': {'color': 'magenta'}, 'spam': {'color': 'green', 'faint': True}, 'success': {'bold': True, 'color': 'green'}, 'verbose': {'color': 'blue'}, 'warning': {'color': 'yellow'}}
    level = logging.DEBUG if '-v' in sys.argv or '--verbose' in sys.argv else logging.INFO
    if 1:
        coloredlogs.install(level=level, fmt='%(asctime)s.%(msecs)03d \033[0;90m%(levelname)-8s '
                            ''
                            '\033[0;36m%(filename)-18s%(lineno)3d\033[00m '
                            '%(message)s',
                            level_styles = styles)
    else:
        # Show process name
        coloredlogs.install(level=level, fmt='%(asctime)s.%(msecs)03d \033[0;90m%(levelname)-8s '
                                '\033[0;90m[\033[00m \033[0;35m%(processName)-15s\033[00m\033[0;90m]\033[00m '
                                '\033[0;36m%(filename)s:%(lineno)d\033[00m '
                                '%(message)s')

    logging.info("---[ Starting %s ]---------------------------------------------" % sys.argv[0])

    if args.pdb_host:
        planedb.init(args.pdb_host)

    tracker = FlightTracker(args.dump1090_host, args.mqtt_host, args.lat, args.lon, args.prox_topic, dump1090_port = args.dump1090_port, mqtt_port = args.mqtt_port, unknown_aircraft_topic = args.unknown_topic)
    tracker.run()  # Never returns


# Ye ol main
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(e, exc_info=True)
