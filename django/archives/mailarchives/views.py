from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.db import connection

import urllib
import re
from datetime import datetime

from models import *

def render_datelist_from(request, l, d, title):
	mlist = Message.objects.select_related().filter(date__gte=d).extra(where=["threadid IN (SELECT threadid FROM list_threads WHERE listid=%s)" % l.listid]).order_by('date')[:200]
	return render_to_response('datelist.html', {
			'list': l,
			'messages': list(mlist),
			'title': title,
			})

def datelistsince(request, listname, msgid):
	l = get_object_or_404(List, listname=listname)
	msg = get_object_or_404(Message, messageid=msgid)
	return render_datelist_from(request, l, msg.date, "%s since %s" % (l.listname, msg.date.strftime("%Y-%m-%d %H:%M:%S")))
	
def datelist(request, listname, year, month):
	l = get_object_or_404(List, listname=listname)
	d = datetime(int(year), int(month), 1)
	return render_datelist_from(request, l, d, "%s - %s %s" % (l.listname, d.strftime("%B"), d.year))


def attachment(request, attid):
	# Use a direct query instead of django, since it has bad support for
	# bytea
	curs = connection.cursor()
	curs.execute("SELECT filename, contenttype, attachment FROM attachments WHERE id=%(id)s", { 'id': int(attid)})
	r = curs.fetchall()
	if len(r) != 1:
		return HttpResponse("Attachment not found")

	return HttpResponse(r[0][2], mimetype=r[0][1])

def _build_thread_structure(threadid):
	# Yeah, this is *way* too complicated for the django ORM
	curs = connection.cursor()
	curs.execute("""WITH RECURSIVE t(id, _from, subject, date, messageid, has_attachment, parentid, parentpath) AS(
  SELECT id,_from,subject,date,messageid,has_attachment,parentid,array[]::int[] FROM messages m WHERE m.threadid=%(threadid)s AND parentid IS NULL
 UNION ALL
  SELECT m.id,m._from,m.subject,m.date,m.messageid,m.has_attachment,m.parentid,t.parentpath||t.id FROM messages m INNER JOIN t ON t.id=m.parentid WHERE m.threadid=%(threadid)s
)
SELECT id,_from,subject,date,messageid,has_attachment,parentid,parentpath FROM t ORDER BY parentpath, date
""", {'threadid': threadid})
	lastpath = []
	for id,_from,subject,date,messageid,has_attachment,parentid,parentpath in curs.fetchall():
		if lastpath != parentpath:
			# We have a previous path, so we need to emit one or more
			# close nodes. We start by finding the longest common path
			# between the two.
			common_path = []
			for i in range(0, min(len(lastpath), len(parentpath))):
				if lastpath[i] == parentpath[i]:
					common_path.append(lastpath[i])
				else:
					break

			# Need to close as many nodes as the difference in length between
			# the previous path and the common path.
			for x in range(0, len(lastpath)-len(common_path)):
				yield {'close':1}

			# We never need to open more than one node
			if len(parentpath) - len(common_path) != 1:
				raise Exception("Invalid paths. Last path %s, new path %s" % (lastpath, common_path))
			yield {'open':1}
			lastpath = parentpath
		yield {'id':id, 'mailfrom':_from, 'subject': subject, 'printdate': date.strftime("%Y-%m-%d %H:%M:%S"), 'messageid': messageid, 'hasattachment': has_attachment, 'parentid': parentid, 'indent': "&nbsp;" * len(parentpath)}
	# At the end we have a number of close tags to export
	for x in range(0,len(lastpath)):
		yield {'close':1}

def message(request, msgid):
	m = get_object_or_404(Message, messageid=msgid)
	lists = List.objects.extra(where=["listid IN (SELECT listid FROM list_threads WHERE threadid=%s)" % m.threadid]).order_by('listname')
	return render_to_response('message.html', {
			'msg': m,
			'threadstruct': list(_build_thread_structure(m.threadid)),
			'lists': lists,
			})

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
