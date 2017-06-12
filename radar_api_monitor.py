#!/usr/bin/env python3

import sys, os, time, datetime
import argparse, json, fileinput
from inspect import isclass
import copy
import math, random
import numpy as np
import collections
import csv

from pprint import pprint
import swagger_client
from swagger_client.rest import ApiException
import urllib3
urllib3.disable_warnings()

from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg

import _thread

global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf

sourceTypes = ["ANDROID", "EMPATICA", "PEBBLE", "BIOVOTION"]
sensors = ["ACCELEROMETER", "BATTERY", "BLOOD_VOLUME_PULSE", "ELECTRODERMAL_ACTIVITY", "INTER_BEAT_INTERVAL", "HEART_RATE", "THERMOMETER"]
stats = ["AVERAGE", "COUNT", "MAXIMUM", "MEDIAN", "MINIMUM", "SUM", "INTERQUARTILE_RANGE", "LOWER_QUARTILE", "UPPER_QUARTILE", "QUARTILES", "RECEIVED_MESSAGES"]
intervals = ["TEN_SECOND", "THIRTY_SECOND", "ONE_MIN", "TEN_MIN", "ONE_HOUR", "ONE_DAY", "ONE_WEEK"]

methods = [
            "all_subjects",
            "all_sources",
            "last_computed_source_status",
            "last_received_sample"
          ]

status_desc = {
                "GOOD": {"priority": 1, "threshold_min": 0, "color": "lightgreen"},
                "OK": {"priority": 2, "threshold_min": 2, "color": "moccasin"},
                "WARNING": {"priority": 3, "threshold_min": 3, "color": "orange"},
                "CRITICAL": {"priority": 4, "threshold_min": 5, "color": "red"},
                "DISCONNECTED": {"priority": 0, "threshold_min": 30, "color": "transparent"},
                "N/A": {"priority": -1, "threshold_min": -1, "color": "lightgrey"}
              }

monitor_plot_range = 100


def eprint(*args, **kwargs):
  print(*args, file=sys.stderr, **kwargs)



def raw_api_callback(response):
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf
  if args.verbose and args.verbose > 1: pprint(response)
  raw_api_data = response

def monitor_callback(response):
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf
  if args.verbose and args.verbose > 1: pprint(response)

  try:
    patient_id = response["header"]["patientId"]
    source_id = response["header"]["sourceId"]
    source_id = source_id if source_id not in devices else devices[source_id][args.dev_replace]
    status = "N/A"
    stamp = response["header"]["effectiveTimeFrame"]["endDateTime"]
    sample = response["dataset"][0]["sample"]
  except TypeError as ex:
    if args.verbose: eprint("WARN: TypeError in monitor_callback:", ex)
    return


  # update monitor table data
  now = datetime.datetime.utcnow()
  stamp_date = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
  diff = now - stamp_date
  if diff < datetime.timedelta():
    diff = datetime.timedelta()
  #print(now, "->", stamp_date, "|", str(diff).split(".")[0])

  for st in sorted(status_desc.items(), key=lambda x: x[1]['threshold_min']):
    th = st[1]["threshold_min"]
    if th >= 0 and diff >= datetime.timedelta(minutes=th):
      status = st[0]

  for i in range(len(monitor_data)):
    if monitor_data[i]["patientId"] == patient_id and monitor_data[i]["sourceId"] == source_id:
      monitor_data[i]["status"] = status
      monitor_data[i]["stamp"] = stamp.replace("T", " ").replace("Z", "")
      monitor_data[i]["diff"] = str(diff).split(".")[0]
      if "value" in sample:
        monitor_data[i]["value"] = str(sample["value"])
      else:
        monitor_data[i]["value"] = "x: {:.2} | y: {:.2} | z: {:.2}".format(sample["x"],sample["y"],sample["z"])
      update_data_buf(monitor_data[i]["data_buf"], response["header"]["sensor"], response["dataset"][0], maxlen=monitor_plot_range)
      break


