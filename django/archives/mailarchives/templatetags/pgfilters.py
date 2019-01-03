from django.template.defaultfilters import stringfilter
from django import template
from email.utils import parseaddr

import re
import hashlib

register = template.Library()

def _rewrite_email(value):
    return value.replace('@', '(at)').replace('.','(dot)')

@register.filter(name='hidemail')
@stringfilter
def hidemail(value):
    return _rewrite_email(value)

# A regular expression and replacement function to mangle email addresses.
#
# The archived messages contain a lot of links to other messages in the
# mailing list archives:
#
#  https://www.postgresql.org/message-id/1asd21das@mail.gmail.com
#  https://postgr.es/m/1asd21das@mail.gmail.com
#
# Those are not email addresses, so ignore them. The links won't work if they
# are mangled.
_re_mail = re.compile('(/m(essage-id)?/)?[^()<>@,;:\/\s"\'&|]+@[^()<>@,;:\/\s"\'&|]+')
def _rewrite_email_match(match):
    if match.group(1):
        return match.group(0)    # was preceded by /message-id/
    else:
        return _rewrite_email(match.group(0))

@register.filter(name='hideallemail')
@stringfilter
def hideallemail(value):
    return _re_mail.sub(lambda x: _rewrite_email_match(x), value)

@register.filter(name='nameonly')
@stringfilter
def nameonly(value):
    (name, email) = parseaddr(value)
    if name:
        return name
    return email.split('@')[0]

@register.filter(name='md5')
@stringfilter
def md5(value):
    return hashlib.md5(value.encode('utf8')).hexdigest()
