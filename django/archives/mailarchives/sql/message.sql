CREATE TEXT SEARCH CONFIGURATION pg (COPY = pg_catalog.english );

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

ALTER TABLE messages ADD COLUMN rawtxt bytea;
ALTER TABLE messages ADD COLUMN fti tsvector;

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
