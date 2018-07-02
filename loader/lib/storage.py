import difflib

from parser import ArchivesParser

from lib.log import log, opstatus

class ArchivesParserStorage(ArchivesParser):
	def __init__(self):
		super(ArchivesParserStorage, self).__init__()
		self.purges = set()

	def purge_list(self, listid, year, month):
		self.purges.add((int(listid), int(year), int(month)))

	def purge_thread(self, threadid):
		self.purges.add(int(threadid))

	def store(self, conn, listid, overwrite=False):
		curs = conn.cursor()

		# Potentially add the information that there exists a mail for
		# this month. We do that this early since we're always going to
		# make the check anyway, and this keeps the code in one place..
		if not overwrite:
			curs.execute("INSERT INTO list_months (listid, year, month) SELECT %(listid)s, %(year)s, %(month)s WHERE NOT EXISTS (SELECT listid FROM list_months WHERE listid=%(listid)s AND year=%(year)s AND month=%(month)s)", {
					'listid': listid,
					'year': self.date.year,
					'month': self.date.month,
					})

		curs.execute("SELECT threadid, EXISTS(SELECT threadid FROM list_threads lt WHERE lt.listid=%(listid)s AND lt.threadid=m.threadid), id FROM messages m WHERE m.messageid=%(messageid)s", {
				'messageid': self.msgid,
				'listid': listid,
				})
		r = curs.fetchall()
		if len(r) > 0:
			# Has to be 1 row, since we have a unique index on id
			if not r[0][1] and not overwrite:
				log.status("Tagging message %s with list %s" % (self.msgid, listid))
				curs.execute("INSERT INTO list_threads (threadid, listid) VALUES (%(threadid)s, %(listid)s)", {
						'threadid': r[0][0],
						'listid': listid,
						})
				opstatus.tagged += 1
				self.purge_list(listid, self.date.year, self.date.month)
				self.purge_thread(r[0][0])
			else:
				opstatus.dupes += 1

			if overwrite:
				pk = r[0][2]
				self.purge_thread(r[0][0])
				# Overwrite an existing message. We do not attempt to
				# "re-thread" a message, we just update the contents. We
				# do remove all attachments and rewrite them. Of course, we
				# don't change the messageid (since it's our primary
				# identifyer), and we don't update the raw text of the message.
				# (since we are expected to have used that raw text to do
				# the re-parsing initially)
				curs.execute("UPDATE messages SET _from=%(from)s, _to=%(to)s, cc=%(cc)s, subject=%(subject)s, date=%(date)s, has_attachment=%(has_attachment)s, bodytxt=%(bodytxt)s WHERE id=%(id)s AND NOT (bodytxt=%(bodytxt)s) RETURNING id", {
						'id': pk,
						'from': self._from,
						'to': self.to or '',
						'cc': self.cc or '',
						'subject': self.subject or '',
						'date': self.date,
						'has_attachment': len(self.attachments) > 0,
						'bodytxt': self.bodytxt,
						})
				if curs.rowcount == 0:
					log.status("Message %s unchanged" % self.msgid)
					return False

				curs.execute("DELETE FROM attachments WHERE message=%(message)s", {
						'message': pk,
						})
				if len(self.attachments):
					curs.executemany("INSERT INTO attachments (message, filename, contenttype, attachment) VALUES (%(message)s, %(filename)s, %(contenttype)s, %(attachment)s)",[ {
								'message': pk,
								'filename': a[0] or 'unknown_filename',
								'contenttype': a[1],
								'attachment': bytearray(a[2]),
								} for a in self.attachments])
				opstatus.overwritten += 1
				log.status("Message %s overwritten" % self.msgid)
			else:
				log.status("Message %s already stored" % self.msgid)
			return True

		if overwrite:
			raise Exception("Attempt to overwrite message that doesn't exist!")
		# Always purge the primary list for this thread
		self.purge_list(listid, self.date.year, self.date.month)

		# Resolve own thread
		curs.execute("SELECT id, messageid, threadid FROM messages WHERE messageid=ANY(%(parents)s)", {
				'parents': self.parents,
				})
		all_parents = curs.fetchall()
		if len(all_parents):
			# At least one of the parents exist. Now try to figure out which one
			best_parent = len(self.parents)+1
			best_threadid = -1
			best_parentid = None
			for i in range(0,len(all_parents)):
				for j in range(0,len(self.parents)):
					if self.parents[j] == all_parents[i][1]:
						# This messageid found. Better than the last one?
						if j < best_parent:
							best_parent = j
							best_parentid = all_parents[i][0]
							best_threadid = all_parents[i][2]
			if best_threadid == -1:
				raise Exception("Message %s, resolve failed in a way it shouldn't :P" % selg.msgid)
			self.parentid = best_parentid
			self.threadid = best_threadid
			# Slice away all matches that are worse than the one we wanted
			self.parents = self.parents[:best_parent]

			log.status("Message %s resolved to existing thread %s, waiting for %s better messages" % (self.msgid, self.threadid, len(self.parents)))
		else:
			# No parent exist. But don't create the threadid just yet, since
			# it's possible that we're somebody elses parent!
			self.parentid = None
			self.threadid = None

		# Now see if we are somebody elses *parent*...
		curs.execute("SELECT message, priority, threadid FROM unresolved_messages INNER JOIN messages ON messages.id=unresolved_messages.message WHERE unresolved_messages.msgid=%(msgid)s ORDER BY threadid", {
				'msgid': self.msgid,
				})
		childrows = curs.fetchall()
		if len(childrows):
			# We are some already existing message's parent (meaning the
			# messages arrived out of order)
			# In the best case, the threadid is the same for all threads.
			# But it might be different if this it the "glue message" that's
			# holding other threads together.
			if self.threadid:
				# Already have a threadid, means that we have a glue message
				print "Message %s resolved to existing thread %s, while being somebodys parent" % (self.msgid, self.threadid)
			else:
				print "Message %s did not resolve to existing thread, but is somebodys parent" % self.msgid
				# In this case, just pick the first thread from the list and merge into that
				# one.
				self.threadid = childrows[0][2]

			# Get a unique list (set) of all threads *except* the primary one,
			# because we'll be merging into that one.
			mergethreads = set([r[2] for r in childrows]).difference(set((self.threadid,)))
			if len(mergethreads):
				# We have one or more merge threads
				log.status("Merging threads %s into thread %s" % (",".join(str(s) for s in mergethreads), self.threadid))
				curs.execute("UPDATE messages SET threadid=%(threadid)s WHERE threadid=ANY(%(oldthreadids)s)", {
						'threadid': self.threadid,
						'oldthreadids': list(mergethreads),
						})
				# Insert any lists that were tagged on the merged threads
				curs.execute("INSERT INTO list_threads (threadid, listid) SELECT DISTINCT %(threadid)s,listid FROM list_threads lt2 WHERE lt2.threadid=ANY(%(oldthreadids)s) AND listid NOT IN (SELECT listid FROM list_threads lt3 WHERE lt3.threadid=%(threadid)s)", {
						'threadid': self.threadid,
						'oldthreadids': list(mergethreads),
						})
				# Remove all old leftovers
				curs.execute("DELETE FROM list_threads WHERE threadid=ANY(%(oldthreadids)s)", {
						'oldthreadids': list(mergethreads),
						})
				# Purge varnish records for all the threads we just removed
				for t in mergethreads:
					self.purge_thread(t)

			# Batch all the children for repointing. We can't do the actual
			# repointing until later, since we don't know our own id yet.
			self.children = [r[0] for r in childrows]
			log.status("Children set to %s with mergethreads being %s (from childrows %s and threadid %s)" % (
					self.children, mergethreads, childrows, self.threadid))

			# Finally, remove all the pending messages that had a higher
			# priority value (meaning less important) than us
			curs.executemany("DELETE FROM unresolved_messages WHERE message=%(msg)s AND priority >= %(prio)s", [{
						'msg': msg,
						'prio': prio,
						} for msg, prio, tid in childrows])
		else:
			self.children = []

		if not self.threadid:
			# No parent and no child exists - create a new threadid, just for us!
			curs.execute("SELECT nextval('threadid_seq')")
			self.threadid = curs.fetchall()[0][0]
			log.status("Message %s resolved to no parent (out of %s) and no child, new thread %s" % (self.msgid, len(self.parents), self.threadid))
		else:
			# We have a threadid already, so we're not a new thread. Thus,
			# we need to purge the old thread
			self.purge_thread(self.threadid)

		# Insert a thread tag if we're on a new list
		curs.execute("INSERT INTO list_threads (threadid, listid) SELECT %(threadid)s, %(listid)s WHERE NOT EXISTS (SELECT * FROM list_threads t2 WHERE t2.threadid=%(threadid)s AND t2.listid=%(listid)s) RETURNING threadid", {
			'threadid': self.threadid,
			'listid': listid,
			})
		if len(curs.fetchall()):
			log.status("Tagged thread %s with listid %s" % (self.threadid, listid))

		curs.execute("INSERT INTO messages (parentid, threadid, _from, _to, cc, subject, date, has_attachment, messageid, bodytxt, rawtxt) VALUES (%(parentid)s, %(threadid)s, %(from)s, %(to)s, %(cc)s, %(subject)s, %(date)s, %(has_attachment)s, %(messageid)s, %(bodytxt)s, %(rawtxt)s) RETURNING id", {
				'parentid': self.parentid,
				'threadid': self.threadid,
				'from': self._from,
				'to': self.to or '',
				'cc': self.cc or '',
				'subject': self.subject or '',
				'date': self.date,
				'has_attachment': len(self.attachments) > 0,
				'messageid': self.msgid,
				'bodytxt': self.bodytxt,
				'rawtxt': bytearray(self.rawtxt),
				})
		id = curs.fetchall()[0][0]
		log.status("Message %s, got id %s, set thread %s, parent %s" % (
				self.msgid, id, self.threadid, self.parentid))
		if len(self.attachments):
			# Insert attachments
			curs.executemany("INSERT INTO attachments (message, filename, contenttype, attachment) VALUES (%(message)s, %(filename)s, %(contenttype)s, %(attachment)s)",[ {
						'message': id,
						'filename': a[0] or 'unknown_filename',
						'contenttype': a[1],
						'attachment': bytearray(a[2]),
						} for a in self.attachments])

		if len(self.children):
			log.status("Setting %s other messages to children of %s" % (len(self.children), self.msgid))
			curs.executemany("UPDATE messages SET parentid=%(parent)s WHERE id=%(id)s",
							 [{'parent': id, 'id': c} for c in self.children])
		if len(self.parents):
			# There are remaining parents we'd rather have to get ourselves
			# properly threaded - so store them in the db.
			curs.executemany("INSERT INTO unresolved_messages (message, priority, msgid) VALUES (%(id)s, %(priority)s, %(msgid)s)",
							 [{'id': id, 'priority': i, 'msgid': self.parents[i]} for i in range(0, len(self.parents))])

		opstatus.stored += 1
		return True

	def diff(self, conn, f, fromonlyf, oldid):
		curs = conn.cursor()

		# Fetch the old one so we have something to diff against
		curs.execute("SELECT id, _from, _to, cc, subject, date, has_attachment, bodytxt FROM messages WHERE messageid=%(msgid)s", {
			'msgid': self.msgid,
			})
		try:
			id, _from, _to, cc, subject, date, has_attachment, bodytxt = curs.fetchone()
		except TypeError, e:
			f.write("---- %s ----\n" % self.msgid)
			f.write("Could not re-find in archives (old id was %s): %s\n" % (oldid, e))
			f.write("\n-------------------------------\n\n")
			return


		if bodytxt.decode('utf8') != self.bodytxt:
			log.status("Message %s has changes " % self.msgid)
			tempdiff = list(difflib.unified_diff(bodytxt.decode('utf8').splitlines(),
												 self.bodytxt.splitlines(),
												 fromfile='old',
												 tofile='new',
												 n=0,
												 lineterm=''))
			if (len(tempdiff)-2) % 3 == 0:
				# 3 rows to a diff, two header rows.
				# Then verify that each slice of 3 contains one @@ row (header), one -From and one +>From,
				# which indicates the only change is in the From.
				ok = True
				for a,b,c in map(None, *([iter(tempdiff[2:])] * 3)):
					if not (a.startswith('@@ ') and b.startswith('-From ') and c.startswith('+>From ')):
						ok=False
						break
				if ok:
					fromonlyf.write("%s\n" % self.msgid)
					return


			# Generate a nicer diff
			d = list(difflib.unified_diff(bodytxt.decode('utf8').splitlines(),
												   self.bodytxt.splitlines(),
												   fromfile='old',
												   tofile='new',
												   n=0,
												   lineterm=''))
			if len(d) > 0:
				f.write("---- %s ----\n" % self.msgid)
				f.write("\n".join(d))
				f.write("\n\n")
		else:
			log.status("Message %s unchanged." % self.msgid)
