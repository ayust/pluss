import flask

from pluss.app import app, full_url_for
from pluss.util.config import Config
from pluss.util.db import TokenIdMapping

@app.route("/")
def main():
    """Display the homepage."""
    gplus_id = flask.request.cookies.get('gplus_id')
    if gplus_id:
        # If we lost rights, but someone still has the cookie, get rid of it.
        if not TokenIdMapping.lookup_refresh_token(gplus_id):
            return flask.redirect(flask.url_for('clear'))
        # Display a page indicating the user's feed URL, since they've authed.
        return flask.render_template('authed_main.html', gplus_id=gplus_id,
            feed_url=full_url(flask.url_for('atom', gplus_id=gplus_id)))
    else:
        return flask.render_template('main.html')

@app.route("/clear")
def clear():
    """Clear cookies, then redirect to the homepage."""
    response = flask.make_response(flask.redirect(flask.url_for('main')))
    response.set_cookie('gplus_id', '', expires=0)
    return response

@app.route("/privacy")
def privacy():
    """Display the privacy policy."""
    return flask.render_template('privacy.html')


# vim: set ts=4 sts=4 sw=4 et:
