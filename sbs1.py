"""
SBS-1 parser in python

The parser is a Python conversion of the JavaScript one in the node-sbs1
project by John Wiseman (github.com/wiseman/node-sbs1)

"""

import sys
try:
  import dateutil.parser
except ImportError:
  print("dateutil module not installed, try 'sudo pip install python-dateutil'")
  sys.exit(1)

import logging

log = logging.getLogger(__name__)

class TransmissionType:
  ES_IDENT_AND_CATEGORY = 1
  ES_SURFACE_POS = 2
  ES_AIRBORNE_POS = 3
  ES_AIRBORNE_VEL = 4
  SURVEILLANCE_ALT = 5
  SURVEILLANCE_ID = 6
  AIR_TO_AIR = 7
  ALL_CALL_REPLY = 8


class SBS1Message (object):
  """A message parsed from the feed output by dump1090 on port 30003

  An SBS-1 message has the following attributes:

    isValid : bool (set if the message is valid)
    messageType : string
    transmissionType : sbs1.TransmissionType
    sessionID : int
    aircraftID : int
    icao24 : string
    flightID : int
    generatedDate : datetime
    loggedDate : datetime
    callsign : string
    altitude : int
    groundSpeed : int
    track : int
    lat : float
    lon : float
    verticalRate : int
    squawk : int
    alert : bool
    emergency : bool
    spi : bool
    onGround : bool

  A field not present in the parsed message will be set to None. For a
  description of the attributes, please see github.com/wiseman/node-sbs1
  """

  """Create an SBS1Message object from the string sbs1Message"""
  def __init__(self, sbs1Message):
    sbs1Message = sbs1Message.decode('utf-8')
    parts = sbs1Message.split(',');
    self.isValid = True # Always an optimist
    self.messageType = self.parseString(parts, 0)
    if self.messageType != "MSG":
      self.messageType = None
      self.isValid = False
    self.transmissionType = self.parseInt(parts, 1)
    self.sessionID = self.parseString(parts, 2)
    self.aircraftID = self.parseString(parts, 3)
    self.icao24 = self.parseString(parts, 4)
    self.flightID = self.parseString(parts, 5)
    self.generatedDate = self.parseDateTime(parts, 6, 7)
    self.loggedDate = self.parseDateTime(parts, 8, 9)
    self.callsign = self.parseString(parts, 10)
    if self.callsign:
      self.callsign = self.callsign.strip()
    self.altitude = self.parseInt(parts, 11)
    self.groundSpeed = self.parseInt(parts, 12)
    self.track = self.parseInt(parts, 13)
    self.lat = self.parseFloat(parts, 14)
    self.lon = self.parseFloat(parts, 15)
    self.verticalRate = self.parseInt(parts, 16)
    self.squawk = self.parseInt(parts, 17)
    self.alert = self.parseBool(parts, 18)
    self.emergency = self.parseBool(parts, 19)
    self.spi = self.parseBool(parts, 20)
    self.onGround = self.parseBool(parts, 21)

  def dump(self):
    if self.messageType == None:
      print("Illegal message")
      return
    else:
      print("messageType      : %s" % self.messageType)
    if self.transmissionType != None:
      print("transmissionType : %s" % self.transmissionType)
    if self.sessionID != None:
      print("sessionID        : %s" % self.sessionID)
    if self.aircraftID != None:
      print("aircraftID       : %s" % self.aircraftID)
    if self.icao24 != None:
      print("icao24           : %s" % self.icao24)
    if self.flightID != None:
      print("flightID         : %s" % self.flightID)
    if self.generatedDate != None:
      print("generatedDate    : %s" % self.generatedDate)
    if self.loggedDate != None:
      print("loggedDate       : %s" % self.loggedDate)
    if self.callsign != None:
      print("callsign         : %s" % self.callsign)
    if self.altitude != None:
      print("altitude         : %s" % self.altitude)
    if self.groundSpeed != None:
      print("groundSpeed      : %s" % self.groundSpeed)
    if self.track != None:
      print("track            : %s" % self.track)
    if self.lat != None and self.lon != None:
      print("lat, lon         : %s, %s" % (self.lat, self.lon))
    if self.verticalRate != None:
      print("verticalRate     : %s" % self.verticalRate)
    if self.squawk != None:
      print("squawk           : %s" % self.squawk)
    if self.alert != None:
      print("alert            : %s" % self.alert)
    if self.emergency != None:
      print("emergency        : %s" % self.emergency)
    if self.spi != None:
      print("spi              : %s" % self.spi)
    if self.onGround != None:
      print("onGround         : %s" % self.onGround)

  """Parse string at given index in array
  Return string or None if string is empty or index is out of bounds"""
  def parseString(self, array, index):
    try:
      value = array[index]
      if len(value) == 0:
        value = None
    except ValueError:
      value = None
    except TypeError:
      value = None
    except IndexError:
      value = None

    return value

  """Parse boolean at given index in array
  Return boolean value or None if index is out of bounds or type casting failed"""
  def parseBool(self, array, index):
    try:
      value = bool(int(array[index]))
    except ValueError:
      value = None
    except TypeError:
      value = None
    except IndexError:
      value = None
    return value

  """Parse int at given index in array
  Return int value or None if index is out of bounds or type casting failed"""
  def parseInt(self, array, index):
    try:
      value = int(array[index])
    except ValueError:
      value = None
    except TypeError:
      value = None
    except IndexError:
      value = None
    return value


  """Parse float at given index in array
  Return float value or None if index is out of bounds or type casting failed"""
  def parseFloat(self, array, index):
    try:
      value = float(array[index])
    except ValueError:
      value = None
    except TypeError:
      value = None
    except IndexError:
      value = None
    return value

  """Parse date and time at given indexes in array
  Return datetime value or None if indexes are out of bounds or type casting failed"""
  def parseDateTime(self, array, dateIndex, timeIndex):
    d = None
    date = self.parseString(array, dateIndex)
    time = self.parseString(array, timeIndex)
    if date != None and time != None:
      try:
        d = dateutil.parser.parse("%s %s" % (date, time))
      except ValueError:
        d = None
      except TypeError:
        d = None
    return d
