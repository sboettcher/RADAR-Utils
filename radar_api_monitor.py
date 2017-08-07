#!/usr/bin/env python3

import sys, os
import time, datetime
import traceback
import argparse, json, fileinput
from inspect import isclass
import copy
import math, random
import numpy as np
import collections
import csv
from pprint import pprint

import libs.swagger_client as api_client
from libs.swagger_client.rest import ApiException
import urllib3
urllib3.disable_warnings()

from pyqtgraph.Qt import VERSION_INFO
from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg
from libs.DateAxisItem import *

import threading
import logging
logging_levels = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]

from libs.radar_patient_source import RadarPatientSource

global running, raw_api_data, monitor_data, subjects, subject_sources

sourceTypes = ["ANDROID", "EMPATICA", "PEBBLE", "BIOVOTION"]
sensorTypes = ["ACCELEROMETER", "BATTERY", "BLOOD_VOLUME_PULSE", "ELECTRODERMAL_ACTIVITY", "INTER_BEAT_INTERVAL", "HEART_RATE", "THERMOMETER"]
stats = ["AVERAGE", "COUNT", "MAXIMUM", "MEDIAN", "MINIMUM", "SUM", "INTERQUARTILE_RANGE", "LOWER_QUARTILE", "UPPER_QUARTILE", "QUARTILES", "RECEIVED_MESSAGES"]
intervals = ["TEN_SECOND", "THIRTY_SECOND", "ONE_MIN", "TEN_MIN", "ONE_HOUR", "ONE_DAY", "ONE_WEEK"]

zoom_intervals = intervals + ["ONE_MONTH", "ALL"]
intervals_to_sec = {"ALL": -1, "TEN_SECOND": 10, "THIRTY_SECOND": 30, "ONE_MIN": 60, "TEN_MIN": 600, "ONE_HOUR": 3600, "ONE_DAY": 86400, "ONE_WEEK": 604800, "ONE_MONTH": 2592000}

methods = [
            "all_subjects",
            "subject",
            "all_sources",
            "source_specification",
            "last_computed_source_status",
            "samples",
            "last_received_sample"
          ]

status_desc = {
                "GOOD": {"priority": 1, "th_min": 0, "th_bat": 0.10, "color": "lightgreen"},
                #"OK": {"priority": 2, "th_min": 2, "th_bat": 0.10, "color": "moccasin"},
                "WARNING": {"priority": 3, "th_min": 5, "th_bat": 0.05, "color": "orange"},
                "CRITICAL": {"priority": 4, "th_min": 10, "th_bat": 0, "color": "red"},
                "DISCONNECTED": {"priority": 0, "th_min": 15, "th_bat": -1, "color": "transparent"},
                "N/A": {"priority": -1, "th_min": -1, "th_bat": -1, "color": "lightgrey"}
              }

max_data_buf = 60480 # 1 week

utcOffset = time.timezone - (time.daylight * 3600)
utcTZ = int(utcOffset/3600)
timedateformat = "%Y-%m-%d %H:%M:%S ({}{:02d}) ".format("-" if utcTZ >= 0 else "+",abs(utcTZ))
datastampformat = "%Y-%m-%dT%H:%M:%SZ"


def eprint(*args, **kwargs):
  print(*args, file=sys.stderr, **kwargs)

def thread_sleep(msec):
  global running
  for i in range(math.ceil(msec/1000.)):
    if running: time.sleep(1)


def raw_api_callback(response):
  global running, raw_api_data, monitor_data, subjects, subject_sources
  logging.debug("[RAW] got response.")
  if args.verbose and args.verbose > 1: pprint(response)
  raw_api_data = response

