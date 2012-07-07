#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from ConfigParser import ConfigParser
import psycopg2
import psycopg2.extras
import urllib
import simplejson as json

def sync_listinfo(conn, objtype, tablename, attrmap, data):
	curs = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
	reversemap = dict((v,k) for k,v in attrmap.items())

	curs.execute("SELECT %s FROM %s" % (",".join(attrmap.keys()), tablename))
	dbdata = curs.fetchall()

	# First look for all that's already in the db, and might need changing
	for g in dbdata:
		match = [x for x in data if x['id'] == g[reversemap['id']]]
		if len(match) == 0:
			# We never remove a group. Should we warn?
			continue
		else:
			# Compare the contents. Assume keys are always present.
			match = match[0]
			changedattr = [a for a in attrmap.keys() if match[attrmap[a]] != g[a]]
			if len(changedattr):
				for a in changedattr:
					print "%s %s changed %s from %s to %s" % (
						objtype,
						match['id'],
						a,
						g[a],
						match[attrmap[a]])
				transformed = dict([(reversemap[k],v) for k,v in match.items() if reversemap.has_key(k)])	
				curs.execute("UPDATE %s SET %s WHERE %s=%%(%s)s" % (
					tablename,
					",".join(["%s=%%(%s)s" % (a,a) for a in changedattr]),
					reversemap['id'],reversemap['id']
					),
							 transformed)

	# Now look for everything that's not in the db (yet)
	for d in data:
		match = [x for x in dbdata if x[reversemap['id']] == d['id']]
		if len(match) == 0:
			print "Adding %s %s" % (objtype, d['name'])
			transformed = dict([(reversemap[k],v) for k,v in d.items() if reversemap.has_key(k)])	
			curs.execute("INSERT INTO %s (%s) VALUES (%s)" % (
					tablename,
					",".join(attrmap.keys()),
					",".join(["%%(%s)s" % k for k in attrmap.keys()]),
					),
					transformed)


if __name__=="__main__":
	cfg = ConfigParser()
	cfg.read('%s/archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
	try:
		connstr = cfg.get('db','connstr')
	except:
		connstr = 'need_connstr'

	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	conn = psycopg2.connect(connstr)

	u = urllib.urlopen("http://www.postgresql.org/community/lists/listinfo/")
	obj = json.load(u)
	u.close()

	# Start by syncing groups
	sync_listinfo(conn,
				  "group",
				  "listgroups",
				  {'groupid':'id', 'groupname': 'name'},
				  obj['groups'],
				  )

	# Now also do groups
	sync_listinfo(conn,
				  "list",
				  "lists",
				  {'listid':'id', 'listname': 'name', 'shortdesc':'shortdesc', 'description':'description', 'active':'active', 'groupid':'groupid'},
				  obj['lists'],
				  )

	conn.commit()
