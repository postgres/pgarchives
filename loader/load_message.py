#!/usr/bin/env python
#
# load_message.py - takes a single email on standard input
# and reads it into the database.
#

import os
import sys

from optparse import OptionParser
from ConfigParser import ConfigParser
import urllib

import psycopg2

from lib.storage import ArchivesParserStorage
from lib.mbox import MailboxBreakupParser
from lib.exception import IgnorableException
from lib.log import log, opstatus

def log_failed_message(listid, srctype, src, msg, err):
	try:
		msgid = msg.msgid
	except:
		msgid = "<unknown>"
	log.error("Failed to load message (msgid %s) from %s, spec %s: %s" % (msgid.encode('us-ascii', 'replace'), srctype, src, unicode(str(err), 'us-ascii', 'replace')))

	# We also put the data in the db. This happens in the main transaction
	# so if the whole script dies, it goes away...
	conn.cursor().execute("INSERT INTO loaderrors (listid, msgid, srctype, src, err) VALUES (%(listid)s, %(msgid)s, %(srctype)s, %(src)s, %(err)s)", {
			'listid': listid,
			'msgid': msgid,
			'srctype': srctype,
			'src': src,
			'err': unicode(str(err), 'us-ascii', 'replace'),
			})


if __name__ == "__main__":
	optparser = OptionParser()
	optparser.add_option('-l', '--list', dest='list', help='Name of list to loiad message for')
	optparser.add_option('-d', '--directory', dest='directory', help='Load all messages in directory')
	optparser.add_option('-m', '--mbox', dest='mbox', help='Load all messages in mbox')
	optparser.add_option('-i', '--interactive', dest='interactive', action='store_true', help='Prompt after each message')
	optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose output')
	optparser.add_option('--force-date', dest='force_date', help='Override date (used for dates that can\'t be parsed)')
	optparser.add_option('--filter-msgid', dest='filter_msgid', help='Only process message with given msgid')

	(opt, args) = optparser.parse_args()

	if (len(args)):
		print "No bare arguments accepted"
		optparser.print_usage()
		sys.exit(1)

	if not opt.list:
		print "List must be specified"
		optparser.print_usage()
		sys.exit(1)

	if opt.directory and opt.mbox:
		print "Can't specify both directory and mbox!"
		optparser.print_usage()
		sys.exit(1)

	if opt.force_date and (opt.directory or opt.mbox) and not opt.filter_msgid:
		print "Can't use force_date with directory or mbox - only individual messages"
		optparser.print_usage()
		sys.exit(1)

	if opt.filter_msgid and not (opt.directory or opt.mbox):
		print "filter_msgid makes no sense without directory or mbox!"
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

	# Get the listid we're working on
	curs = conn.cursor()
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
				except IgnorableException, e:
					log_failed_message(listid, "directory", os.path.join(opt.directory, x), ap, e)
					opstatus.failed += 1
					continue
				ap.store(conn, listid)
				purges.update(ap.purges)
			if opt.interactive:
				print "Interactive mode, committing transaction"
				conn.commit()
				print "Proceed to next message with Enter, or input a period (.) to stop processing"
				x = raw_input()
				if x == '.':
					print "Ok, aborting!"
					break
				print "---------------------------------"
	elif opt.mbox:
		if not os.path.isfile(opt.mbox):
			print "File %s does not exist" % opt.mbox
			sys.exit(1)
		mboxparser = MailboxBreakupParser(opt.mbox)
		while not mboxparser.EOF:
			ap = ArchivesParserStorage()
			msg = mboxparser.next()
			if not msg: break
			ap.parse(msg)
			if opt.filter_msgid and not ap.is_msgid(opt.filter_msgid):
				continue
			try:
				ap.analyze(date_override=opt.force_date)
			except IgnorableException, e:
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
		ap.parse(sys.stdin)
		try:
			ap.analyze(date_override=opt.force_date)
		except IgnorableException, e:
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

	if len(purges):
		# There is something to purge
		if cfg.has_option('varnish', 'purgeurl'):
			purgeurl = cfg.get('varnish', 'purgeurl')
			exprlist = []
			for p in purges:
				if isinstance(p, tuple):
					# Purging a list
					exprlist.append('obj.http.x-pglm ~ :%s/%s/%s:' % p)
				else:
					# Purging individual thread
					exprlist.append(purgeexp = 'obj.http.x-pgthread ~ :%s:' % p)
			purgedict = dict(zip(['p%s' % n for n in range(0, len(exprlist))], exprlist))
			purgedict['n'] = len(exprlist)
			r = urllib.urlopen(purgeurl, urllib.urlencode({'purges': purgedict}))
			if r.getcode() != 200:
				log.error("Failed to send purge request!")
