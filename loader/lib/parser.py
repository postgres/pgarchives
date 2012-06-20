import re
import datetime
import dateutil.parser

from email.parser import Parser
from email.header import decode_header

from lib.exception import IgnorableException
from lib.log import log

class ArchivesParser(object):
	def __init__(self):
		self.parser = Parser()

	def parse(self, stream):
		self.msg = self.parser.parse(stream)

	def analyze(self):
		self.msgid = self.clean_messageid(self.get_mandatory('Message-ID'))
		self._from = self.decode_mime_header(self.get_mandatory('From'))
		self.to = self.decode_mime_header(self.get_optional('To'))
		self.cc = self.decode_mime_header(self.get_optional('CC'))
		self.subject = self.decode_mime_header(self.get_mandatory('Subject'))
		self.date = self.forgiving_date_decode(self.get_mandatory('Date'))
		self.bodytxt = self.get_body()
		self.attachments = []
		self.get_attachments()
		if len(self.attachments) > 0:
			log.status("Found %s attachments" % len(self.attachments))
			log.status([(a[0],a[1],len(a[2])) for a in self.attachments])

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
				return unicode(b, errors='ignore')

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
				log.log("Found multipart/mixed in message '%s', but no MIME type on part. Trying text/plain." % self.msgid)
				return self.get_payload_as_unicode(p)
			if p.get_params()[0][0].lower() == 'text/plain':
				# Don't include it if it looks like an attachment
				if p.has_key('Content-Disposition') and p['Content-Disposition'].startswith('attachment'):
					continue
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
				log.log("Could not parse messageid '%s', ignoring it" % messageid)
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
			dp = dateutil.parser.parse(d)

			# Some offsets are >16 hours, which postgresql will not
			# (for good reasons) accept
			if dp.utcoffset().seconds > 60 * 60 * 16 - 1 and dp.utcoffset().days >= 0:
				# Convert it to a UTC timestamp using Python. It will give
				# us the right time, but the wrong timezone. Should be
				# enough...
				dp = datetime.datetime(*dp.utctimetuple()[:6])
			return dp
		except Exception, e:
			log.log("Failed to parse date '%s'" % d)
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
