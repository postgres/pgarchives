#!/usr/bin/env python
#
# load_message.py - takes a single email on standard input
# and reads it into the database.
#

import os
import sys
import re
import datetime
import dateutil.parser

from optparse import OptionParser
from email.parser import Parser
from email.header import decode_header

import psycopg2

class IgnorableException(Exception):
	pass

class ArchivesParser(object):
	def __init__(self):
		self.parser = Parser()

	def parse(self, stream):
		self.msg = self.parser.parse(stream)

	def analyze(self):
		self.msgid = self.clean_messageid(self.get_mandatory('Message-ID'))
		self._from = self.decode_mime_header(self.get_mandatory('From'))
		self.to = self.decode_mime_header(self.get_mandatory('To'))
		self.cc = self.decode_mime_header(self.get_optional('CC'))
		self.subject = self.decode_mime_header(self.get_mandatory('Subject'))
		self.date = self.forgiving_date_decode(self.get_mandatory('Date'))
		self.bodytxt = self.get_body()
		self.attachments = []
		self.get_attachments()
		if len(self.attachments) > 0:
			print "Found %s attachments" % len(self.attachments)
			print [(a[0],a[1],len(a[2])) for a in self.attachments]

		# Build an list of the message id's we are interested in
		self.parents = []
		# The first one is in-reply-to, if it exists
		if self.get_optional('in-reply-to'):
			m = self.clean_messageid(self.get_optional('in-reply-to'), True)
			if m:
				self.parents.append(m)

		# Then we add all References values, in backwards order
		if self.get_optional('references'):
			cleaned_msgids = [self.clean_messageid(x, True) for x in reversed(self.get_optional('references').split())]
			# Can't do this with a simple self.parents.extend() due to broken
			# mailers that add the same reference more than once. And we can't
			# use a set() to make it unique, because order is very important
			for m in cleaned_msgids:
				if m and not m in self.parents:
					self.parents.append(m)


	def store(self, conn, listid):
		curs = conn.cursor()
		curs.execute("SELECT threadid, EXISTS(SELECT threadid FROM list_threads lt WHERE lt.listid=%(listid)s AND lt.threadid=m.threadid) FROM messages m WHERE m.messageid=%(messageid)s", {
				'messageid': self.msgid,
				'listid': listid,
				})
		r = curs.fetchall()
		if len(r) > 0:
			# Has to be 1 row, since we have a unique index on id
			if not r[0][1]:
				print "Tagging message %s with list %s" % (self.msgid, listid)
				curs.execute("INSERT INTO list_threads (threadid, listid) VALUES (%(threadid)s, %(listid)s)", {
						'threadid': r[0][0],
						'listid': listid,
						})

			#FIXME: option to overwrite existing message!
			print "Message %s already stored" % self.msgid
			return

		# Resolve own thread
		curs.execute("SELECT id, messageid, threadid FROM messages WHERE messageid=ANY(%(parents)s)", {
				'parents': self.parents,
				})
		all_parents = curs.fetchall()
		if len(all_parents):
			# At least one of the parents exist. Now try to figure out which one
			best_parent = len(self.parents)+1
			best_threadid = -1
			best_parentid = None
			for i in range(0,len(all_parents)):
				for j in range(0,len(self.parents)):
					if self.parents[j] == all_parents[i][1]:
						# This messageid found. Better than the last one?
						if j < best_parent:
							best_parent = j
							best_parentid = all_parents[i][0]
							best_threadid = all_parents[i][2]
			if best_threadid == -1:
				raise Exception("Message %s, resolve failed in a way it shouldn't :P" % selg.msgid)
			self.parentid = best_parentid
			self.threadid = best_threadid
			# Slice away all matches that are worse than the one we wanted
			self.parents = self.parents[:best_parent]
			
			print "Message %s resolved to existing thread %s, waiting for %s better messages" % (self.msgid, self.threadid, len(self.parents))
		else:
			# No parent exist. But don't create the threadid just yet, since
			# it's possible that we're somebody elses parent!
			self.parentid = None
			self.threadid = None
			
		# Now see if we are somebody elses *parent*...
		curs.execute("SELECT message, priority, threadid FROM unresolved_messages INNER JOIN messages ON messages.id=unresolved_messages.message WHERE unresolved_messages.msgid=%(msgid)s ORDER BY threadid", {
				'msgid': self.msgid,
				})
		childrows = curs.fetchall()
		if len(childrows):
			# We are some already existing message's parent (meaning the
			# messages arrived out of order)
			# In the best case, the threadid is the same for all threads.
			# But it might be different if this it the "glue message" that's
			# holding other threads together.
			self.threadid = childrows[0][2]

			# Get a unique list (set) of all threads *except* the primary one,
			# because we'll be merging into that one.
			mergethreads = set([r[2] for r in childrows]).difference(set((self.threadid,)))
			if len(mergethreads):
				# We have one or more merge threads
				print "Merging threads %s into thread %s" % (",".join(str(s) for s in mergethreads), self.threadid)
				curs.execute("UPDATE messages SET threadid=%(threadid)s WHERE threadid=ANY(%(oldthreadids)s)", {
						'threadid': self.threadid,
						'oldthreadids': list(mergethreads),
						})
				# Insert any lists that were tagged on the merged threads
				curs.execute("INSERT INTO list_threads (threadid, listid) SELECT %(threadid)s,listid FROM list_threads lt2 WHERE lt2.threadid=ANY(%(oldthreadids)s) AND listid NOT IN (SELECT listid FROM list_threads lt3 WHERE lt3.threadid=%(threadid)s)", {
						'threadid': self.threadid,
						'oldthreadids': list(mergethreads),
						})
				# Remove all old leftovers
				curs.execute("DELETE FROM list_threads WHERE threadid=ANY(%(oldthreadids)s)", {
						'oldthreadids': list(mergethreads),
						})

			# Batch all the children for repointing. We can't do the actual
			# repointing until later, since we don't know our own id yet.
			self.children = [r[0] for r in childrows]

			# Finally, remove all the pending messages that had a higher
			# priority value (meaning less important) than us
			curs.executemany("DELETE FROM unresolved_messages WHERE message=%(msg)s AND priority >= %(prio)s", [{
						'msg': msg,
						'prio': prio,
						} for msg, prio, tid in childrows])
		else:
			self.children = []

		if not self.threadid:
			# No parent and no child exists - create a new threadid, just for us!
			curs.execute("SELECT nextval('threadid_seq')")
			self.threadid = curs.fetchall()[0][0]
			print "Message %s resolved to no parent (out of %s) and no child, new thread %s" % (self.msgid, len(self.parents), self.threadid)

		# Insert a thread tag if we're on a new list
		curs.execute("INSERT INTO list_threads (threadid, listid) SELECT %(threadid)s, %(listid)s WHERE NOT EXISTS (SELECT * FROM list_threads t2 WHERE t2.threadid=%(threadid)s AND t2.listid=%(listid)s) RETURNING threadid", {
			'threadid': self.threadid,
			'listid': listid,
			})
		if len(curs.fetchall()):
			print "Tagged thread %s with listid %s" % (self.threadid, listid)

		curs.execute("INSERT INTO messages (parentid, threadid, _from, _to, cc, subject, date, messageid, bodytxt) VALUES (%(parentid)s, %(threadid)s, %(from)s, %(to)s, %(cc)s, %(subject)s, %(date)s, %(messageid)s, %(bodytxt)s) RETURNING id", {
				'parentid': self.parentid,
				'threadid': self.threadid,
				'from': self._from,
				'to': self.to or '',
				'cc': self.cc or '',
				'subject': self.subject,
				'date': self.date,
				'messageid': self.msgid,
				'bodytxt': self.bodytxt,
				})
		id = curs.fetchall()[0][0]
		if len(self.attachments):
			# Insert attachments
			curs.executemany("INSERT INTO attachments (message, filename, contenttype, attachment) VALUES (%(message)s, %(filename)s, %(contenttype)s, %(attachment)s)",[ {
						'message': id,
						'filename': a[0] or 'unknown_filename',
						'contenttype': a[1],
						'attachment': bytearray(a[2]),
						} for a in self.attachments])

		if len(self.children):
			print "Setting %s other threads to children of %s" % (len(self.children), self.msgid)
			curs.executemany("UPDATE messages SET parentid=%(parent)s WHERE id=%(id)s",
							 [{'parent': id, 'id': c} for c in self.children])
		if len(self.parents):
			# There are remaining parents we'd rather have to get ourselves
			# properly threaded - so store them in the db.
			curs.executemany("INSERT INTO unresolved_messages (message, priority, msgid) VALUES (%(id)s, %(priority)s, %(msgid)s)",
							 [{'id': id, 'priority': i, 'msgid': self.parents[i]} for i in range(0, len(self.parents))])


	def get_payload_as_unicode(self, msg):
		b = msg.get_payload(decode=True)
		if b:
			# Find out if there is a charset
			charset = None
			params = msg.get_params()
			if not params:
				# No content-type, so we assume us-ascii
				return unicode(b, 'us-ascii', errors='ignore')
			for k,v in params:
				if k.lower() == 'charset':
					charset = v
					break
			if charset:
				if charset.lower() == 'unknown-8bit':
					# Special case where we don't know... We'll assume
					# us-ascii and use replacements
					charset = 'us-ascii'
				return unicode(b, charset, errors='ignore')
			else:
				# XXX: reasonable default?
				return unicode(b)

	def get_body(self):
		# This is where the magic happens - try to figure out what the body
		# of this message should render as.

		# First see if this is a single-part message that we can just
		# decode and go.
		b = self.get_payload_as_unicode(self.msg)
		if b: return b

		# Ok, it's multipart. Find the first part that is text/plain,
		# and use that one. Do this recursively, since we may have something
		# like:
		# multipart/mixed:
		#   multipart/alternative:
		#      text/plain
		#      text/html
		#   application/octet-stream (attachment)
		b = self.recursive_first_plaintext(self.msg)
		if b: return b
		
		raise Exception("Don't know how to read the body from %s" % self.msgid)

	def recursive_first_plaintext(self, container):
		for p in container.get_payload():
			if p.get_params() == None:
				# MIME multipart/mixed, but no MIME type on the part
				print "Found multipart/mixed in message '%s', but no MIME type on part. Trying text/plain." % self.msgid
				return self.get_payload_as_unicode(p)
			if p.get_params()[0][0].lower() == 'text/plain':
				return self.get_payload_as_unicode(p)
			if p.is_multipart():
				b = self.recursive_first_plaintext(p)
				if b: return b

		# Yikes, nothing here! Hopefully we'll find something when
		# we continue looping at a higher level.
		return None

	def get_attachments(self):
		self.recursive_get_attachments(self.msg)

	def _extract_filename(self, container):
		# Try to get the filename for an attachment in the container.
		# If the standard library can figure one out, use that one.
		f = container.get_filename()
		if f: return f

		# Failing that, some mailers set Content-Description to the
		# filename
		if container.has_key('Content-Description'):
			return container['Content-Description']
		return None

	def recursive_get_attachments(self, container):
		if container.get_content_type() == 'multipart/mixed':
			# Multipart - worth scanning into
			for p in container.get_payload():
				if p.get_params() == None:
					continue
				self.recursive_get_attachments(p)
		elif container.get_content_type() == 'multipart/alternative':
			# Alternative is not an attachment (we decide)
			# It's typilcally plantext + html
			return
		elif container.is_multipart():
			# Other kinds of multipart, such as multipart/signed...
			return
		else:
			# Not a multipart.
			# Exclude specific contenttypes
			if container.get_content_type() == 'application/pgp-signature':
				return
			# For now, accept anything not text/plain
			if container.get_content_type() != 'text/plain':
				self.attachments.append((self._extract_filename(container), container.get_content_type(), container.get_payload(decode=True)))
				return
			# It's a text/plain, it might be worthwhile.
			# If it has a name, we consider it an attachments
			if not container.get_params():
				return
			for k,v in container.get_params():
				if k=='name' and v != '':
					# Yes, it has a name
					self.attachments.append((self._extract_filename(container), container.get_content_type(), container.get_payload(decode=True)))
					return
			# No name, and text/plain, so ignore it

	re_msgid = re.compile('^\s*<(.*)>\s*')
	def clean_messageid(self, messageid, ignorebroken=False):
		m = self.re_msgid.match(messageid)
		if not m:
			if ignorebroken:
				print "Could not parse messageid '%s', ignoring it" % messageid
				return None
			raise Exception("Could not parse message id '%s'" % messageid)
		return m.groups(1)[0]

	_date_multi_OL = re.compile(' \((\w+\s\w+|)\)$')
	_date_multi_re = re.compile(' \((\w+\s\w+(\s+\w+)*|)\)$')
	def forgiving_date_decode(self, d):
		# We have a number of dates in the format
		# "<full datespace> +0200 (MET DST)"
		# or similar. The problem coming from the space within the
		# parenthesis, or if the contents of the parenthesis is
		# completely empty
		if self._date_multi_re.search(d):
			d = self._date_multi_re.sub('', d)

		try:
			return dateutil.parser.parse(d)
		except Exception, e:
			print "Failed to parse date '%s'" % d
			raise e

	def decode_mime_header(self, hdr):
		if hdr == None:
			return None

		return " ".join([unicode(s, charset or 'us-ascii', errors='ignore') for s,charset in decode_header(hdr)])
		(s, charset) = decode_header(hdr)[0]
		if charset:
			return unicode(s, charset, errors='ignore')
		return unicode(s, 'us-ascii', errors='ignore')

	def get_mandatory(self, fieldname):
		try:
			x = self.msg[fieldname]
			if x==None: raise Exception()
			return x
		except:
			raise IgnorableException("Mandatory field '%s' is missing" % fieldname)

	def get_optional(self, fieldname):
		try:
			return self.msg[fieldname]
		except:
			return None

