from django.template import RequestContext
from django.http import HttpResponse, HttpResponseForbidden, Http404
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.db import connection
from django.db.models import Q
from django.conf import settings

import urllib
import re
import os
import base64
from datetime import datetime, timedelta
import calendar

import simplejson as json

from models import *

# Decorator to set cache age
def cache(days=0, hours=0, minutes=0, seconds=0):
	"Set the server to cache object a specified time. td must be a timedelta object"
	def _cache(fn):
		def __cache(request, *_args, **_kwargs):
			resp = fn(request, *_args, **_kwargs)
			td = timedelta(hours=hours, minutes=minutes, seconds=seconds)
			resp['Cache-Control'] = 's-maxage=%s' % (td.days*3600*24 + td.seconds)
			return resp
		return __cache
	return _cache

def nocache(fn):
	def _nocache(request, *_args, **_kwargs):
		resp = fn(request, *_args, **_kwargs)
		resp['Cache-Control'] = 's-maxage=0'
		return resp
	return _nocache


def get_all_groups_and_lists(listid=None):
	# Django doesn't (yet) support traversing the reverse relationship,
	# so we'll get all the lists and rebuild it backwards.
	lists = List.objects.select_related('group').all().order_by('listname')
	listgroupid = None
	groups = {}
	for l in lists:
		if l.listid == listid:
			listgroupid = l.group.groupid

		if groups.has_key(l.group.groupid):
			groups[l.group.groupid]['lists'].append(l)
		else:
			groups[l.group.groupid] = {
				'groupid': l.group.groupid,
				'groupname': l.group.groupname,
				'sortkey': l.group.sortkey,
				'lists': [l,],
				'homelink': 'list/group/%s' % l.group.groupid,
				}

	return (sorted(groups.values(), key=lambda g: g['sortkey']), listgroupid)


class NavContext(RequestContext):
	def __init__(self, request, listid=None, all_groups=None, expand_groupid=None):
		RequestContext.__init__(self, request)

		if all_groups:
			groups = all_groups
			if expand_groupid:
				listgroupid = int(expand_groupid)
		else:
			(groups, listgroupid) = get_all_groups_and_lists(listid)

		for g in groups:
			# On the root page, remove *all* entries
			# On other lists, remove the entries in all groups other than our
			# own.
			if (not listid and not expand_groupid) or listgroupid != g['groupid']:
				# Root page, so remove *all* entries
				g['lists'] = []

		self.update({'listgroups': groups})
		if listid:
			self.update({'searchform_list': listid})


@cache(hours=4)
def index(request):
	(groups, listgroupid) = get_all_groups_and_lists()
	return render_to_response('index.html', {
			'groups': [{'groupname': g['groupname'], 'lists': g['lists']} for g in groups],
			}, NavContext(request, all_groups=groups))

@cache(hours=8)
def groupindex(request, groupid):
	(groups, listgroupid) = get_all_groups_and_lists()
	mygroups = [{'groupname': g['groupname'], 'lists': g['lists']} for g in groups if g['groupid']==int(groupid)]
	if len(mygroups) == 0:
		raise Http404('List group does not exist')

	return render_to_response('index.html', {
			'groups': mygroups,
			}, NavContext(request, all_groups=groups, expand_groupid=groupid))

def _has_mbox(listname, year, month):
	return os.path.isfile("%s/%s/files/public/archive/%s.%04d%02d" % (
			settings.MBOX_ARCHIVES_ROOT,
			listname,
			listname, year, month))

@cache(hours=8)
def monthlist(request, listname):
	l = get_object_or_404(List, listname=listname)
	curs = connection.cursor()
	curs.execute("SELECT year, month FROM list_months WHERE listid=%(listid)s ORDER BY year DESC, month DESC", {'listid': l.listid})
	months=[{'year':r[0],'month':r[1], 'date':datetime(r[0],r[1],1), 'hasmbox': _has_mbox(listname, r[0], r[1])} for r in curs.fetchall()]

	return render_to_response('monthlist.html', {
			'list': l,
			'months': months,
			}, NavContext(request, l.listid))

