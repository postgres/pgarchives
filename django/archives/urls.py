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

    (r'^test/(\d+)/$', 'archives.mailarchives.views.testview'),
    (r'^test/oldsite/([^/]+)/$', 'archives.mailarchives.views.oldsite'),

    (r'^message-id/([^/]+)/', 'archives.mailarchives.views.message'),
    (r'^([\w-]+)/$', 'archives.mailarchives.views.monthlist'),
    (r'^([\w-]+)/(\d+)-(\d+)/$', 'archives.mailarchives.views.datelist'),
    (r'^([\w-]+)/since/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', 'archives.mailarchives.views.datelistsincetime'),
    (r'^([\w-]+)/since/([^/]+)/$', 'archives.mailarchives.views.datelistsince'),
    (r'^([\w-]+)/before/(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})', 'archives.mailarchives.views.datelistbeforetime'),
    (r'^([\w-]+)/before/([^/]+)/$', 'archives.mailarchives.views.datelistbefore'),

    (r'^attachment/(\d+)/.*$', 'archives.mailarchives.views.attachment'),

    # Normally served by the webserver, but needed for development installs
    (r'^media/(.*)$', 'django.views.static.serve', {
			'document_root': '../media',
    })
)
