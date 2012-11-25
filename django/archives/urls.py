from django.conf.urls.defaults import patterns, include, url

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'archives.views.home', name='home'),
    # url(r'^archives/', include('archives.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),

    (r'^web_sync_timestamp$', 'archives.mailarchives.views.web_sync_timestamp'),
    (r'^$', 'archives.mailarchives.views.index'),
    (r'^list/$', 'archives.mailarchives.views.index'),
    (r'^message-id/([^/]+)$', 'archives.mailarchives.views.message'),
    (r'^message-id/flat/([^/]+)$', 'archives.mailarchives.views.message_flat'),
    (r'^message-id/raw/([^/]+)$', 'archives.mailarchives.views.message_raw'),
    (r'^archives-search/', 'archives.mailarchives.views.search'),

    # Date etc indexes
    (r'^list/([\w-]+)/$', 'archives.mailarchives.views.monthlist'),
    (r'^list/([\w-]+)/(\d+)-(\d+)/$', 'archives.mailarchives.views.datelist'),
    (r'^list/([\w-]+)/since/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', 'archives.mailarchives.views.datelistsincetime'),
    (r'^list/([\w-]+)/since/([^/]+)/$', 'archives.mailarchives.views.datelistsince'),
    (r'^list/([\w-]+)/before/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', 'archives.mailarchives.views.datelistbeforetime'),
    (r'^list/([\w-]+)/before/([^/]+)$', 'archives.mailarchives.views.datelistbefore'),

    (r'^message-id/attachment/(\d+)/.*$', 'archives.mailarchives.views.attachment'),

    # Legacy forwarding from old archives site
    (r'^message-id/legacy/([\w-]+)/(\d+)-(\d+)/msg(\d+).php$', 'archives.mailarchives.views.legacy'),

    # Normally served by the webserver, but needed for development installs
    (r'^media/(.*)$', 'django.views.static.serve', {
			'document_root': '../media',
    }),
    (r'^media-archives/(.*)$', 'django.views.static.serve', {
			'document_root': '../media',
    }),

)