# update a dictionary of deque buffers; add empty buffer if key not present, otherwise append
# check for time stamp before appending to prevent duplicates
def update_data_buf(buffer_dict, key, data, maxlen=None):
  if key not in buffer_dict:
    buffer_dict[key] = collections.deque(maxlen=maxlen)
  for i in buffer_dict[key]:
    if i["startDateTime"] == data["startDateTime"]: return
  buffer_dict[key].append(data)


def api_thread(api_instance):
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf

  monitor_index = 0
  while(running):
    time.sleep(args.api_refresh/1000.)
    # always get list of subjects and sources first, everything else depends on this
    get_subjects_sources_info()

    try:
      if (tab_widget.currentIndex() == 0):
        cb = raw_api_callback
      elif (tab_widget.currentIndex() == 1):
        cb = monitor_callback
        for sub in subject_sources.keys():
          for src in subject_sources[sub]:
            thread = api_instance.get_last_received_sample_json(monitor_sensor_select.value(), monitor_stat_select.value(), monitor_interval_select.value(), sub, src, callback=cb)
            time.sleep(0.1)
        continue
      else:
        continue

      if req_conf["method"] == "all_subjects":
        thread = api_instance.get_all_subjects_json("0", callback=cb)

      elif req_conf["method"] == "all_sources":
        if req_conf["subjectId"]:
          thread = api_instance.get_all_sources_json(req_conf["subjectId"], callback=cb)

      elif req_conf["method"] == "last_computed_source_status":
        if req_conf["subjectId"] and req_conf["sourceId"]:
          thread = api_instance.get_last_computed_source_status_json(req_conf["subjectId"], req_conf["sourceId"], callback=cb)

      elif req_conf["method"] == "last_received_sample":
        if req_conf["subjectId"] and req_conf["sourceId"] and req_conf["sensor"] and req_conf["stat"] and req_conf["interval"]:
          thread = api_instance.get_last_received_sample_json(req_conf["sensor"], req_conf["stat"], req_conf["interval"], req_conf["subjectId"], req_conf["sourceId"], callback=cb)

    except ApiException as e:
      eprint("Exception when calling DefaultApi->get_[]: %s\n" % e)


def get_subjects_sources_info():
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf
  try:
    #subjects = api_instance.get_all_subjects_json("0")
    for s in subjects:
      sources_tmp = api_instance.get_all_sources_json(s)
      if sources_tmp: subject_sources[s] = [ sid["id"] for sid in sources_tmp["sources"] if sid["type"] == "EMPATICA" ]
  except ApiException as e:
    print("Exception when calling DefaultApi->get_all_sources_json[]: %s\n" % e)

  # update monitor data
  for sub in sorted(subject_sources.keys()):
    for src in subject_sources[sub]:
      # update monitor sources list
      src = src if src not in devices else devices[src][args.dev_replace]
      # check if entry already exists, skip if yes
      exists = False
      for i in range(len(monitor_data)):
        if monitor_data[i]["patientId"] == sub and monitor_data[i]["sourceId"] == src:
          exists = True
      if len(monitor_data) > 0 and exists: continue

      row = collections.OrderedDict()
      row["patientId"] = sub
      row["sourceId"] = src
      row["status"] = "N/A"
      row["stamp"] = "-"
      row["diff"] = "-"
      row["value"] = "-"
      row["data_buf"] = dict()
      monitor_data.append(row)



# recursively sorts a qt tree item and its children
def sort_tree_item(treeitem, recursive=True):
  if treeitem.childCount() == 0: return
  treeitem.sortChildren(0,0)
  if not recursive: return
  for c in range(treeitem.childCount()):
    sort_tree_item(treeitem.child(c))


# checks if the given table contains the data row (as list or OrderedDict),
# tests if all columns in colcheck are equal
def table_contains_data(table, data, colcheck=[0]):
  if not isinstance(data, list): data = list(data.items())
  for r in range(table.rowCount()):
    equal = 0
    for c in colcheck:
      if table.item(r,c).text() == data[c][1]: equal += 1
    if equal == len(colcheck): return r
  return -1

