ALTER TABLE messages ADD COLUMN rawtxt bytea;
ALTER TABLE messages ADD COLUMN fti tsvector;

CREATE TRIGGER messages_fti_trigger
 BEFORE INSERT OR UPDATE OF subject, bodytxt ON  messages
 FOR EACH ROW EXECUTE PROCEDURE tsvector_update_trigger(fti, 'pg_catalog.english', subject, bodytxt);
CREATE INDEX messages_fti_idx ON messages USING gin(fti);
