#!/usr/bin/python3 -u
#
# archives_resender.py - resend messages to authenticated users
#
# This script is intended to be run as a daemon.
#


import os
import sys
import select
import smtplib
from configparser import ConfigParser
import psycopg2


def process_queue(conn, sender, smtpserver, heloname):
    with conn.cursor() as curs:
        curs.execute("SELECT r.id, u.email, m.rawtxt FROM mailarchives_resendmessage r INNER JOIN auth_user u ON u.id=r.sendto_id INNER JOIN messages m ON m.id=r.message_id ORDER BY r.id FOR UPDATE OF r LIMIT 1")
        ll = curs.fetchall()
        if len(ll) == 0:
            conn.rollback()
            return False

        recipient = ll[0][1]
        contents = ll[0][2]

        try:
            # Actually resend! New SMTP connection for each message because we're not sending
            # that many.
            smtp = smtplib.SMTP(smtpserver, local_hostname=heloname)
            smtp.sendmail(sender, recipient, contents)
            smtp.close()
        except Exception as e:
            sys.stderr.write("Error sending email to {0}: {1}\n".format(recipient, e))

            # Fall through and just delete the email, we never make more than one attempt

        curs.execute("DELETE FROM mailarchives_resendmessage WHERE id=%(id)s", {
            'id': ll[0][0],
        })
        conn.commit()
        return True


if __name__ == "__main__":
    cfg = ConfigParser()
    cfg.read(os.path.join(os.path.realpath(os.path.dirname(sys.argv[0])), '../loader', 'archives.ini'))
    if not cfg.has_option('smtp', 'server'):
        print("Must specify server under smtp in configuration")
        sys.exit(1)
    if not cfg.has_option('smtp', 'heloname'):
        print("Must specify heloname under smtp in configuration")
        sys.exit(1)
    if not cfg.has_option('smtp', 'resender'):
        print("Must specify resender under smtp in configuration")
        sys.exit(1)

    smtpserver = cfg.get('smtp', 'server')
    heloname = cfg.get('smtp', 'heloname')
    sender = cfg.get('smtp', 'resender')

    conn = psycopg2.connect(cfg.get('db', 'connstr') + ' application_name=archives_resender')

    curs = conn.cursor()

    curs.execute("LISTEN archives_resend")
    conn.commit()

    while True:
        # Process everything in the queue now
        while True:
            if not process_queue(conn, sender, smtpserver, heloname):
                break

        # Wait for a NOTIFY. Poll every 5 minutes.
        select.select([conn], [], [], 5 * 60)

        # Eat up all notifications, since we're just going to process
        # all pending messages until the queue is empty.
        conn.poll()
        while conn.notifies:
            conn.notifies.pop()
