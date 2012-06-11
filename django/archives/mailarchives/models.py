from django.db import models

class Message(models.Model):
	mailfrom = models.TextField(null=False, db_column='_from')
	to = models.TextField(null=False, db_column='_to')
	cc = models.TextField(null=False)
	subject = models.TextField(null=False)
	date = models.DateTimeField(null=False)
	messageid = models.TextField(null=False)
	bodytxt = models.TextField(null=False)

	class Meta:
		db_table = 'messages'
		
class List(models.Model):
	listid = models.IntegerField(null=False, primary_key=True)
	listname = models.CharField(max_length=200, null=False, blank=False, unique=True)

	class Meta:
		db_table = 'lists'

class Attachment(models.Model):
	message = models.ForeignKey(Message, null=False, blank=False, db_column='message')
	filename = models.CharField(max_length=1000, null=False, blank=False)
	contenttype = models.CharField(max_length=1000, null=False, blank=False)
	# attachment = bytea, not supported by django at this point

	class Meta:
		db_table = 'attachments'
