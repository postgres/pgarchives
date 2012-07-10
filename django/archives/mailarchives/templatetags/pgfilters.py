from django.template.defaultfilters import stringfilter
from django import template
from email.utils import parseaddr

import re

register = template.Library()

def _rewrite_email(value):
	return value.replace('@', '(at)').replace('.','(dot)')

@register.filter(name='hidemail')
@stringfilter
def hidemail(value):
	return _rewrite_email(value)

_re_mail = re.compile('[^()<>@,;:\/\s"\'&|]+@[^()<>@,;:\/\s"\'&|]+')
@register.filter(name='hideallemail')
@stringfilter
def hideallemail(value):
	return _re_mail.sub(lambda x: _rewrite_email(x.group(0)), value)

@register.filter(name='nameonly')
@stringfilter
def nameonly(value):
	(name, email) = parseaddr(value)
	if name:
		return name
	return email.split('@')[0]
