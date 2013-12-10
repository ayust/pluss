import datetime
import urllib
import pprint

import flask
import requests

from pluss.app import app, full_url_for
from pluss.util.cache import Cache
from pluss.util.config import Config
from pluss.util.db import TokenIdMapping

GOOGLE_API_TIMEOUT = 5

OAUTH2_BASE = 'https://accounts.google.com/o/oauth2'
OAUTH2_SCOPE = 'https://www.googleapis.com/auth/plus.me'

GPLUS_API_ME_ENDPOINT = 'https://www.googleapis.com/plus/v1/people/me'

ACCESS_TOKEN_CACHE_KEY_TEMPLATE = 'pluss--gplusid--oauth--1--%s'
PROFILE_CACHE_KEY_TEMPLATE = 'pluss--gplusid--profile--1--%s'

# Shared session to allow persistent connection pooling
session = requests.Session()

@app.route("/auth")
def auth():
    """Redirect the user to Google to obtain authorization."""
    data = {
        # Basic OAuth2 parameters
        'client_id': Config.get('oauth', 'client-id'),
        'redirect_uri': full_url_for('oauth2'),
        'scope': OAUTH2_SCOPE,
        'response_type': 'code',

        # Settings necessary for daemon operation
        'access_type': 'offline',
        'approval_prompt': 'force',
    }
    return flask.redirect('%s/auth?%s' % (OAUTH2_BASE, urllib.urlencode(data)))

@app.route("/access_denied")
def denied():
    return flask.render_template('denied_main.html')

@app.route("/oauth2callback")
def oauth2():
    """Google redirects the user back to this endpoint to continue the OAuth2 flow."""

    # Check for errors from the OAuth2 process
    err = flask.request.args.get('error')
    if err == 'access_denied':
        return flask.redirect(url_for('denied'))
    elif err is not None:
        app.logger.warning("OAuth2 callback received error: %s", err)
        # TODO: handle this better (flash message?)
        message = 'Whoops, something went wrong (error=%s). Please try again later.'
        return message % flask.escape(err), 500

    # Okay, no errors, so we should have a valid authorization code.
    # Time to go get our server-side tokens for this user from Google.
    auth_code = flask.request.args['code']
    if auth_code is None:
        return 'Authorization code is missing.', 400 # Bad Request

    data =  {
        'code': auth_code,
        'client_id': Config.get('oauth', 'client-id'),
        'client_secret': Config.get('oauth', 'client-secret'),
        'redirect_uri': full_url_for('oauth2'),
        'grant_type': 'authorization_code',
    }
    try:
        response = session.post(OAUTH2_BASE + '/token', data, timeout=GOOGLE_API_TIMEOUT)
    except requests.exceptions.Timeout:
        app.logger.error('OAuth2 token request timed out.')
        # TODO: handle this better (flash message?)
        message = 'Whoops, Google took too long to respond. Please try again later.'
        return message, 504 # Gateway Timeout

    if response.status_code != 200:
        app.logger.error('OAuth2 token request got HTTP response %s for code "%s".',
            response.status_code, auth_code)
        # TODO: handle this better (flash message?)
        message = ('Whoops, we failed to finish processing your authorization with Google.'
                   ' Please try again later.')
        return message, 401 # Unauthorized

    try:
        result = response.json()
    except ValueError:
        app.logger.error('OAuth2 token request got non-JSON response for code "%s".', auth_code)
        # TODO: handle this better (flash message?)
        message = ('Whoops, we got an invalid response from Google for your authorization.'
                   ' Please try again later.')
        return message, 502 # Bad Gateway

    # Sanity check: we always expect Bearer tokens.
    if result.get('token_type') != 'Bearer':
        app.logger.error('OAuth2 token request got unknown token type "%s" for code "%s".',
            result['token_type'], auth_code)
        # TODO: handle this better (flash message?)
        message = ('Whoops, we got an invalid response from Google for your authorization.'
                   ' Please try again later.')
        return message, 502 # Bad Gateway

    # All non-error responses should have an access token.
    access_token = result['access_token']
    refresh_token = result.get('refresh_token')

    # This is in seconds, but we convert it to an absolute timestamp so that we can
    # account for the potential delay it takes to look up the G+ id we should associate
    # the access tokens with. (Could be up to GOOGLE_API_TIMEOUT seconds later.)
    expiry = datetime.datetime.today() + datetime.timedelta(seconds=result['expires_in'])

    try:
        person = get_person_by_access_token(access_token)
    except UnavailableException as e:
        app.logger.error('Unable to finish OAuth2 flow: %r.' % e)
        message = ('Whoops, we got an invalid response from Google for your authorization.'
                   ' Please try again later.')
        return message, 502 # Bad Gateway

    if refresh_token is not None:
        TokenIdMapping.update_refresh_token(person['id'], refresh_token)

    # Convert the absolute expiry timestamp back into a duration in seconds
    expires_in = int((expiry - datetime.datetime.today()).total_seconds())
    Cache.set(ACCESS_TOKEN_CACHE_KEY_TEMPLATE % person['id'], access_token, time=expires_in)

    # Whew, all done! Set a cookie with the user's G+ id and send them back to the homepage.
    app.logger.info("Successfully authenticated G+ id %s.", person['id'])
    response = flask.make_response(flask.redirect(flask.url_for('main')))
    response.set_cookie('gplus_id', person['id'])
    return response

