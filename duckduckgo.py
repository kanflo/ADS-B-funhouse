"""
Based on https://github.com/deepanprabhu/duckduckgo-images-api/blob/master/duckduckgo_images_api/api.py
"""

from typing import *
import requests
import re
import json
import logging

def search(keywords: str, max_results: int = 10) -> list:
    """Search DuckDuckGo for keywords

    Args:
        keywords (str): Keywords to search for
        max_results (int, optional): Requested number of search results. Defaults to 10.

    Returns:
        list: A list of dictionaries containing the following fields:
                "image"     : image URL
                "url"       : URL of page where image was found
                "height"    : height of image
                "width"     : width of image
                "title"     : title of page
                "source"    : No idea, often "Bing"
                "thumbnail" : URL of thumbnail
        None: in case of errors
    """
    url = 'https://duckduckgo.com/'
    params = {'q': keywords}
    headers = {
        'authority': 'duckduckgo.com',
        'accept': 'application/json, text/javascript, */* q=0.01',
        'sec-fetch-dest': 'empty',
        'x-requested-with': 'XMLHttpRequest',
        'user-agent': 'Mozilla/5.0 (Macintosh Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.163 Safari/537.36',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'cors',
        'referer': 'https://duckduckgo.com/',
        'accept-language': 'en-US,enq=0.9',
    }

    # First make a request to above URL, and parse out the 'vqd'
    # This is a special token, which should be used in the subsequent request
    res = requests.post(url, headers = headers, data = params)
    if res.status_code != 200:
        logging.error("DuckDuckGo responded with %d" % (res.status_code))
        return None
    search_obj = re.search(r'vqd=([\d-]+)\&', res.text, re.M|re.I)

    if not search_obj:
        logging.error("Token parsing failed")
        return None

    params = (
        ('l', 'us-en'),
        ('o', 'json'),
        ('q', keywords),
        ('vqd', search_obj.group(1)),
        ('f', ',,,'),
        ('p', '1'),
        ('v7exp', 'a'),
    )

    request_url = url + "i.js"
    search_results = []
    counter = 0
    while True:
        try:
            res = requests.get(request_url, headers = headers, params = params)
            if res.status_code != 200:
                logging.error("DuckDuckGo responded with %d" % (res.status_code))
                return search_results
            data = json.loads(res.text)
        except ValueError as e:
            logging.error("Caught exception", exc_info = True)
            continue

        for foo in data["results"]:
            search_results.append(foo)
            counter += 1
            if counter == max_results:
                return search_results

        if "next" not in data:
            return search_results

        request_url = url + data["next"]
