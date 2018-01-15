from django.http import HttpResponse
from django.db import connection

def validate_new_user(username, email, firstname, lastname):
	# Only allow user creation if they are already a subscriber
	curs = connection.cursor()
	curs.execute("SELECT EXISTS(SELECT 1 FROM listsubscribers WHERE username=%(username)s)", {
		'username': username,
	})
	if curs.fetchone()[0]:
		# User is subscribed to something, so allow creation
		return None

	return HttpResponse("You are not currently subscribed to any mailing list on this server. Account not created.")

