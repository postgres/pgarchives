class Log(object):
	def __init__(self):
		self.verbose = False

	def set(self, verbose):
		self.verbose = verbose

	def status(self, msg):
		if self.verbose:
			print msg

	def log(self, msg):
		print msg

	def error(self, msg):
		print msg

	def print_status(self):
		opstatus.print_status()

class OpStatus(object):
	def __init__(self):
		self.stored = 0
		self.dupes = 0
		self.tagged = 0
		self.failed = 0

	def print_status(self):
		print "%s stored, %s new-list tagged, %s dupes, %s failed" % (self.stored, self.tagged, self.dupes, self.failed)


log = Log()
opstatus = OpStatus()

