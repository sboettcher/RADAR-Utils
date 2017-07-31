import logging
from pprint import pprint

from .radar_data_buffer import RadarDataBuffer

__all__ = ['RadarPatientSource']


class RadarPatientSource(object):
  def __init__(self, subjectID, sourceID, sourceType="EMPATICA", bufferlen=None):
    self.subjectID = subjectID
    self.sourceID = sourceID
    self.sourceType = sourceType

    self.prio_status = "N/A"
    self.latest_stamp = "N/A"
    self.latest_diff = "N/A"
    self.battery = "N/A"

    self.data_buf = RadarDataBuffer(self.sourceType, maxlen=bufferlen)

  #
  # operator== overload
  #
  def __eq__(self, other):
    if isinstance(other, RadarPatientSource):
      return self.subjectID == other.subjectID and self.sourceID == other.sourceID
    elif (isinstance(other, tuple) or isinstance(other, list)) and len(other) == 2:
      return self.subjectID == other[0] and self.sourceID == other[1]
    else:
      return NotImplemented


  #
  # Simple Data Getter
  #

  def getLastSample(self, sensorType):
    return self.data_buf.getLastSample(sensorType)

  def getSamples(self, sensorType):
    return self.data_buf.getSamples(sensorType)


  #
  # Simple Meta Getter
  #

  def getStatus(self, sensorType):
    return self.data_buf.getMeta(sensorType).status

  def getLastStamp(self, sensorType):
    return self.data_buf.getMeta(sensorType).last_stamp

  def getDiff(self, sensorType):
    return self.data_buf.getMeta(sensorType).diff

  def getBattery(self):
    if self.data_buf.getMeta("BATTERY").last_sample is None:
      return "N/A"
    return self.data_buf.getMeta("BATTERY").last_sample["sample"]["value"]


  #
  # Aggregator Meta Getter
  #

  def getPrioStatus(self):
    statuses = [ self.getStatus(s) for s in ["ACCELEROMETER","BATTERY","BLOOD_VOLUME_PULSE"] ]
    statuses = sorted(statuses, key=lambda x: self.data_buf.getStatusDesc()[x]['priority'])
    if "DISCONNECTED" in statuses: return "DISCONNECTED"
    return statuses[-1]

  def getLatestStamp(self):
    stamps = [ self.getLastStamp(s) for s in self.data_buf.sensors ]

  def getLatestDiff(self):
    diffs = [ self.getDiff(s) for s in self.data_buf.sensors ]

  def getBufferLengths(self):
    return [ self.data_buf.getMeta(s).num_samples for s in self.data_buf.sensors ]
