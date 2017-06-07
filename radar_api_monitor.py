#!/usr/bin/env python3

import sys, os, time
import argparse, json, fileinput
from inspect import isclass
import copy
import math, random
import numpy as np
import collections

from pprint import pprint
import swagger_client
from swagger_client.rest import ApiException
import urllib3
urllib3.disable_warnings()

#import matplotlib as mp
#import matplotlib.pyplot as plt
#import matplotlib.animation as animation
#from matplotlib import gridspec
#mp.style.use("ggplot")

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
                "GOOD": {"threshold_min": 0, "color": "lightgreen"},
                "OK": {"threshold_min": 2, "color": "moccasin"},
                "WARNING": {"threshold_min": 3, "color": "orange"},
                "CRITICAL": {"threshold_min": 5, "color": "red"},
                "DISCONNECTED": {"threshold_min": 30, "color": "transparent"},
                "N/A": {"threshold_min": None, "color": "lightgrey"}
              }


def raw_api_callback(response):
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf
  if args.verbose and args.verbose > 1: pprint(response)
  raw_api_data = response

def monitor_callback(response):
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf
  if args.verbose and args.verbose > 1: pprint(response)

  patient_id = response["header"]["patientId"]
  source_id = response["header"]["sourceId"]
  status = "GOOD"
  stamp = response["header"]["effectiveTimeFrame"]["endDateTime"]

  for i in range(len(monitor_data)):
    if monitor_data[i]["patientId"] == patient_id and monitor_data[i]["sourceId"] == source_id:
      monitor_data[i]["status"] = status
      monitor_data[i]["stamp"] = stamp
      break




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
            thread = api_instance.get_last_received_sample_json("ACCELEROMETER", "AVERAGE", "TEN_SECOND", sub, src, callback=cb)
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
      print("Exception when calling DefaultApi->get_[]: %s\n" % e)


def get_subjects_sources_info():
  global running, raw_api_data, monitor_data, subjects, subject_sources, req_conf
  try:
    #subjects = api_instance.get_all_subjects_json("0")
    for s in subjects:
      sources_tmp = api_instance.get_all_sources_json(s)
      if sources_tmp: subject_sources[s] = [ sid["id"] for sid in sources_tmp["sources"] if sid["type"] == "EMPATICA" ]
  except ApiException as e:
    print("Exception when calling DefaultApi->get_all_sources_json[]: %s\n" % e)

  # update monitor list
  for sub in sorted(subject_sources.keys()):
    for src in subject_sources[sub]:
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
      monitor_data.append(row)




def sort_tree_item(treeitem):
  if treeitem.childCount() == 0: return
  treeitem.sortChildren(0,0)
  for c in range(treeitem.childCount()):
    sort_tree_item(treeitem.child(c))


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
    # update monitor table
    monitor_table.setData(monitor_data)
    for status in status_desc.keys():
      for item in monitor_table.findItems(status, QtCore.Qt.MatchExactly):
        item.setBackground(QtGui.QBrush(QtGui.QColor(status_desc[status]["color"])))




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

  cmdline.add_argument('--start-tab', type=int, default=0, help="start with this tab selected\n")

  cmdline.add_argument('-u', '--userid', type=str, default="UKLFR", help="start with this userId selected\n")
  cmdline.add_argument('-s', '--sourceid', type=str, help="start with this sourceId selected\n")
  cmdline.add_argument('--sensor', type=str, help="start with this sensor selected\n", choices=sensors)
  cmdline.add_argument('--stat', type=str, help="start with this stat selected\n", choices=stats)
  cmdline.add_argument('--interval', type=str, help="start with this interval selected\n", choices=intervals)
  cmdline.add_argument('-m', '--method', type=str, default="all_sources", help="start with this method selected\n", choices=methods)


  #cmdline.add_argument('--num-samples', '-n', type=int, default=0,     help="plot the last n samples, 0 keeps all\n")
  #cmdline.add_argument('--frame-rate',  '-f', type=float, default=60., help="limit the frame-rate, 0 is unlimited\n")

  args = cmdline.parse_args()

  running = False
  raw_api_data = dict()
  monitor_data = list()
  subjects = ["UKLFR","LTT_1","LTT_2","LTT_3"]
  subject_sources = dict()
  req_conf = dict()

  # create an instance of the API class
  api_instance = swagger_client.DefaultApi()

  # get some api info
  get_subjects_sources_info()



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

  # create raw api tab
  raw_api_widget = QtGui.QWidget()
  raw_api_layout = QtGui.QGridLayout()
  raw_api_layout.setColumnStretch(1, 1)
  raw_api_widget.setLayout(raw_api_layout)

  # create monitor tab
  monitor_widget = QtGui.QWidget()
  monitor_layout = QtGui.QGridLayout()
  monitor_widget.setLayout(monitor_layout)
  monitor_layout.addWidget(QtGui.QLabel("Coming soon..."),0,0)

  # create graph tab
  graph_widget = QtGui.QWidget()
  graph_layout = QtGui.QGridLayout()
  graph_widget.setLayout(graph_layout)
  graph_layout.addWidget(QtGui.QLabel("Coming soon..."),0,0)

  # create devices tab
  devices_widget = QtGui.QWidget()
  devices_layout = QtGui.QGridLayout()
  devices_widget.setLayout(devices_layout)
  devices_layout.addWidget(QtGui.QLabel("Coming soon..."),0,0)

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


  # add data tree for response vis
  monitor_table = pg.TableWidget()
  monitor_layout.addWidget(monitor_table,0,0)


  # add main widgets as tabs
  tab_widget.addTab(raw_api_widget, "Raw API")
  tab_widget.addTab(monitor_widget, "Monitor")
  tab_widget.addTab(graph_widget, "Graph")
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
    print ("Error: unable to start thread")

  # start gui thread (blocking until window closed)
  app.exec_()

  running = False

  print("DONE")
