from django.template import RequestContext
from django.http import HttpResponse, HttpResponseForbidden, Http404
from django.http import StreamingHttpResponse
from django.http import HttpResponsePermanentRedirect, HttpResponseNotModified
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404
from django.utils.http import http_date, parse_http_date_safe
from django.db import connection, transaction
from django.db.models import Q
from django.conf import settings

import copy
import re
import os
import base64
from datetime import datetime, timedelta, date
import calendar
import email.parser
import email.policy
from io import BytesIO

import json

from .redirecthandler import ERedirect

from .models import *


# Ensure the user is logged in (if it's not public lists)
def ensure_logged_in(request):
    if settings.PUBLIC_ARCHIVES:
        return
    if hasattr(request, 'user') and request.user.is_authenticated():
        return
    raise ERedirect('%s?next=%s' % (settings.LOGIN_URL, request.path))


# Ensure the user has permissions to access a list. If not, raise
# a permissions exception.
def ensure_list_permissions(request, l):
    if settings.PUBLIC_ARCHIVES:
        return
    if hasattr(request, 'user') and request.user.is_authenticated():
        if request.user.is_superuser:
            return
        if l.subscriber_access and ListSubscriber.objects.filter(list=l, username=request.user.username).exists():
            return
        # Logged in but no access
        raise PermissionDenied("Access denied.")

    # Redirect to a login page
    raise ERedirect('%s?next=%s' % (settings.LOGIN_URL, request.path))


# Ensure the user has permissions to access a message. In order to view
# a message, the user must have permissions on *all* lists the thread
# appears on.
def ensure_message_permissions(request, msgid):
    if settings.PUBLIC_ARCHIVES:
        return
    if hasattr(request, 'user') and request.user.is_authenticated():
        if request.user.is_superuser:
            return

        curs = connection.cursor()
        curs.execute("""SELECT EXISTS (
 SELECT 1 FROM list_threads
 INNER JOIN messages ON messages.threadid=list_threads.threadid
 WHERE messages.messageid=%(msgid)s
 AND NOT EXISTS (
  SELECT 1 FROM listsubscribers
  WHERE listsubscribers.list_id=list_threads.listid
  AND listsubscribers.username=%(username)s
 )
)""", {
            'msgid': msgid,
            'username': request.user.username,
        })
        if not curs.fetchone()[0]:
            # This thread is not on any list that the user does not have permissions on.
            return

        # Logged in but no access
        raise PermissionDenied("Access denied.")

    # Redirect to a login page
    raise ERedirect('%s?next=%s' % (settings.LOGIN_URL, request.path))


# Decorator to set cache age
def cache(days=0, hours=0, minutes=0, seconds=0):
    "Set the server to cache object a specified time. td must be a timedelta object"
    def _cache(fn):
        def __cache(request, *_args, **_kwargs):
            resp = fn(request, *_args, **_kwargs)
            if settings.PUBLIC_ARCHIVES:
                # Only set cache headers on public archives
                td = timedelta(hours=hours, minutes=minutes, seconds=seconds)
                resp['Cache-Control'] = 's-maxage=%s' % (td.days * 3600 * 24 + td.seconds)
            return resp
        return __cache
    return _cache


def nocache(fn):
    def _nocache(request, *_args, **_kwargs):
        resp = fn(request, *_args, **_kwargs)
        if settings.PUBLIC_ARCHIVES:
            # Only set cache headers on public archives
            resp['Cache-Control'] = 's-maxage=0'
        return resp
    return _nocache


# Decorator to require http auth
def antispam_auth(fn):
    def _antispam_auth(request, *_args, **_kwargs):
        if not settings.PUBLIC_ARCHIVES:
            return fn(request, *_args, **_kwargs)

        if 'HTTP_AUTHORIZATION' in request.META:
            auth = request.META['HTTP_AUTHORIZATION'].split()
            if len(auth) != 2:
                return HttpResponseForbidden("Invalid authentication")
            if auth[0].lower() == "basic":
                user, pwd = base64.b64decode(auth[1]).decode('utf8', errors='ignore').split(':')
                if user == 'archives' and pwd == 'antispam':
                    # Actually run the function if auth is correct
                    resp = fn(request, *_args, **_kwargs)
                    return resp
        # Require authentication
        response = HttpResponse()
        response.status_code = 401
        response['WWW-Authenticate'] = 'Basic realm="Please authenticate with user archives and password antispam"'
        return response

    return _antispam_auth


