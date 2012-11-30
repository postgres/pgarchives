#!/usr/bin/env python
#
# Make sure the archives are subscribed to the majordomo2 lists,
# to receive realtime data.
#
import os
import sys
import re
from urllib import urlopen, urlencode
from ConfigParser import ConfigParser
import psycopg2

def ensure_subscribed(listname):
	u = 'http://%s/mj/mj_wwwadm?%s' % (
		cfg.get('majordomo', 'server'),
		urlencode((
				('passw', cfg.get('majordomo', 'password')),
				('list', listname),
				('func', 'who-enhanced'),
				('pattern', '%s@%s' % (listname, cfg.get('mail', 'server'))),
				)))
	f = urlopen(u)
	s = f.read()
	f.close()
	if s.find("No matching addresses were found") > 0:
		print "User %s@%s is not subscribed to list %s" % (listname, cfg.get('mail', 'server'), listname)
		if os.isatty(sys.stdout.fileno()):
			while True:
				x = raw_input("Attempt to subscribe? ")
				if x.upper() == 'N': return False
				if x.upper() != 'Y': continue
		else:
			# Output is not a tty, so don't prompt.
			print "Attempting to subscribe..."
			u = 'https://%s/mj/mj_wwwadm?%s' % (cfg.get('majordomo','server'), urlencode((
						('passw', cfg.get('majordomo', 'password')),
						('list', listname),
						('func', 'subscribe-set-nowelcome'),
						('setting', 'hideaddress'),
						('setting', 'hideall'),
						('setting', 'postblock'),
						('setting', 'selfcopy'),
						('setting', 'each'),
						('victims', '%s@%s' % (listname, cfg.get('mail', 'server'))),
						)))
			f = urlopen(u)
			s = f.read()
			f.close()
			if s.find("%s@%s was added to the %s mailing list." % (
					listname,
					cfg.get('mail', 'server'),
					listname)) > 0:
				print "SUCCESS!"
				return True
			else:
				print "FAILED to add the subscriber!"
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
	ok=True
	if checkedboxes.difference(shouldbechecked):
		print "Subscriber for %s has options %s that should NOT be set!" % (
			listname,
			",".join(checkedboxes.difference(shouldbechecked)))
		ok = False
	if shouldbechecked.difference(checkedboxes):
		print "Subscriber for %s is missing options %s that SHOULD Be set!" % (
			listname,
			",".join(shouldbechecked.difference(checkedboxes)))
		ok = False
	return ok

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
