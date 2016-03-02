#!/usr/bin/env python

import os
import sys
import re
import tempfile
import difflib

from optparse import OptionParser
from ConfigParser import ConfigParser
from StringIO import StringIO

import psycopg2

sys.path.append('..')
from lib.storage import ArchivesParserStorage

if __name__ == "__main__":
	optparser = OptionParser()
	optparser.add_option('-m', dest='msgid', help='Messageid to edit')
	optparser.add_option('-i', dest='id', help='Message primary key id to edit')
	optparser.add_option('-c', dest='charset', help='Charset to edit as', default='utf8')
	optparser.add_option('--nodiff', dest='nodiff', action="store_true", help='Disable viewing of diff', default=False)
	(opt, args) = optparser.parse_args()

	if (len(args)):
		print "No bare arguments accepted"
		optparser.print_usage()
		sys.exit(1)

	cfg = ConfigParser()
	cfg.read('%s/../archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
	try:
		connstr = cfg.get('db','connstr')
	except:
		connstr = 'need_connstr'

	conn = psycopg2.connect(connstr)
	curs = conn.cursor()

	if not (opt.msgid or opt.id):
		print "Need -m or -i!"
		sys.exit(1)
	if opt.msgid and opt.id:
		print "Can't specify both -m and -i!"
		sys.exit(1)

	if opt.msgid:
		curs.execute("SELECT id, rawtxt FROM messages WHERE messageid=%(msgid)s", {
			'msgid': opt.msgid,
		})
	else:
		curs.execute("SELECT id, rawtxt FROM messages WHERE id=%(id)s", {
			'id': opt.id,
		})

	id, rawtxt = curs.fetchone()
	s = StringIO(rawtxt)

	f = tempfile.NamedTemporaryFile(delete=False)
	try:
		f.write(s.getvalue())
		f.close()
		os.system("vim %s" % f.name)
		f2 = open(f.name, "rb")
		s2 = f2.read()
		f2.close()

		if not opt.nodiff:
			print "\n".join(difflib.unified_diff(s.getvalue().decode(opt.charset).splitlines(),
												 s2.decode(opt.charset).splitlines(),
												 fromfile='old',
												 tofile='new',
												 lineterm=''))

		while True:
			a = raw_input('Save this to db?').lower()
			if a == 'y' or a == 'yes':
				curs.execute("INSERT INTO messages_edited SELECT * FROM messages WHERE id=%(id)s", {
					'id': id,
					})
				curs.execute("UPDATE messages SET rawtxt=%(raw)s WHERE id=%(id)s", {
					'id': id,
					'raw': bytearray(s2),
				})
				conn.commit()
				break
			elif a == 'n' or a == 'no':
				print "Ok, not saving"
				break

	finally:
		try:
			f.close()
		except:
			pass
		os.unlink(f.name)