def get_all_groups_and_lists(request, listid=None):
    # Django doesn't (yet) support traversing the reverse relationship,
    # so we'll get all the lists and rebuild it backwards.
    if settings.PUBLIC_ARCHIVES or request.user.is_superuser:
        lists = List.objects.select_related('group').all().order_by('listname')
    else:
        lists = List.objects.select_related('group').filter(subscriber_access=True, listsubscriber__username=request.user.username).order_by('listname')
    listgroupid = None
    groups = {}
    for l in lists:
        if l.listid == listid:
            listgroupid = l.group.groupid

        if l.group.groupid in groups:
            groups[l.group.groupid]['lists'].append(l)
        else:
            groups[l.group.groupid] = {
                'groupid': l.group.groupid,
                'groupname': l.group.groupname,
                'sortkey': l.group.sortkey,
                'lists': [l, ],
                'homelink': 'list/group/%s' % l.group.groupid,
            }

    return (sorted(list(groups.values()), key=lambda g: g['sortkey']), listgroupid)


class NavContext(object):
    def __init__(self, request, listid=None, listname=None, all_groups=None, expand_groupid=None):
        self.request = request
        self.ctx = {}

        if all_groups:
            groups = copy.deepcopy(all_groups)
            if expand_groupid:
                listgroupid = int(expand_groupid)
        else:
            (groups, listgroupid) = get_all_groups_and_lists(request, listid)

        for g in groups:
            # On the root page, remove *all* entries
            # On other lists, remove the entries in all groups other than our
            # own.
            if (not listid and not expand_groupid) or listgroupid != g['groupid']:
                # Root page, so remove *all* entries
                g['lists'] = []

        self.ctx.update({'listgroups': groups})
        if listname:
            self.ctx.update({'searchform_listname': listname})


def render_nav(navcontext, template, ctx):
    ctx.update(navcontext.ctx)
    return render(navcontext.request, template, ctx)


@cache(hours=4)
def index(request):
    ensure_logged_in(request)

    (groups, listgroupid) = get_all_groups_and_lists(request)
    return render_nav(NavContext(request, all_groups=groups), 'index.html', {
        'groups': [{'groupname': g['groupname'], 'lists': g['lists']} for g in groups],
    })


@cache(hours=8)
def groupindex(request, groupid):
    (groups, listgroupid) = get_all_groups_and_lists(request)
    mygroups = [{'groupname': g['groupname'], 'lists': g['lists']} for g in groups if g['groupid'] == int(groupid)]
    if len(mygroups) == 0:
        raise Http404('List group does not exist')

    return render_nav(NavContext(request, all_groups=groups, expand_groupid=groupid), 'index.html', {
        'groups': mygroups,
    })


@cache(hours=8)
def monthlist(request, listname):
    l = get_object_or_404(List, listname=listname)
    ensure_list_permissions(request, l)

    curs = connection.cursor()
    curs.execute("SELECT year, month FROM list_months WHERE listid=%(listid)s ORDER BY year DESC, month DESC", {'listid': l.listid})
    months = [{'year': r[0], 'month': r[1], 'date': datetime(r[0], r[1], 1)} for r in curs.fetchall()]

    return render_nav(NavContext(request, l.listid, l.listname), 'monthlist.html', {
        'list': l,
        'months': months,
    })


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