def monitor_callback(response, replace=False):
  global running, raw_api_data, monitor_data, subjects, subject_sources
  if args.verbose and args.verbose > 1: pprint(response)

  if response == '': return

  try:
    patient_id = response["header"]["subjectId"]
    source_id = response["header"]["sourceId"]
    source_id = source_id if source_id not in devices or not args.dev_replace or devices[source_id][args.dev_replace] == "" else devices[source_id][args.dev_replace]
    sensor = response["header"]["sensor"]
    status = "N/A"
    samples = response["dataset"]
    last_sample = samples[len(samples)-1]
    last_stamp = last_sample["startDateTime"]
  except TypeError as ex:
    logging.warn("[MONITOR] TypeError in monitor_callback: " + str(ex))
    return

  monitor_data_rlock.acquire()

  # find current data index
  data_idx = monitor_data.index((patient_id,source_id))

  if replace:
    monitor_data[data_idx].data_buf.replaceSamples(sensor, samples)
  else:
    monitor_data[data_idx].data_buf.addSamples(sensor, samples)

  status = monitor_data[data_idx].getStatus(sensor)
  logging.debug("[MONITOR] status of {} @ {}/{}: {}".format(sensor, patient_id, source_id, status))

  monitor_data_rlock.release()


# update a dictionary of deque buffers; add empty buffer if key not present, otherwise append
# check for time stamp before appending to prevent duplicates
def update_data_buf(buffer_dict, key, data, maxlen=None):
  if key not in buffer_dict:
    buffer_dict[key] = collections.deque(maxlen=maxlen)
  for i in buffer_dict[key]:
    if i["startDateTime"] == data["startDateTime"]: return
  buffer_dict[key].append(data)

# replace a dictionary of deque buffers; add empty buffer if key not present, otherwise clear and extend
def replace_data_buf(buffer_dict, key, data, maxlen=None):
  if key not in buffer_dict:
    buffer_dict[key] = collections.deque(maxlen=maxlen)
  else: buffer_dict[key].clear()
  buffer_dict[key].extend(data)




def raw_api_thread(api_instance):
  global running, raw_api_data, monitor_data, subjects, subject_sources

  while(running):
    if (tab_widget.currentIndex() != 0):
      thread_sleep(args.api_refresh)
      continue

    # always get list of subjects and sources first, everything else depends on this
    get_subjects_sources_info()

    try:
      cb = raw_api_callback

      logging.info("query of raw api method {}".format(method_select.value()))

      if method_select.value() == "all_subjects":
        if args.studyid:
          thread = api_instance.get_all_subjects_json(args.studyid, callback=cb)

      elif method_select.value() == "subject":
        if id_select.currentText():
          thread = api_instance.get_subject_json(id_select.currentText(), callback=cb)

      elif method_select.value() == "all_sources":
        if id_select.currentText():
          thread = api_instance.get_all_sources_json(id_select.currentText(), callback=cb)

      elif method_select.value() == "source_specification":
        if stype_select.value():
          thread = api_instance.get_source_specification_json(stype_select.value(), callback=cb)

      elif method_select.value() == "last_computed_source_status":
        if id_select.currentText() and source_select.value():
          thread = api_instance.get_last_computed_source_status_json(id_select.currentText(), source_select.value(), callback=cb)

      elif method_select.value() == "samples":
        if id_select.currentText() and source_select.value() and sensor_select.value() and stat_select.value() and interval_select.value():
          thread = api_instance.get_samples_json(sensor_select.value(), stat_select.value(), interval_select.value(), id_select.currentText(), source_select.value(), callback=cb)

      elif method_select.value() == "last_received_sample":
        if id_select.currentText() and source_select.value() and sensor_select.value() and stat_select.value() and interval_select.value():
          thread = api_instance.get_last_received_sample_json(sensor_select.value(), stat_select.value(), interval_select.value(), id_select.currentText(), source_select.value(), callback=cb)

    except ApiException as e:
      logging.error("Exception when calling DefaultApi->get_%s_json[]: %s\n" % method_select.value(), e)

    thread_sleep(args.api_refresh)