# adds a new data row to the given table, or replaces the data if it already exists
def table_add_data(table, data, colcheck=[0]):
  if not isinstance(data, list): data = list(data.items())
  row = table_contains_data(table, data, colcheck)
  #assert table.columnCount() == len(data)
  if row < 0:
    row = table.rowCount()
    table.insertRow(row)
    for i in range(table.columnCount()):
      table.setItem(row, i, QtGui.QTableWidgetItem(data[i][1]))
  else:
    for i in range(table.columnCount()):
      table.item(row,i).setText(data[i][1])

# clears the table of rows, except those with indices in keep
def table_clear(table, keep):
  for r in [ r for r in reversed(range(table.rowCount())) if r not in keep ]:
    table.removeRow(r)


def update_gui():
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf

  # raw api tab
  if (tab_widget.currentIndex() == 0):
    # check for updated subjectId
    if req_conf["subjectId"] != id_select.currentText() and len(id_select.currentText()) > 0:
      source_select.clear()
      if id_select.currentText() in subject_sources:
        source_select.addItems(subject_sources[id_select.currentText()])
        if id_select.currentText() not in subject_sources or len(subject_sources[id_select.currentText()]) == 0: id_select.lineEdit().setStyleSheet("background-color: rgb(255, 0, 0);")
      else: id_select.lineEdit().setStyleSheet("background-color: rgb(255, 255, 255);")

    # update data tree
    data_tree.setData(raw_api_data)
    data_tree.sortItems(0,0)
    for i in range(data_tree.topLevelItemCount()):
      sort_tree_item(data_tree.topLevelItem(i))

    # update config
    req_conf["method"] = method_select.value()
    req_conf["subjectId"] = id_select.currentText()
    req_conf["sourceId"] = source_select.value()
    req_conf["sensor"] = sensor_select.value()
    req_conf["stat"] = stat_select.value()
    req_conf["interval"] = interval_select.value()

    # disable widgets according to method
    if req_conf["method"] == "all_sources":
      source_select.setEnabled(False)
      sensor_select.setEnabled(False)
      stat_select.setEnabled(False)
      interval_select.setEnabled(False)
    elif req_conf["method"] == "last_computed_source_status":
      source_select.setEnabled(True)
      sensor_select.setEnabled(False)
      stat_select.setEnabled(False)
      interval_select.setEnabled(False)
    elif req_conf["method"] == "last_received_sample":
      source_select.setEnabled(True)
      sensor_select.setEnabled(True)
      stat_select.setEnabled(True)
      interval_select.setEnabled(True)

  # monitor tab
  elif (tab_widget.currentIndex() == 1):
    # filter monitor data
    dataset = [ d for d in monitor_data if monitor_view_all_check.isChecked() or status_desc[d["status"]]["priority"] > 0 ]

    # clear table
    contains = []
    for d in dataset:
      c = table_contains_data(monitor_table, d, [0,1])
      if c > -1: contains.append(c)
    table_clear(monitor_table, contains)

    # add/replace data
    for d in dataset:
      table_add_data(monitor_table, d, [0,1])

    for status in status_desc.keys():
      for item in monitor_table.findItems(status, QtCore.Qt.MatchExactly):
        item.setBackground(QtGui.QBrush(QtGui.QColor(status_desc[status]["color"])))

    # get selected item and draw line plot
    sel = monitor_table.selectedItems()
    if len(sel) > 0:
      sel_p = monitor_table.item(sel[0].row(), 0).text()
      sel_s = monitor_table.item(sel[0].row(), 1).text()
      data = [ d for d in monitor_data if d["patientId"] == sel_p and d["sourceId"] == sel_s ][0]
      if monitor_sensor_select.value() in data["data_buf"]:
        data = data["data_buf"][monitor_sensor_select.value()]
        if monitor_sensor_select.value() == "ACCELEROMETER":
          monitor_plot_x.setData([ d["sample"]["x"] for d in data ])
          monitor_plot_y.setData([ d["sample"]["y"] for d in data ])
          monitor_plot_z.setData([ d["sample"]["z"] for d in data ])
        else:
          monitor_plot_x.setData([ d["sample"]["value"] for d in data ])
          monitor_plot_y.clear()
          monitor_plot_z.clear()





