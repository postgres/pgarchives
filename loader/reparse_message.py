#!/usr/bin/env python
#
# reparse_message.py - using the rawtxt stored in the database,
# redo the parsing of it and overwrite it with itself. Used when
# parsing rules have changed.
#

import os
import sys

from optparse import OptionParser
from ConfigParser import ConfigParser
from StringIO import StringIO

import psycopg2

from lib.storage import ArchivesParserStorage
from lib.exception import IgnorableException
from lib.log import log, opstatus
from lib.varnish import VarnishPurger

if __name__ == "__main__":
	optparser = OptionParser()
	optparser.add_option('-m', '--msgid', dest='msgid', help='Messageid to load')
	optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose output')
	optparser.add_option('--force-date', dest='force_date', help='Override date (used for dates that can\'t be parsed)')

	(opt, args) = optparser.parse_args()

	if (len(args)):
		print "No bare arguments accepted"
		optparser.print_usage()
		sys.exit(1)

	if not opt.msgid:
		print "Messageid must be specified"
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

	# Load our message
	curs = conn.cursor()
	curs.execute("SELECT id, rawtxt FROM messages WHERE messageid=%(msgid)s", {
			'msgid': opt.msgid,
			})
	r = curs.fetchall()
	if len(r) == 0:
		log.error("Message '%s' not found" % opt.msgid)
		conn.close()
		sys.exit(1)
	if len(r) != 1:
		log.error("!= 1 row existed (can't happen?) for message '%s'" % opt.msgid)
		conn.close()
		sys.exit(1)
	(id, rawtxt) = r[0]

	ap = ArchivesParserStorage()
	ap.parse(StringIO(rawtxt))
	ap.analyze(date_override=opt.force_date)
	ap.store(conn, listid=-9, overwrite=True)

	conn.commit()
	conn.close()
	opstatus.print_status()
	VarnishPurger(cfg).purge(ap.purges)