def monitor_api_thread(api_instance):
  global running, raw_api_data, monitor_data, subjects, subject_sources

  while(running):
    if (tab_widget.currentIndex() != 1):
      thread_sleep(args.api_refresh)
      continue

    # always get list of subjects and sources first, everything else depends on this
    get_subjects_sources_info()

    try:
      cb = monitor_callback
      if logging.getLogger().getEffectiveLevel() < 30: print()
      logging.info("----------")
      databuf_lengths = [ l for buf in [ ps.getBufferLengths() for ps in monitor_data ] for l in buf ]
      logging.info("Starting API requests.")
      if len(databuf_lengths) > 0: logging.info("Databuffer size min:{} avg:{} max:{}".format(min(databuf_lengths), np.mean(databuf_lengths, dtype=np.int_), max(databuf_lengths)))
      logging.info("----------")
      for sub in subject_sources.keys():
        for src in subject_sources[sub]:
          logging.info("query of sensorTypes @ {}/{}".format(sub, src))
          for s in ["ACCELEROMETER","BATTERY"]:#sensorTypes:
            thread = api_instance.get_last_received_sample_json(s, monitor_stat_select.value(), monitor_interval_select.value(), sub, src, callback=cb)
            time.sleep(args.api_interval/1000.)
      #if args.api_refresh/1000. < 10: time.sleep(10 - (args.api_refresh/1000.)) #wait at least ten seconds for refresh

    except ApiException as e:
      logging.error("Exception when calling DefaultApi->get_last_received_sample_json[]: %s\n" % e)

    thread_sleep(args.api_refresh)


def monitor_get_all_thread(sens, stat, inter, sub, src):
  logging.info("Getting all available {} data for {}/{}".format(sens, sub, src))
  monitor_get_data_button.setEnabled(False)
  response = api_instance.get_samples_json(sens, stat, inter, sub, src)
  monitor_callback(response, replace=True)
  monitor_get_data_button.setEnabled(True)
  logging.info("Got {} data for {}/{}".format(sens, sub, src))

def monitor_get_all_handle():
  sens = monitor_sensor_select.value()
  stat = monitor_stat_select.value()
  inter = monitor_interval_select.value()

  sel = monitor_table.selectedItems()
  if len(sel) < 1:
    logging.debug("No source selected for get_samples_json!")
    return
  sub = monitor_table.item(sel[0].row(), 0).text()
  src = monitor_table.item(sel[0].row(), 1).text()

  t = threading.Thread( target=monitor_get_all_thread, args=(sens, stat, inter, sub, src), name="monitor_get_all" )
  t.start()


def get_subjects_sources_info():
  global running, raw_api_data, monitor_data, subjects, subject_sources
  try:
    subjects_tmp = api_instance.get_all_subjects_json(args.studyid)
    for subject in subjects_tmp["subjects"]:
      if subject["subjectId"] not in subjects: subjects.append(subject["subjectId"])
      subject_sources[subject["subjectId"]] = [ source["id"] for source in subject["sources"] if source["type"] == "EMPATICA" ]
  except ApiException as e:
    logging.error("Exception when calling DefaultApi->get_all_sources_json[]: %s\n" % e)

  # update monitor data
  monitor_data_rlock.acquire()
  for sub in sorted(subject_sources.keys()):
    for src in subject_sources[sub]:
      src = src if src not in devices or not args.dev_replace or devices[src][args.dev_replace] == "" else devices[src][args.dev_replace]
      # check if entry already exists, skip if yes
      if len(monitor_data) > 0 and (sub,src) in monitor_data: continue
      monitor_data.append(RadarPatientSource(sub, src, bufferlen=max_data_buf))
  monitor_data_rlock.release()



# recursively sorts a qt tree item and its children
def sort_tree_item(treeitem, recursive=True):
  if treeitem.childCount() == 0: return
  treeitem.sortChildren(0,0)
  if not recursive: return
  for c in range(treeitem.childCount()):
    sort_tree_item(treeitem.child(c))


# checks if the given table contains the data row (list),
# tests if all columns in colcheck are equal
def table_contains_data(table, data, colcheck=[0]):
  if not isinstance(data, list): return
  for r in range(table.rowCount()):
    comp = [ table.item(r,c).text() for c in colcheck ]
    if len([ i for i in comp if i in data ]) == len(comp): return r
  return -1

