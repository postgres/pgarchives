from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.conf import settings

from .views import cache
from .models import Message, List, ApiClient, ThreadSubscription

import json


@cache(hours=4)
def listinfo(request):
	if not settings.PUBLIC_ARCHIVES:
		return HttpResponseForbidden('No API access on private archives for now')

	if not request.META['REMOTE_ADDR'] in settings.API_CLIENTS:
		return HttpResponseForbidden('Invalid host')

	resp = HttpResponse(content_type='application/json')
	json.dump([{
		'name': l.listname,
		'shortdesc': l.shortdesc,
		'description': l.description,
		'active': l.active,
		'group': l.group.groupname,
		} for l in List.objects.select_related('group').all()], resp)

	return resp

@cache(hours=4)
def latest(request, listname):
	if not settings.PUBLIC_ARCHIVES:
		return HttpResponseForbidden('No API access on private archives for now')

	if not request.META['REMOTE_ADDR'] in settings.API_CLIENTS:
		return HttpResponseForbidden('Invalid host')

	# Return the latest <n> messages on this list.
	# If <n> is not specified, return 50. Max value for <n> is 100.
	if 'n' in request.GET:
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
	if 'a' in request.GET:
		if request.GET['a'] == '1':
			extrawhere.append("has_attachment")

	# Restrict by full text search
	if 's' in request.GET and request.GET['s']:
		extrawhere.append("fti @@ plainto_tsquery('public.pg', %s)")
		extraparams.append(request.GET['s'])

	if listname != '*':
		list = get_object_or_404(List, listname=listname)
		extrawhere.append("threadid IN (SELECT threadid FROM list_threads WHERE listid=%s)" % list.listid)
	else:
		list = None
		extrawhere=''

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
	# XXX: need to deal with the global view, but for now API callers come in directly
	if list:
		resp['X-pglm'] = ':%s:' % (':'.join(['%s/%s/%s' % (list.listid, year, month) for year, month in allyearmonths]))
	return resp


@cache(hours=4)
def thread(request, msgid):
	if not settings.PUBLIC_ARCHIVES:
		return HttpResponseForbidden('No API access on private archives for now')

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

def thread_subscribe(request, msgid):
	if not settings.PUBLIC_ARCHIVES:
		return HttpResponseForbidden('No API access on private archives for now')

	if not request.META['REMOTE_ADDR'] in settings.API_CLIENTS:
		return HttpResponseForbidden('Invalid host')

	if 'HTTP_X_APIKEY' not in request.META:
		return HttpResponseForbidden('No API key')

	if request.method != 'PUT':
		return HttpResponseForbidden('Invalid HTTP verb')

	apiclient = get_object_or_404(ApiClient, apikey=request.META['HTTP_X_APIKEY'])
	msg = get_object_or_404(Message, messageid=msgid)

	(obj, created) = ThreadSubscription.objects.get_or_create(apiclient=apiclient,
															  threadid=msg.threadid)
	if created:
		return HttpResponse(status=201)
	else:
		return HttpResponse(status=200)
