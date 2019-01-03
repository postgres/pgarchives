from django.http import HttpResponse
from django.db import connection
from django.utils.functional import SimpleLazyObject


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


def _get_gitrev():
    # Return the current git revision, that is used for
    # cache-busting URLs.
    try:
        with open('../.git/refs/heads/master') as f:
            return f.readline()[:8]
    except IOError:
        # A "git gc" will remove the ref and replace it with a packed-refs.
        try:
            with open('../.git/packed-refs') as f:
                for l in f.readlines():
                    if l.endswith("refs/heads/master\n"):
                        return l[:8]
                # Not found in packed-refs. Meh, just make one up.
                return 'ffffffff'
        except IOError:
            # If packed-refs also can't be read, just give up
            return 'eeeeeeee'


# Template context processor to add information about the root link and
# the current git revision. git revision is returned as a lazy object so
# we don't spend effort trying to load it if we don't need it (though
# all general pages will need it since it's used to render the css urls)
def PGWebContextProcessor(request):
    gitrev = SimpleLazyObject(_get_gitrev)
    return {
        'gitrev': gitrev,
    }
