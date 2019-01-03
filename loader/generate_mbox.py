#!/usr/bin/env python3
#
# generate_mbox.py - generate an mbox file from the rawtxt stored
#                    in the datatabase.
#

import os
import sys
from datetime import date, timedelta
import calendar
import re

import argparse
from configparser import ConfigParser
import email.parser
import email.policy
import email.generator
from io import BytesIO

import psycopg2


def generate_single_mbox(conn, listid, year, month, destination):
    curs = conn.cursor()
    curs.execute("SELECT id, rawtxt FROM messages m INNER JOIN list_threads t ON t.threadid=m.threadid WHERE hiddenstatus IS NULL AND listid=%(listid)s AND date>=%(startdate)s AND date <= %(enddate)s ORDER BY date", {
        'listid': listid,
        'startdate': date(year, month, 1),
        'enddate': date(year, month, calendar.monthrange(year, month)[1]),
    })
    with open(destination, 'w', encoding='utf8') as f:
        for id, raw, in curs:
            s = BytesIO(raw)
            parser = email.parser.BytesParser(policy=email.policy.compat32)
            msg = parser.parse(s)
            try:
                x = msg.as_string(unixfrom=True)
                f.write(x)
            except UnicodeEncodeError as e:
                print("Not including {0}, unicode error".format(msg['message-id']))
            except Exception as e:
                print("Not including {0}, exception {1}".format(msg['message-id'], e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate mbox file(s)")
    parser.add_argument('--list', type=str, help='List to generate for')
    parser.add_argument('--month', type=str, help='year-month to generate for, e.g. 2017-02')
    parser.add_argument('--destination', type=str, help='File to write into (or directory for --auto)', required=True)
    parser.add_argument('--auto', action='store_true', help='Auto-generate latest month mboxes for all lists')
    parser.add_argument('--quiet', action='store_true', help='Run quiet')

    args = parser.parse_args()

    if args.auto:
        if (args.list or args.month):
            print("Must not specify list and month when auto-generating!")
            sys.exit(1)
        if not os.path.isdir(args.destination):
            print("Destination must be a directory, and exist, when auto-generating")
            sys.exit(1)
    else:
        if not (args.list and args.month and args.destination):
            print("Must specify list, month and destination when generating a single mailbox")
            parser.print_help()
            sys.exit(1)

    # Arguments OK, now connect
    cfg = ConfigParser()
    cfg.read(os.path.join(os.path.realpath(os.path.dirname(sys.argv[0])), 'archives.ini'))
    try:
        connstr = cfg.get('db', 'connstr')
    except:
        connstr = 'need_connstr'

    conn = psycopg2.connect(connstr)
    curs = conn.cursor()

    if args.auto:
        curs.execute("SELECT listid, listname FROM lists WHERE active ORDER BY listname")
        all_lists = curs.fetchall()
        today = date.today()
        yesterday = today - timedelta(days=1)
        if today.month == yesterday.month:
            # Same month, so do it
            monthrange = ((today.year, today.month),)
        else:
            monthrange = ((today.year, today.month), (yesterday.year, yesterday.month))
        for lid, lname in all_lists:
            for year, month in monthrange:
                fullpath = os.path.join(args.destination, lname, 'files/public/archive')
                if not os.path.isdir(fullpath):
                    os.makedirs(fullpath)
                if not args.quiet:
                    print("Generating {0}-{1} for {2}".format(year, month, lname))
                generate_single_mbox(conn, lid, year, month,
                                     os.path.join(fullpath, "{0}.{0:04d}{1:02d}".format(year, month)))
    else:
        # Parse year and month
        m = re.match('^(\d{4})-(\d{2})$', args.month)
        if not m:
            print("Month must be specified on format YYYY-MM, not {0}".format(args.month))
            sys.exit(1)
        year = int(m.group(1))
        month = int(m.group(2))

        curs.execute("SELECT listid FROM lists WHERE listname=%(name)s", {
            'name': args.list,
        })
        if curs.rowcount != 1:
            print("List {0} not found.".format(args.list))
            sys.exit(1)

        if not args.quiet:
            print("Generating {0}-{1} for {2}".format(year, month, args.list))
        generate_single_mbox(conn, curs.fetchone()[0], year, month, args.destination)
