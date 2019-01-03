#!/usr/bin/env python3
#
# Clean up old, broken, dates
#

import os
import sys
import re

from configparser import ConfigParser

from email.parser import Parser
from urllib.request import urlopen
import dateutil.parser

import psycopg2


def scan_message(messageid, olddate, curs):
    u = "http://archives.postgresql.org/msgtxt.php?id=%s" % messageid
    print("Scanning message at %s (date reported as %s)..." % (u, olddate))

    f = urlopen(u)
    p = Parser()
    msg = p.parse(f)
    f.close()

    # Can be either one of them, but we really don't care...
    ds = None
    for k, r in list(msg.items()):
        if k != 'Received': continue

        print("Trying on %s" % r)
        m = re.search(';\s*(.*)$', r)
        if m:
            ds = m.group(1)
            break
        m = re.search(';\s*(.*)\s*\(envelope-from [^\)]+\)$', r)
        if m:
            ds = m.group(1)
            break

    if not ds:
        print("Could not find date. Sorry.")
        return False
    d = None
    try:
        d = dateutil.parser.parse(ds)
    except:
        print("Could not parse date '%s', sorry." % ds)
        return

    while True:
        x = input("Parsed this as date %s. Update? " % d)
        if x.upper() == 'Y':
            curs.execute("UPDATE messages SET date=%(d)s WHERE messageid=%(m)s", {
                'd': d,
                'm': messageid,
            })
            print("Updated.")
            break
        elif x.upper() == 'N':
            break


if __name__ == "__main__":
    cfg = ConfigParser()
    cfg.read('%s/archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
    connstr = cfg.get('db', 'connstr')

    conn = psycopg2.connect(connstr)

    curs = conn.cursor()
    curs.execute("SELECT messageid, date FROM messages WHERE date>(CURRENT_TIMESTAMP+'1 day'::interval) OR date < '1997-01-01'")
    for messageid, date in curs.fetchall():
        scan_message(messageid, date, curs)

    conn.commit()
    print("Done.")
