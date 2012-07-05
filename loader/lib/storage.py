from parser import ArchivesParser

from lib.log import log, opstatus

class ArchivesParserStorage(ArchivesParser):
	def __init__(self):
		super(ArchivesParserStorage, self).__init__()

	def store(self, conn, listid):
		curs = conn.cursor()

		# Potentially add the information that there exists a mail for
		# this month. We do that this early since we're always going to
		# make the check anyway, and this keeps the code in one place..
		curs.execute("INSERT INTO list_months (listid, year, month) SELECT %(listid)s, %(year)s, %(month)s WHERE NOT EXISTS (SELECT listid FROM list_months WHERE listid=%(listid)s AND year=%(year)s AND month=%(month)s)", {
						'listid': listid,
						'year': self.date.year,
						'month': self.date.month,
						})

		curs.execute("SELECT threadid, EXISTS(SELECT threadid FROM list_threads lt WHERE lt.listid=%(listid)s AND lt.threadid=m.threadid) FROM messages m WHERE m.messageid=%(messageid)s", {
				'messageid': self.msgid,
				'listid': listid,
				})
		r = curs.fetchall()
		if len(r) > 0:
			# Has to be 1 row, since we have a unique index on id
			if not r[0][1]:
				log.status("Tagging message %s with list %s" % (self.msgid, listid))
				curs.execute("INSERT INTO list_threads (threadid, listid) VALUES (%(threadid)s, %(listid)s)", {
						'threadid': r[0][0],
						'listid': listid,
						})
				opstatus.tagged += 1
			else:
				opstatus.dupes += 1

			#FIXME: option to overwrite existing message!
			log.status("Message %s already stored" % self.msgid)
			return

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

			# Batch all the children for repointing. We can't do the actual
			# repointing until later, since we don't know our own id yet.
			self.children = [r[0] for r in childrows]

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

		# Insert a thread tag if we're on a new list
		curs.execute("INSERT INTO list_threads (threadid, listid) SELECT %(threadid)s, %(listid)s WHERE NOT EXISTS (SELECT * FROM list_threads t2 WHERE t2.threadid=%(threadid)s AND t2.listid=%(listid)s) RETURNING threadid", {
			'threadid': self.threadid,
			'listid': listid,
			})
		if len(curs.fetchall()):
			log.status("Tagged thread %s with listid %s" % (self.threadid, listid))

		curs.execute("INSERT INTO messages (parentid, threadid, _from, _to, cc, subject, date, has_attachment, messageid, bodytxt) VALUES (%(parentid)s, %(threadid)s, %(from)s, %(to)s, %(cc)s, %(subject)s, %(date)s, %(has_attachment)s, %(messageid)s, %(bodytxt)s) RETURNING id", {
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
				})
		id = curs.fetchall()[0][0]
		if len(self.attachments):
			# Insert attachments
			curs.executemany("INSERT INTO attachments (message, filename, contenttype, attachment) VALUES (%(message)s, %(filename)s, %(contenttype)s, %(attachment)s)",[ {
						'message': id,
						'filename': a[0] or 'unknown_filename',
						'contenttype': a[1],
						'attachment': bytearray(a[2]),
						} for a in self.attachments])

		if len(self.children):
			log.status("Setting %s other threads to children of %s" % (len(self.children), self.msgid))
			curs.executemany("UPDATE messages SET parentid=%(parent)s WHERE id=%(id)s",
							 [{'parent': id, 'id': c} for c in self.children])
		if len(self.parents):
			# There are remaining parents we'd rather have to get ourselves
			# properly threaded - so store them in the db.
			curs.executemany("INSERT INTO unresolved_messages (message, priority, msgid) VALUES (%(id)s, %(priority)s, %(msgid)s)",
							 [{'id': id, 'priority': i, 'msgid': self.parents[i]} for i in range(0, len(self.parents))])

		opstatus.stored += 1
