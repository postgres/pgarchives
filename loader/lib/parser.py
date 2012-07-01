import re
import datetime
import dateutil.parser

from email.parser import Parser
from email.header import decode_header
from email.errors import HeaderParseError
from HTMLParser import HTMLParser, HTMLParseError
import tidy
import StringIO

from lib.exception import IgnorableException
from lib.log import log

class ArchivesParser(object):
	def __init__(self):
		self.parser = Parser()

	def parse(self, stream):
		self.msg = self.parser.parse(stream)

	def analyze(self):
		self.msgid = self.clean_messageid(self.decode_mime_header(self.get_mandatory('Message-ID')))
		self._from = self.decode_mime_header(self.get_mandatory('From'))
		self.to = self.decode_mime_header(self.get_optional('To'))
		self.cc = self.decode_mime_header(self.get_optional('CC'))
		self.subject = self.decode_mime_header(self.get_optional('Subject'))
		self.date = self.forgiving_date_decode(self.decode_mime_header(self.get_mandatory('Date')))
		self.bodytxt = self.get_body()
		self.attachments = []
		self.get_attachments()
		if len(self.attachments) > 0:
			log.status("Found %s attachments" % len(self.attachments))

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


	def clean_charset(self, charset):
		lcharset = charset.lower()
		if lcharset == 'unknown-8bit' or lcharset == 'x-unknown':
			# Special case where we don't know... We'll assume
			# us-ascii and use replacements
			return 'us-ascii'
		if lcharset == 'x-gbk':
			# Some MUAs set it to x-gbk, but there is a valid
			# declaratoin as gbk...
			return 'gbk'
		if lcharset == 'iso-8859-8-i':
			# -I is a special logical version, but should be the
			# same charset
			return 'iso-8859-8'
		if lcharset == 'iso-88-59-1' or lcharset == 'iso-8858-1':
			# Strange way of saying 8859....
			return 'iso-8859-1'
		if lcharset == 'iso-850':
			# Strange spelling of cp850 (windows charset)
			return 'cp850'
		return charset

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
				try:
					return unicode(b, self.clean_charset(charset), errors='ignore')
				except LookupError, e:
					raise IgnorableException("Failed to get unicode payload: %s" % e)
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

		# Couldn't find a plaintext. Look for the first HTML in that case.
		# Fallback, but what can we do at this point...
		b = self.recursive_first_plaintext(self.msg, True)
		if b:
			b = self.html_clean(b)
			if b: return b

		raise IgnorableException("Don't know how to read the body from %s" % self.msgid)

	def recursive_first_plaintext(self, container, html_instead=False):
		for p in container.get_payload():
			if p.get_params() == None:
				# MIME multipart/mixed, but no MIME type on the part
				log.status("Found multipart/mixed in message '%s', but no MIME type on part. Trying text/plain." % self.msgid)
				return self.get_payload_as_unicode(p)
			if p.get_params()[0][0].lower() == 'text/plain':
				# Don't include it if it looks like an attachment
				if p.has_key('Content-Disposition') and p['Content-Disposition'].startswith('attachment'):
					continue
				return self.get_payload_as_unicode(p)
			if html_instead and p.get_params()[0][0].lower() == 'text/html':
				# Don't include it if it looks like an attachment
				if p.has_key('Content-Disposition') and p['Content-Disposition'].startswith('attachment'):
					continue
				return self.get_payload_as_unicode(p)
			if p.is_multipart():
				b = self.recursive_first_plaintext(p, html_instead)
				if b: return b

		# Yikes, nothing here! Hopefully we'll find something when
		# we continue looping at a higher level.
		return None

	def get_attachments(self):
		self.recursive_get_attachments(self.msg)

	def _clean_filename_encoding(self, filename):
		# Anything that's not UTF8, we just get rid of. We can live with
		# filenames slightly mangled in this case.
		return unicode(filename, 'utf-8', errors='ignore')

	def _extract_filename(self, container):
		# Try to get the filename for an attachment in the container.
		# If the standard library can figure one out, use that one.
		f = container.get_filename()
		if f: return self._clean_filename_encoding(f)

		# Failing that, some mailers set Content-Description to the
		# filename
		if container.has_key('Content-Description'):
			return self._clean_filename_encoding(container['Content-Description'])
		return None

	def recursive_get_attachments(self, container):
		if container.get_content_type() == 'multipart/mixed':
			# Multipart - worth scanning into
			if not container.is_multipart():
				# Wow, this is broken. It's multipart/mixed, but doesn't
				# contain multiple parts.
				# Since we're just looking for attachments, let's just
				# ignore it...
				return
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
				log.status("Could not parse messageid '%s', ignoring it" % messageid)
				return None
			raise IgnorableException("Could not parse message id '%s'" % messageid)
		return m.groups(1)[0]

