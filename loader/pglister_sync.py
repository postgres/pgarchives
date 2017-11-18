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
		curs.execute("INSERT INTO listgroups (groupid, groupname, sortkey) VALUES (%(id)s, %(group)s, 100) ON CONFLICT (groupid) DO UPDATE SET groupname=excluded.groupname RETURNING groupname", {
			'id': id,
			'group': name,
		})

	# Add any missing lists.
	for l in obj:
		curs.execute("INSERT INTO lists (listid, listname, shortdesc, description, active, groupid) VALUES (%(id)s, %(name)s, %(desc)s, %(desc)s, 't', %(groupid)s) ON CONFLICT (listid) DO UPDATE SET listname=excluded.listname,shortdesc=excluded.shortdesc,groupid=excluded.groupid RETURNING listid", {
			'id': l['listid'],
			'name': l['listname'],
			'desc': l['shortdesc'],
			'groupid': l['group']['id'],
		})

	# We don't remove lists ever, because we probably want to keep archives around.
	# We also don't currently support updating them, but that might be interesting in the future. For now,
	# claim it's a feature that the description can be different :)

	conn.commit()
	conn.close()
