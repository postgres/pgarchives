from django.conf.urls import include, url
from django.conf import settings

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

import archives.mailarchives.views
import archives.mailarchives.api

urlpatterns = [
    # Examples:
    # url(r'^$', 'archives.views.home', name='home),
    # url(r'^archives/', include('archives.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),

    url(r'^web_sync_timestamp$', archives.mailarchives.views.web_sync_timestamp),
    url(r'^$', archives.mailarchives.views.index),
    url(r'^list/$', archives.mailarchives.views.index),
    url(r'^list/group/(\d+)/$', archives.mailarchives.views.groupindex),

    # some user agents generate broken URLs that include <>
    url(r'^(?P<prefix>message-id/(|flat/|raw/))<(?P<msgid>.*)>$', archives.mailarchives.views.re_redirect),

    # message-id ending in a slash needs to be redirected to one without it
    url(r'^(message-id/.*)/$', archives.mailarchives.views.slash_redirect),

    # Match regular messages
    url(r'^message-id/flat/(.+)$', archives.mailarchives.views.message_flat),
    url(r'^message-id/raw/(.+)$', archives.mailarchives.views.message_raw),
    url(r'^message-id/mbox/(.+)$', archives.mailarchives.views.message_mbox),
    url(r'^message-id/(.+)$', archives.mailarchives.views.message),
    url(r'^list/([\w-]+)/mbox/([\w-]+)\.(\d{4})(\d{2})', archives.mailarchives.views.mbox),

    # Search
    url(r'^archives-search/', archives.mailarchives.views.search),

    # Date etc indexes
    url(r'^list/([\w-]+)/$', archives.mailarchives.views.monthlist),
    url(r'^list/([\w-]+)/(\d+)-(\d+)/$', archives.mailarchives.views.datelist),
    url(r'^list/([\w-]+)/since/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', archives.mailarchives.views.datelistsincetime),
    url(r'^list/([\w-]+)/since/([^/]+)/$', archives.mailarchives.views.datelistsince),
    url(r'^list/([\w-]+)/before/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', archives.mailarchives.views.datelistbeforetime),
    url(r'^list/([\w-]+)/before/([^/]+)$', archives.mailarchives.views.datelistbefore),

    url(r'^message-id/attachment/(\d+)/.*$', archives.mailarchives.views.attachment),

    # API calls
    url(r'^list/([\w-]+|\*)/latest.json$', archives.mailarchives.api.latest),
    url(r'^message-id.json/(.+)$', archives.mailarchives.api.thread),
    url(r'^listinfo/$', archives.mailarchives.api.listinfo),
    #    url(r'^thread/(.+)/subscribe/$', archives.mailarchives.api.thread_subscribe),

    # Legacy forwarding from old archives site
    url(r'^message-id/legacy/([\w-]+)/(\d+)-(\d+)/msg(\d+).php$', archives.mailarchives.views.legacy),

    # Normally served off www.postgresql.org, but manually handled here for
    # development installs.
    url(r'^dyncss/(?P<css>base|docs).css$', archives.mailarchives.views.dynamic_css),
]

if not settings.PUBLIC_ARCHIVES:
    import archives.auth

    urlpatterns += [
        # For non-public archives, support login
        url(r'^accounts/login/?$', archives.auth.login),
        url(r'^accounts/logout/?$', archives.auth.logout),
        url(r'^auth_receive/$', archives.auth.auth_receive),
    ]