################################################################################
# HELPER FUNCTIONS
################################################################################

# Exception raised by any of the following if they are unable to acquire a result.
class UnavailableException(Exception):
    def __init__(self, message, status, *args, **kwargs):
        super(UnavailableException, self).__init__(message, status, *args, **kwargs)
        self.status = status

def get_person_by_access_token(token):
    """Fetch details about an individual from the G+ API and return a dict with the response."""
    headers = {
        'Authorization': 'Bearer %s' % token,
    }
    try:
        response = session.get(GPLUS_API_ME_ENDPOINT, headers=headers, timeout=GOOGLE_API_TIMEOUT)
        person = response.json()
    except requests.exceptions.Timeout:
        raise UnavailableException('Person API request timed out.', 504)
    except Exception as e:
        raise UnavailableException('Person API request raised exception "%r" for %s.' % (e, pprint.pformat(response).text), 502)

    Cache.set(PROFILE_CACHE_KEY_TEMPLATE % person['id'], person,
        time=Config.getint('cache', 'profile-expire'))
    return person

def get_person_by_id(gplus_id):
    """A proxy for fetch_person_by_access_token that resolves an id into an access token first."""
    # Check the cache first.
    person = Cache.get(PROFILE_CACHE_KEY_TEMPLATE % gplus_id)
    if person:
        return person

    # If we don't have them cached, try to get an access token.
    access_token = get_access_token_for_id(gplus_id)
    return get_person_by_token(access_token)

def get_access_token_for_id(gplus_id):
    """Get an access token for an id, potentially via refresh token if necessary."""
    # Check the cache first.
    token = Cache.get(ACCESS_TOKEN_CACHE_KEY_TEMPLATE % gplus_id)
    if token:
        return token

    # If we don't have a cached token, see if we have a refresh token available.
    refresh_token = TokenIdMapping.lookup_refresh_token(gplus_id)
    if not refresh_token:
        raise UnavailableException('No tokens available for G+ id %s.' % gplus_id, 401)

    data = {
        'client_id': Config.get('oauth', 'client-id'),
        'client_secret': Config.get('oauth', 'client-secret'),
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }
    try:
        response = session.post(OAUTH2_BASE + '/token', data=data, timeout=GOOGLE_API_TIMEOUT)
        result = response.json()
    except requests.exceptions.Timeout:
        raise UnavailableException('Access token API request timed out.', 504)
    except Exception as e:
        raise UnavailableException('Access token API request raised exception "%r".' % e, 502)

    if 'invalid_grant' in result:
        # The provided refresh token is invalid which means the user has revoked
        # access to their content - thus, pluss should forget about them.
        Cache.delete(ACCESS_TOKEN_CACHE_KEY_TEMPLATE % gplus_id)
        Cache.delete(PROFILE_CACHE_KEY_TEMPLATE % gplus_id)
        TokenIdMapping.remove_id(gplus_id)
        raise UnvailableException('Access revoked for G+ id %s.' % gplus_id)
    elif response.status_code != 200:
        app.logging.error('Non-200 response to access token refresh request (%s): "%r".',
            response.status_code, result)
        raise UnavailableException('Failed to refresh access token for G+ id %s.' % gplus_id, 502)
    elif result.get('token_type') != 'Bearer':
        app.logging.error('Unknown token type "%s" refreshed for G+ id %s.', result.get('token_type'), gplus_id)
        raise UnavailableException('Failed to refresh access token for G+ id %s.' % gplus_id, 502)

    token = result['access_token']
    Cache.set(ACCESS_TOKEN_CACHE_KEY_TEMPLATE % gplus_id, token, time=result['expires_in'])
    return token

def authed_request_for_id(gplus_id, request):
    """Adds the proper access credentials for the specified user and then makes an HTTP request."""

    # Helper method to make retry easier
    def make_request(retry=True):
        token = get_access_token_for_id(gplus_id)
        request.headers['Authorization'] = 'Bearer %s' % token
        prepared_request = request.prepare()
        response = session.send(prepared_request, timeout=GOOGLE_API_TIMEOUT)
        if response.status_code == 401:
            # Our access token is invalid. If this is the first failure,
            # try forcing a refresh of the access token.
            if retry:
                Cache.delete(ACCESS_TOKEN_CACHE_KEY_TEMPLATE % gplus_id)
                return make_request(retry=False)
        return response

    response = make_request()

    if response.status_code == 403:
        # Typically used to indicate that Google is rate-limiting the API call
        raise UnavailableException('API 403 response: %r' % api_response.json(), 503)
    elif response.status_code == 401:
        raise UnavailableException('Invalid access token.', 401)
    elif response.status_code != 200:
        raise UnavailableException(
            'Unknown API error (code=%d): %r' % (response.status_code, response.json()), 502)

    return response

# vim: set ts=4 sts=4 sw=4 et:
