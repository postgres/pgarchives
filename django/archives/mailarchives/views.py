from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
import urllib
import re
from datetime import datetime

from models import *

def render_datelist_from(request, l, d):
	mlist = Message.objects.filter(date__gte=d).extra(where=["threadid IN (SELECT threadid FROM list_threads WHERE listid=%s)" % l.listid]).order_by('date')[:200]
	return render_to_response('datelist.html', {
			'list': l,
			'messages': list(mlist),
			})

def datelistsince(request, listname, msgnum):
	l = get_object_or_404(List, listname=listname)
	msg = get_object_or_404(Message, pk=msgnum)
	return render_datelist_from(request, l, msg.date)
	
def datelist(request, listname, year, month):
	listid = get_object_or_404(List, listname=listname)
	return render_datelist_from(request, listid, datetime(int(year), int(month), 1))

def testview(request, seqid):
	m = Message.objects.get(pk=seqid)
	try:
		nextm = Message.objects.filter(id__gt=m.id).order_by('id')[0]
	except IndexError:
		nextm = None
	try:
		prevm = Message.objects.filter(id__lt=m.id).order_by('-id')[0]
	except IndexError:
		prevm = None

	return render_to_response('test.html', {
			'msg': m,
			'nextmsg': nextm,
			'prevmsg': prevm,
			})


def oldsite(request, msgid):
	u = urllib.urlopen('http://archives.postgresql.org/message-id/%s' % msgid)
	m = re.search('<!--X-Body-of-Message-->(.*)<!--X-Body-of-Message-End-->', u.read(), re.DOTALL)
	return HttpResponse(m.groups(1), content_type='text/html')
