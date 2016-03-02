#!/usr/bin/env python
#
# reparse_message.py - using the rawtxt stored in the database,
# redo the parsing of it and overwrite it with itself. Used when
# parsing rules have changed.
#

import os
import sys
import codecs

from optparse import OptionParser
from ConfigParser import ConfigParser
from StringIO import StringIO
from datetime import datetime, timedelta

import psycopg2

from lib.storage import ArchivesParserStorage
from lib.exception import IgnorableException
from lib.log import log, opstatus
from lib.varnish import VarnishPurger

def ResultIter(cursor):
	# Fetch lots of data but keep memory usage down a bit, by feeding it out of
	# a generator, and use fetchmany()
	while True:
		results = cursor.fetchmany(5000)
		if not results:
			break
		for r in results:
			yield r


if __name__ == "__main__":
	optparser = OptionParser()
	optparser.add_option('-m', '--msgid', dest='msgid', help='Messageid to load')
	optparser.add_option('--all', dest='all', action='store_true', help='Load *all* messages currently in the db')
	optparser.add_option('--sample', dest='sample', help='Load a sample of <n> messages')
	optparser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Verbose output')
	optparser.add_option('--force-date', dest='force_date', help='Override date (used for dates that can\'t be parsed)')
	optparser.add_option('--update', dest='update', action='store_true', help='Actually update, not just diff (default is diff)')

	(opt, args) = optparser.parse_args()

	if (len(args)):
		print "No bare arguments accepted"
		optparser.print_usage()
		sys.exit(1)

	if sum([1 for x in [opt.all, opt.sample, opt.msgid] if x]) != 1:
		print "Must specify exactly one of --msgid, --all and --sample"
		sys.exit(1)

	if not opt.update and os.path.exists('reparse.diffs'):
		print "File reparse.diffs already exists. Remove or rename and try again."
		sys.exit(1)

	log.set(opt.verbose)

	cfg = ConfigParser()
	cfg.read('%s/archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
	try:
		connstr = cfg.get('db','connstr')
	except:
		connstr = 'need_connstr'

	conn = psycopg2.connect(connstr)

	# Get messages
	curs = conn.cursor('msglist')
	if opt.all:
		curs.execute("SELECT id, rawtxt FROM messages WHERE hiddenstatus IS NULL ORDER BY id")
	elif opt.sample:
		curs.execute("SELECT id, rawtxt FROM messages WHERE hiddenstatus IS NULL ORDER BY id DESC LIMIT %(num)s", {
			'num': int(opt.sample),
		})
	else:
		curs.execute("SELECT id, rawtxt FROM messages WHERE messageid=%(msgid)s", {
			'msgid': opt.msgid,
		})

	if not opt.update:
		f = codecs.open("reparse.diffs", "w", "utf-8")
		fromonlyf = open("reparse.fromonly","w")

	firststatus = datetime.now()
	laststatus = datetime.now()
	num = 0
	for id, rawtxt in ResultIter(curs):
		num += 1
		ap = ArchivesParserStorage()
		ap.parse(StringIO(rawtxt))
		try:
			ap.analyze(date_override=opt.force_date)
		except IgnorableException, e:
			if opt.update:
				raise e
			f.write("Message %s lacks message-id?\n" % id)
			continue

		if opt.update:
			ap.store(conn, listid=-9, overwrite=True)
		else:
			ap.diff(conn, f, fromonlyf, id)
		if datetime.now() - laststatus > timedelta(seconds=5):
			sys.stdout.write("%s messages parsed (%s / second)\r" % (num, num / ((datetime.now()-firststatus).seconds)))
			sys.stdout.flush()
			laststatus = datetime.now()

	print ""

	if opt.update:
		conn.commit()
		VarnishPurger(cfg).purge(ap.purges)
		opstatus.print_status()
	else:
		fromonlyf.close()
		f.close()
		if os.path.getsize('reparse.diffs') == 0:
			os.unlink('reparse.diffs')
		# Just in case
		conn.rollback()
	conn.close()
