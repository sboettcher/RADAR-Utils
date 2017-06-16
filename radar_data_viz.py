#!/usr/bin/env python3

import sys, os, time
import argparse, json, csv, fileinput
import copy
import math, random
import numpy as np
from pprint import pprint

import matplotlib
import matplotlib.pyplot as plt

from datetime import datetime,timezone

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
        if not csv_header: csv_header = line.split(",")
        else: samples.append(parse_csv(csv_header, line.split(","), s, len(streams)))

  print("[LOAD] Done. Loaded", len(samples), "samples")
  return samples

def parse_json(line, idx, num):
  sample = json.loads(line)
  if num > 1:
    datakeys = [ k for k in sample["value"].keys() if "time" not in k ]
    for k in datakeys:
      sample["value"]["{0:0{width}d}_{1}".format(idx+1,k, width=len(str(num)))] = sample["value"].pop(k)
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


def graph(args, samples):
    fig = plt.figure(1, figsize=(15,8))
    fig.clf()
    fig.canvas.set_window_title('data')

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

    if args.all:
      print("[GRAPH] Merging available data sources into one line. This is experimental at best...")
      d_stampdata["all"] = []
      d_datetimedata["all"] = []
      d_keydata["all"] = []

      for k,v in sorted(copy.deepcopy(d_stampdata).items()):
        d_stampdata["all"].extend(v)
      for k,v in sorted(copy.deepcopy(d_datetimedata).items()):
        d_datetimedata["all"].extend(v)
      for k,v in sorted(copy.deepcopy(d_keydata).items()):
        d_keydata["all"].extend(v)

      datakeys = ["all"]

    #sys.exit(0)

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

    plt.subplots_adjust(hspace=0.3)
    plt.show()








if __name__=="__main__":
    class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter): pass
    cmdline = argparse.ArgumentParser(description="radar data visualizer, for use with json formatted data streams", formatter_class=Formatter)

    # general options
    cmdline.add_argument('data', metavar='SAMPLES', type=str, nargs='*', default='-', help="sample stream or file, in json format\n")
    cmdline.add_argument('-v', '--verbose', help='be verbose\n', action='count')
    cmdline.add_argument('-u', '--unique', help='only plot unique timestamp data\n', action='store_true')
    cmdline.add_argument('-1', '--single', help='plot into single graph, e.g. for acceleration\n', action='store_true')
    cmdline.add_argument('-a', '--all', help='merge multiple data sources into one data line\n', action='store_true')

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

    samples = load(args.data)

    graph(args, samples)
