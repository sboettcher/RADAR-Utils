#!/usr/bin/env python3

import sys, os, time
import argparse, json, csv, fileinput
import copy
import math, random
import numpy as np
import collections
from pprint import pprint

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button

from datetime import datetime,timezone,timedelta

stampkeys = ["time", "timeReceived"]



def valid_datetime(s):
  try:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
  except ValueError:
    msg = "Not a valid date: '{0}'.".format(s)
    raise argparse.ArgumentTypeError(msg)
def valid_date(s):
  try:
    return datetime.strptime(s, "%Y-%m-%d")
  except ValueError:
    msg = "Not a valid date: '{0}'.".format(s)
    raise argparse.ArgumentTypeError(msg)


def print_progress(iteration, total, prefix='', suffix='', decimals=1, bar_length=100, fill='█', empty='-', lastprogress=None):
    str_format = "{0:." + str(decimals) + "f}"
    percents = str_format.format(100 * (iteration / float(total)))
    filled_length = int(round(bar_length * iteration / float(total)))
    bar = fill * filled_length + empty * (bar_length - filled_length)

    if lastprogress is not None and percents == lastprogress and iteration != total:
      return lastprogress

    sys.stdout.write('\r%s |%s| %s%s %s' % (prefix, bar, percents, '%', suffix))

    if iteration == total:
      sys.stdout.write('\n')
    sys.stdout.flush()

    if lastprogress is not None:
      return percents


def load(streams):
  print("[LOAD] Loading samples from {} source{} ...".format(len(streams),'s' if len(streams) > 1 else ''))
  samples = list()
  for s in range(len(streams)):
    stream = streams[s]
    streamSize = 0 if stream == '-' else os.path.getsize(stream)
    progress = 0
    lp = ''
    fname, fext = os.path.splitext(stream)

    if args.verbose: print(stream)
    csv_header = None
    for line in fileinput.input(stream, bufsize=1000):
      progress += len(line)
      if streamSize > 0: lp = print_progress(progress, streamSize, prefix=s+1, decimals=0, bar_length=50, fill='-', empty=' ', lastprogress=lp)

      line = line.strip()
      line = line.strip('\n')

      # skip empty and comment lines
      if line == "" or line == "#":
        continue

      if fext == ".json":
        samples.append(parse_json(line, s, len(streams)))
      elif fext == ".csv":
        if not csv_header: csv_header = line.replace("\"", "").split(",")
        else: samples.append(parse_csv(csv_header, line.split(","), s, len(streams)))

  print("[LOAD] Done. Loaded", len(samples), "samples")
  return samples

def parse_json(line, idx, num):
  sample = json.loads(line)
  #if num > 1:
  #  datakeys = [ k for k in sample["value"].keys() if "time" not in k ]
  #  for k in datakeys:
  #    sample["value"]["{0:0{width}d}_{1}".format(idx+1,k, width=len(str(num)))] = sample["value"].pop(k)
  return sample

def parse_csv(header, linesplit, idx, num):
  sample = dict()
  for h in range(len(header)):
    pair = header[h].split(".")
    if pair[0] not in sample: sample[pair[0]] = dict()
    value = linesplit[h]
    try: value = float(value)
    except: pass
    sample[pair[0]][pair[1]] = value
  return sample


def data_print(sample):
    key, stamps, data = data_get_fields(sample)

    print()
    print("[DATA PRINT]")
    print("key: {} - {}".format(key["userId"], key["sourceId"]))
    print("stamps:")
    for key in stamps:
        print("\t{}: {}".format(key, stamps[key]))
    print("data:")
    for key in data:
        print("\t{}: {}".format(key, data[key]))


def get_ax_size(fig, ax):
    bbox = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
    width, height = bbox.width, bbox.height
    width *= fig.dpi
    height *= fig.dpi
    return width, height


def data_get_fields(sample):
    key = sample["key"]
    value = sample["value"]

    stamps = { key: value[key] for key in stampkeys }
    data = { key: value[key] for key in value if key not in stampkeys}

    return key, stamps, data


