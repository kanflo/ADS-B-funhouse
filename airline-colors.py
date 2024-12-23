#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-2024 Johan Kanflo (github.com/kanflo)
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
# Subscribes to the topic "adsb/proximity/json" and publishes a color fade to the
# topic "ghost/fade" according to operator an aircraft. The fade topic has the format
# '#rrggbbtt' where rr, gg, bb are RGB values and tt a time in seconds that the ghost will
# fade from black to the given color and then back to black, indicating an aircraft passong by
#

from typing import *
import imagecolor
import time
import sys
import logging
import coloredlogs
import time
import json
import argparse
import utils
try:
    import mqttwrapper
except ImportError:
    print("sudo -H python -m pip install git+https://github.com/kanflo/mqttwrapper")
    sys.exit(1)

# ICAO24 of current aircraft being tracked
current_icao24: str|None = None
# Last timestamp we received an update
last_update_time = time.time()


def mqtt_callback(topic: str, payload: str) -> list|tuple:
    del topic
    try:
        global args
        global current_icao24
        global last_update_time
        try:
            payload = payload.decode("utf-8")
            payload = payload.replace("\r", "")
            payload = payload.replace("\n", "")
            data = json.loads(payload)
        except Exception as e:
            logging.error(f"JSON load failed for '{payload}'", exc_info = e)
            return
        # Santetize data
        if not data["operator"] or not data["distance"] or not data["icao24"]:
            return
        if not data["lat"] or not data["lon"] or not data["speed"] or not data["heading"]:
            return

        icao24: str = data["icao24"]
        airline: str = data["operator"]
        distance_m: float = 1000 * data["distance"]

        if airline == "SAS":
            airline = "SAS Airlines"

        if "lost" in data:
            logging.debug("Lost sight of aircraft")
            current_icao24 = None
            return [(args.color_topic, "#000000")]
        try:
            # We always get the airline color before checking distance, that way
            # we will probably have the color when the airplane comes within
            # distance.
            color = imagecolor.get_color(airline)
            if color == (0, 0, 0):
                logging.info(f"No color found for {airline}, using default")
                color = (0, 255, 0)  # Just for fun
        except Exception as e:
            logging.error("get_color failed, using default", exc_info = e)
            color = (0, 255, 0)  # Just for fun

        # Our target went ouf of rance or we did not find the color
        if current_icao24 == icao24 and distance_m > args.max_distance:
            logging.info(f"Icao24 {icao24} went out of range")
            current_icao24 = None
            return [(args.color_topic, "#000000")]

        lat: float = float(data["lat"])
        lon: float = float(data["lon"])
        speed: float = float(data["speed"])
        heading: float = float(data["heading"])

        # New target found
        if current_icao24 is None and distance_m < args.max_distance:
            last_update_time = time.time()
            logging.info(f"New target found: {icao24}")
            current_icao24 = icao24
            (min_time, min_distance) = utils.find_time_min_distance(float(args.lat), float(args.lon), lat, lon, speed, heading)
            if min_time is None or min_distance is None:
                current_icao24 = None
                logging.info(f"Plane {icao24} is moving away")
            else:
                logging.info(f"Plane {icao24} reaches min distance {round(min_distance)}m after {round(min_time):d}s")
                return [(args.fade_topic, f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}{min_time:02x}")]

            logging.debug(f"Tracking {current_icao24} at {round(distance_m)}m (#{color[0]:02x}{color[1]:02x}{color[2]:02x})")

        #color_0 = int(color[0] * (1 - (distance / args.max_distance)))
        #color_1 = int(color[1] * (1 - (distance / args.max_distance)))
        #color_2 = int(color[2] * (1 - (distance / args.max_distance)))
        #color = (color_0, color_1, color_2)
    except Exception as e:
        logging.error("Exception occurred in MQTT callback", exc_info = e)


def main():
    global args
    global last_update_time
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--mqtt-host", dest="mqtt_host", help="MQTT broker hostname", default="127.0.0.1")
    parser.add_argument("-p", "--prox-topic", dest="prox_topic", help="ADSB MQTT proximity topic", default="/adsb/proximity/json")
    parser.add_argument("-t", "--color-topic", dest="color_topic", help="MQTT color topic", default="ghost/color")
    parser.add_argument("-f", "--fade-topic", dest="fade_topic", help="MQTT fade topic", default="ghost/fade")
    parser.add_argument("-d", "--max-distance", dest="max_distance", type=float, help="Max distance to light the ghost (m)", default=1000)
    parser.add_argument("-v", "--verbose", dest="verbose", action="store_true", help="Verbose output")
    parser.add_argument("-l", "--lat", dest="lat", type=float, help="Latitude of receiver", required=True)
    parser.add_argument("-L", "--lon", dest="lon", type=float, help="Longitude of receiver", required=True)

    args = parser.parse_args()

    imagecolor.load_color_data()

    styles = {"critical": {"bold": True, "color": "red"}, "debug": {"color": "green"}, "error": {"color": "red"}, "info": {"color": "white"}, "notice": {"color": "magenta"}, "spam": {"color": "green", "faint": True}, "success": {"bold": True, "color": "green"}, "verbose": {"color": "blue"}, "warning": {"color": "yellow"}}
    level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=level, fmt="%(asctime)s.%(msecs)03d \033[0;90m%(levelname)-8s "
                        ""
                        "\033[0;36m%(filename)-18s%(lineno)3d\033[00m "
                        "%(message)s",
                        level_styles = styles)
    logging.info(f"---[ Starting {sys.argv[0]} ]---------------------------------------------")

    try:
        mqttwrapper.run_script(mqtt_callback, broker=f"mqtt://{args.mqtt_host}", topics=[args.prox_topic], blocking=False)
        while True:
            time.sleep(5)
            if time.time() - last_update_time > 30 and current_icao24 is not None:
                mqttwrapper.publish(args.color_topic, "#000000")
    except Exception as e:
        logging.error("Caught exception", exc_info = e)


# Ye ol main
if __name__ == "__main__":
    main()