def _render_datelist(request, l, d, datefilter, title, queryproc):
    # NOTE! Basic permissions checks must be done before calling this function!

    if not settings.PUBLIC_ARCHIVES and not request.user.is_superuser:
        mlist = Message.objects.defer('bodytxt', 'cc', 'to').select_related().filter(datefilter, hiddenstatus__isnull=True).extra(
            where=["threadid IN (SELECT threadid FROM list_threads t WHERE listid=%s AND NOT EXISTS (SELECT 1 FROM list_threads t2 WHERE t2.threadid=t.threadid AND listid NOT IN (SELECT list_id FROM listsubscribers WHERE username=%s)))"],
            params=(l.listid, request.user.username),
        )
    else:
        # Else we return everything
        mlist = Message.objects.defer('bodytxt', 'cc', 'to').select_related().filter(datefilter, hiddenstatus__isnull=True).extra(where=["threadid IN (SELECT threadid FROM list_threads WHERE listid=%s)" % l.listid])
    mlist = queryproc(mlist)

    allyearmonths = set([(m.date.year, m.date.month) for m in mlist])
    (yearmonth, daysinmonth) = get_monthday_info(mlist, l, d)

    r = render_nav(NavContext(request, l.listid, l.listname), 'datelist.html', {
        'list': l,
        'messages': mlist,
        'title': title,
        'daysinmonth': daysinmonth,
        'yearmonth': yearmonth,
    })
    r['X-pglm'] = ':%s:' % (':'.join(['%s/%s/%s' % (l.listid, year, month) for year, month in allyearmonths]))
    return r


def render_datelist_from(request, l, d, title, to=None):
    # NOTE! Basic permissions checks must be done before calling this function!
    datefilter = Q(date__gte=d)
    if to:
        datefilter.add(Q(date__lt=to), Q.AND)

    return _render_datelist(request, l, d, datefilter, title,
                            lambda x: list(x.order_by('date')[:200]))


def render_datelist_to(request, l, d, title):
    # NOTE! Basic permissions checks must be done before calling this function!

    # Need to sort this backwards in the database to get the LIMIT applied
    # properly, and then manually resort it in the correct order. We can do
    # the second sort safely in python since it's not a lot of items..

    return _render_datelist(request, l, d, Q(date__lte=d), title,
                            lambda x: sorted(x.order_by('-date')[:200], key=lambda m: m.date))


@cache(hours=2)
def datelistsince(request, listname, msgid):
    l = get_object_or_404(List, listname=listname)
    ensure_list_permissions(request, l)

    msg = get_object_or_404(Message, messageid=msgid)
    return render_datelist_from(request, l, msg.date, "%s since %s" % (l.listname, msg.date.strftime("%Y-%m-%d %H:%M:%S")))


# Longer cache since this will be used for the fixed date links
@cache(hours=4)
def datelistsincetime(request, listname, year, month, day, hour, minute):
    l = get_object_or_404(List, listname=listname)
    ensure_list_permissions(request, l)

    try:
        d = datetime(int(year), int(month), int(day), int(hour), int(minute))
    except ValueError:
        raise Http404("Invalid date format, not found")
    return render_datelist_from(request, l, d, "%s since %s" % (l.listname, d.strftime("%Y-%m-%d %H:%M")))


@cache(hours=2)
def datelistbefore(request, listname, msgid):
    l = get_object_or_404(List, listname=listname)
    ensure_list_permissions(request, l)

    msg = get_object_or_404(Message, messageid=msgid)
    return render_datelist_to(request, l, msg.date, "%s before %s" % (l.listname, msg.date.strftime("%Y-%m-%d %H:%M:%S")))


@cache(hours=2)
def datelistbeforetime(request, listname, year, month, day, hour, minute):
    l = get_object_or_404(List, listname=listname)
    ensure_list_permissions(request, l)

    try:
        d = datetime(int(year), int(month), int(day), int(hour), int(minute))
    except ValueError:
        raise Http404("Invalid date format, not found")
    return render_datelist_to(request, l, d, "%s before %s" % (l.listname, d.strftime("%Y-%m-%d %H:%M")))


@cache(hours=4)
def datelist(request, listname, year, month):
    l = get_object_or_404(List, listname=listname)
    ensure_list_permissions(request, l)

    try:
        d = datetime(int(year), int(month), 1)
    except ValueError:
        raise Http404("Malformatted date, month not found")

    enddate = d + timedelta(days=31)
    enddate = datetime(enddate.year, enddate.month, 1)
    return render_datelist_from(request, l, d, "%s - %s %s" % (l.listname, d.strftime("%B"), d.year), enddate)


