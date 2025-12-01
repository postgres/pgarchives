from django.urls import re_path
from django.conf import settings

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

import archives.mailarchives.views
import archives.mailarchives.api

urlpatterns = [
    # Examples:
    # re_path(r'^$', 'archives.views.home', name='home),
    # re_path(r'^archives/', include('archives.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # re_path(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # re_path(r'^admin/', include(admin.site.urls)),

    re_path(r'^web_sync_timestamp$', archives.mailarchives.views.web_sync_timestamp),
    re_path(r'^$', archives.mailarchives.views.index),
    re_path(r'^list/$', archives.mailarchives.views.index),
    re_path(r'^list/group/(\d+)/$', archives.mailarchives.views.groupindex),

    # some user agents generate broken URLs that include <>
    re_path(r'^(?P<prefix>message-id/(|flat/|raw/))<(?P<msgid>.*)>$', archives.mailarchives.views.re_redirect),

    # message-id ending in a slash needs to be redirected to one without it
    re_path(r'^(message-id/.*)/$', archives.mailarchives.views.slash_redirect),

    # Match regular messages
    re_path(r'^message-id/flat/(.+)$', archives.mailarchives.views.message_flat),
    re_path(r'^message-id/raw/(.+)$', archives.mailarchives.views.message_raw),
    re_path(r'^message-id/mbox/(.+)$', archives.mailarchives.views.message_mbox),
    re_path(r'^message-id/resend/(.+)/complete$', archives.mailarchives.views.resend_complete),
    re_path(r'^message-id/resend/(.+)$', archives.mailarchives.views.resend),
    re_path(r'^message-id/attachment/(\d+)/?.*$', archives.mailarchives.views.attachment),
    re_path(r'^message-id/legacy/([\w-]+)/(\d+)-(\d+)/msg(\d+).php$', archives.mailarchives.views.legacy),
    re_path(r'^message-id/(.+)$', archives.mailarchives.views.message),

    re_path(r'^list/([\w-]+)/mbox/([\w-]+)\.(\d{4})(\d{2})', archives.mailarchives.views.mbox),

    # Search
    re_path(r'^archives-search/', archives.mailarchives.views.search),

    # Date etc indexes
    re_path(r'^list/([\w-]+)/$', archives.mailarchives.views.monthlist),
    re_path(r'^list/([\w-]+)/(\d+)-(\d+)/$', archives.mailarchives.views.datelist),
    re_path(r'^list/([\w-]+)/since/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', archives.mailarchives.views.datelistsincetime),
    re_path(r'^list/([\w-]+)/since/([^/]+)/$', archives.mailarchives.views.datelistsince),
    re_path(r'^list/([\w-]+)/before/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', archives.mailarchives.views.datelistbeforetime),
    re_path(r'^list/([\w-]+)/before/([^/]+)$', archives.mailarchives.views.datelistbefore),

    # API calls
    re_path(r'^list/([\w-]+|\*)/latest.json$', archives.mailarchives.api.latest),
    re_path(r'^message-id.json/(.+)$', archives.mailarchives.api.thread),
    re_path(r'^listinfo/$', archives.mailarchives.api.listinfo),

    # Normally served off www.postgresql.org, but manually handled here for
    # development installs.
    re_path(r'^dyncss/(?P<css>base|docs).css$', archives.mailarchives.views.dynamic_css),
]

if settings.ALLOW_RESEND or not settings.PUBLIC_ARCHIVES:
    import archives.auth

    urlpatterns += [
        # For non-public archives, support login
        re_path(r'^(?:list/_auth/)?accounts/login/?$', archives.auth.login),
        re_path(r'^(?:list/_auth/)?accounts/logout/?$', archives.auth.logout),
        re_path(r'^(?:list/_auth/)?auth_receive/$', archives.auth.auth_receive),
        re_path(r'^(?:list/_auth/)?auth_api/$', archives.auth.auth_api),
    ]
