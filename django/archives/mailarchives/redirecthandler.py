from django import shortcuts

class ERedirect(Exception):
    def __init__(self, url):
        self.url = url

class RedirectMiddleware(object):
    def process_exception(self, request, exception):
        if isinstance(exception, ERedirect):
            return shortcuts.redirect(exception.url)
