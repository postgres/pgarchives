\set ON_ERROR_STOP on

CREATE TABLE messages (
   id SERIAL NOT NULL PRIMARY KEY,
   parentid int REFERENCES messages,
   threadid int NOT NULL,
   _from text NOT NULL,
   _to text NOT NULL,
   cc text NOT NULL,
   subject text NOT NULL,
   date timestamptz NOT NULL,
   has_attachment boolean NOT NULL,
   messageid text NOT NULL,
   bodytxt text NOT NULL
);
CREATE INDEX idx_messages_threadid ON messages(threadid);
CREATE UNIQUE INDEX idx_messages_msgid ON messages(messageid);

CREATE SEQUENCE threadid_seq;

CREATE TABLE unresolved_messages(
   message int NOT NULL REFERENCES messages,
   priority int NOT NULL,
   msgid text NOT NULL,
   CONSTRAINT unresolved_messages_pkey PRIMARY KEY (message, priority)
);

CREATE UNIQUE INDEX idx_unresolved_msgid_message ON unresolved_messages(msgid, message);


CREATE TABLE lists(
   listid int NOT NULL PRIMARY KEY,
   listname text NOT NULL UNIQUE
);

CREATE TABLE list_months(
   listid int NOT NULL REFERENCES lists(listid),
   year int NOT NULL,
   month int NOT NULL,
   CONSTRAINT list_months_pk PRIMARY KEY (listid, year, month)
);

CREATE TABLE list_threads(
   threadid int NOT NULL, /* comes from threadid_seq */
   listid int NOT NULL REFERENCES lists(listid),
   CONSTRAINT pg_list_threads PRIMARY KEY (threadid, listid)
);

CREATE TABLE attachments(
   id serial not null primary key,
   message int not null references messages(id),
   filename text not null,
   contenttype text not null,
   attachment bytea not null
);
CREATE INDEX idx_attachments_msg ON attachments(message);
