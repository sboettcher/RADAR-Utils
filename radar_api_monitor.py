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

global running, data, subject_sources, req_conf

sourceTypes = ["ANDROID", "EMPATICA", "PEBBLE", "BIOVOTION"]
sensors = ["ACCELEROMETER", "BATTERY", "BLOOD_VOLUME_PULSE", "ELECTRODERMAL_ACTIVITY", "INTER_BEAT_INTERVAL", "HEART_RATE", "THERMOMETER"]
stats = ["AVERAGE", "COUNT", "MAXIMUM", "MEDIAN", "MINIMUM", "SUM", "INTERQUARTILE_RANGE", "LOWER_QUARTILE", "UPPER_QUARTILE", "QUARTILES", "RECEIVED_MESSAGES"]
intervals = ["TEN_SECOND", "THIRTY_SECOND", "ONE_MIN", "TEN_MIN", "ONE_HOUR", "ONE_DAY", "ONE_WEEK"]

methods = {
            "all_subjects": "get_all_subjects_json",
            "all_sources": "get_all_sources_json",
            "last_computed_source_status": "get_last_computed_source_status_json",
            "last_received_sample": "get_last_received_sample_json"
          }




def api_callback(response):
  global running, data, subject_sources, req_conf
  if args.verbose and args.verbose > 1: pprint(response)
  data = response



def api_thread(api_instance):
  global running, data, subject_sources, req_conf

  while(running):
    try:
      if req_conf["method"] == "get_all_subjects_json":
        thread = api_instance.get_all_subjects_json("0", callback=api_callback)
      elif req_conf["method"] == "get_all_sources_json":
        if req_conf["subjectId"]:
          thread = api_instance.get_all_sources_json(req_conf["subjectId"], callback=api_callback)
      elif req_conf["method"] == "get_last_computed_source_status_json":
        if req_conf["subjectId"] and req_conf["sourceId"]:
          thread = api_instance.get_last_computed_source_status_json(req_conf["subjectId"], req_conf["sourceId"], callback=api_callback)
      elif req_conf["method"] == "get_last_received_sample_json":
        if req_conf["subjectId"] and req_conf["sourceId"] and req_conf["sensor"] and req_conf["stat"] and req_conf["interval"]:
          thread = api_instance.get_last_received_sample_json(req_conf["sensor"], req_conf["stat"], req_conf["interval"], req_conf["subjectId"], req_conf["sourceId"], callback=api_callback)
    except ApiException as e:
      print("Exception when calling DefaultApi->get_[]: %s\n" % e)

    time.sleep(args.api_refresh/1000.)



def sort_tree_item(treeitem):
  if treeitem.childCount() == 0: return
  treeitem.sortChildren(0,0)
  for c in range(treeitem.childCount()):
    sort_tree_item(treeitem.child(c))


def update_gui():
  global running, data, subject_sources, req_conf
  # check for updated subjectId
  if req_conf["subjectId"] != id_select.currentText() and len(id_select.currentText()) > 0:
    sources_tmp = None
    try:
      sources_tmp = api_instance.get_all_sources_json(id_select.currentText())
    except ApiException as e:
      print("Exception when calling DefaultApi->get_all_sources_json: %s\n" % e)
    if sources_tmp: subject_sources = [ sid for sid in sources_tmp["sources"] if sid["type"] == "EMPATICA" ]
    source_select.clear()
    source_select.addItems([s["id"] for s in subject_sources])
    if len(subject_sources) == 0: id_select.lineEdit().setStyleSheet("background-color: rgb(255, 0, 0);")
    else: id_select.lineEdit().setStyleSheet("background-color: rgb(255, 255, 255);")

  # update data tree
  data_tree.setData(data)
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
  if req_conf["method"] == "get_all_sources_json":
    source_select.setEnabled(False)
    sensor_select.setEnabled(False)
    stat_select.setEnabled(False)
    interval_select.setEnabled(False)
  elif req_conf["method"] == "get_last_computed_source_status_json":
    source_select.setEnabled(True)
    sensor_select.setEnabled(False)
    stat_select.setEnabled(False)
    interval_select.setEnabled(False)
  elif req_conf["method"] == "get_last_received_sample_json":
    source_select.setEnabled(True)
    sensor_select.setEnabled(True)
    stat_select.setEnabled(True)
    interval_select.setEnabled(True)





