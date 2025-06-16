\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE messages (
   id SERIAL NOT NULL PRIMARY KEY,
   parentid int REFERENCES messages,
   threadid int NOT NULL,
   _from text NOT NULL,
   _to text NOT NULL,
   cc text NOT NULL,
   subject text NOT NULL,
   date timestamptz NOT NULL,
   loaddate timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
   has_attachment boolean NOT NULL,
   hiddenstatus int NULL,
   messageid text NOT NULL,
   bodytxt text NOT NULL,
   rawtxt bytea NOT NULL,
   fti tsvector NOT NULL
);
CREATE INDEX idx_messages_threadid ON messages(threadid);
CREATE UNIQUE INDEX idx_messages_msgid ON messages(messageid);
CREATE INDEX idx_messages_date ON messages(date);
CREATE INDEX idx_messages_parentid ON messages(parentid);

CREATE TABLE message_hide_reasons (
   message int NOT NULL PRIMARY KEY REFERENCES messages,
   dt timestamptz,
   reason text,
   by text
);

CREATE SEQUENCE threadid_seq;

CREATE TABLE unresolved_messages(
   message int NOT NULL REFERENCES messages,
   priority int NOT NULL,
   msgid text NOT NULL,
   CONSTRAINT unresolved_messages_pkey PRIMARY KEY (message, priority)
);

CREATE UNIQUE INDEX idx_unresolved_msgid_message ON unresolved_messages(msgid, message);

CREATE TABLE listgroups(
   groupid int NOT NULL PRIMARY KEY,
   groupname text NOT NULL UNIQUE,
   sortkey int NOT NULL
);

CREATE TABLE lists(
   listid int NOT NULL PRIMARY KEY,
   listname text NOT NULL UNIQUE,
   shortdesc text NOT NULL,
   description text NOT NULL,
   active boolean NOT NULL,
   subscriber_access boolean NOT NULL,
   groupid int NOT NULL REFERENCES listgroups(groupid)
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
CREATE INDEX list_threads_listid_idx ON list_threads(listid);

CREATE TABLE attachments(
   id serial not null primary key,
   message int not null references messages(id),
   filename text not null,
   contenttype text not null,
   attachment bytea not null
);
CREATE INDEX idx_attachments_msg ON attachments(message);

CREATE TABLE loaderrors(
   id SERIAL NOT NULL PRIMARY KEY,
   listid int NOT NULL,
   dat timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
   msgid text NOT NULL,
   srctype text NOT NULL,
   src text NOT NULL,
   err text NOT NULL
);

/* textsearch configs */
CREATE TEXT SEARCH CONFIGURATION pg (PARSER=tsparser);

CREATE TEXT SEARCH DICTIONARY english_ispell (
   TEMPLATE = ispell,
   DictFile = en_us,
   AffFile = en_us,
   StopWords = english
);
CREATE TEXT SEARCH DICTIONARY pg_dict (
   TEMPLATE = synonym,
   SYNONYMS = pg_dict
);
CREATE TEXT SEARCH DICTIONARY pg_stop (
   TEMPLATE = simple,
   StopWords = pg_dict
);
ALTER TEXT SEARCH CONFIGURATION pg
   ALTER MAPPING FOR asciiword, asciihword, hword_asciipart,
                     word, hword, hword_part
    WITH pg_stop, pg_dict, english_ispell, english_stem;
ALTER TEXT SEARCH CONFIGURATION pg
   DROP MAPPING FOR email, url, url_path, sfloat, float;

CREATE FUNCTION messages_fti_trigger_func() RETURNS trigger AS $$
BEGIN
   NEW.fti = setweight(to_tsvector('public.pg', coalesce(new.subject, '')), 'A') ||
             setweight(to_tsvector('public.pg', coalesce(new.bodytxt, '')), 'D');
   RETURN NEW;
END
$$ LANGUAGE 'plpgsql';

CREATE TRIGGER messages_fti_trigger
 BEFORE INSERT OR UPDATE OF subject, bodytxt ON  messages
 FOR EACH ROW EXECUTE PROCEDURE messages_fti_trigger_func();
CREATE INDEX messages_fti_idx ON messages USING gin(fti);

CREATE TABLE legacymap(
       listid int not null,
       year int not null,
       month int not null,
       msgnum int not null,
       msgid text not null,
CONSTRAINT legacymap_pk PRIMARY KEY (listid, year, month, msgnum)
);

/* Simple API for hiding messages */
CREATE OR REPLACE FUNCTION hide_message(msgid_txt text, reason_code integer, user_txt text, reason_txt text)
  RETURNS integer AS
$BODY$
DECLARE
    returned_id integer;
BEGIN
    UPDATE messages SET hiddenstatus = reason_code WHERE messageid = msgid_txt RETURNING id INTO returned_id;

    IF NOT FOUND THEN
	RAISE EXCEPTION 'The specified message (%) could not be found.', msgid_txt;
    END IF;

    INSERT INTO message_hide_reasons (message, dt, reason, by) VALUES (returned_id, now(), reason_txt, user_txt);

    RETURN returned_id;
END;
$BODY$
  LANGUAGE plpgsql VOLATILE
  COST 100;

\echo Dont forget to commit!
