#!/usr/bin/env python
#
# Make sure the archives are subscribed to the majordomo2 lists,
# to receive realtime data.
#
import os
import sys
import re
from urllib import urlopen
from ConfigParser import ConfigParser
import psycopg2

def ensure_subscribed(listname):
	u = 'http://%s/mj/mj_wwwadm?passw=%s&list=%s&func=who-enhanced&pattern=%s@%s' % (
		cfg.get('majordomo', 'server'),
		cfg.get('majordomo', 'password'),
		listname,
		listname,
		cfg.get('mail', 'server'),
		)
	f = urlopen(u)
	s = f.read()
	f.close()
	if s.find("No matching addresses were found") > 0:
		print "User %s@%s is not subscribed to list %s" % (listname, cfg.get('mail', 'server'), listname)
		return False

	# Wow this is ugly - but regexps are useful
	m = re.search('Addresses found: (\d+)\s', s)
	if not m:
		print "Could not determine match count for list %s" % listname
		return False
	matchcount = int(m.group(1))
	if matchcount != 1:
		print "Found %s matches, not 1, for list %s" % (matchcount, listname)
		return False
	# Now validate the checkboxes
	checkedboxes = set(re.findall('<td align="center"><input type="checkbox" name="%s@%s" value="([^"]+)" checked>' % (listname, cfg.get('mail', 'server')), s))
	shouldbechecked = set(('hideaddress', 'hideall', 'postblock', 'selfcopy'))
	if checkedboxes.difference(shouldbechecked):
		print "Subscriber for %s has options %s that should NOT be set!" % (
			listname,
			",".join(checkedboxes.difference(shouldbechecked)))
	if shouldbechecked.difference(checkedboxes):
		print "Subscriber for %s is missing options %s that SHOULD Be set!" % (
			listname,
			",".join(shouldbechecked.difference(checkedboxes)))

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
	curs.execute("SELECT listname FROM lists WHERE active ORDER BY listname")
	for listname, in curs.fetchall():
		ensure_subscribed(listname)
