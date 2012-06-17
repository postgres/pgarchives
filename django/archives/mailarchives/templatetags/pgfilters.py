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
	return parseaddr(value)[0]