if __name__ == "__main__":
	optparser = OptionParser()
	optparser.add_option('-l', '--list', dest='list', help='Name of list to loiad message for')
	optparser.add_option('-d', '--directory', dest='directory', help='Load all messages in directory')
	optparser.add_option('-i', '--interactive', dest='interactive', action='store_true', help='Prompt after each message')

	(opt, args) = optparser.parse_args()

	if (len(args)):
		print "No bare arguments accepted"
		optparser.print_usage()
		sys.exit(1)

	if not opt.list:
		print "List must be specified"
		optparser.print_usage()
		sys.exit(1)

	# Yay for hardcoding
	conn = psycopg2.connect("host=/tmp dbname=archives")

	# Get the listid we're working on
	curs = conn.cursor()
	curs.execute("SELECT listid FROM lists WHERE listname=%(list)s", {
			'list': opt.list
			})
	r = curs.fetchall()
	if len(r) != 1:
		print "List %s not found" % opt.list
		conn.close()
		sys.exit(1)
	listid = r[0][0]

	if opt.directory:
		# Parse all files in directory
		for x in os.listdir(opt.directory):
			print "Parsing file %s" % x
			with open(os.path.join(opt.directory, x)) as f:
				ap = ArchivesParser()
				ap.parse(f)
				try:
					ap.analyze()
				except IgnorableException, e:
					print "%s :: ignoring" % e
					continue
				ap.store(conn, listid)
			if opt.interactive:
				print "Interactive mode, committing transaction"
				conn.commit()
				print "Proceed to next message with Enter, or input a period (.) to stop processing"
				x = raw_input()
				if x == '.':
					print "Ok, aborting!"
					break
				print "---------------------------------"
	else:
		# Parse single message on stdin
		ap = ArchivesParser()
		ap.parse(sys.stdin)
		try:
			ap.analyze()
		except IgnorableException, e:
			print "%s :: ignoring" % e
			conn.close()
			sys.exit(1)
		ap.store(conn, listid)

	print "Committing..."
	conn.commit()
	print "Done."
	conn.close()
