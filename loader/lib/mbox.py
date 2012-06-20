from subprocess import Popen, PIPE
import cStringIO as StringIO

# The hack of all hacks...
# The python mbox parser fails to split some messages from mj2
# correctly - they appear to be too far out of spec. However,
# formail does it right. So open a formail pipe on the mbox,
# reassemble it to one long stream with a unique separator,
# and then split it apart again in python.. Isn't it cute?
SEPARATOR = "ABCARCHBREAK123" * 50

class MailboxBreakupParser(object):
	def __init__(self, fn):
		self.EOF = False

		cmd = "formail -s /bin/sh -c 'cat && echo %s' < %s" % (SEPARATOR, fn)
		self.pipe = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)

	def returncode(self):
		self.pipe.wait()
		return self.pipe.returncode

	def stderr_output(self):
		return self.pipe.stderr.read()

	def next(self):
		sio = StringIO.StringIO()
		while True:
			try:
				l = self.pipe.stdout.next()
			except StopIteration:
				# End of file!
				self.EOF = True
				if sio.tell() == 0:
					# Nothing read yet, so return None instead of an empty
					# stringio
					return None
				sio.seek(0)
				return sio
			if l.rstrip() == SEPARATOR:
				# Reached a separator. Meaning we're not at end of file,
				# but we're at end of message.
				sio.seek(0)
				return sio
			# Otherwise, append it to where we are now
			sio.write(l)
