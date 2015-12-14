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
import json
from pprint import pprint
import urllib
import os.path

# Bing image search for python
#
# Signup at
#  https://datamarket.azure.com/account/keys
#
# Add access to the Bing api at 
#  https://datamarket.azure.com/dataset/bing/search
#
# Add access to web search api at 
#  https://datamarket.azure.com/dataset/8818F55E-2FE5-4CE3-A617-0B8BA8419F65
#
# Get your API key from
#  https://datamarket.azure.com/account/keys
#
# import this module and call bing.setKey(yourKey)
# followed by bing.search("nyan cat")


# Supported image formats
extensions = ['jpg', 'jpeg', 'png']
apiKey = None

# Set api key
def setKey(key):
	global apiKey
	apiKey = key

# Search for 'keywords' and return image URLs in a list or None if, well, none
# are found or an error occurred
#
# options is a hash and the following keys are supported:
#  'numResults' number of images to query for (default 20)
#  'minWidth'   only include images with minimum width
#  'minHeight'  and minimum height
#  'debug'      print debug info
#  'saveData'   save query result to a file named options['saveData']
#  'loadData'   skip API call and load JSON from a file named options['loadData']
def imageSearch(keywords, options = None):
	global apiKey
	global extensions
	imgs = []
	if not apiKey:
		raise Exception('Bing API key not speified')
	debug = options and 'debug' in options and options['debug']
	if not options or (options and not 'loadData' in options):
		credentialBing = 'Basic ' + (':%s' % apiKey).encode('base64')[:-1] # the "-1" is to remove the trailing "\n" which encode adds
		searchString = (urllib.quote_plus("'%s'" % keywords))
		if options and 'numResults' in options:
			count = options['numResults']
		else:
			count = 20
		offset = 0

		url = 'https://api.datamarket.azure.com/Bing/Search/v1/Image?' + \
		      'Query=%s&$top=%d&$skip=%d&$format=json' % (searchString, count, offset)

		request = urllib2.Request(url)
		request.add_header('Authorization', credentialBing)
		requestOpener = urllib2.build_opener()
		response = requestOpener.open(request) 
		results = json.load(response)

		if options and 'saveData' in options:
			with open(options['saveData'], 'w') as f:
				f.write(json.dumps(results))
	else:
		with open(options['loadData']) as f:
			results = json.load(f)

	if not 'd' in results:
		return None
	if not 'results' in results['d']:
		return None
	for r in results['d']['results']:
		include = True
		if options and 'minWidth' in options and int(r['Width']) < options['minWidth']:
			include = False
		if options and 'minHeight' in options and int(r['Height']) < options['minHeight']:
			include = False
		extension = os.path.splitext(r['MediaUrl'])[-1][1:].lower()
		if not extension in extensions:
			include = False

		if include:
			if debug:
				print "+",
			imgs.append(r['MediaUrl'])
		else:
			if debug:
				print "-",
		if debug:
			print "[%4d x %4d] %s" % (int(r['Width']), int(r['Height']), r['MediaUrl'])

	return imgs