def get_monthday_info(mlist, l, d):
	allmonths = set([m.date.month for m in mlist])
	monthdate = None
	daysinmonth = None
	if len(allmonths) == 1:
		# All hits are from one month, so generate month links
		monthdate = mlist[0].date
	elif len(allmonths) == 0:
		# No hits at all, so generate month links from the specified date
		monthdate = d

	if monthdate:
		curs = connection.cursor()
		curs.execute("SELECT DISTINCT extract(day FROM date) FROM messages WHERE date >= %(startdate)s AND date < %(enddate)s AND threadid IN (SELECT threadid FROM list_threads WHERE listid=%(listid)s) ORDER BY 1", {
				'startdate': datetime(year=monthdate.year, month=monthdate.month, day=1),
				'enddate': monthdate + timedelta(days=calendar.monthrange(monthdate.year, monthdate.month)[1]),
				'listid': l.listid,
				})
		daysinmonth = [int(r[0]) for r in curs.fetchall()]

	yearmonth = None
	if monthdate:
		yearmonth = "%s%02d" % (monthdate.year, monthdate.month)
	return (yearmonth, daysinmonth)

def render_datelist_from(request, l, d, title, to=None):
	datefilter = Q(date__gte=d)
	if to:
		datefilter.add(Q(date__lt=to), Q.AND)

	mlist = Message.objects.defer('bodytxt', 'cc', 'to').select_related().filter(datefilter).extra(where=["threadid IN (SELECT threadid FROM list_threads WHERE listid=%s)" % l.listid]).order_by('date')[:200]

	threads = set([m.threadid for m in mlist])
	allyearmonths = set([(m.date.year, m.date.month) for m in mlist])
	(yearmonth, daysinmonth) = get_monthday_info(mlist, l, d)

	r = render_to_response('datelist.html', {
			'list': l,
			'messages': list(mlist),
			'title': title,
			'daysinmonth': daysinmonth,
			'yearmonth': yearmonth,
			}, NavContext(request, l.listid))
	r['X-pglm'] = ':%s:' % (':'.join(['%s/%s/%s' % (l.listid, year, month) for year,month in allyearmonths]))
	return r

def render_datelist_to(request, l, d, title):
	# Need to sort this backwards in the database to get the LIMIT applied
	# properly, and then manually resort it in the correct order. We can do
	# the second sort safely in python since it's not a lot of items..
	mlist = sorted(Message.objects.defer('bodytxt', 'cc', 'to').select_related().filter(date__lte=d).extra(where=["threadid IN (SELECT threadid FROM list_threads WHERE listid=%s)" % l.listid]).order_by('-date')[:200], key=lambda m: m.date)

	threads = set([m.threadid for m in mlist])
	allyearmonths = set([(m.date.year, m.date.month) for m in mlist])
	(yearmonth, daysinmonth) = get_monthday_info(mlist, l, d)

	r = render_to_response('datelist.html', {
			'list': l,
			'messages': list(mlist),
			'title': title,
			'daysinmonth': daysinmonth,
			'yearmonth': yearmonth,
			}, NavContext(request, l.listid))
	r['X-pglm'] = ':%s:' % (':'.join(['%s/%s/%s' % (l.listid, year, month) for year,month in allyearmonths]))
	return r

@cache(hours=2)
def datelistsince(request, listname, msgid):
	l = get_object_or_404(List, listname=listname)
	msg = get_object_or_404(Message, messageid=msgid)
	return render_datelist_from(request, l, msg.date, "%s since %s" % (l.listname, msg.date.strftime("%Y-%m-%d %H:%M:%S")))

# Longer cache since this will be used for the fixed date links
@cache(hours=4)
def datelistsincetime(request, listname, year, month, day, hour, minute):
	l = get_object_or_404(List, listname=listname)
	try:
		d = datetime(int(year), int(month), int(day), int(hour), int(minute))
	except ValueError:
		raise Http404("Invalid date format, not found")
	return render_datelist_from(request, l, d, "%s since %s" % (l.listname, d.strftime("%Y-%m-%d %H:%M")))

