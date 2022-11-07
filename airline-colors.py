#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021 Johan Kanflo (github.com/kanflo)
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
# Subscribes to the topic 'adsb/proximity/json' and publishes a color to the
# topic 'ghost/led' according to operator/distance of an aircraft.
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
try:
    import mqttwrapper
except ImportError:
    print("sudo -H python -m pip install git+https://github.com/kanflo/mqttwrapper")
    sys.exit(1)


current_color = (0, 0, 0)
color_time = time.time()


def mqtt_callback(topic: str, payload: str) -> Optional[list[tuple]]:
    try:
        global args
        global current_color
        global color_time
        try:
            payload = payload.decode("utf-8")
            payload = payload.replace("\r", "")
            payload = payload.replace("\n", "")
            data = json.loads(payload)
        except Exception as e:
            logging.error("JSON load failed for '%s'" % (payload), exc_info=True)
            return

        if data["operator"] and data["distance"]:
            airline = data["operator"]
            distance = data["distance"]
            lost = False
            if "lost" in data:
                lost = data["lost"]

            if airline == "SAS":
                airline = "SAS Airlines"

            if lost:
                logging.debug("Lost sight of aircraft")
                color = (0, 0, 0)
            else:
                try:
                    # We always get the airline color before checking distance, that way
                    # we will probably have the color when the airplane comes within
                    # distance.
                    color = imagecolor.get_color(airline)
                except Exception as e:
                    logging.error("get_color failed  %s" % (e), exc_info = True)
                    return
            if distance > args.max_distance or not color:
                color = (0, 0, 0)
            else:
                if color != current_color or current_color == (0, 0, 0):
                    logging.debug("Tracking %s at %dkm (#%02x%02x%02x)" % (airline, distance, color[0], color[1], color[2]))

                color_0 = int(color[0] * (1 - (distance / args.max_distance)))
                color_1 = int(color[1] * (1 - (distance / args.max_distance)))
                color_2 = int(color[2] * (1 - (distance / args.max_distance)))
                color = (color_0, color_1, color_2)
            if color != current_color:
                logging.debug("New color is %02x%02x%02x (%d)" % (color[0], color[1], color[2], 1000*distance))
                current_color = color
                resp = (args.color_topic, "#%02x%02x%02x" % (color[0], color[1], color[2]))
                color_time = time.time()
                return [resp]
    except Exception as e:
        logging.error("Exception occurred in MQTT callback", exc_info = True)


def main():
    global args
    global current_color
    global color_time
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--mqtt-host', dest='mqtt_host', help="MQTT broker hostname", default='127.0.0.1')
    parser.add_argument('-p', '--prox-topic', dest='prox_topic', help="ADSB MQTT proximity topic", default="/adsb/proximity/json")
    parser.add_argument('-t', '--color-topic', dest='color_topic', help="MQTT color topic", default="ghost/color")
    parser.add_argument('-d', '--max-distance', dest='max_distance', type=float, help="Max distance to light the LED (km)", default=10.0)
    parser.add_argument('-v', '--verbose', dest='verbose', action="store_true", help="Verbose output")
    parser.add_argument('-l', '--logger', dest='log_host', help="Remote log host")

    args = parser.parse_args()

    imagecolor.load_color_data()

    styles = {"critical": {"bold": True, "color": "red"}, "debug": {"color": "green"}, "error": {"color": "red"}, "info": {"color": "white"}, "notice": {"color": "magenta"}, "spam": {"color": "green", "faint": True}, "success": {"bold": True, "color": "green"}, "verbose": {"color": "blue"}, "warning": {"color": "yellow"}}
    level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=level, fmt="%(asctime)s.%(msecs)03d \033[0;90m%(levelname)-8s "
                        ""
                        "\033[0;36m%(filename)-18s%(lineno)3d\033[00m "
                        "%(message)s",
                        level_styles = styles)
    logging.info("---[ Starting %s ]---------------------------------------------" % sys.argv[0])

    try:
        mqttwrapper.run_script(mqtt_callback, broker="mqtt://%s" % (args.mqtt_host), topics=[args.prox_topic], blocking=False)
        while True:
            time.sleep(5)
            if time.time() - color_time > 15 and current_color != (0, 0, 0):
                mqttwrapper.publish(args.color_topic, "#000000")
                current_color = (0, 0, 0)
    except Exception as e:
        logging.error("Caught exception", exc_info = True)


# Ye ol main
if __name__ == "__main__":
    main()
