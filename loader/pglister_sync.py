#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Synchronize list info from pglister

import os
import sys
from ConfigParser import ConfigParser
import psycopg2
import requests

if __name__=="__main__":
	cfg = ConfigParser()
	cfg.read('%s/archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
	try:
		connstr = cfg.get('db','connstr')
	except:
		connstr = 'need_connstr'

	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	conn = psycopg2.connect(connstr)
	curs = conn.cursor()

	r = requests.get('{0}/api/archive/{1}/lists/'.format(
		cfg.get('pglister', 'root'),
		cfg.get('pglister', 'myname'),
		), headers={
			'X-Api-Key': cfg.get('pglister', 'apikey'),
		})
	obj = r.json()

	# For groups, just add them if they don't exist
	groups = {g['group']['id']:g['group']['groupname'] for g in obj}

	for id,name in groups.items():
		curs.execute("SELECT EXISTS (SELECT 1 FROM listgroups WHERE groupname=%(group)s)", {
			'group': name,
		})
		if not curs.fetchone()[0]:
			curs.execute("INSERT INTO listgroups (groupname, sortkey) VALUES (%(group)s, 100) RETURNING groupname", {
				'group': name,
			})
			print "Added group %s" % name

	# Add any missing lists.
	for l in obj:
		curs.execute("SELECT EXISTS (SELECT 1 FROM lists WHERE listname=%(name)s)", {
			'name': l['listname'],
		})
		if not curs.fetchone()[0]:
			curs.execute("INSERT INTO lists (listname, shortdesc, description, active, groupid) SELECT %(name)s, %(name)s, %(desc)s, 't', id FROM listgroups WHERE groupname=%(groupname)s RETURNING listname", {
				'name': l['listname'],
				'desc': l['shortdesc'],
				'groupname': l['group']['groupname'],
			})
			print "Added list %s" % l['listname']
		else:
			curs.execute("UPDATE lists SET shortdesc=%(name)s, description=%(desc)s, groupid=(SELECT groupid FROM listgroups WHERE groupname=%(groupname)s) WHERE listname=%(name)s AND NOT (shortdesc=%(name)s AND groupid=(SELECT groupid FROM listgroups WHERE groupname=%(groupname)s)) RETURNING listname", {
				'name': l['listname'],
				'desc': l['shortdesc'],
				'groupname': l['group']['groupname'],
			})
			for n, in curs.fetchall():
				print "Updated list %s " % n

	# We don't remove lists ever, because we probably want to keep archives around.
	# But for now, we alert on them.
	curs.execute("SELECT listname FROM lists WHERE active AND NOT listname=ANY(%(lists)s)", {
		'lists': [l['listname'] for l in obj],
	})
	for n, in curs.fetchall():
		print "List %s exists in archives, but not in upstream! Should it be marked inactive?"

	conn.commit()
	conn.close()