@cache(hours=2)
def datelistbefore(request, listname, msgid):
	l = get_object_or_404(List, listname=listname)
	msg = get_object_or_404(Message, messageid=msgid)
	return render_datelist_to(request, l, msg.date, "%s before %s" % (l.listname, msg.date.strftime("%Y-%m-%d %H:%M:%S")))

@cache(hours=2)
def datelistbeforetime(request, listname, year, month, day, hour, minute):
	l = get_object_or_404(List, listname=listname)
	try:
		d = datetime(int(year), int(month), int(day), int(hour), int(minute))
	except ValueError:
		raise Http404("Invalid date format, not found")
	return render_datelist_to(request, l, d, "%s before %s" % (l.listname, d.strftime("%Y-%m-%d %H:%M")))

@cache(hours=4)
def datelist(request, listname, year, month):
	l = get_object_or_404(List, listname=listname)
	try:
		d = datetime(int(year), int(month), 1)
	except ValueError:
		raise Http404("Malformatted date, month not found")

	enddate = d+timedelta(days=31)
	enddate = datetime(enddate.year, enddate.month, 1)
	return render_datelist_from(request, l, d, "%s - %s %s" % (l.listname, d.strftime("%B"), d.year), enddate)

@cache(hours=4)
def attachment(request, attid):
	# Use a direct query instead of django, since it has bad support for
	# bytea
	curs = connection.cursor()
	curs.execute("SELECT filename, contenttype, attachment FROM attachments WHERE id=%(id)s AND EXISTS (SELECT 1 FROM messages WHERE messages.id=attachments.message AND messages.hiddenstatus IS NULL)", { 'id': int(attid)})
	r = curs.fetchall()
	if len(r) != 1:
		return HttpResponse("Attachment not found")

	return HttpResponse(r[0][2], mimetype=r[0][1])

def _build_thread_structure(threadid):
	# Yeah, this is *way* too complicated for the django ORM
	curs = connection.cursor()
	curs.execute("""WITH RECURSIVE t(id, _from, subject, date, messageid, has_attachment, parentid, datepath) AS(
  SELECT id,_from,subject,date,messageid,has_attachment,parentid,array[]::timestamptz[] FROM messages m WHERE m.threadid=%(threadid)s AND parentid IS NULL
 UNION ALL
  SELECT m.id,m._from,m.subject,m.date,m.messageid,m.has_attachment,m.parentid,t.datepath||t.date FROM messages m INNER JOIN t ON t.id=m.parentid WHERE m.threadid=%(threadid)s
)
SELECT id,_from,subject,date,messageid,has_attachment,parentid,datepath FROM t ORDER BY datepath||date
""", {'threadid': threadid})
	lastpath = []
	for id,_from,subject,date,messageid,has_attachment,parentid,parentpath in curs.fetchall():
		yield {'id':id, 'mailfrom':_from, 'subject': subject, 'printdate': date.strftime("%Y-%m-%d %H:%M:%S"), 'messageid': messageid, 'hasattachment': has_attachment, 'parentid': parentid, 'indent': "&nbsp;" * len(parentpath)}


def _get_nextprevious(listmap, dt):
	curs = connection.cursor()
	curs.execute("""WITH l(listid) AS (
   SELECT unnest(%(lists)s)
)
SELECT l.listid,1,
 (SELECT ARRAY[messageid,to_char(date, 'yyyy-mm-dd hh24:mi:ss'),subject,_from] FROM messages m
     INNER JOIN list_threads lt ON lt.threadid=m.threadid
     WHERE m.date>%(time)s AND lt.listid=l.listid
     ORDER BY m.date LIMIT 1
  ) FROM l
UNION ALL
SELECT l.listid,0,
 (SELECT ARRAY[messageid,to_char(date, 'yyyy-mm-dd hh24:mi:ss'),subject,_from] FROM messages m
     INNER JOIN list_threads lt ON lt.threadid=m.threadid
     WHERE m.date<%(time)s AND lt.listid=l.listid
     ORDER BY m.date DESC LIMIT 1
 ) FROM l""", {
			'lists': listmap.keys(),
			'time': dt,
			})
	retval = {}
	for listid, isnext, data in curs.fetchall():
		if data:
			# Can be NULL, but if not, it will always have all fields
			listname = listmap[listid]
			d = {
				'msgid': data[0],
				'date': data[1],
				'subject': data[2],
				'from': data[3],
				}
			if retval.has_key(listname):
				retval[listname][isnext and 'next' or 'prev'] = d
			else:
				retval[listname] = {
					isnext and 'next' or 'prev': d
					}
	return retval