# adds a new data row (list) to the given table, or replaces the data if it already exists.
# Possibility to provide a key if an item turns out to be a dict
def table_add_data(table, data, colcheck=[0], key=None):
  if not isinstance(data, list): return

  # check if row exists, else add one
  row = table_contains_data(table, data, colcheck)
  if row < 0:
    row = table.rowCount()
    table.insertRow(row)
    for i in range(table.columnCount()):
      table.setItem(row, i, QtGui.QTableWidgetItem())

  # add data
  for i in range(table.columnCount()):
    table.item(row,i).setText(str(data[i]))

# clears the table of rows, except those with indices in keep
def table_clear(table, keep=[]):
  for r in [ r for r in reversed(range(table.rowCount())) if r not in keep ]:
    table.removeRow(r)


def update_gui():
  global running, raw_api_data, monitor_data, subjects, subject_sources

  # update timedate label
  timedate_label.setText(api_instance.config.host + " | " + datetime.datetime.now().strftime(timedateformat))

  # raw api tab
  if (tab_widget.currentIndex() == 0 and data_update_check.isChecked()):
    # update id and source fields
    id_select.clear()
    source_select.clear()
    id_select.addItems(subjects)
    if id_select.currentText() in subject_sources:
      source_select.addItems(subject_sources[id_select.currentText()])


    # update data tree
    data_tree.setData(raw_api_data)
    data_tree.sortItems(0,0)
    for i in range(data_tree.topLevelItemCount()):
      sort_tree_item(data_tree.topLevelItem(i))


  # monitor tab
  elif (tab_widget.currentIndex() == 1):
    sensor = monitor_sensor_select.value()

    # filter monitor data
    monitor_data_rlock.acquire()
    dataset = [ copy.deepcopy(d) for d in monitor_data if monitor_view_all_check.isChecked() or status_desc[d.getPrioStatus()]["priority"] > 0 ]
    monitor_data_rlock.release()

    # clear table
    contains = []
    for d in dataset:
      c = table_contains_data(monitor_table, [d.subjectID, d.sourceID], [0,1])
      if c > -1: contains.append(c)
    table_clear(monitor_table, contains)

    # add/replace data
    for d in dataset:
      # populate value field
      if d.getLastSample(sensor) is not None:
        sample = d.getLastSample(sensor)["sample"]
        if "value" in sample:
          value = str(sample["value"])
        else:
          value = "x: {:.2} | y: {:.2} | z: {:.2}".format(sample["x"],sample["y"],sample["z"])
      else: value = "N/A"

      # get battery status
      battery = d.getBattery()
      if not isinstance(battery, str): battery = "{:.2%}".format(battery)

      # get stamp
      stamp = d.getLastStamp(sensor)
      if stamp is not None: stamp -= datetime.timedelta(seconds=utcOffset)
      else: stamp = "N/A"

      # add data
      # ["subjectId","sourceId","status","stamp","diff","battery","value"]
      row = [d.subjectID, d.sourceID, d.getPrioStatus(), battery, stamp, str(d.getDiff(sensor)).split(".")[0], value]
      table_add_data(monitor_table, row, colcheck=[0,1])

    # reset color of table cells
    for item in monitor_table.findItems("*", QtCore.Qt.MatchWildcard):
        item.setBackground(QtGui.QBrush(QtGui.QColor("transparent")))
    # set color of status fields
    for status in status_desc.keys():
      for item in monitor_table.findItems(status, QtCore.Qt.MatchExactly):
        item.setBackground(QtGui.QBrush(QtGui.QColor(status_desc[status]["color"])))

    # get selected item and draw line plot
    sel = monitor_table.selectedItems()
    if len(sel) > 0 and monitor_update_check.isChecked():
      sel_sub = monitor_table.item(sel[0].row(), 0).text()
      sel_src = monitor_table.item(sel[0].row(), 1).text()
      data = [ d for d in dataset if d == (sel_sub,sel_src) ][0]
      if data.getLastSample(sensor) is not None:
        # data samples to be plotted (y-axis)
        data = data.getSamples(sensor)
        # unix time stamps from the data samples (x-axis)
        stamps = [ datetime.datetime.strptime(d["startDateTime"], datastampformat).timestamp() - utcOffset for d in data ]

        # set plot x-axis range according to zoom level
        if monitor_zoom_select.value() != "ALL":
          monitor_plotw.setRange(xRange=[ int(time.time()-intervals_to_sec[monitor_zoom_select.value()]), int(time.time()) ])
        else:
          monitor_plotw.setRange(xRange=[ int(stamps[0]), int(stamps[-1]) ])

        # plot data, distinguish accelerometer (multi line) and others (single line)
        if sensor == "ACCELEROMETER":
          monitor_plot_x.setData(x=stamps, y=[ d["sample"]["x"] for d in data ])
          monitor_plot_y.setData(x=stamps, y=[ d["sample"]["y"] for d in data ])
          monitor_plot_z.setData(x=stamps, y=[ d["sample"]["z"] for d in data ])
        else:
          monitor_plot_x.setData(x=stamps, y=[ d["sample"]["value"] for d in data ])
          monitor_plot_y.clear()
          monitor_plot_z.clear()





