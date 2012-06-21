from django.template.defaultfilters import stringfilter
from django import template
from email.utils import parseaddr

register = template.Library()

@register.filter(name='hidemail')
@stringfilter
def hidemail(value):
	return value.replace('@', '(at)').replace('.','(dot)')

@register.filter(name='nameonly')
@stringfilter
def nameonly(value):
	(name, email) = parseaddr(value)
	if name:
		return name
	return email.split('@')[0]