@cache(hours=4)
def message(request, msgid):
	try:
		m = Message.objects.get(messageid=msgid)
	except Message.DoesNotExist, e:
		raise Http404('Message does not exist')

	lists = List.objects.extra(where=["listid IN (SELECT listid FROM list_threads WHERE threadid=%s)" % m.threadid]).order_by('listname')
	listmap = dict([(l.listid, l.listname) for l in lists])
	threadstruct = list(_build_thread_structure(m.threadid))
	responses = [t for t in threadstruct if t['parentid']==m.id]
	if m.parentid:
		for t in threadstruct:
			if t['id'] == m.parentid:
				parent = t
				break
	else:
		parent = None
	nextprev = _get_nextprevious(listmap, m.date)

	r = render_to_response('message.html', {
			'msg': m,
			'threadstruct': threadstruct,
			'responses': responses,
			'parent': parent,
			'lists': lists,
			'nextprev': nextprev,
			}, NavContext(request, lists[0].listid))
	r['X-pgthread'] = ":%s:" % m.threadid
	return r

@cache(hours=4)
def message_flat(request, msgid):
	try:
		msg = Message.objects.get(messageid=msgid)
	except Message.DoesNotExist, e:
		raise Http404('Message does not exist')
	allmsg = Message.objects.filter(threadid=msg.threadid).order_by('date')
	# XXX: need to get the complete list of lists!

	r = render_to_response('message_flat.html', {
			'msg': msg,
			'allmsg': allmsg,
			}, NavContext(request))
	r['X-pgthread'] = ":%s:" % msg.threadid
	return r

@nocache
def message_raw(request, msgid):
	if 'HTTP_AUTHORIZATION' in request.META:
		auth = request.META['HTTP_AUTHORIZATION'].split()
		if len(auth) != 2:
			return HttpResponseForbidden("Invalid authentication")
		if auth[0].lower() == "basic":
			user, pwd = base64.b64decode(auth[1]).split(':')
			if user == 'archives' and pwd == 'antispam':
				curs = connection.cursor()
				curs.execute("SELECT threadid, hiddenstatus, rawtxt FROM messages WHERE messageid=%(messageid)s", {
						'messageid': msgid,
						})
				row = curs.fetchall()
				if len(row) != 1:
					raise Http404('Message does not exist')

				if row[0][1]:
					r = HttpResponse('This message has been hidden.', content_type='text/plain')
				else:
					r = HttpResponse(row[0][2], content_type='text/plain')
				r['X-pgthread'] = ":%s:" % row[0][0]
				return r
			# Invalid password falls through
		# Other authentication types fall through

	# Require authentication
	response = HttpResponse()
	response.status_code = 401
	response['WWW-Authenticate'] = 'Basic realm="Please authenticate with user archives and password antispam"'
	return response

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