if __name__=="__main__":
  global running, raw_api_data, monitor_data, subjects, subject_sources
  class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter): pass
  cmdline = argparse.ArgumentParser(description="RADAR-CNS api monitor", formatter_class=Formatter)

  # general options
  cmdline.add_argument('-V', '--version', help='print version info and exit\n', action='store_true')
  cmdline.add_argument('-v', '--verbose', help='be verbose\n', action='count')
  #cmdline.add_argument('-q', '--quiet', help='be quiet\n', action='store_true')
  cmdline.add_argument('-l', '--logging', metavar="LVL", type=str, default="INFO", help='set logging level\n', choices=logging_levels)

  cmdline.add_argument('-ar', '--api-refresh', metavar="MS", type=float, default=1000., help="api refresh rate (ms)\n")
  cmdline.add_argument('-ai', '--api-interval', metavar="MS", type=float, default=100., help="api interval rate (ms)\n")

  cmdline_gui_group = cmdline.add_argument_group('GUI arguments')
  cmdline_gui_group.add_argument('--title', type=str, default="RADAR-CNS api monitor", help="window title\n")
  cmdline_gui_group.add_argument('--invert-fbg-colors', help="invert fore/background colors\n", action="store_true")
  cmdline_gui_group.add_argument('-gr', '--gui-refresh', metavar="MS", type=float, default=1000., help="gui refresh rate (ms)\n")
  cmdline_gui_group.add_argument('-m', '--maximized', help="start window maximized\n", action="store_true")

  cmdline_devices_group = cmdline.add_argument_group('device manipulation arguments')
  cmdline_devices_group.add_argument('-d', '--devices', type=str, help="csv file for importing device descriptions.\n")
  cmdline_devices_group.add_argument('-dr', '--dev-replace', type=str, help="replace device source string (MAC) with the string from this column in the loaded csv.\nMust be unique!\nRequires --devices.\n")

  cmdline_defaults_group = cmdline.add_argument_group('default selections')
  cmdline_defaults_group.add_argument('-t', '--start-tab', type=int, default=1, help="start with this tab selected\n")
  cmdline_defaults_group.add_argument('--studyid', type=str, default="0", help="start with this studyId selected\n")
  cmdline_defaults_group.add_argument('-u', '--userid', type=str, default="UKLFR", help="start with this userId selected\n")
  cmdline_defaults_group.add_argument('-s', '--sourceid', type=str, help="start with this sourceId selected\n")
  cmdline_defaults_group.add_argument('--sensor', type=str, default="ACCELEROMETER", help="start with this sensor selected\n", choices=sensorTypes)
  cmdline_defaults_group.add_argument('--stat', type=str, default="AVERAGE", help="start with this stat selected\n", choices=stats)
  cmdline_defaults_group.add_argument('--interval', type=str, default="TEN_SECOND", help="start with this interval selected\n", choices=intervals)
  cmdline_defaults_group.add_argument('--method', type=str, default="all_subjects", help="start with this method selected\n", choices=methods)
  cmdline_defaults_group.add_argument('--zoom', type=str, default="ONE_HOUR", help="start with this monitor graph zoom level selected\n", choices=zoom_intervals)


  #cmdline.add_argument('--num-samples', '-n', type=int, default=0,     help="plot the last n samples, 0 keeps all\n")
  #cmdline.add_argument('--frame-rate',  '-f', type=float, default=60., help="limit the frame-rate, 0 is unlimited\n")

  args = cmdline.parse_args()

  logging.basicConfig(level=args.logging,
                      format='[%(levelname)-8s][%(asctime)-23s] (%(threadName)-12s) %(message)s'
                      )

  if args.dev_replace and not args.devices:
    logging.error("--dev-replace requires --devices!")
    sys.exit(1)

  if args.version:
    pg.systemInfo()
    sys.exit(0)

  if "PyQt5" not in VERSION_INFO:
    logging.error("requires PyQt5 bindings!")
    logging.error("bindings are: " + VERSION_INFO)
    sys.exit(1)

  running = False
  raw_api_data = dict()
  monitor_data = list()
  subjects = list()
  subject_sources = dict()
  devices = dict()

  # create an instance of the API class
  api_instance = api_client.DefaultApi()
  logging.info("RADAR-CNS API client @ {}".format(api_instance.config.host))

  monitor_data_rlock = threading.RLock()

  # Enable antialiasing for prettier plots
  pg.setConfigOptions(antialias=True)

  # set fore/background colors
  if args.invert_fbg_colors:
    pg.setConfigOption('background', 'k')
    pg.setConfigOption('foreground', 'w')
  else:
    pg.setConfigOption('background', 'w')
    pg.setConfigOption('foreground', 'k')

  # create window, layout and central widget
  app = QtGui.QApplication([])
  win = QtGui.QMainWindow()
  win.setWindowTitle(args.title)
  win.resize(1100,900)
  if args.maximized: win.setWindowState(QtCore.Qt.WindowMaximized)

  tab_widget = QtGui.QTabWidget()
  win.setCentralWidget(tab_widget)


  #
  # TABS
  #

  # create raw api tab
  raw_api_widget = QtGui.QWidget()
  raw_api_layout = QtGui.QGridLayout()
  raw_api_layout.setColumnStretch(1, 1)
  raw_api_widget.setLayout(raw_api_layout)
  #raw_api_layout.addWidget(QtGui.QLabel("Coming soon..."),0,0)

  # create monitor tab
  monitor_widget = QtGui.QWidget()
  monitor_layout = QtGui.QGridLayout()
  monitor_widget.setLayout(monitor_layout)
  #monitor_layout.addWidget(QtGui.QLabel("Coming soon..."),0,0)

  # create devices tab
  devices_widget = QtGui.QWidget()
  devices_layout = QtGui.QGridLayout()
  devices_widget.setLayout(devices_layout)
  #devices_layout.addWidget(QtGui.QLabel("Coming soon..."),0,0)

  # load devices if file specified
  if not args.devices:
    devices_layout.addWidget(QtGui.QLabel("Import a device csv table via the -d/--devices CLI flag."),0,0)
  else:
    try:
      with open(args.devices, newline='') as csvfile:
        csvreader = csv.reader(csvfile)
        header = None
        for row in csvreader:
          if not header:
            header = row
            devices["header"] = header
          else:
            dev = collections.OrderedDict()
            for h in range(len(header)):
              dev[header[h]] = row[h]
            devices[dev["MAC"]] = dev
    except:
      logging.error("Exception while trying to import csv file {}!".format(args.devices))
      devices_layout.addWidget(QtGui.QLabel("Exception while trying to import {}".format(args.devices)),0,0)


  # get some api info
  get_subjects_sources_info()

  #
  # RAW API TAB
  #

  # separator
  def separator():
    sep = QtGui.QFrame()
    sep.setFrameShape(QtGui.QFrame.HLine)
    sep.setFrameShadow(QtGui.QFrame.Sunken)
    raw_api_layout.addWidget(sep,grid_idx,0,1,2)

  grid_idx = 0

  # add subject selection field
  id_select = pg.ComboBox()
  id_select.setEditable(False)
  id_select.addItems(subjects)
  if args.userid and args.userid in subjects: id_select.setValue(args.userid)
  raw_api_layout.addWidget(QtGui.QLabel("Patient ID"),grid_idx,0)
  raw_api_layout.addWidget(id_select,grid_idx,1)

  grid_idx+=1
  # add source selection field
  source_select = pg.ComboBox()
  if args.userid in subject_sources:
    source_select.addItems(subject_sources[args.userid])
  if args.sourceid and source_select.findText(args.sourceid) > -1: source_select.setValue(args.sourceid)
  source_select.setEnabled(True)
  raw_api_layout.addWidget(QtGui.QLabel("Device ID"),grid_idx,0)
  raw_api_layout.addWidget(source_select,grid_idx,1)

  grid_idx+=1
  separator()

  grid_idx+=1
  # add sensor selection field
  sensor_select = pg.ComboBox()
  sensor_select.addItems(sensorTypes)
  if args.sensor: sensor_select.setValue(args.sensor)
  sensor_select.setEnabled(True)
  raw_api_layout.addWidget(QtGui.QLabel("Sensor"),grid_idx,0)
  raw_api_layout.addWidget(sensor_select,grid_idx,1)

  grid_idx+=1
  # add stat selection field
  stat_select = pg.ComboBox()
  stat_select.addItems(stats)
  if args.stat: stat_select.setValue(args.stat)
  stat_select.setEnabled(True)
  raw_api_layout.addWidget(QtGui.QLabel("Stat"),grid_idx,0)
  raw_api_layout.addWidget(stat_select,grid_idx,1)

  grid_idx+=1
  # add interval selection field
  interval_select = pg.ComboBox()
  interval_select.addItems(intervals)
  if args.interval: interval_select.setValue(args.interval)
  interval_select.setEnabled(True)
  raw_api_layout.addWidget(QtGui.QLabel("Interval"),grid_idx,0)
  raw_api_layout.addWidget(interval_select,grid_idx,1)

  grid_idx+=1
  separator()

  grid_idx+=1
  # add source type selection field
  stype_select = pg.ComboBox()
  stype_select.addItems(sourceTypes)
  stype_select.setValue("EMPATICA")
  stype_select.setEnabled(True)
  raw_api_layout.addWidget(QtGui.QLabel("Source Type"),grid_idx,0)
  raw_api_layout.addWidget(stype_select,grid_idx,1)

  grid_idx+=1
  separator()

  grid_idx+=1
  # add method selection field
  method_select = pg.ComboBox()
  method_select.addItems(methods)
  if args.method: method_select.setValue(args.method)
  raw_api_layout.addWidget(QtGui.QLabel("Method"),grid_idx,0)
  raw_api_layout.addWidget(method_select,grid_idx,1)

  grid_idx+=1
  # add data update checkbox
  data_update_check = QtGui.QCheckBox("Update data")
  data_update_check.setChecked(True)
  raw_api_layout.addWidget(data_update_check,grid_idx,0)

  grid_idx+=1
  # add data tree for response vis
  data_tree = pg.DataTreeWidget()
  raw_api_layout.addWidget(data_tree,grid_idx,0,1,2)


  #
  # MONITOR TAB
  #

  # add view all checkbox
  monitor_view_all_check = QtGui.QCheckBox("View all sources")
  #monitor_view_all_check.setChecked(True)
  monitor_layout.addWidget(monitor_view_all_check,0,0)

  # add sensor selection field
  monitor_sensor_select = pg.ComboBox()
  monitor_sensor_select.addItems(sensorTypes)
  if args.sensor: monitor_sensor_select.setValue(args.sensor)
  monitor_layout.addWidget(monitor_sensor_select,0,1)

  # add stat selection field
  monitor_stat_select = pg.ComboBox()
  monitor_stat_select.addItems(stats)
  if args.stat: monitor_stat_select.setValue(args.stat)
  #monitor_stat_select.setEnabled(False)
  monitor_layout.addWidget(monitor_stat_select,0,2)

  # add interval selection field
  monitor_interval_select = pg.ComboBox()
  monitor_interval_select.addItems(intervals)
  if args.interval: monitor_interval_select.setValue(args.interval)
  monitor_interval_select.setEnabled(False)
  monitor_layout.addWidget(monitor_interval_select,0,3)

  # add table for monitor overview
  monitor_table = QtGui.QTableWidget(0,7)
  monitor_table.setHorizontalHeaderLabels(["subjectId","sourceId","status","battery","stamp","diff","value"])
  monitor_table.horizontalHeader().setSectionResizeMode(QtGui.QHeaderView.ResizeToContents)
  monitor_layout.addWidget(monitor_table,1,0,1,4)

  # add graph update checkbox
  monitor_update_check = QtGui.QCheckBox("Update graph")
  monitor_update_check.setChecked(True)
  monitor_layout.addWidget(monitor_update_check,2,0)

  monitor_get_data_button = QtGui.QPushButton("Get All Data")
  monitor_get_data_button.setAutoDefault(False)
  monitor_get_data_button.setAutoRepeat(False)
  monitor_get_data_button.clicked.connect(monitor_get_all_handle)
  monitor_layout.addWidget(monitor_get_data_button,2,2)

  # add zoom selection field
  monitor_zoom_select = pg.ComboBox()
  monitor_zoom_select.addItems(zoom_intervals)
  if args.zoom: monitor_zoom_select.setValue(args.zoom)
  else: monitor_zoom_select.setValue(zoom_intervals[-1])
  monitor_layout.addWidget(monitor_zoom_select,2,3)

  # add plot for monitor overview
  date_axis = DateAxisItem(orientation='bottom')
  monitor_plotw = pg.PlotWidget(name='monitor_plot', axisItems={'bottom':date_axis})
  monitor_plotw.setRange(xRange=[ int(time.time()-intervals_to_sec[monitor_zoom_select.value()]), int(time.time()) ])
  #monitor_plotw.setLimits(xMax=max_data_buf)
  monitor_plotw.setLimits(xMin=0)
  monitor_layout.addWidget(monitor_plotw,3,0,1,4)

  monitor_plot_x = monitor_plotw.plot(pen=(255,0,0), name="x")
  monitor_plot_y = monitor_plotw.plot(pen=(0,255,0), name="y")
  monitor_plot_z = monitor_plotw.plot(pen=(0,0,255), name="z")


  #
  # DEVICES TAB
  #

  # add and fill table for devices overview
  if "header" in devices:
    devices_table = QtGui.QTableWidget(0,len(devices["header"]))
    devices_table.setHorizontalHeaderLabels(devices["header"])
    devices_table.horizontalHeader().setSectionResizeMode(QtGui.QHeaderView.ResizeToContents)
    devices_layout.addWidget(devices_table,0,0)
    for dev in [ d for d in devices.keys() if "header" not in d ]:
      table_add_data(devices_table, list(devices[dev].values()))
    devices_table.setSortingEnabled(True)
    devices_table.sortByColumn(0, QtCore.Qt.AscendingOrder)




  # add main widgets as tabs
  tab_widget.addTab(raw_api_widget, "Raw API")
  tab_widget.addTab(monitor_widget, "Monitor")
  tab_widget.addTab(devices_widget, "Devices")
  tab_widget.setCurrentIndex(args.start_tab)
  timedate_label = QtGui.QLabel(api_instance.config.host + " | " + datetime.datetime.now().strftime(timedateformat))
  tab_widget.setCornerWidget(timedate_label)

  # connect update and start timer
  timer = QtCore.QTimer()
  timer.timeout.connect(update_gui)
  win.show()
  timer.start(args.gui_refresh)

  running = True

  # start threads
  threads = []
  try:
    threads.append(threading.Thread( target=raw_api_thread, args=(api_instance,), name="raw_api" ))
    threads.append(threading.Thread( target=monitor_api_thread, args=(api_instance,), name="monitor_api" ))
    for t in threads:
      logging.info("starting thread " + t.getName())
      t.start()
  except:
    logging.error("unable to start thread")
    traceback.print_exc(file=sys.stderr)

  # start gui thread (blocking until window closed)
  app.exec_()

  running = False

  # join threads
  for t in threads:
    logging.info("joining thread " + t.getName())
    t.join()

  logging.info("DONE")
