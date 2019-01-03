#!/usr/bin/env python3
#
# load_message.py - takes a single email or mbox formatted
# file on stdin or in a file and reads it into the database.
#

import os
import sys

from optparse import OptionParser
from configparser import ConfigParser
import urllib.request, urllib.parse, urllib.error
import urllib.request, urllib.error, urllib.parse

import psycopg2

from lib.storage import ArchivesParserStorage
from lib.mbox import MailboxBreakupParser
from lib.exception import IgnorableException
from lib.log import log, opstatus
from lib.varnish import VarnishPurger

def log_failed_message(listid, srctype, src, msg, err):
    try:
        msgid = msg.msgid
    except:
        msgid = "<unknown>"
    log.error("Failed to load message (msgid %s) from %s, spec %s: %s" % (msgid.encode('us-ascii', 'replace'), srctype, src, str(str(err), 'us-ascii', 'replace')))

    # We also put the data in the db. This happens in the main transaction
    # so if the whole script dies, it goes away...
    conn.cursor().execute("INSERT INTO loaderrors (listid, msgid, srctype, src, err) VALUES (%(listid)s, %(msgid)s, %(srctype)s, %(src)s, %(err)s)", {
            'listid': listid,
            'msgid': msgid,
            'srctype': srctype,
            'src': src,
            'err': str(str(err), 'us-ascii', 'replace'),
            })


if __name__ == "__main__":
    optparser = OptionParser()
    optparser.add_option('-l', '--list', dest='list', help='Name of list to load message for')
    optparser.add_option('-d', '--directory', dest='directory', help='Load all messages in directory')
    optparser.add_option('-m', '--mbox', dest='mbox', help='Load all messages in mbox')
    optparser.add_option('-i', '--interactive', dest='interactive', action='store_true', help='Prompt after each message')
    optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose output')
    optparser.add_option('--force-date', dest='force_date', help='Override date (used for dates that can\'t be parsed)')
    optparser.add_option('--filter-msgid', dest='filter_msgid', help='Only process message with given msgid')

    (opt, args) = optparser.parse_args()

    if (len(args)):
        print("No bare arguments accepted")
        optparser.print_usage()
        sys.exit(1)

    if not opt.list:
        print("List must be specified")
        optparser.print_usage()
        sys.exit(1)

    if opt.directory and opt.mbox:
        print("Can't specify both directory and mbox!")
        optparser.print_usage()
        sys.exit(1)

    if opt.force_date and (opt.directory or opt.mbox) and not opt.filter_msgid:
        print("Can't use force_date with directory or mbox - only individual messages")
        optparser.print_usage()
        sys.exit(1)

    if opt.filter_msgid and not (opt.directory or opt.mbox):
        print("filter_msgid makes no sense without directory or mbox!")
        optparser.print_usage()
        sys.exit(1)

    log.set(opt.verbose)

    cfg = ConfigParser()
    cfg.read('%s/archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
    try:
        connstr = cfg.get('db','connstr')
    except:
        connstr = 'need_connstr'

    conn = psycopg2.connect(connstr)
    curs = conn.cursor()

    # Take an advisory lock to force serialization.
    # We could do this "properly" by reordering operations and using ON CONFLICT,
    # but concurrency is not that important and this is easier...
    try:
        curs.execute("SET statement_timeout='30s'")
        curs.execute("SELECT pg_advisory_xact_lock(8059944559669076)")
    except Exception as e:
        print(("Failed to wait on advisory lock: %s" % e))
        sys.exit(1)

    # Get the listid we're working on
    curs.execute("SELECT listid FROM lists WHERE listname=%(list)s", {
            'list': opt.list
            })
    r = curs.fetchall()
    if len(r) != 1:
        log.error("List %s not found" % opt.list)
        conn.close()
        sys.exit(1)
    listid = r[0][0]

    purges = set()

    if opt.directory:
        # Parse all files in directory
        for x in os.listdir(opt.directory):
            log.status("Parsing file %s" % x)
            with open(os.path.join(opt.directory, x)) as f:
                ap = ArchivesParserStorage()
                ap.parse(f)
                if opt.filter_msgid and not ap.is_msgid(opt.filter_msgid):
                    continue
                try:
                    ap.analyze(date_override=opt.force_date)
                except IgnorableException as e:
                    log_failed_message(listid, "directory", os.path.join(opt.directory, x), ap, e)
                    opstatus.failed += 1
                    continue
                ap.store(conn, listid)
                purges.update(ap.purges)
            if opt.interactive:
                print("Interactive mode, committing transaction")
                conn.commit()
                print("Proceed to next message with Enter, or input a period (.) to stop processing")
                x = input()
                if x == '.':
                    print("Ok, aborting!")
                    break
                print("---------------------------------")
    elif opt.mbox:
        if not os.path.isfile(opt.mbox):
            print("File %s does not exist" % opt.mbox)
            sys.exit(1)
        mboxparser = MailboxBreakupParser(opt.mbox)
        while not mboxparser.EOF:
            ap = ArchivesParserStorage()
            msg = next(mboxparser)
            if not msg:
                break
            ap.parse(msg)
            if opt.filter_msgid and not ap.is_msgid(opt.filter_msgid):
                continue
            try:
                ap.analyze(date_override=opt.force_date)
            except IgnorableException as e:
                log_failed_message(listid, "mbox", opt.mbox, ap, e)
                opstatus.failed += 1
                continue
            ap.store(conn, listid)
            purges.update(ap.purges)
        if mboxparser.returncode():
            log.error("Failed to parse mbox:")
            log.error(mboxparser.stderr_output())
            sys.exit(1)
    else:
        # Parse single message on stdin
        ap = ArchivesParserStorage()
        ap.parse(sys.stdin.buffer)
        try:
            ap.analyze(date_override=opt.force_date)
        except IgnorableException as e:
            log_failed_message(listid, "stdin","", ap, e)
            conn.close()
            sys.exit(1)
        ap.store(conn, listid)
        purges.update(ap.purges)
        if opstatus.stored:
            log.log("Stored message with message-id %s" % ap.msgid)

    conn.commit()
    conn.close()
    opstatus.print_status()

    VarnishPurger(cfg).purge(purges)
