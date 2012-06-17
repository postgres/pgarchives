\set ON_ERROR_STOP
BEGIN;

TRUNCATE TABLE list_months;

INSERT INTO list_months(listid, year, month)
SELECT DISTINCT listid, EXTRACT(year FROM date), EXTRACT(month FROM date)
FROM messages INNER JOIN list_threads ON messages.threadid=list_threads.threadid;

COMMIT;