#	_date_multi_re = re.compile(' \((\w+\s\w+(\s+\w+)*|)\)$')
	# Now using [^\s] instead of \w, to work with japanese chars
	_date_multi_re = re.compile(' \(([^\s]+\s[^\s]+(\s+[^\s]+)*|)\)$')
	_date_multi_re2 = re.compile(' ([\+-]\d{4}) \([^)]+\)$')
	def forgiving_date_decode(self, d):
		# We have a number of dates in the format
		# "<full datespace> +0200 (MET DST)"
		# or similar. The problem coming from the space within the
		# parenthesis, or if the contents of the parenthesis is
		# completely empty
		if self._date_multi_re.search(d):
			d = self._date_multi_re.sub('', d)

		# If the spec is instead
		# "<full datespace> +0200 (...)"
		# of any kind, we can just remove what's in the (), because the
		# parser is just going to rely on the fixed offset anyway.
		if self._date_multi_re2.search(d):
			d = self._date_multi_re2.sub(' \\1', d)

		try:
			dp = dateutil.parser.parse(d, fuzzy=True)

			# Some offsets are >16 hours, which postgresql will not
			# (for good reasons) accept
			if dp.utcoffset() and dp.utcoffset().seconds > 60 * 60 * 16 - 1 and dp.utcoffset().days >= 0:
				# Convert it to a UTC timestamp using Python. It will give
				# us the right time, but the wrong timezone. Should be
				# enough...
				dp = datetime.datetime(*dp.utctimetuple()[:6])
			return dp
		except Exception, e:
			raise IgnorableException("Failed to parse date '%s': %s" % (d, e))

	def _decode_mime_header(self, hdr):
		if hdr == None:
			return None

		# Per http://bugs.python.org/issue504152 (and lots of testing), it seems
		# we must get rid of the sequence \n\t at least in the header. If we
		# do this *before* doing any MIME decoding, we should be safe against
		# anybody *actually* putting that sequence in the header (since we
		# won't match the encoded contents)
		hdr = hdr.replace("\n\t","")
		try:
			return " ".join([unicode(s, charset and self.clean_charset(charset) or 'us-ascii', errors='ignore') for s,charset in decode_header(hdr)])
			(s, charset) = decode_header(hdr)[0]
			if charset:
				return unicode(s, self.clean_charset(charset), errors='ignore')
			return unicode(s, 'us-ascii', errors='ignore')
		except HeaderParseError, e:
			# Parser error is typically someone specifying an encoding,
			# but then not actually using that encoding. We'll do the best
			# we can, which is cut it down to ascii and ignore errors
			return unicode(hdr, 'us-ascii', errors='ignore')

	def decode_mime_header(self, hdr):
		try:
			return self._decode_mime_header(hdr)
		except LookupError, e:
			raise IgnorableException("Failed to decode header value '%s': %s" % (hdr, e))
		except ValueError, ve:
			raise IgnorableException("Failed to decode header value '%s': %s" % (hdr, ve))

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

	def html_clean(self, html):
		# First we pass it through tidy
		html = unicode(str(tidy.parseString(html.encode('utf8'), drop_proprietary_attributes=1, alt_text='',hide_comments=1,output_xhtml=1,show_body_only=1,clean=1,char_encoding='utf8')), 'utf8')

		try:
			cleaner = HTMLCleaner()
			cleaner.feed(html)
			return cleaner.get_text()
		except HTMLParseError, e:
			# Failed to parse the html, thus failed to clean it. so we must
			# give up...
			return None


class HTMLCleaner(HTMLParser):
	def __init__(self):
		HTMLParser.__init__(self)
		self.io = StringIO.StringIO()

	def get_text(self):
		return self.io.getvalue()

	def handle_data(self, data):
		self.io.write(data)

	def handle_starttag(self, tag, attrs):
		if tag == "p" or tag == "br":
			self.io.write("\n")