def search(request):
	# Only certain hosts are allowed to call the search API
	if not request.META['REMOTE_ADDR'] in settings.SEARCH_CLIENTS:
		return HttpResponseForbidden('Invalid host')

	# Perform a search of the archives and return a JSON document.
	# Expects the following (optional) POST parameters:
	# q = query to search for
	# l = comma separated list of lists to search for
	# d = number of days back to search for, or -1 (or not specified)
	#     to search the full archives
	# s = sort results by ['r'=rank, 'd'=date]
	if not request.method == 'POST':
		raise Http404('I only respond to POST')

	if not request.POST.has_key('q'):
		raise Http404('No search query specified')
	query = request.POST['q']

	if request.POST.has_key('l'):
		try:
			lists = [int(x) for x in request.POST['l'].split(',')]
		except:
			# If failing to parse list of lists, just search all
			lists = None
	else:
		lists = None

	if request.POST.has_key('d'):
		days = int(request.POST['d'])
		if days < 1 or days > 365:
			firstdate = None
		else:
			firstdate = datetime.now() - timedelta(days=days)
	else:
		firstdate = None

	if request.POST.has_key('s'):
		list_sort = request.POST['s'] == 'd' and 'd' or 'r'
	else:
		list_sort = 'r'

	# Ok, we have all we need to do the search
	curs = connection.cursor()

	if query.find('@') > 0:
		# This could be a messageid. So try to get that one specifically first.
		# We don't do a more specific check if it's a messageid because doing
		# a key lookup is cheap...
		curs.execute("SELECT messageid FROM messages WHERE messageid=%(q)s", {
				'q': query,
				})
		a = curs.fetchall()
		if len(a) == 1:
			# Yup, this was a messageid
			resp = HttpResponse(mimetype='application/json')

			json.dump({'messageidmatch': 1}, resp)
			return resp
		# If not found, fall through to a regular search

	curs.execute("SET gin_fuzzy_search_limit=10000")
	qstr = "SELECT messageid, date, subject, _from, ts_rank_cd(fti, plainto_tsquery('public.pg', %(q)s)), ts_headline(bodytxt, plainto_tsquery('public.pg', %(q)s),'StartSel=\"[[[[[[\",StopSel=\"]]]]]]\"') FROM messages m WHERE fti @@ plainto_tsquery('public.pg', %(q)s)"
	params = {
		'q': query,
	}
	if lists:
		qstr += " AND EXISTS (SELECT 1 FROM list_threads lt WHERE lt.threadid=m.threadid AND lt.listid=ANY(%(lists)s))"
		params['lists'] = lists
	if firstdate:
		qstr += " AND m.date > %(date)s"
		params['date'] = firstdate
	if list_sort == 'r':
		qstr += " ORDER BY ts_rank_cd(fti, plainto_tsquery(%(q)s)) DESC LIMIT 1000"
	else:
		qstr += " ORDER BY date DESC LIMIT 1000"

	curs.execute(qstr, params)

	resp = HttpResponse(mimetype='application/json')

	json.dump([{
				'm': messageid,
				'd': date.isoformat(),
				's': subject,
				'f': mailfrom,
				'r': rank,
				'a': abstract.replace("[[[[[[", "<b>").replace("]]]]]]","</b>"),

				} for messageid, date, subject, mailfrom, rank, abstract in curs.fetchall()],
			  resp)
	return resp

@cache(seconds=10)
def web_sync_timestamp(request):
	s = datetime.now().strftime("%Y-%m-%d %H:%M:%S\n")
	r = HttpResponse(s, mimetype='text/plain')
	r['Content-Length'] = len(s)
	return r

@cache(hours=8)
def legacy(request, listname, year, month, msgnum):
	curs = connection.cursor()
	curs.execute("SELECT msgid FROM legacymap WHERE listid=(SELECT listid FROM lists WHERE listname=%(list)s) AND year=%(year)s AND month=%(month)s AND msgnum=%(msgnum)s", {
			'list': listname,
			'year': year,
			'month': month,
			'msgnum': msgnum,
			})
	r = curs.fetchall()
	if len(r) != 1:
		raise Http404('Message does not exist')
	return HttpResponsePermanentRedirect('/message-id/%s' % r[0][0])

@cache(hours=8)
def mbox(request, listname, mboxname):
	return HttpResponse('This needs to be handled by the webserver. This view should never be called.', content_type='text/plain')

# Redirect to the requested url, with a slash first. This is used to remove
# trailing slashes on messageid links by doing a permanent redirect. This is
# better than just eating them, since this way we only end up with one copy
# in the cache.
@cache(hours=8)
def slash_redirect(request, url):
	return HttpResponsePermanentRedirect("/%s" % url)
