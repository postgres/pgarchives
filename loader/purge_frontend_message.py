#!/usr/bin/env python3
#
# purge_frontend_message.py - issue varnish purge for the message
# in question, to for example force an expire of a hidden message.
#

import os
import sys

from optparse import OptionParser
from configparser import ConfigParser

import psycopg2

from lib.varnish import VarnishPurger

if __name__ == "__main__":
	optparser = OptionParser()
	optparser.add_option('-m', '--msgid', dest='msgid', help='Messageid to load')

	(opt, args) = optparser.parse_args()

	if (len(args)):
		print("No bare arguments accepted")
		optparser.print_help()
		sys.exit(1)

	if not opt.msgid:
		print("Message-id must be specified")
		optparser.print_help()
		sys.exit(1)

	cfg = ConfigParser()
	cfg.read('%s/archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
	try:
		connstr = cfg.get('db','connstr')
	except:
		connstr = 'need_connstr'

	conn = psycopg2.connect(connstr)
	curs = conn.cursor()

	curs.execute("SELECT id, threadid FROM messages WHERE messageid=%(msgid)s", {
		'msgid': opt.msgid,
	})
	id, threadid = curs.fetchone()

	VarnishPurger(cfg).purge([int(threadid), ])
	conn.close()
