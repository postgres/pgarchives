#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Synchronize list info from pglister

import os
import sys
import argparse
from ConfigParser import ConfigParser
import psycopg2
import requests

if __name__=="__main__":
	parser = argparse.ArgumentParser(description="Synchronize lists from pglister")
	parser.add_argument('--dryrun', action='store_true', help="Don't commit changes to database")

	args = parser.parse_args()

	cfg = ConfigParser()
	cfg.read('%s/archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
	try:
		connstr = cfg.get('db','connstr')
	except:
		connstr = 'need_connstr'

	if cfg.has_option('pglister', 'subscribers') and cfg.getint('pglister', 'subscribers'):
		do_subscribers=1
	else:
		do_subscribers=0

	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	conn = psycopg2.connect(connstr)
	curs = conn.cursor()

	r = requests.get('{0}/api/archive/{1}/lists/?subscribers={2}'.format(
		cfg.get('pglister', 'root'),
		cfg.get('pglister', 'myname'),
		do_subscribers and 1 or 0,
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

	# Add any missing lists, and synchronize their contents.
	for l in obj:
		curs.execute("SELECT listid,listname FROM lists WHERE listname=%(name)s", {
			'name': l['listname'],
		})
		if curs.rowcount == 0:
			curs.execute("INSERT INTO lists (listname, shortdesc, description, active, groupid) SELECT %(name)s, %(name)s, %(desc)s, 't', groupid FROM listgroups WHERE groupname=%(groupname)s RETURNING listid, listname", {
				'name': l['listname'],
				'desc': l['longdesc'],
				'groupname': l['group']['groupname'],
			})
			listid, name = curs.fetchone()
			print "Added list %s" % name
		else:
			listid, name = curs.fetchone()
			curs.execute("UPDATE lists SET shortdesc=%(name)s, description=%(desc)s, groupid=(SELECT groupid FROM listgroups WHERE groupname=%(groupname)s) WHERE listid=%(id)s AND NOT (shortdesc=%(name)s AND description=%(desc)s AND groupid=(SELECT groupid FROM listgroups WHERE groupname=%(groupname)s)) RETURNING listname", {
				'id': listid,
				'name': l['listname'],
				'desc': l['longdesc'],
				'groupname': l['group']['groupname'],
			})
			for n, in curs.fetchall():
				print "Updated list %s " % n

		if do_subscribers:
			# If we synchronize subscribers, we do so on all lists for now.
			curs.execute("WITH t(u) AS (SELECT UNNEST(%(usernames)s)), ins(un) AS (INSERT INTO listsubscribers (username, list_id) SELECT u, %(listid)s FROM t WHERE NOT EXISTS (SELECT 1 FROM listsubscribers WHERE username=u AND list_id=%(listid)s) RETURNING username), del(un) AS (DELETE FROM listsubscribers WHERE list_id=%(listid)s AND NOT EXISTS (SELECT 1 FROM t WHERE u=username) RETURNING username) SELECT 'ins',un FROM ins UNION ALL SELECT 'del',un FROM del ORDER BY 1,2", {
				'usernames': l['subscribers'],
				'listid': listid,
			})
			for what, who in curs.fetchall():
				if what == 'ins':
					print "Added subscriber %s to list %s" % (who, name)
				else:
					print "Removed subscriber %s from list %s" % (who, name)


	# We don't remove lists ever, because we probably want to keep archives around.
	# But for now, we alert on them.
	curs.execute("SELECT listname FROM lists WHERE active AND NOT listname=ANY(%(lists)s)", {
		'lists': [l['listname'] for l in obj],
	})
	for n, in curs.fetchall():
		print "List %s exists in archives, but not in upstream! Should it be marked inactive?"

	if args.dryrun:
		print "Dry-run, rolling back"
		conn.rollback()
	else:
		conn.commit()
	conn.close()