if __name__=="__main__":
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf
  class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter): pass
  cmdline = argparse.ArgumentParser(description="RADAR-CNS api monitor", formatter_class=Formatter)

  # general options
  cmdline.add_argument('-v', '--verbose', help='be verbose\n', action='count')
  cmdline.add_argument('-q', '--quiet', help='be quiet\n', action='store_true')
  cmdline.add_argument('-t', '--title', type=str, default="RADAR-CNS api monitor", help="plot window title\n")
  cmdline.add_argument('-ic', '--invert-fbg-colors', help="invert fore/background colors\n", action="store_true")
  cmdline.add_argument('-c', '--pen-color', metavar='COLOR', type=str, default="r", help="plot line pen color\n", choices=['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'])

  cmdline.add_argument('-ra', '--api-refresh', type=float, default=1000., help="api refresh rate (ms)\n")
  cmdline.add_argument('-rg', '--gui-refresh', type=float, default=1000., help="gui refresh rate (ms)\n")

  cmdline.add_argument('--start-tab', type=int, default=1, help="start with this tab selected\n")

  cmdline.add_argument('-u', '--userid', type=str, default="UKLFR", help="start with this userId selected\n")
  cmdline.add_argument('-s', '--sourceid', type=str, help="start with this sourceId selected\n")
  cmdline.add_argument('--sensor', type=str, default="ACCELEROMETER", help="start with this sensor selected\n", choices=sensors)
  cmdline.add_argument('--stat', type=str, default="AVERAGE", help="start with this stat selected\n", choices=stats)
  cmdline.add_argument('--interval', type=str, default="TEN_SECOND", help="start with this interval selected\n", choices=intervals)
  cmdline.add_argument('-m', '--method', type=str, default="all_sources", help="start with this method selected\n", choices=methods)

  cmdline.add_argument('-d', '--devices', type=str, help="csv file fo importing device descriptions.\n")
  cmdline.add_argument('--dev-replace', type=str, help="replace device source string (MAC) with the string from this column in the loaded csv.\nMust be unique!\nRequires --devices.\n")


  #cmdline.add_argument('--num-samples', '-n', type=int, default=0,     help="plot the last n samples, 0 keeps all\n")
  #cmdline.add_argument('--frame-rate',  '-f', type=float, default=60., help="limit the frame-rate, 0 is unlimited\n")

  args = cmdline.parse_args()

  if args.dev_replace and not args.devices:
    eprint("ERROR: --dev-replace requires --devices!")
    sys.exit(1)

  running = False
  raw_api_data = dict()
  monitor_data = list()
  subjects = ["UKLFR","LTT_1","LTT_2","LTT_3"]
  subject_sources = dict()
  req_conf = dict()
  devices = dict()

  # create an instance of the API class
  api_instance = swagger_client.DefaultApi()


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
  win.resize(900,900)

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
      eprint("ERROR: Exception while trying to import csv file {}!".format(args.devices))
      devices_layout.addWidget(QtGui.QLabel("Error while trying to import {}".format(args.devices)),0,0)


  # get some api info
  get_subjects_sources_info()

  #
  # RAW API TAB
  #

  # add subject selection field
  id_select = pg.ComboBox()
  id_select.setEditable(True)
  id_select.addItems(subjects)
  if args.userid and id_select.findText(args.userid) > -1: id_select.setValue(args.userid)
  raw_api_layout.addWidget(QtGui.QLabel("Patient ID"),0,0)
  raw_api_layout.addWidget(id_select,0,1)

  # add source selection field
  source_select = pg.ComboBox()
  if args.userid in subject_sources:
    source_select.addItems(subject_sources[args.userid])
  if args.sourceid and source_select.findText(args.sourceid) > -1: source_select.setValue(args.sourceid)
  source_select.setEnabled(False)
  raw_api_layout.addWidget(QtGui.QLabel("Device ID"),1,0)
  raw_api_layout.addWidget(source_select,1,1)

  # add sensor selection field
  sensor_select = pg.ComboBox()
  sensor_select.addItems(sensors)
  if args.sensor: sensor_select.setValue(args.sensor)
  sensor_select.setEnabled(False)
  raw_api_layout.addWidget(QtGui.QLabel("Sensor"),2,0)
  raw_api_layout.addWidget(sensor_select,2,1)

  # add stat selection field
  stat_select = pg.ComboBox()
  stat_select.addItems(stats)
  if args.stat: stat_select.setValue(args.stat)
  stat_select.setEnabled(False)
  raw_api_layout.addWidget(QtGui.QLabel("Stat"),3,0)
  raw_api_layout.addWidget(stat_select,3,1)

  # add interval selection field
  interval_select = pg.ComboBox()
  interval_select.addItems(intervals)
  if args.interval: interval_select.setValue(args.interval)
  interval_select.setEnabled(False)
  raw_api_layout.addWidget(QtGui.QLabel("Interval"),4,0)
  raw_api_layout.addWidget(interval_select,4,1)

  # add method selection field
  method_select = pg.ComboBox()
  method_select.addItems(methods)
  if args.method: method_select.setValue(args.method)
  raw_api_layout.addWidget(QtGui.QLabel("Method"),5,0)
  raw_api_layout.addWidget(method_select,5,1)

  # add data tree for response vis
  data_tree = pg.DataTreeWidget()
  raw_api_layout.addWidget(data_tree,6,0,1,2)


  #
  # MONITOR TAB
  #

  # add view all checkbox
  monitor_view_all_check = QtGui.QCheckBox("View all sources")
  #monitor_view_all_check.setChecked(True)
  monitor_layout.addWidget(monitor_view_all_check,0,0)

  # add sensor selection field
  monitor_sensor_select = pg.ComboBox()
  monitor_sensor_select.addItems(sensors)
  if args.sensor: monitor_sensor_select.setValue(args.sensor)
  monitor_layout.addWidget(monitor_sensor_select,0,1)

  # add stat selection field
  monitor_stat_select = pg.ComboBox()
  monitor_stat_select.addItems(stats)
  if args.stat: monitor_stat_select.setValue(args.stat)
  monitor_layout.addWidget(monitor_stat_select,0,2)

  # add interval selection field
  monitor_interval_select = pg.ComboBox()
  monitor_interval_select.addItems(intervals)
  if args.interval: monitor_interval_select.setValue(args.interval)
  monitor_interval_select.setEnabled(False)
  monitor_layout.addWidget(monitor_interval_select,0,3)

  # add table for monitor overview
  monitor_table = QtGui.QTableWidget(0,6)
  monitor_table.setHorizontalHeaderLabels(["patientId","sourceId","status","stamp","diff","value"])
  monitor_table.horizontalHeader().setSectionResizeMode(QtGui.QHeaderView.ResizeToContents)
  monitor_layout.addWidget(monitor_table,1,0,1,4)

  # add plot for monitor overview
  monitor_plotw = pg.PlotWidget(name='monitor_plot')
  monitor_plotw.setRange(xRange=[0,monitor_plot_range])
  monitor_plotw.setLimits(xMax=100)
  monitor_plotw.setLimits(xMin=0)
  monitor_layout.addWidget(monitor_plotw,2,0,1,4)

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
      table_add_data(devices_table, devices[dev])
    devices_table.setSortingEnabled(True)
    devices_table.sortByColumn(0, QtCore.Qt.AscendingOrder)




  # add main widgets as tabs
  tab_widget.addTab(raw_api_widget, "Raw API")
  tab_widget.addTab(monitor_widget, "Monitor")
  tab_widget.addTab(devices_widget, "Devices")
  tab_widget.setCurrentIndex(args.start_tab)


  # set api request parameters
  req_conf["method"] = method_select.value()
  req_conf["subjectId"] = id_select.currentText()
  req_conf["sourceId"] = source_select.value()
  req_conf["sensor"] = sensor_select.value()
  req_conf["stat"] = stat_select.value()
  req_conf["interval"] = interval_select.value()

  # connect update and start timer
  timer = QtCore.QTimer()
  timer.timeout.connect(update_gui)
  win.show()
  timer.start(args.gui_refresh)

  running = True

  # start api thread
  try:
    _thread.start_new_thread( api_thread , (api_instance,) )
  except:
    eprint ("Error: unable to start thread")

  # start gui thread (blocking until window closed)
  app.exec_()

  running = False

  print("DONE")
