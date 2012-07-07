from django.db import models

class Message(models.Model):
	threadid = models.IntegerField(null=False, blank=False)
	mailfrom = models.TextField(null=False, db_column='_from')
	to = models.TextField(null=False, db_column='_to')
	cc = models.TextField(null=False)
	subject = models.TextField(null=False)
	date = models.DateTimeField(null=False)
	messageid = models.TextField(null=False)
	bodytxt = models.TextField(null=False)
	parentid = models.IntegerField(null=False, blank=False)
	has_attachment = models.BooleanField(null=False, default=False)

	class Meta:
		db_table = 'messages'

	@property
	def printdate(self):
		return self.date.strftime("%Y-%m-%d %H:%M:%S")

	@property
	def shortdate(self):
		return self.date.strftime("%Y%m%d%H%M")

class ListGroup(models.Model):
	groupid = models.IntegerField(null=False, primary_key=True)
	groupname = models.CharField(max_length=200, null=False, blank=False)

	class Meta:
		db_table = 'listgroups'

class List(models.Model):
	listid = models.IntegerField(null=False, primary_key=True)
	listname = models.CharField(max_length=200, null=False, blank=False, unique=True)
	shortdesc = models.TextField(null=False, blank=False)
	description = models.TextField(null=False, blank=False)
	active = models.BooleanField(null=False, blank=False)
	groupid = models.ForeignKey(ListGroup)

	class Meta:
		db_table = 'lists'

class Attachment(models.Model):
	message = models.ForeignKey(Message, null=False, blank=False, db_column='message')
	filename = models.CharField(max_length=1000, null=False, blank=False)
	contenttype = models.CharField(max_length=1000, null=False, blank=False)
	# attachment = bytea, not supported by django at this point

	class Meta:
		db_table = 'attachments'
