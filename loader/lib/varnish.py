import requests

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
        purgedict = dict(list(zip(['p%s' % n for n in range(0, len(exprlist))], exprlist)))
        purgedict['n'] = len(exprlist)
        r = requests.post(purgeurl, data=purgedict, headers={
            'Content-type': 'application/x-www-form-urlencoded',
            'Host': 'www.postgresql.org',
        })
        if r.status_code != 200:
            log.error("Failed to send purge request!")
