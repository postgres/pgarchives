#!/usr/bin/env python
# -*- coding: utf-8 -*-

import psycopg2
import urllib
import simplejson as json

if __name__=="__main__":
	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	conn = psycopg2.connect("dbname=archives")
	curs = conn.cursor()

	u = urllib.urlopen("http://www.postgresql.org/community/lists/listinfo/")
	obj = json.load(u)
	u.close()

	# XXX: need to fix group processing as well at some point
	curs.execute("SELECT listid, listname FROM lists")
	lists = curs.fetchall()
	for id, name in lists:
		thislist = [x for x in obj['lists'] if x['id'] == id]
		if len(thislist) == 0:
			# We never remove lists from the archives, even if the main
			# db claims they shouldn't exist anymore.
			# XXX: should it still be a warning?
			continue
		else:
			# Compare contents of list
			l = thislist[0]
			if l['name'] != name:
				print "Renaming list %s -> %s" % (name, l['name'])
				curs.execute("UPDATE lists SET listname=%(name)s WHERE listid=%(id)s", l)

	for l in obj['lists']:
		thislist = [x for x in lists if x[0] == l['id']]
		if len(thislist) == 0:
			print "Adding list %s" % l['name']
			curs.execute("INSERT INTO lists (listid, listname) VALUES (%(id)s, %(name)s)",
						 l)

	conn.commit()