class XYZoomLevel(object):
  def __init__(self):
    self.reset = None

  def setXZoom(self, event, zoom, axes):
    print("[GRAPH] set X zoom to {} seconds".format(zoom))

    current = axes.get_xlim()
    if not self.reset: self.reset = current

    left = current[0]
    left_dt = mdates.num2date(left)
    right_dt = left_dt + timedelta(seconds=zoom)
    right = mdates.date2num(right_dt)

    axes.set_xlim(left, right, auto=True)

    minorLocator = mdates.SecondLocator()
    axes.xaxis.set_minor_locator(minorLocator)

  def setXZoomMM(self, event, min, max, axes):
    print("[GRAPH] set X zoom to {} <> {}".format(min, max))
    axes.set_xlim(mdates.date2num(min), mdates.date2num(max), auto=True)
    axes.xaxis.set_minor_locator(plt.NullLocator())

  def resetXZoom(self, event, axes):
    if not self.reset: return
    print("[GRAPH] reset X zoom")
    axes.set_xlim(self.reset[0], self.reset[1], auto=True)
    axes.xaxis.set_minor_locator(plt.NullLocator())

  def setYZoomMM(self, event, min, max, axes):
    print("[GRAPH] set Y zoom to {} <> {}".format(min, max))
    axes.set_ylim(min, max, auto=True)
    axes.yaxis.set_minor_locator(plt.NullLocator())


