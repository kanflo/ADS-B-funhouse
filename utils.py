#pyright: strict

#import typing import (
#
#)
import logging
import math
import bing
import planedb
from datetime import datetime


def deg2rad(deg: float) -> float:
    """Convert degrees to radians

    Arguments:
        deg {float} -- Angle in degrees

    Returns:
        float -- Angle in radians
    """
    return deg * (math.pi/180)


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate bearing from lat1/lon2 to lat2/lon2

    Arguments:
        lat1 {float} -- Start latitude
        lon1 {float} -- Start longitude
        lat2 {float} -- End latitude
        lon2 {float} -- End longitude

    Returns:
        float -- bearing in degrees
    """
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    #rlon1 = math.radians(lon1)
    #rlon2 = math.radians(lon2)
    dlon = math.radians(lon2-lon1)

    b = math.atan2(math.sin(dlon)*math.cos(rlat2),math.cos(rlat1)*math.sin(rlat2)-math.sin(rlat1)*math.cos(rlat2)*math.cos(dlon)) # bearing calc
    bd = math.degrees(b)
    _ ,bn = divmod(bd+360, 360) # the bearing remainder and final bearing

    return bn


def coordinate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between the two coordinates

    Arguments:
        lat1 {float} -- Start latitude
        lon1 {float} -- Start longitude
        lat2 {float} -- End latitude
        lon2 {float} -- End longitude

    Returns:
        float -- Distance in meters
    """
    R = 6371 # Radius of the earth in km
    dLat = deg2rad(lat2-lat1)
    dLon = deg2rad(lon2-lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + math.cos(deg2rad(lat1)) * math.cos(deg2rad(lat2)) * math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    d = R * c * 1000 #  Distance in m
    return d


def calc_travel2(lat: float, lon: float, duration_s: float, speed_kts: float, heading: float):
    """Calculate travel from lat, lon starting given speed, heading and duration

    Arguments:
        lat {float} -- Starting latitude
        lon {float} -- Starting longitude
        duration_s {float} -- Travel duration in seconds
        speed_kts {float} -- Speed in knots
        heading {float} -- Heading in degress

    Returns:
        Tuple[float, float] -- The new lat/lon as a tuple
    """
    R = 6378.1 # Radius of the Earth
    brng = math.radians(heading) # Bearing is 90 degrees converted to radians.
    speed_mps = 0.514444 * speed_kts # knots -> m/s
    d = (duration_s * speed_mps) / 1000.0 # Distance in km

    lat1 = math.radians(lat) # Current lat point converted to radians
    lon1 = math.radians(lon) # Current long point converted to radians

    lat2 = math.asin(math.sin(lat1)*math.cos(d/R) + math.cos(lat1)*math.sin(d/R)*math.cos(brng))
    lon2 = lon1 + math.atan2(math.sin(brng)*math.sin(d/R)*math.cos(lat1), math.cos(d/R)-math.sin(lat1)*math.sin(lat2))

    lat2 = math.degrees(lat2)
    lon2 = math.degrees(lon2)

    return (lat2, lon2)


def calc_travel(lat: float, lon: float, utc_start: datetime, speed_kts: float, heading: float) -> tuple[float, float]:
    """Calculate travel from lat, lon starting at a utc_start with given speed and heading to now

    Arguments:
        lat {float} -- Starting latitude
        lon {float} -- Starting longitude
        utc_start {datetime} -- Start time
        speed_kts {float} -- Speed in knots
        heading {float} -- Heading in degress

    Returns:
        Tuple[float, float] -- The new lat/lon as a tuple
    """
    age = datetime.utcnow() - utc_start
    age_s = age.total_seconds()
    return calc_travel2(lat, lon, age_s, speed_kts, heading)


def blacklisted(url: str) -> bool:
    """Return True if the URL points to a blacklisted source (ie. one that is on to us and reponds with a 403)

    Args:
        url (str): URL to image

    Returns:
        bool: True if URL is blacklisted
    """
    if "airliners.net" in url:
        return True
    if "planefinder.net" in url:
        return True
    if "carsbase.com" in url:
        return True
    return False


def image_search(icao24: str, operator: str|None = None, type: str|None = None, registration: str|None = None, update_planedb: bool = True) -> str:
    """Search Bing for plane images. If found, update planedb with URL

    #TODO: This is currently broken

    Arguments:
        icao24 {str} -- ICAO24 designation
        operator {str} -- Operator of aircraft
        type {str} -- Aircraft type
        registration {str} -- Aircraft registration

    Returns:
        str -- URL of image, hopefully

    @todo: don't search for
        Bluebird Nordic Boeing 737 4Q8SF TF-BBM
    but rather
        "Bluebird Nordic" "Boeing 737" "TF-BBM"
    or
        "Bluebird Nordic" "TF-BBM"
    or
        "Bluebird Nordic" Boeing "TF-BBM"
    """
    img_url = None
    # Bing sometimes refuses to search for "Scandinavian Airlines System" :-/
    op = None
    if operator is not None:
        op = operator.replace("Scandinavian Airlines System", "SAS")
    searchTerm = ""
    if op is not None:
        searchTerm = "%s %s" % (searchTerm, op)
    if type is not None:
        searchTerm = "%s %s" % (searchTerm, type)
    if registration is not None:
        searchTerm = "%s %s" % (searchTerm, registration)
    logging.debug("Searching for %s" % searchTerm)
    imageUrls = bing.imageSearch(searchTerm)
    if not imageUrls:
        imageUrls = bing.imageSearch(registration)
    if imageUrls:
        # Filter sources as picking a random image has been known to produce naked women...
        img_url = None
        for temp in imageUrls:
            # These are prisitine sources
            if "planespotters" in temp or "jetphotos" in temp:
                img_url = temp
                break
        if img_url is None:
            for temp in imageUrls:
                if blacklisted(temp):
                    continue
                if "flugzeug" in temp or "plane" in temp or "airport" in temp:
                    img_url = temp
                    break
        if update_planedb and img_url is not None:
            logging.info("Added image %s for %s", img_url, icao24)
            if not planedb.update_aircraft(icao24, {'image' : img_url}):
                logging.error("Failed to update PlaneDB image for %s" % (icao24))
        return img_url
    else:
        logging.error("Image search came up short for '%s', blacklisted (%s)?" % (searchTerm, icao24))
    return img_url

def find_time_min_distance(my_lat: float, my_lon: float, lat: float, lon: float, speed_kts: float, heading: float) -> tuple[float|None, float|None]:
    """Find minimum distance and how long until the aircraft reaches that distance

    Args:
        my_lat (float): Latitude of receiver
        my_lon (float): Longitude of receiver
        lat (float): Latitude of aircraft
        lon (float): Longitude of aircraft
        speed_kts (float): Aircraft speed in knots
        heading (float): Aircraft heading in degrees

    Returns:
        tuple[float|None, float|None]: Time and min distance or (None, None) if plane is moving away
    """
    min_distance: float = 1e9
    min_time: float = 0
    time_step_s: float = 0.5
    time: float = 0
    initial_distance: float = coordinate_distance(my_lat, my_lon, lat, lon)

    for _ in range(1, 60 * int(1/time_step_s)):
        (new_lat, new_lon) = calc_travel2(lat, lon, time, speed_kts, heading)
        distance: float = coordinate_distance(my_lat, my_lon, new_lat, new_lon)
        if distance < min_distance:
            min_distance = distance
            min_time = time
        #print(f"[{time:.2f}] : {distance:.3f}")
        time += time_step_s

    if initial_distance < min_distance or min_time == 0:
        return (None, None)
    return (round(min_time), min_distance)


if __name__ == "__main__":
    home_lat: float = 45.1
    home_lon: float = 14.1
    start_lat: float = 45.2
    start_lon: float = 14
    speed_kts: float = 120
    heading: float = 170
    min_distance: float|None
    min_time: float|None

    # Plane moving out way
    (min_time, min_distance) = find_time_min_distance(home_lat, home_lon, start_lat, start_lon, speed_kts, heading)
    if min_time is None or min_distance is None:
        print("Plane is moving away")
    else:
        print(f"Min distance after {round(min_time):d}s: {min_distance:.1f} meters")

    # Plane moving away
    heading = 270
    (min_time, min_distance) = find_time_min_distance(home_lat, home_lon, start_lat, start_lon, speed_kts, heading)
    if min_time is None or min_distance is None:
        print("Plane is moving away")
    else:
        print(f"Min distance after {round(min_time):d}s: {min_distance:.1f} meters")