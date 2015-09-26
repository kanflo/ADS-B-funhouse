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
# Download BaseStation.sqb from http://planebase.biz/bstnsqb to add information
# about plane type and operator to the radar.
#

import sqlite3
import datetime
import dateutil.parser
import logging

log = logging.getLogger(__name__)

class Plane(object):
  def __init__(self):
    self.icao24 = None
    self.registration = None
    self.manufacturer = None
    self.type = None
    self.operator = None

class PlaneDB(object):
  def __init__(self, dbPath):
    global log
    self.path = dbPath
    self.db = sqlite3.connect(self.path)
    self.db.row_factory = sqlite3.Row
    self.db.text_factory = str
    c = self.db.cursor()
    c.execute("select count(*) from sqlite_master where type='table';")
    r = c.fetchone()
    if r[0] == 0:
      log.info("Initialized %s" % (self.path))
      self.dbInitialize()
    else:
      log.info("Opened %s" % (self.path))


  """Initialize database"""
  def dbInitialize(self):
    c = self.db.cursor()    
    c.execute("CREATE TABLE IF NOT EXISTS Aircraft(ModeS varchar(6) NOT NULL UNIQUE, Registration varchar(20), Manufacturer varchar(60), Type varchar(40), RegisteredOwners varchar(100), `FirstCreated` datetime NOT NULL);")
    self.db.commit()

  """Find aircraft based on icao24"""
  def find(self, icao24):
    plane = None
    c = self.db.cursor()    
    c.execute("SELECT * FROM Aircraft WHERE ModeS=?;", (icao24,))
    row = c.fetchone()
    if row:
      plane = Plane()
      plane.icao24 = row["ModeS"]
      plane.registration = row["Registration"]
      if row["Manufacturer"]:
        plane.type = "%s %s" % (row["Manufacturer"], row["Type"])
      else:
        plane.type = row["Type"]
      plane.operator = row["RegisteredOwners"]
    return plane

  """Add a plane to the db"""
  def add(self, plane):
    c = self.db.cursor()    
    c.execute("INSERT OR REPLACE INTO Aircraft(ModeS, Registration, Manufacturer, Type, RegisteredOwners, FirstCreated) VALUES(?, ?, ?, ?, ?, ?);", (plane.icao24, plane.registration, plane.manufacturer, plane.type, plane.operator, datetime.datetime.now()))
    self.db.commit()

