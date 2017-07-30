import time, datetime
import collections
import logging
from pprint import pprint

__all__ = ['RadarDataBufferError','RDBTypeError','RadarDataBuffer','RadarSensorMeta']


sourceTypes = ["ANDROID", "EMPATICA", "PEBBLE", "BIOVOTION"]
sensorTypes = ["ACCELEROMETER", "BATTERY", "BLOOD_VOLUME_PULSE", "ELECTRODERMAL_ACTIVITY", "INTER_BEAT_INTERVAL", "HEART_RATE", "THERMOMETER"]

status_desc = {
                "GOOD": {"priority": 1, "th_min": 0, "th_bat": 0.25, "color": "lightgreen"},
                "OK": {"priority": 2, "th_min": 2, "th_bat": 0.10, "color": "moccasin"},
                "WARNING": {"priority": 3, "th_min": 3, "th_bat": 0.05, "color": "orange"},
                "CRITICAL": {"priority": 4, "th_min": 5, "th_bat": 0, "color": "red"},
                "DISCONNECTED": {"priority": 0, "th_min": 10, "th_bat": -1, "color": "transparent"},
                "N/A": {"priority": -1, "th_min": -1, "th_bat": -1, "color": "lightgrey"}
              }

datastampformat = "%Y-%m-%dT%H:%M:%SZ"
utcOffset = time.timezone - (time.daylight * 3600)

class RadarDataBufferError(Exception):
  def __init__(self, msg=None):
    if msg is None: msg = "An error occured in RadarDataBuffer."
    super().__init__(msg)

class RDBTypeError(RadarDataBufferError):
  def __init__(self, type, allowed):
    super().__init__("given type {} not in allowed types {}.".format(type, allowed))
    self.type = type
    self.allowed = allowed

class RDBMetaError(RadarDataBufferError):
  def __init__(self, sensor):
    super().__init__("MetaData error for sensor type {}.".format(sensor))
    self.sensor = sensor


class RadarDataBuffer(object):
  def __init__(self, sourceType, sensors=sensorTypes, maxlen=None):
    self.sourceType = sourceType
    self.sensors = sensors
    self.maxlen = maxlen
    self.checkType(self.sourceType, sourceTypes)

    self.meta = { k:RadarSensorMeta(k) for k in self.sensors }
    self.buffer = { k:collections.deque(maxlen=self.maxlen) for k in self.sensors }


  def checkType(self, type, allowed):
    if type not in allowed:
      raise RDBTypeError(type, allowed)

  def addSample(self, sensorType, sample):
    self.checkType(sensorType, self.sensors)
    self.buffer[sensorType].append(sample)
    self.updateMeta()

  def addSamples(self, sensorType, samples):
    self.checkType(sensorType, self.sensors)
    self.buffer[sensorType].extend(samples)
    self.updateMeta()

  def replaceSamples(self, sensorType, samples):
    self.checkType(sensorType, self.sensors)
    self.buffer[sensorType].clear()
    self.buffer[sensorType].extend(samples)
    self.updateMeta()

  def updateMeta(self):
    for s in self.sensors:
      self.meta[s].update(len(self.buffer[s]), self.getLastSample(s))

  def getLastSample(self, sensorType):
    self.checkType(sensorType, self.sensors)
    if len(self.buffer[sensorType]) < 1:
      return None
    return self.buffer[sensorType][-1]

  def getSamples(self, sensorType):
    self.checkType(sensorType, self.sensors)
    return self.buffer[sensorType]

  def getBuffer(self):
    return self.buffer

  def getMeta(self, sensorType):
    self.checkType(sensorType, self.sensors)
    return self.meta[sensorType]

  def getStatusDesc(self):
    return status_desc


class RadarSensorMeta(object):
  def __init__(self, sensorType):
    self.sensorType = sensorType

    self.num_samples = 0
    self.last_sample = None
    self.last_stamp = "N/A"
    self.diff = "N/A"
    self.status = "N/A"

  def update(self, num_samples, last_sample):
    self.num_samples = num_samples
    self.last_sample = last_sample

    if self.num_samples < 1 or self.last_sample is None: return

    # update last stamp
    self.last_stamp = datetime.datetime.strptime(self.last_sample["startDateTime"], datastampformat)

    # update time diff
    now = datetime.datetime.utcnow()
    diff = now - self.last_stamp
    if diff < datetime.timedelta():
      diff = datetime.timedelta()
    self.diff = diff

    # update status
    if self.sensorType == "BATTERY":
      bat = self.last_sample["sample"]["value"]
      for st in sorted(status_desc.items(), key=lambda x: x[1]['th_bat']):
        th = st[1]["th_bat"]
        if th >= 0 and bat > th:
          self.status = st[0]
    else:
      for st in sorted(status_desc.items(), key=lambda x: x[1]['th_min']):
        th = st[1]["th_min"]
        if th >= 0 and self.diff >= datetime.timedelta(minutes=th):
          self.status = st[0]
