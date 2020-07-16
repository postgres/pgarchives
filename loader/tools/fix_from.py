#!/usr/bin/env python

import os
import sys
import re
import difflib

from ConfigParser import ConfigParser
from StringIO import StringIO

import psycopg2

sys.path.append('..')
from lib.storage import ArchivesParserStorage

if __name__ == "__main__":
    cfg = ConfigParser()
    cfg.read('%s/../archives.ini' % os.path.realpath(os.path.dirname(sys.argv[0])))
    try:
        connstr = cfg.get('db', 'connstr')
    except Exception:
        connstr = 'need_connstr'

    conn = psycopg2.connect(connstr)
    curs = conn.cursor()

    with open('fromlist', 'r') as f:
        for l in f:
            curs.execute("SAVEPOINT msg")

            msgid = l.strip()
            curs.execute("SELECT id, rawtxt, bodytxt FROM messages WHERE messageid=%(msgid)s", {
                'msgid': msgid,
            })
            id, rawtxt, bodytxt = curs.fetchone()

            ap = ArchivesParserStorage()
            s = StringIO(rawtxt)

            # Parse the old message, so we can fix it.
            ap.parse(s)
            ap.analyze()

            # Double check...
            if bodytxt.decode('utf8') == ap.bodytxt:
                print "Message already fixed: %s" % msgid
                curs.execute("ROLLBACK TO SAVEPOINT msg")
                continue

            # Now try to fix it...
            s.seek(0)

            fixed = re.sub('^>From ', 'From ', s.getvalue(), flags=re.MULTILINE)

            curs.execute("UPDATE messages SET rawtxt=%(raw)s WHERE messageid=%(msgid)s", {
                'msgid': msgid,
                'raw': bytearray(fixed),
            })

            # Ok, read it back and try again
            curs.execute("SELECT id, rawtxt, bodytxt FROM messages WHERE messageid=%(msgid)s", {
                'msgid': msgid,
            })
            id, rawtxt, bodytxt = curs.fetchone()

            ap = ArchivesParserStorage()

            # Parse the old message, so we can
            ap.parse(StringIO(rawtxt))
            ap.analyze()

            if ap.bodytxt != bodytxt.decode('utf8'):
                print "Failed to fix %s!" % msgid

                # Generate diff to show what we changed
                print "CHANGED:"
                print "\n".join(difflib.unified_diff(s.getvalue(),
                                                     fixed,
                                                     fromfile='old',
                                                     tofile='new',
                                                     n=2,
                                                     lineterm=''))
                print "----"
                # Generate a diff to show what's left
                print "REMAINING:"
                print "\n".join(difflib.unified_diff(bodytxt.decode('utf8').splitlines(),
                                                     ap.bodytxt.splitlines(),
                                                     fromfile='old',
                                                     tofile='new',
                                                     n=2,
                                                     lineterm=''))
                print "--------------"
                while True:
                    a = raw_input('Save this change anyway?').lower()
                    if a == 'y' or a == 'yes':
                        print "Ok, saving!"
                        curs.execute("RELEASE SAVEPOINT msg")
                        break
                    elif a == 'n' or a == 'no':
                        print "Ok, rolling back!"
                        curs.execute("ROLLBACK TO SAVEPOINT msg")
                        break
                    elif a == 'yq':
                        print "Ok, committing and then exiting"
                        curs.execute("RELEASE SAVEPOINT msg")
                        conn.commit()
                        conn.close()
                        sys.exit(0)
            else:
                print "Fixed %s!" % msgid
                curs.execute("RELEASE SAVEPOINT msg")
            s.close()

    print "Committing all that's there..."
    conn.commit()
    conn.close()
