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

	def is_msgid(self, msgid):
		# Look for a specific messageid. This means we might parse it twice,
		# but so be it. Any exception means we know it's not this one...
		try:
			if self.clean_messageid(self.decode_mime_header(self.get_mandatory('Message-ID'))) == msgid:
				return True
		except Exception, e:
			return False

	def analyze(self, date_override=None):
		self.msgid = self.clean_messageid(self.decode_mime_header(self.get_mandatory('Message-ID')))
		self._from = self.decode_mime_header(self.get_mandatory('From'))
		self.to = self.decode_mime_header(self.get_optional('To'))
		self.cc = self.decode_mime_header(self.get_optional('CC'))
		self.subject = self.decode_mime_header(self.get_optional('Subject'))
		if date_override:
			self.date = self.forgiving_date_decode(date_override)
		else:
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
		if lcharset == 'unknown-8bit' or lcharset == 'x-unknown' or lcharset == 'unknown':
			# Special case where we don't know... We'll assume
			# us-ascii and use replacements
			return 'us-ascii'
		if lcharset == '0' or lcharset == 'x-user-defined' or lcharset == '_autodetect_all' or lcharset == 'default_charset':
			# Seriously broken charset definitions, map to us-ascii
			# and throw away the rest with replacements
			return 'us-ascii'
		if lcharset == 'x-gbk':
			# Some MUAs set it to x-gbk, but there is a valid
			# declaratoin as gbk...
			return 'gbk'
		if lcharset == 'iso-8859-8-i':
			# -I is a special logical version, but should be the
			# same charset
			return 'iso-8859-8'
		if lcharset == 'windows-874':
			# This is an alias for iso-8859-11
			return 'iso-8859-11'
		if lcharset == 'iso-88-59-1' or lcharset == 'iso-8858-1':
			# Strange way of saying 8859....
			return 'iso-8859-1'
		if lcharset == 'iso885915':
			return 'iso-8859-15'
		if lcharset == 'iso-latin-2':
			return 'iso-8859-2'
		if lcharset == 'iso-850':
			# Strange spelling of cp850 (windows charset)
			return 'cp850'
		if lcharset == 'koi8r':
			return 'koi8-r'
		if lcharset == 'cp 1252':
			return 'cp1252'
		if lcharset == 'iso-8859-1,iso-8859-2' or lcharset == 'iso-8859-1:utf8:us-ascii':
			# Why did this show up more than once?!
			return 'iso-8859-1'
		if lcharset == 'x-windows-949':
			return 'ms949'
		if lcharset == 'pt_pt' or lcharset == 'de_latin' or lcharset == 'de':
			# This is a locale, and not a charset, but most likely it's this one
			return 'iso-8859-1'
		if lcharset == 'ýso-8859-1':
			# Nice mis-encoding. But shows up for several mails...
			return 'iso-8859-1'
		if lcharset == 'iso-8858-15':
			# How is this a *common* mistake?
			return 'iso-8859-15'
		if lcharset == 'macintosh':
			return 'mac_roman'
		if lcharset == 'cn-big5':
			return 'big5'
		if lcharset == 'x-unicode-2-0-utf-7':
			return 'utf-7'
		if lcharset == 'tscii':
			# No support for this charset :S Map it down to ascii
			# and throw away all the rest. sucks, but we have to
			return 'us-ascii'
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
		# Return None or empty string, depending on what we got back
		return b

	def get_body(self):
		b = self._get_body()
		if b:
			# Python bug 9133, allows unicode surrogate pairs - which PostgreSQL will
			# later reject..
			if b.find(u'\udbff\n\udef8'):
				b = b.replace(u'\udbff\n\udef8', '')
		return b

	def _get_body(self):
		# This is where the magic happens - try to figure out what the body
		# of this message should render as.
		hasempty = False

		# First see if this is a single-part message that we can just
		# decode and go.
		b = self.get_payload_as_unicode(self.msg)
		if b: return b
		if b == '':
			# We found something, but it was empty. We'll keep looking as
			# there might be something better available, but make a note
			# that empty exists.
			hasempty = True

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
		if b == '':
			hasempty = True

		# Couldn't find a plaintext. Look for the first HTML in that case.
		# Fallback, but what can we do at this point...
		b = self.recursive_first_plaintext(self.msg, True)
		if b:
			b = self.html_clean(b)
			if b: return b
		if b == '':
			hasempty = True

		if hasempty:
			log.status('Found empty body in %s' % self.msgid)
			return ''
		raise IgnorableException("Don't know how to read the body from %s" % self.msgid)

	def recursive_first_plaintext(self, container, html_instead=False):
		pl = container.get_payload()
		if isinstance(pl, str):
			# This was not a multipart, but it leaked... Give up!
			return None
		for p in pl:
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
				if b or b == '': return b

		# Yikes, nothing here! Hopefully we'll find something when
		# we continue looping at a higher level.
		return None

	def get_attachments(self):
		self.recursive_get_attachments(self.msg)

	def _clean_filename_encoding(self, filename):
		# Clean a filenames encoding and return it as a unicode string

		# If it's already unicode, just return it
		if isinstance(filename, unicode):
			return filename

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
	_date_multiminus_re = re.compile(' -(-\d+)$')
	def forgiving_date_decode(self, d):
		# Strange timezones requiring manual adjustments
		if d.endswith('-7700 (EST)'):
			d = d.replace('-7700 (EST)', 'EST')
		if d.endswith('+6700 (EST)'):
			d = d.replace('+6700 (EST)', 'EST')
		if d.endswith('+-4-30'):
			d = d.replace('+-4-30', '+0430')
		if d.endswith('+1.00'):
			d = d.replace('+1.00', '+0100')
		if d.endswith('+-100'):
			d = d.replace('+-100', '+0100')
		if d.endswith('+500'):
			d = d.replace('+500', '+0500')
		if d.endswith('-500'):
			d = d.replace('-500', '-0500')
		if d.endswith('-700'):
			d = d.replace('-700', '-0700')
		if d.endswith('-800'):
			d = d.replace('-800', '-0800')
		if d.endswith('+05-30'):
			d = d.replace('+05-30', '+0530')
		if d.endswith('+0-900'):
			d = d.replace('+0-900', '-0900')
		if d.endswith('Mexico/General'):
			d = d.replace('Mexico/General','CDT')
		if d.endswith('Pacific Daylight Time'):
			d = d.replace('Pacific Daylight Time', 'PDT')
		if d.endswith(' ZE2'):
			d = d.replace(' ZE2',' +0200')
		if d.find('-Juin-') > 0:
			d = d.replace('-Juin-','-Jun-')
		if d.find('-Juil-') > 0:
			d = d.replace('-Juil-','-Jul-')
		if d.find(' 0 (GMT)'):
			d = d.replace(' 0 (GMT)',' +0000')

		if self._date_multiminus_re.search(d):
			d = self._date_multiminus_re.sub(' \\1', d)


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
			if dp.utcoffset() and abs(dp.utcoffset().days * (24*60*60) + dp.utcoffset().seconds) > 60*60*16-1:
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
