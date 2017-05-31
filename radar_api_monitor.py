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
            "all_sources": "get_all_sources_json",
            "last_computed_source_status": "get_last_computed_source_status_json"
          }




def api_callback(response):
  global running, data, subject_sources, req_conf
  if args.verbose and args.verbose > 1: pprint(response)
  data = response



def api_thread(api_instance):
  global running, data, subject_sources, req_conf

  while(running):
    try:
      if req_conf["subjectId"] and req_conf["sourceId"]:
        thread = api_instance.get_last_computed_source_status_json(req_conf["subjectId"], req_conf["sourceId"], callback=api_callback)
    except ApiException as e:
      print("Exception when calling DefaultApi->get_last_computed_source_status_json: %s\n" % e)

    time.sleep(args.api_refresh/1000.)



def sort_tree_item(treeitem):
  if treeitem.childCount() == 0: return
  treeitem.sortChildren(0,0)
  for c in range(treeitem.childCount()):
    sort_tree_item(treeitem.child(c))


def update_gui():
  global running, data, subject_sources, req_conf
  # check for updated subjectId
  if req_conf["subjectId"] != id_text.text() and len(id_text.text()) > 0:
    sources_tmp = None
    try:
      sources_tmp = api_instance.get_all_sources_json(id_text.text())
    except ApiException as e:
      print("Exception when calling DefaultApi->get_all_sources_json: %s\n" % e)
    if sources_tmp: subject_sources = [ sid for sid in sources_tmp["sources"] if sid["type"] == "EMPATICA" ]
    sources_select.clear()
    sources_select.addItems([s["id"] for s in subject_sources])
    if len(subject_sources) == 0: id_text.setStyleSheet("background-color: rgb(255, 0, 0);")
    else: id_text.setStyleSheet("background-color: rgb(255, 255, 255);")

  # update data tree
  data_tree.setData(data)
  data_tree.sortItems(0,0)
  for i in range(data_tree.topLevelItemCount()):
    sort_tree_item(data_tree.topLevelItem(i))

  # update config
  req_conf["subjectId"] = id_text.text()
  req_conf["sourceId"] = sources_select.value()





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

  cmdline.add_argument('-u', '--userid', type=str, default="UKLFR", help="\n")
  cmdline.add_argument('-s', '--sourceid', type=str, help="\n")
  cmdline.add_argument('-ra', '--api-refresh', type=float, default=1000., help="api refresh rate (ms)\n")
  cmdline.add_argument('-rg', '--gui-refresh', type=float, default=500., help="gui refresh rate (ms)\n")

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
  cw = QtGui.QWidget()
  win.setCentralWidget(cw)
  layout = QtGui.QGridLayout()
  cw.setLayout(layout)

  # add patient ID text widget
  id_text = QtGui.QLineEdit()
  if args.userid: id_text.setText(args.userid)
  layout.addWidget(QtGui.QLabel("Patient ID"),0,0)
  layout.addWidget(id_text,0,1)

  # add source selection field
  sources_select = pg.ComboBox()
  sources_select.addItems([s["id"] for s in subject_sources])
  if args.sourceid and sources_select.findText(args.sourceid) > -1: sources_select.setValue(args.sourceid)
  layout.addWidget(QtGui.QLabel("Device ID"),1,0)
  layout.addWidget(sources_select,1,1)

  # add method selection field
  method_select = pg.ComboBox()
  method_select.addItems(methods)
  layout.addWidget(QtGui.QLabel("Method"),2,0)
  layout.addWidget(method_select,2,1)

  # add data tree for response vis
  data_tree = pg.DataTreeWidget()
  layout.addWidget(data_tree,3,0,1,2)

  # set api request parameters
  req_conf["subjectId"] = id_text.text()
  req_conf["sourceId"] = sources_select.value()

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
