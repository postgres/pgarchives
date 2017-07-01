#!/usr/bin/env python
#
# hide_message.py - hide a message (spam etc) in the archives, including
# frontend expiry.
#

import os
import sys

from optparse import OptionParser
from ConfigParser import ConfigParser

import psycopg2

from lib.varnish import VarnishPurger

reasons = [
	None, # Placeholder for 0
	"virus",
	"violates policies",
	"privacy",
	"corrupt",
]

if __name__ == "__main__":
	optparser = OptionParser()
	optparser.add_option('-m', '--msgid', dest='msgid', help='Messageid to hide')

	(opt, args) = optparser.parse_args()

	if (len(args)):
		print "No bare arguments accepted"
		optparser.print_help()
		sys.exit(1)

	if not opt.msgid:
		print "Message-id must be specified"
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

	curs.execute("SELECT id, threadid, hiddenstatus FROM messages WHERE messageid=%(msgid)s", {
		'msgid': opt.msgid,
	})
	if curs.rowcount <= 0:
		print "Message not found."
		sys.exit(1)

	id, threadid, previous = curs.fetchone()

	# Message found, ask for reason
	reason = 0
	print "Current status: %s" % reasons[previous or 0]
	print "\n".join("%s - %s " % (n, reasons[n]) for n in range(len(reasons)))
	while True:
		reason = raw_input('Reason for hiding message? ')
		try:
			reason = int(reason)
		except ValueError:
			continue

		if reason == 0:
			print "Un-hiding message"
			reason = None
			break
		else:
			try:
				print "Hiding message for reason: %s" % reasons[reason]
			except:
				continue
			break
	if previous == reason:
		print "No change in status, not updating"
		conn.close()
		sys.exit(0)

	curs.execute("UPDATE messages SET hiddenstatus=%(new)s WHERE id=%(id)s", {
		'new': reason,
		'id': id,
	})
	if curs.rowcount != 1:
		print "Failed to update! Not hiding!"
		conn.rollback()
		sys.exit(0)
	conn.commit()

	VarnishPurger(cfg).purge([int(threadid), ])
	conn.close()

	print "Message hidden and varnish purge triggered."
