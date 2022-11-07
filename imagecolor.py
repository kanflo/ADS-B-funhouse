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

from typing import *
import os
from urllib.request import urlopen
import io
import json
import logging
import duckduckgo
try:
    from colorthief import ColorThief
except ImportError:
    print("Color Thief module not found, install using 'sudo -H python -m pip install colorthief'")
    exit(1)


def get_prominent_color(search_term: str) -> tuple:
    logging.debug("Searching for %s" % search_term)
    try:
        images = duckduckgo.search(search_term)
    except Exception as e:
        logging.error("Search exception error: %s" % (e))
        return None

    color = (0, 0, 0)
    for image in images:
        if image["height"] > 3000 or image["width"] > 3000:
            logging.debug("Image %s too large (WxH : %dx%d)" % (image["image"], image["width"], image["height"]))
            continue
        _, fileExtension = os.path.splitext(image["image"])
        if fileExtension != ".svg" and fileExtension != ".gif":
            try:
                logging.debug("Fetching %s" % (image["image"]))
                fd = urlopen(image["image"])
                f = io.BytesIO(fd.read())
                color_thief = ColorThief(f)
                color = color_thief.get_color(quality=1)
            except Exception as e:
                logging.error("Image fetch caused exception", exc_info = True)
                continue
            return (color, image["image"])

    # In case we cannot find a color, make sure we don't end up here in 10 milliseconds
    return ((0,0,0), "error")


def load_color_data():
    global colors
    try:
        colors = json.load(open("logocolors.json"))
    except:
        colors = {}
    return colors

def get_color(key: str) -> tuple:
    global colors
    if key in colors:
        color = colors[key]["color"]
    else:
        (color, url) = get_prominent_color(key + " logo")
        if color and url:
            colors[key] = {}
            colors[key]["color"] = color
            colors[key]["url"] = url
            colors[key]["hex"] = "%02x%02x%02x" % (color[0], color[1], color[2])
            logging.info("New color: %s : #%s" % (key, colors[key]["hex"]))
            with open("logocolors.json", "w+") as f:
                f.write(json.dumps(colors))
    return color