@cache(hours=4)
def attachment(request, attid):
    # Use a direct query instead of django, since it has bad support for
    # bytea
    # XXX: minor information leak, because we load the whole attachment before we check
    # the thread permissions. Is that OK?
    curs = connection.cursor()
    curs.execute("SELECT filename, contenttype, messageid, attachment FROM attachments INNER JOIN messages ON messages.id=attachments.message AND attachments.id=%(id)s AND messages.hiddenstatus IS NULL", {'id': int(attid)})
    r = curs.fetchall()
    if len(r) != 1:
        return HttpResponse("Attachment not found")

    ensure_message_permissions(request, r[0][2])

    return HttpResponse(r[0][3], content_type=r[0][1])


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

    for id, _from, subject, date, messageid, has_attachment, parentid, parentpath in curs.fetchall():
        yield {
            'id': id,
            'mailfrom': _from,
            'subject': subject,
            'date': date,
            'printdate': date.strftime("%Y-%m-%d %H:%M:%S"),
            'messageid': messageid,
            'hasattachment': has_attachment,
            'parentid': parentid,
            'indent': "&nbsp;" * len(parentpath),
        }


def _get_nextprevious(listmap, dt):
    curs = connection.cursor()
    curs.execute("""
WITH l(listid) AS (
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
 ) FROM l""",
                 {
                     'lists': list(listmap.keys()),
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
            if listname in retval:
                retval[listname][isnext and 'next' or 'prev'] = d
            else:
                retval[listname] = {
                    isnext and 'next' or 'prev': d
                }
    return retval


@cache(hours=4)
def message(request, msgid):
    ensure_message_permissions(request, msgid)

    try:
        m = Message.objects.get(messageid=msgid)
    except Message.DoesNotExist:
        raise Http404('Message does not exist')

    lists = List.objects.extra(where=["listid IN (SELECT listid FROM list_threads WHERE threadid=%s)" % m.threadid]).order_by('listname')
    listmap = dict([(l.listid, l.listname) for l in lists])
    threadstruct = list(_build_thread_structure(m.threadid))
    newest = calendar.timegm(max(threadstruct, key=lambda x: x['date'])['date'].utctimetuple())
    if 'HTTP_IF_MODIFIED_SINCE' in request.META and not settings.DEBUG:
        ims = parse_http_date_safe(request.META.get("HTTP_IF_MODIFIED_SINCE"))
        if ims >= newest:
            return HttpResponseNotModified()

    responses = [t for t in threadstruct if t['parentid'] == m.id]

    if m.parentid:
        for t in threadstruct:
            if t['id'] == m.parentid:
                parent = t
                break
    else:
        parent = None
    nextprev = _get_nextprevious(listmap, m.date)

    r = render_nav(NavContext(request, lists[0].listid, lists[0].listname), 'message.html', {
        'msg': m,
        'threadstruct': threadstruct,
        'responses': responses,
        'parent': parent,
        'lists': lists,
        'nextprev': nextprev,
    })
    r['X-pgthread'] = ":%s:" % m.threadid
    r['Last-Modified'] = http_date(newest)
    return r


@cache(hours=4)
def message_flat(request, msgid):
    ensure_message_permissions(request, msgid)

    try:
        msg = Message.objects.get(messageid=msgid)
    except Message.DoesNotExist:
        raise Http404('Message does not exist')
    allmsg = list(Message.objects.filter(threadid=msg.threadid).order_by('date'))
    lists = List.objects.extra(where=["listid IN (SELECT listid FROM list_threads WHERE threadid=%s)" % msg.threadid]).order_by('listname')

    isfirst = (msg == allmsg[0])

    newest = calendar.timegm(max(allmsg, key=lambda x: x.date).date.utctimetuple())
    if 'HTTP_IF_MODIFIED_SINCE' in request.META and not settings.DEBUG:
        ims = parse_http_date_safe(request.META.get('HTTP_IF_MODIFIED_SINCE'))
        if ims >= newest:
            return HttpResponseNotModified()

    r = render_nav(NavContext(request), 'message_flat.html', {
        'msg': msg,
        'allmsg': allmsg,
        'lists': lists,
        'isfirst': isfirst,
    })
    r['X-pgthread'] = ":%s:" % msg.threadid
    r['Last-Modified'] = http_date(newest)
    return r


@nocache
@antispam_auth
def message_raw(request, msgid):
    ensure_message_permissions(request, msgid)

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


def _build_mbox(query, params, msgid=None):
    connection.ensure_connection()

    # Rawmsg is not in the django model, so we have to query it separately
    curs = connection.connection.cursor(name='mbox', withhold=True)
    curs.itersize = 50
    curs.execute(query, params)

    firstmsg = curs.fetchone()
    if msgid and firstmsg[0] != msgid:
        # Always redirect to the first message in the thread when building
        # the mbox, to not generate potentially multiple copies in
        # the cache.
        return HttpResponsePermanentRedirect(firstmsg[0])

    def _one_message(raw):
        # Parse as a message to generate headers
        s = BytesIO(raw)
        parser = email.parser.BytesParser(policy=email.policy.compat32)
        msg = parser.parse(s)
        return msg.as_string(unixfrom=True)

    def _message_stream(first):
        yield _one_message(first[1])

        for mid, raw in curs:
            yield _one_message(raw)

        # Close must be done inside this function. If we close it in the
        # main function, it won't let the iterator run to completion.
        curs.close()

    r = StreamingHttpResponse(_message_stream(firstmsg))
    r['Content-type'] = 'application/mbox'
    return r


@nocache
@antispam_auth
def message_mbox(request, msgid):
    ensure_message_permissions(request, msgid)

    msg = get_object_or_404(Message, messageid=msgid)

    return _build_mbox(
        "SELECT messageid, rawtxt FROM messages WHERE threadid=%(thread)s AND hiddenstatus IS NULL ORDER BY date",
        {
            'thread': msg.threadid,
        },
        msgid)


@nocache
@antispam_auth
def mbox(request, listname, listname2, mboxyear, mboxmonth):
    if (listname != listname2):
        raise Http404('List name mismatch')
    l = get_object_or_404(List, listname=listname)
    ensure_list_permissions(request, l)

    mboxyear = int(mboxyear)
    mboxmonth = int(mboxmonth)

    query = "SELECT messageid, rawtxt FROM messages m INNER JOIN list_threads t ON t.threadid=m.threadid WHERE listid=%(listid)s AND hiddenstatus IS NULL AND date >= %(startdate)s AND date <= %(enddate)s %%% ORDER BY date"
    params = {
        'listid': l.listid,
        'startdate': date(mboxyear, mboxmonth, 1),
        'enddate': datetime(mboxyear, mboxmonth, calendar.monthrange(mboxyear, mboxmonth)[1], 23, 59, 59),
    }

    if not settings.PUBLIC_ARCHIVES and not request.user.is_superuser:
        # Restrict to only view messages that the user has permissions on all threads they're on
        query = query.replace('%%%', 'AND NOT EXISTS (SELECT 1 FROM list_threads t2 WHERE t2.threadid=t.threadid AND listid NOT IN (SELECT list_id FROM listsubscribers WHERE username=%(username)s))')
        params['username'] = request.user.username
    else:
        # Just return the whole thing
        query = query.replace('%%%', '')
    return _build_mbox(query, params)


def search(request):
    if not settings.PUBLIC_ARCHIVES:
        # We don't support searching of non-public archives at all at this point.
        # XXX: room for future improvement
        return HttpResponseForbidden('Not public archives')

    # Only certain hosts are allowed to call the search API
    if not request.META['REMOTE_ADDR'] in settings.SEARCH_CLIENTS:
        return HttpResponseForbidden('Invalid host')

    curs = connection.cursor()

    # Perform a search of the archives and return a JSON document.
    # Expects the following (optional) POST parameters:
    # q = query to search for
    # ln = comma separate list of listnames to search in
    # d = number of days back to search for, or -1 (or not specified)
    #      to search the full archives
    # s = sort results by ['r'=rank, 'd'=date, 'i'=inverse date]
    if not request.method == 'POST':
        raise Http404('I only respond to POST')

    if 'q' not in request.POST:
        raise Http404('No search query specified')
    query = request.POST['q']

    if 'ln' in request.POST:
        try:
            curs.execute("SELECT listid FROM lists WHERE listname=ANY(%(names)s)", {
                'names': request.POST['ln'].split(','),
            })
            lists = [x for x, in curs.fetchall()]
        except:
            # If failing to parse list of lists, just search all
            lists = None
    else:
        lists = None

    if 'd' in request.POST:
        days = int(request.POST['d'])
        if days < 1 or days > 365:
            firstdate = None
        else:
            firstdate = datetime.now() - timedelta(days=days)
    else:
        firstdate = None

    if 's' in request.POST:
        list_sort = request.POST['s']
        if list_sort not in ('d', 'r', 'i'):
            list_stort = 'r'
    else:
        list_sort = 'r'

    # Ok, we have all we need to do the search

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
            resp = HttpResponse(content_type='application/json')

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
    elif list_sort == 'd':
        qstr += " ORDER BY date DESC LIMIT 1000"
    else:
        qstr += " ORDER BY date ASC LIMIT 1000"

    curs.execute(qstr, params)

    resp = HttpResponse(content_type='application/json')

    json.dump([
        {
            'm': messageid,
            'd': date.isoformat(),
            's': subject,
            'f': mailfrom,
            'r': rank,
            'a': abstract.replace("[[[[[[", "<b>").replace("]]]]]]", "</b>"),
        } for messageid, date, subject, mailfrom, rank, abstract in curs.fetchall()],
        resp)
    return resp


@cache(seconds=10)
def web_sync_timestamp(request):
    s = datetime.now().strftime("%Y-%m-%d %H:%M:%S\n")
    r = HttpResponse(s, content_type='text/plain')
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


# dynamic CSS serving, meaning we merge a number of different CSS into a
# single one, making sure it turns into a single http response. We do this
# dynamically, since the output will be cached.
_dynamic_cssmap = {
    'base': ['media/css/main.css',
             'media/css/normalize.css', ],
    'docs': ['media/css/global.css',
             'media/css/table.css',
             'media/css/text.css',
             'media/css/docs.css'],
}


@cache(hours=8)
def dynamic_css(request, css):
    if css not in _dynamic_cssmap:
        raise Http404('CSS not found')
    files = _dynamic_cssmap[css]
    resp = HttpResponse(content_type='text/css')

    # We honor if-modified-since headers by looking at the most recently
    # touched CSS file.
    latestmod = 0
    for fn in files:
        try:
            stime = os.stat(fn).st_mtime
            if latestmod < stime:
                latestmod = stime
        except OSError:
            # If we somehow referred to a file that didn't exist, or
            # one that we couldn't access.
            raise Http404('CSS (sub) not found')
    if 'HTTP_IF_MODIFIED_SINCE' in request.META:
        # This code is mostly stolen from django :)
        matches = re.match(r"^([^;]+)(; length=([0-9]+))?$",
                           request.META.get('HTTP_IF_MODIFIED_SINCE'),
                           re.IGNORECASE)
        header_mtime = parse_http_date_safe(matches.group(1))
        # We don't do length checking, just the date
        if int(latestmod) <= header_mtime:
            return HttpResponseNotModified(content_type='text/css')
    resp['Last-Modified'] = http_date(latestmod)

    for fn in files:
        with open(fn) as f:
            resp.write("/* %s */\n" % fn)
            resp.write(f.read())
            resp.write("\n")

    return resp


# Redirect to the requested url, with a slash first. This is used to remove
# trailing slashes on messageid links by doing a permanent redirect. This is
# better than just eating them, since this way we only end up with one copy
# in the cache.
@cache(hours=8)
def slash_redirect(request, url):
    return HttpResponsePermanentRedirect("/%s" % url)


# Redirect the requested URL to whatever happens to be in the regexp capture.
# This is used for user agents that generate broken URLs that are easily
# captured using regexp.
@cache(hours=8)
def re_redirect(request, prefix, msgid):
    return HttpResponsePermanentRedirect("/%s%s" % (prefix, msgid))
