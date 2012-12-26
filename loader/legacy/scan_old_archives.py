#!/usr/bin/env python

# Scan the old archives, including all subdirs, and generate
# a mapping table on the format:
# <listid>;<year>;<month>;num;<messageid>

# Used to map from the old site

import os
import os.path
import sys
import re

root = "/srv/archives/repo/archives/html"


# Holy crap this is ugly, but yes, this is a direct dump from the
# global database. Because, well, it doesn't actually matter :)
# Run (in \a mode):
#  select '''' || listname || ''':' || listid || ',' from lists order by listname;
listmap = {
'adelaide-au-pug':63,
'am-central-pug':62,
'arpug':61,
'atlpug':42,
'austinpug':49,
'bapug':55,
'bostonpug':50,
'bwpug':48,
'denpug':69,
'ecpug':71,
'iepug':73,
'jnbpug':66,
'lapug':43,
'melbourne-au-pug':65,
'mtlpug':68,
'mumbai-pug':70,
'norpug':57,
'ohiopug':47,
'okpug':52,
'pdxpug':41,
'persianpug':40,
'pgadmin-hackers':25,
'pgadmin-support':26,
'pgeu-general':36,
'pgsql-admin':5,
'pgsql-advocacy':6,
'pgsql-announce':7,
'pgsql-benchmarks':14,
'pgsql-bugs':8,
'pgsql-chat':15,
'pgsql-cluster-hackers':74,
'pgsql-committers':16,
'pgsql-cygwin':17,
'pgsql-de-allgemein':28,
'pgsql-docs':10,
'pgsql-es-ayuda':29,
'pgsql-es-fomento':60,
'pgsql-es-trabajos':77,
'pgsql-fr-generale':27,
'pgsql-general':2,
'pgsql-hackers':1,
'pgsql-hackers-pitr':54,
'pgsql-hackers-win32':18,
'pgsql-in-general':38,
'pgsql-interfaces':11,
'pgsql-it-generale':39,
'pgsql-jdbc':19,
'pgsql-jobs':20,
'pgsql-nl-algemeen':37,
'pgsql-novice':12,
'pgsql-odbc':21,
'pgsql-patches':3,
'pgsql-performance':13,
'pgsql-php':22,
'pgsql-pkg-debian':76,
'pgsql-pkg-yum':79,
'pgsql-ports':23,
'pgsql-rrreviewers':59,
'pgsql-ru-general':30,
'pgsql-sql':4,
'pgsql-students':34,
'pgsql-testers':72,
'pgsql-tr-genel':31,
'pgsql-www':24,
'pgsql-zh-general':81,
'pgus-general':46,
'psycopg':75,
'rgnpug':67,
'seapug':44,
'sfpug':32,
'spug':45,
'sthlm-pug':78,
'sydpug':33,
'torontopug':53,
'vepug':56,
}

def get_messageid(fn):
	with open(fn) as f:
		for l in f:
			if l.startswith('<!--X-Message-Id: '):
				# Found it!
				return l[18:-5]
	raise Exception("No messageid in %s" % fn)

dirre = re.compile("^(\d+)-(\d+)$")
fnre = re.compile("^msg(\d+)\.php$")
for (dirpath, dirnames, filenames) in os.walk(root):
	# Dirpath is the full pathname
	base = os.path.basename(dirpath)
	m = dirre.match(base)
	if m:
		# Directory with actual files in it
		listname = os.path.basename(os.path.dirname(dirpath))
		for fn in filenames:
			m2 = fnre.match(fn)
			if m2:
				print "%s;%s;%s;%s;%s" % (listmap[listname], m.group(1), m.group(2), m2.group(1), get_messageid("%s/%s" % (dirpath, fn)))
