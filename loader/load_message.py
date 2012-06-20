#!/usr/bin/env python
#
# load_message.py - takes a single email on standard input
# and reads it into the database.
#

import os
import sys

from optparse import OptionParser

import psycopg2

from lib.storage import ArchivesParserStorage
from lib.mbox import MailboxBreakupParser
from lib.exception import IgnorableException


if __name__ == "__main__":
	optparser = OptionParser()
	optparser.add_option('-l', '--list', dest='list', help='Name of list to loiad message for')
	optparser.add_option('-d', '--directory', dest='directory', help='Load all messages in directory')
	optparser.add_option('-i', '--interactive', dest='interactive', action='store_true', help='Prompt after each message')

	(opt, args) = optparser.parse_args()

	if (len(args)):
		print "No bare arguments accepted"
		optparser.print_usage()
		sys.exit(1)

	if not opt.list:
		print "List must be specified"
		optparser.print_usage()
		sys.exit(1)

	# Yay for hardcoding
	conn = psycopg2.connect("host=/tmp dbname=archives")

	# Get the listid we're working on
	curs = conn.cursor()
	curs.execute("SELECT listid FROM lists WHERE listname=%(list)s", {
			'list': opt.list
			})
	r = curs.fetchall()
	if len(r) != 1:
		print "List %s not found" % opt.list
		conn.close()
		sys.exit(1)
	listid = r[0][0]

	if opt.directory:
		# Parse all files in directory
		for x in os.listdir(opt.directory):
			print "Parsing file %s" % x
			with open(os.path.join(opt.directory, x)) as f:
				ap = ArchivesParserStorage()
				ap.parse(f)
				try:
					ap.analyze()
				except IgnorableException, e:
					print "%s :: ignoring" % e
					continue
				ap.store(conn, listid)
			if opt.interactive:
				print "Interactive mode, committing transaction"
				conn.commit()
				print "Proceed to next message with Enter, or input a period (.) to stop processing"
				x = raw_input()
				if x == '.':
					print "Ok, aborting!"
					break
				print "---------------------------------"
	else:
		# Parse single message on stdin
		ap = ArchivesParserStorage()
		ap.parse(sys.stdin)
		try:
			ap.analyze()
		except IgnorableException, e:
			print "%s :: ignoring" % e
			conn.close()
			sys.exit(1)
		ap.store(conn, listid)

	print "Committing..."
	conn.commit()
	print "Done."
	conn.close()
