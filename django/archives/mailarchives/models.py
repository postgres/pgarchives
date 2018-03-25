from django.db import models

# Reason a message was hidden.
# We're intentionally putting the prefix text in the array here, since
# we might need that flexibility in the future.
hide_reasons = [
	None,                                # placeholder for 0
	'This message has been hidden because a virus was found in the message.', # 1
	'This message has been hidden because the message violated policies.',    # 2
	'This message has been hidden because for privacy reasons.',              # 3
	'This message was corrupt',                                               # 4
	]


class Message(models.Model):
	threadid = models.IntegerField(null=False, blank=False)
	mailfrom = models.TextField(null=False, db_column='_from')
	to = models.TextField(null=False, db_column='_to')
	cc = models.TextField(null=False)
	subject = models.TextField(null=False)
	date = models.DateTimeField(null=False)
	messageid = models.TextField(null=False)
	bodytxt = models.TextField(null=False)
	# rawtxt is a bytea field, which django doesn't support (easily)
	parentid = models.IntegerField(null=False, blank=False)
	has_attachment = models.BooleanField(null=False, default=False)
	hiddenstatus = models.IntegerField(null=True)
	# fti is a tsvector field, which django doesn't support (easily)

	class Meta:
		db_table = 'messages'

	@property
	def printdate(self):
		return self.date.strftime("%Y-%m-%d %H:%M:%S")

	@property
	def shortdate(self):
		return self.date.strftime("%Y%m%d%H%M")

	# We explicitly cache the attachments here, so we can use them
	# multiple times from templates without generating multiple queries
	# to the database.
	_attachments = None
	@property
	def attachments(self):
		if not self._attachments:
			self._attachments = self.attachment_set.extra(select={'len': 'length(attachment)'}).all()
		return self._attachments

	@property
	def hiddenreason(self):
		if not self.hiddenstatus: return None
		try:
			return hide_reasons[self.hiddenstatus]
		except:
			# Weird value
			return 'This message has been hidden.'

class ListGroup(models.Model):
	groupid = models.IntegerField(null=False, primary_key=True)
	groupname = models.CharField(max_length=200, null=False, blank=False)
	sortkey = models.IntegerField(null=False)

	class Meta:
		db_table = 'listgroups'

class List(models.Model):
	listid = models.IntegerField(null=False, primary_key=True)
	listname = models.CharField(max_length=200, null=False, blank=False, unique=True)
	shortdesc = models.TextField(null=False, blank=False)
	description = models.TextField(null=False, blank=False)
	active = models.BooleanField(null=False, blank=False)
	group = models.ForeignKey(ListGroup, db_column='groupid')
	subscriber_access = models.BooleanField(null=False, blank=False, default=False, help_text="Subscribers can access contents (default is admins only)")


	@property
	def maybe_shortdesc(self):
		if self.shortdesc:
			return self.shortdesc
		return self.listname

	class Meta:
		db_table = 'lists'

class Attachment(models.Model):
	message = models.ForeignKey(Message, null=False, blank=False, db_column='message')
	filename = models.CharField(max_length=1000, null=False, blank=False)
	contenttype = models.CharField(max_length=1000, null=False, blank=False)
	# attachment = bytea, not supported by django at this point

	class Meta:
		db_table = 'attachments'
		# Predictable same-as-insert order
		ordering = ('id',)

	def inlineable(self):
		# Return True if this image should be inlined
		if self.contenttype in ('image/png', 'image/gif', 'image/jpg', 'image/jpeg'):
			# Note! len needs to be set with extra(select=)
			if self.len < 75000:
				return True
		return False


class ListSubscriber(models.Model):
	# Only used when public access is not allowed.
	# We set the username of the community account instead of a
	# foreign key, because the user might not exist.
	list = models.ForeignKey(List, null=False, blank=False)
	username = models.CharField(max_length=30, null=False, blank=False)

	class Meta:
		unique_together = (('list', 'username'), )
		db_table = 'listsubscribers'

class ApiClient(models.Model):
	apikey = models.CharField(max_length=100, null=False, blank=False)
	postback = models.URLField(max_length=500, null=False, blank=False)

	class Meta:
		db_table = 'apiclients'

class ThreadSubscription(models.Model):
	apiclient = models.ForeignKey(ApiClient, null=False, blank=False)
	threadid = models.IntegerField(null=False, blank=False)

	class Meta:
		db_table = 'threadsubscriptions'
		unique_together = (('apiclient', 'threadid'),)