if __name__=="__main__":
  global running, data, subject_sources, req_conf
  class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter): pass
  cmdline = argparse.ArgumentParser(description="RADAR-CNS api monitor", formatter_class=Formatter)

  # general options
  cmdline.add_argument('-v', '--verbose', help='be verbose\n', action='count')
  cmdline.add_argument('-q', '--quiet', help='be quiet\n', action='store_true')
  cmdline.add_argument('-t', '--title', type=str, default="RADAR-CNS api monitor", help="plot window title\n")
  cmdline.add_argument('-ic', '--invert-fbg-colors', help="invert fore/background colors\n", action="store_true")
  cmdline.add_argument('-c', '--pen-color', metavar='COLOR', type=str, default="r", help="plot line pen color\n", choices=['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'])

  cmdline.add_argument('-ra', '--api-refresh', type=float, default=1000., help="api refresh rate (ms)\n")
  cmdline.add_argument('-rg', '--gui-refresh', type=float, default=500., help="gui refresh rate (ms)\n")

  cmdline.add_argument('-u', '--userid', type=str, default="UKLFR", help="start with this userId selected\n")
  cmdline.add_argument('-s', '--sourceid', type=str, help="start with this sourceId selected\n")
  cmdline.add_argument('--sensor', type=str, help="start with this sensor selected\n", choices=sensors)
  cmdline.add_argument('--stat', type=str, help="start with this stat selected\n", choices=stats)
  cmdline.add_argument('--interval', type=str, help="start with this interval selected\n", choices=intervals)
  cmdline.add_argument('-m', '--method', type=str, default="all_sources", help="start with this method selected\n", choices=methods.keys())


  #cmdline.add_argument('--num-samples', '-n', type=int, default=0,     help="plot the last n samples, 0 keeps all\n")
  #cmdline.add_argument('--frame-rate',  '-f', type=float, default=60., help="limit the frame-rate, 0 is unlimited\n")

  args = cmdline.parse_args()

  running = False
  data = dict()
  subject_sources = list()
  req_conf = dict()

  # create an instance of the API class
  api_instance = swagger_client.DefaultApi()

  # get some api info
  try:
    subject_sources = api_instance.get_all_sources_json(args.userid)
  except ApiException as e:
    print("Exception when calling DefaultApi->get_all_sources_json: %s\n" % e)

  # filter only empaticas
  subject_sources = [ sid for sid in subject_sources["sources"] if sid["type"] == "EMPATICA" ]

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

  id_select = pg.ComboBox()
  id_select.setEditable(True)
  #id_select.addItems([s["id"] for s in subjects])
  id_select.addItems(["UKLFR","LTT_1","LTT_2","LTT_3"])
  if args.userid and id_select.findText(args.userid) > -1: id_select.setValue(args.userid)
  raw_api_layout.addWidget(QtGui.QLabel("Patient ID"),0,0)
  raw_api_layout.addWidget(id_select,0,1)

  # add source selection field
  source_select = pg.ComboBox()
  source_select.addItems([s["id"] for s in subject_sources])
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
  if args.method: method_select.setValue(methods[args.method])
  raw_api_layout.addWidget(QtGui.QLabel("Method"),5,0)
  raw_api_layout.addWidget(method_select,5,1)

  # add data tree for response vis
  data_tree = pg.DataTreeWidget()
  raw_api_layout.addWidget(data_tree,6,0,1,2)


  # add main widgets as tabs
  tab_widget.addTab(raw_api_widget, "Raw API")
  tab_widget.addTab(monitor_widget, "Monitor")
  tab_widget.addTab(graph_widget, "Graph")
  tab_widget.addTab(devices_widget, "Devices")


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
