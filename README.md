**ADS-B funhouse**
==========

This is a collection of Python scripts for playing with [ADS-B](https://en.wikipedia.org/wiki/Automatic_dependent_surveillance-broadcast) data from [dump1090](https://github.com/antirez/dump1090). You will need an [rtl-sdr](http://sdr.osmocom.org/trac/wiki/rtl-sdr) receiver to join the fun.

## adsbclient.py

This is yet another ADS-B decoder written in Python. It feeds off port 30003 on your dump1090 receiver and is invoked using:

`% adsbclient.py -m <dump1090 host> -H <MQTT host> -r <radar name> -pdb PlaneBase.sqb`

The MQTT publish topic is `/adsb/<radar name>/json` and the JSON data contains the following fields:

| Key          |  Description                              | Sample data                   |
| ------------ | ----------------------------------------- | ----------------------------- |
| icao24       | ICAO24 designator                         | "4787B0"
| loggedDate   | Local timestamp                           | "2015-09-08 21:08:26.061000" 
| operator     | Name of airline                           | "Cathay Pacific Airways"
| type         | Type of aircraft                          | "Boeing 777 367ER"
| registration | Aircrafts ICAO registration               | "B-KPY"
| callsign     | Flight's callsign                         | "CPA257"
| lost         | `true` if receiver lost sight of aircraft | `false`
| track        | Track [degrees]                           | 131 
| groundSpeed  | Ground speed [knots]                      | 413 
| altitude     | Altitude [feet]                           | 17500 
| lon          | Lontitudee                                | 13.33108 
| lat          | Latitude                                  | 55.29126
| verticalRate | Vertical climb/descend rate [ft/min]      | 2240

The aircraft's operator, type and registration are not available in the ADS-B data the aircraft transmits and needs to be pulled from another data source. On excellent source is [PlaneBaseNG](http://planebase.biz) and can be downloaded [here](http://planebase.biz/bstnsqb). If you often see aircrafts that are not found in PlaneBase.sqb you can add them manually to your own database and tell adsbclient.py to search it using the argument `--myplanedb`. Invoking adsbclient.py with a non existent database will create and initialize the database in the specified file.

The following arguments are supported by adsbclient.py:

| Key          |  Description |
| ------------ | ------------- |
| --help       | well...
| --radar-name RADAR_NAME   | name of radar, used as topic string /adsb/RADAR_NAME/json
| --mqtt-host HOST | MQTT broker hostname
| --mqtt-port PORT | MQTT broker port number (default 1883)
| --dump1090-host HOST | dump1090 hostname
| --dump1090-port PORT | dump1090 port number (default 30003)
| --verbose | Verbose output
| --basestationdb DB | BaseStation SQLite DB 
| --myplanedb DB | Your own SQLite DB with the same structure as BaseStation.sqb where you can add planes missing from BaseStation db

-
Released under the MIT license. Have fun!