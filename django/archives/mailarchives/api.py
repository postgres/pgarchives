from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.conf import settings

from views import cache
from models import Message, List

import json


@cache(hours=4)
def latest(request, listname):
	if not request.META['REMOTE_ADDR'] in settings.API_CLIENTS:
		return HttpResponseForbidden('Invalid host')

	# Return the latest <n> messages on this list.
	# If <n> is not specified, return 50. Max value for <n> is 100.
	if request.GET.has_key('n'):
		try:
			limit = int(request.GET['n'])
		except:
			limit = 0
	else:
		limit = 50
	if limit <= 0 or limit > 100:
		limit = 50

	extrawhere=[]
	extraparams=[]

	# Return only messages that have attachments?
	if request.GET.has_key('a'):
		if request.GET['a'] == '1':
			extrawhere.append("has_attachment")

	# Restrict by full text search
	if request.GET.has_key('s') and request.GET['s']:
		extrawhere.append("fti @@ plainto_tsquery('public.pg', %s)")
		extraparams.append(request.GET['s'])

	list = get_object_or_404(List, listname=listname)
	extrawhere.append("threadid IN (SELECT threadid FROM list_threads WHERE listid=%s)" % list.listid)
	mlist = Message.objects.defer('bodytxt', 'cc', 'to').select_related().extra(where=extrawhere, params=extraparams).order_by('-date')[:limit]
	allyearmonths = set([(m.date.year, m.date.month) for m in mlist])

	resp = HttpResponse(content_type='application/json')
	json.dump([
		{'msgid': m.messageid,
		 'date': m.date.isoformat(),
		 'from': m.mailfrom,
		 'subj': m.subject,}
		for m in mlist], resp)

	# Make sure this expires from the varnish cache when new entries show
	# up in this month.
	resp['X-pglm'] = ':%s:' % (':'.join(['%s/%s/%s' % (list.listid, year, month) for year, month in allyearmonths]))
	return resp


@cache(hours=4)
def thread(request, msgid):
	if not request.META['REMOTE_ADDR'] in settings.API_CLIENTS:
		return HttpResponseForbidden('Invalid host')

	# Return metadata about a single thread. A list of all the emails
	# that are in the thread with their basic attributes are included.
	msg = get_object_or_404(Message, messageid=msgid)
	mlist = Message.objects.defer('bodytxt', 'cc', 'to').filter(threadid=msg.threadid)

	resp = HttpResponse(content_type='application/json')
	json.dump([
		{'msgid': m.messageid,
		 'date': m.date.isoformat(),
		 'from': m.mailfrom,
		 'subj': m.subject,
		 'atts': [{'id': a.id, 'name': a.filename} for a in m.attachment_set.all()],
	 }
		for m in mlist], resp)
	resp['X-pgthread'] = m.threadid
	return resp
