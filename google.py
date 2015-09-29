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

import urllib2
import cStringIO
import json
import os
import socket
import logging
from StringIO import StringIO
import gzip

log = logging.getLogger(__name__)

# Perform a Goolge Image search for 'searchTerm' and return an image with
# width minWidth and aspect ratio between 1.3 and 1.55
# Returns (urlString, imageData) or (None, None) in case of en error
def imageSearch(searchTerm, minWidth = 0):
    searchTerm = searchTerm.replace(" ", "+")

    headers = [ ('Accept-Language', 'en-us'),
				('Accept-Encoding', 'gzip, deflate'),
				('Connection', 'close'),
				('Accept', 'application/json, text/javascript, */*; q=0.01'),
				('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) AppleWebKit/600.8.9 (KHTML, like Gecko) Version/7.1.8 Safari/537.85.17'),
				('DNT', '1')
				 ]

    if 0: # Add proxy for debugging
        proxy = urllib2.ProxyHandler({'http': '127.0.0.1:8888'})
        fetcher = urllib2.build_opener(proxy)
    else:
        fetcher = urllib2.build_opener()
    fetcher.addheaders = headers

    log.debug(">>> Googeling '%s'" % searchTerm)
    startIndex = 0

    while startIndex < 25:
        searchUrl = "http://ajax.googleapis.com/ajax/services/search/images?v=1.0&q=" + searchTerm + "&start=%d" % (startIndex)
        try:
            f = fetcher.open(searchUrl, timeout = 10)
        except UnicodeEncodeError, e:
            log.critical("Google UnicodeEncode error: %s" % (e))
            log.critical("searchTerm : '%s'" % (searchTerm))
            return (None, None)
        except urllib2.error, e: # [Errno 61] Connection refused>
            log.critical("Google error: %s" % (e))
            return (None, None)

        data = f.read()
        if f.info().get('Content-Encoding') == 'gzip':
            buf = StringIO(data)
            f = gzip.GzipFile(fileobj=buf)
            data = f.read()

        j = json.loads(data)
        if not len(j['responseData']['results']):
            return (None, None)
        count = len(j['responseData']['results'])
        startIndex += count
        for i in range(0, count):
            url = j['responseData']['results'][i]['unescapedUrl']
            height = float(j['responseData']['results'][i]['height'])
            width = float(j['responseData']['results'][i]['width'])
            aspectRatio = width / height
            if width >= minWidth and aspectRatio > 1.3 and aspectRatio < 1.55:
                fileName, fileExtension = os.path.splitext(url)
                if fileExtension != ".svg" and fileExtension != ".gif":
                    log.debug("%d x %d (%.2f) - %s" % (width, height, aspectRatio, url))
                    log.debug("Fetching %s" % url)
                    fetcher = urllib2.build_opener()
                    fetcher.addheaders = headers
                    counter = 3
                    while counter > 0:
                        try:
                            f = fetcher.open(url, timeout = 10)
                            data = f.read()
                            if f.info().get('Content-Encoding') == 'gzip':
                                buf = StringIO(data)
                                f = gzip.GzipFile(fileobj=buf)
                                data = f.read()
                            return (url, data)
                        except socket.timeout, e:
                            # For Python 2.7
                            log.critical("  Timeout, retrying")
                            counter -= 1
                            pass
                        except urllib2.HTTPError, e:
                            log.critical("HTTP error: %s" % (e))
                            log.critical("searchTerm : '%s'" % (searchTerm))
                            return (None, None)
                        except UnicodeEncodeError, e:
                            log.critical("UnicodeEncodeError error: %s" % (e))
                            log.critical("searchTerm : '%s'" % (searchTerm))
                            return (None, None)
                        except urllib2.URLError, e:
                            log.critical("URLError error: %s" % (e))
                            log.critical("searchTerm : '%s'" % (searchTerm))
                            return (None, None)
    return (None, None)
