import pytz
import json
import copy
import datetime
import numpy
import sys
import time
import requests
sys.path.append('..')
from model import date2secs


def make_blob(epoch):
    blob = {
        "root.folder.sin": numpy.sin(2*numpy.pi*(1/20)*epoch),
        "root.folder.cos": numpy.cos(2*numpy.pi*(1/20)*epoch),
        "root.folder.step": round(epoch%20),
        "root.folder.time": epoch
    }
    return blob



def write_test(rate):

    while True:
        time.sleep(float(rate)/1000)
        now = datetime.datetime.now(pytz.timezone("Europe/Berlin"))
        epoch = date2secs(now)
        blob = make_blob(epoch)
        body = [blob]
        try:
            r = requests.post("http://localhost:6001/_appendRow", data=json.dumps(body),timeout=0.1)
            print(f"sent {json.dumps(body)} with result {r.status_code}")
        except Exception as ex:
            print(f"sent {json.dumps(body)} with exception {ex}")


if __name__ == '__main__':
    # give the rate in ms
    if len(sys.argv)>1:
        rate = int(sys.argv[1])
    else:
        rate = 1000
    write_test(rate)