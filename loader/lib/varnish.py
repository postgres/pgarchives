import urllib
import urllib2

from lib.log import log

class VarnishPurger(object):
	def __init__(self, cfg):
		self.cfg = cfg

	def purge(self, purges):
		if not len(purges):
			return

		if not self.cfg.has_option('varnish', 'purgeurl'):
			return

		purgeurl = self.cfg.get('varnish', 'purgeurl')
		exprlist = []
		for p in purges:
			if isinstance(p, tuple):
				# Purging a list
				exprlist.append('obj.http.x-pglm ~ :%s/%s/%s:' % p)
			else:
				# Purging individual thread
				exprlist.append('obj.http.x-pgthread ~ :%s:' % p)
		purgedict = dict(zip(['p%s' % n for n in range(0, len(exprlist))], exprlist))
		purgedict['n'] = len(exprlist)
		r = urllib2.Request(purgeurl, data=urllib.urlencode(purgedict))
		r.add_header('Content-type', 'application/x-www-form-urlencoded')
		r.add_header('Host', 'www.postgresql.org')
		r.get_method = lambda: 'POST'
		u = urllib2.urlopen(r)
		if u.getcode() != 200:
			log.error("Failed to send purge request!")

