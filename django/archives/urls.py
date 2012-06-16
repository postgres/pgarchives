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

    (r'^([\w-]+)/(\d+)-(\d+)/$', 'archives.mailarchives.views.datelist'),
    (r'^([\w-]+)/since/([^/]+)/$', 'archives.mailarchives.views.datelistsince'),

    (r'^attachment/(\d+)/$', 'archives.mailarchives.views.attachment'),
)