def graph(samples):
    fig = plt.figure(1, figsize=(15,8))
    fig.clf()
    fig.canvas.set_window_title('data')

    if args.maximized:
      mng = plt.get_current_fig_manager()
      mng.resize(*mng.window.maxsize())

    keys,stamps,data,datakeys = list(),list(),list(),list()

    print("[GRAPH] Processing...")
    lp = ''

    # separate fields into lists
    for s in range(len(samples)):
      lp = print_progress(s+1, len(samples), prefix='1/2', decimals=0, bar_length=50, fill='-', empty=' ', lastprogress=lp)
      f_key,f_stamps,f_data = data_get_fields(samples[s])
      if args.userID and f_key["userId"] != args.userID: continue
      if args.sourceID and f_key["sourceId"] != args.sourceID: continue
      keys.append(f_key)
      stamps.append(f_stamps)
      data.append(f_data)
      datakeys.extend([ k for k in f_data.keys() if k not in datakeys ])

    assert len(keys) == len(stamps)
    assert len(keys) == len(data)
    if not keys:
      print("[GRAPH] abort, nothing to show")
      return

    # separate per datakey into dicts and check for uniqueness
    datakeys = sorted(datakeys)
    print_progress(0, len(datakeys), prefix='2/2', suffix="{}/{}".format(0,len(datakeys)), decimals=0, bar_length=50, fill='-', empty=' ')
    d_stampdata,d_datetimedata,d_keydata = dict(),dict(),dict()
    for k in range(len(datakeys)):
      d_stampdata[datakeys[k]] = [ int(stamps[s][args.timestamp]*1000) for s in range(len(stamps)) if datakeys[k] in data[s] ]
      d_datetimedata[datakeys[k]] = [ datetime.fromtimestamp(ms//1000, timezone.utc if args.utc else None).replace(microsecond=ms%1000*1000) for ms in d_stampdata[datakeys[k]] ]
      d_keydata[datakeys[k]] = [ d[datakeys[k]] for d in data if datakeys[k] in d ]

      if args.unique:
        uniq_data = dict()
        for s,t,d in zip(d_stampdata[datakeys[k]],d_datetimedata[datakeys[k]],d_keydata[datakeys[k]]):
          if (args.begin and t < args.begin) or (args.end and t > args.end) or (args.day and t.date() != args.day.date()):
            continue
          if args.verbose and args.verbose > 1: print("[GRAPH] {}: {} {} {}".format("update" if s in uniq_data else "new",s,t,d))
          uniq_data[s] = d
        d_stampdata[datakeys[k]] = sorted(uniq_data)
        d_datetimedata[datakeys[k]] = [ datetime.fromtimestamp(ms//1000, timezone.utc if args.utc else None).replace(microsecond=ms%1000*1000) for ms in d_stampdata[datakeys[k]] ]
        d_keydata[datakeys[k]] = [ uniq_data[s] for s in d_stampdata[datakeys[k]] ]
      lp = print_progress(k+1, len(datakeys), prefix='2/2', suffix="{}/{}".format(k+1,len(datakeys)), decimals=0, bar_length=50, fill='-', empty=' ', lastprogress=lp)

    print("[GRAPH] Done.")

    #if args.all:
    #  print("[GRAPH] Merging available data sources into one line. This is experimental at best...")
    #  d_stampdata["all"] = []
    #  d_datetimedata["all"] = []
    #  d_keydata["all"] = []

    #  for k,v in sorted(copy.deepcopy(d_stampdata).items()):
    #    d_stampdata["all"].extend(v)
    #  for k,v in sorted(copy.deepcopy(d_datetimedata).items()):
    #    d_datetimedata["all"].extend(v)
    #  for k,v in sorted(copy.deepcopy(d_keydata).items()):
    #    d_keydata["all"].extend(v)

    #  datakeys = ["all"]


    print("[GRAPH] Drawing {} data line{} ...".format(len(datakeys), 's' if len(datakeys) > 1 else ''))

    if stamps[0][args.timestamp] < 1451606400 or stamps[0][args.timestamp] > 1640995200: # 2016-2022
      print("[GRAPH] First timestamp seems weird, may try timeReceived for correct results")

    has_plot = False
    for k in range(len(datakeys)):
      stampdata = d_stampdata[datakeys[k]]
      datetimedata = d_datetimedata[datakeys[k]]
      keydata = d_keydata[datakeys[k]]

      if not args.unique and len(stampdata) != len(set(stampdata)):
        print("[GRAPH] there seem to be non-unique timestamps in the data, consider applying the -u option.")

      plot_x = stampdata if args.unix else datetimedata
      plot_y = keydata

      assert len(plot_x) == len(plot_y)

      print("[GRAPH] {} {} | {} -> {} | num: {}".format(k+1, datakeys[k], plot_x[0] if plot_x else '', plot_x[-1] if plot_x else '', len(plot_y)))

      if not plot_x:
        continue

      if args.single:
        ax = fig.add_subplot(1,1,1)
      else:
        ax = fig.add_subplot(len(datakeys), 1, k+1)

      has_plot = True

      y_min_curr = ax.get_ylim()[0]
      y_max_curr = ax.get_ylim()[1]
      y_min_new = min(y_min_curr, min(plot_y)) if args.ymin is None else args.ymin
      y_max_new = max(y_max_curr, max(plot_y)) if args.ymax is None else args.ymax
      ax.set_ylim(y_min_new, y_max_new)

      if args.single:
        ax.set_ylabel([k for k in datakeys])
        ax.set_title("{} {} | {} -> {}".format('', [k for k in datakeys], plot_x[0], plot_x[-1]))
      else:
        ax.set_ylabel(datakeys[k])
        ax.set_title("{} {} | {} -> {}".format(k+1, datakeys[k], plot_x[0], plot_x[-1]))

      ax.set_xlabel('unix timestamp' if args.unix else 'date/time')
      ax.grid(True, which='both', axis='x')

      majorLocator = mdates.AutoDateLocator(minticks=8)#mdates.MinuteLocator()
      majorLocator.intervald[mdates.SECONDLY] = [1,5,10,20,30]
      majorFormatter = mdates.AutoDateFormatter(majorLocator)
      majorFormatter.scaled[1./(mdates.MUSECONDS_PER_DAY)] = '%H:%M:%S'

      ax.xaxis.set_major_locator(majorLocator)
      ax.xaxis.set_major_formatter(majorFormatter)



      if args.verbose and args.verbose > 1:
        print("[GRAPH] plotting samples from data key {}".format(datakeys[k]))
        for i in range(len(plot_x)):
          print("{} | {}".format(plot_x[i], plot_y[i]))
      ax.plot(plot_x, plot_y, label=datakeys[k])

      if args.single:
        #legend = ax.legend(bbox_to_anchor=(1, 0.5), loc=6, shadow=True)
        legend = ax.legend(loc=0, shadow=True)

    if not has_plot:
      print("[GRAPH] nothing to show")
      return
    else:
      print("[GRAPH] Done")

    zoom_level = XYZoomLevel()
    ax_zoom_res = plt.axes([0.01, 0.01, 0.04, 0.025])
    ax_zoom_10s = plt.axes([0.06, 0.01, 0.025, 0.025])
    ax_zoom_30s = plt.axes([0.09, 0.01, 0.025, 0.025])
    ax_zoom_60s = plt.axes([0.12, 0.01, 0.025, 0.025])
    b_zoom_res = Button(ax_zoom_res, 'X reset')
    b_zoom_10s = Button(ax_zoom_10s, '10s')
    b_zoom_30s = Button(ax_zoom_30s, '30s')
    b_zoom_60s = Button(ax_zoom_60s, '60s')
    b_zoom_res.on_clicked(lambda x: zoom_level.setXZoomMM(x,min=datetimedata[0],max=datetimedata[-1],axes=ax))
    b_zoom_10s.on_clicked(lambda x: zoom_level.setXZoom(x,zoom=10,axes=ax))
    b_zoom_30s.on_clicked(lambda x: zoom_level.setXZoom(x,zoom=30,axes=ax))
    b_zoom_60s.on_clicked(lambda x: zoom_level.setXZoom(x,zoom=60,axes=ax))

    ax_y_range = plt.axes([0.01, 0.04, 0.04, 0.025])
    b_y_range = Button(ax_y_range, 'Y reset')
    b_y_range.on_clicked(lambda x: zoom_level.setYZoomMM(x,min=y_min_new,max=y_max_new,axes=ax))

    plt.subplots_adjust(hspace=0.3)
    plt.show()





def parse_fs_tree(path, tree):
  listdir = [ path+"/"+p for p in os.listdir(path) ]
  for p in listdir:
    if os.path.isdir(p):
      tree[p] = collections.OrderedDict()
      parse_fs_tree(p, tree[p])
    elif os.path.isfile(p):
      tree[p] = None
  return tree

def print_fs_tree(tree, level=0):
  for base in tree.keys():
    for t in range(level): print("|---", end="")
    print(os.path.basename(base))
    if tree[base]:
      print_fs_tree(tree[base], level+1)

def isel_fs_tree(tree):
  keylist = list(tree.keys())
  for i in range(len(keylist)):
    p = keylist[i]
    print("{} | {}{}".format(i, "-> " if os.path.isdir(p) else "", os.path.basename(p)))
  sel = int(input("select: "))
  if os.path.isdir(keylist[sel]):
    return isel_fs_tree(tree[keylist[sel]])
  else:
    return keylist[sel]

def interactive(path):
  tree = parse_fs_tree(path, collections.OrderedDict())
  #print_fs_tree(tree)
  sel = isel_fs_tree(tree)
  print(sel)


if __name__=="__main__":
    class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter): pass
    cmdline = argparse.ArgumentParser(description="radar data visualizer, for use with json formatted data streams", formatter_class=Formatter)

    # general options
    cmdline.add_argument('data', metavar='SAMPLES', type=str, nargs='*', default='-', help="sample stream or file, in json format\n")
    cmdline.add_argument('-v', '--verbose', help='be verbose\n', action='count')
    cmdline.add_argument('-u', '--unique', help='only plot unique timestamp data\n', action='store_true')
    cmdline.add_argument('-1', '--single', help='plot into single graph, e.g. for acceleration\n', action='store_true')
    #cmdline.add_argument('-a', '--all', help='merge multiple data sources into one data line\n', action='store_true')
    cmdline.add_argument('-i', '--interactive', type=str, help='interactive mode, reads file structure of provided path and displays options\n')
    cmdline.add_argument('-m', '--maximized', help="start plot maximized\n", action="store_true")

    # timestamp options
    cmdline.add_argument('-s', '--timestamp', metavar='STR', type=str, default="time", choices=stampkeys, help="timestamp to be used.\none of: " + str(stampkeys) + "\n")
    cmdline.add_argument('--utc', help='use UTC time instead of local time\n', action='store_true')
    cmdline.add_argument('--unix', help='use unix timestamp instead of translated time\n', action='store_true')

    # axis options
    cmdline.add_argument('--begin', metavar='STAMP', type=valid_datetime, help="Start date and time. (i.e. xmin)\nFormat: '%%Y-%%m-%%d %%H:%%M:%%S'\n")
    cmdline.add_argument('--end', metavar='STAMP', type=valid_datetime, help="End date and time. (i.e. xmax)\nFormat: '%%Y-%%m-%%d %%H:%%M:%%S'\n")
    cmdline.add_argument('--day', metavar='STAMP', type=valid_date, help="Single day view, 24h\nFormat: '%%Y-%%m-%%d'\n")
    cmdline.add_argument('--ymin', metavar='FLOAT', type=float, help="Y axis minimum\n")
    cmdline.add_argument('--ymax', metavar='FLOAT', type=float, help="Y axis maximum\n")

    # filter options
    cmdline.add_argument('--userID', metavar='STR', type=str, help="Filter by key:userId\n")
    cmdline.add_argument('--sourceID', metavar='STR', type=str, help="Filter by key:sourceId\n")

    args = cmdline.parse_args()

    if args.day and (args.begin or args.end):
      sys.stderr.write("[OPT] conflicting options: --day and --begin/--end are exclusive\n")
      sys.exit(-1)

    if not args.unique and (args.day or args.begin or args.end):
      sys.stderr.write("[OPT] --day, --begin and --end have no effect if --unique is not specified!\n")

    if args.interactive:
      interactive(args.interactive)
      sys.exit(0)

    samples = load(args.data)

    graph(samples)
