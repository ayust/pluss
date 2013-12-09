import flask
import requests

from pluss.app import app, full_url_for
from pluss.handlers import oauth2
from pluss.util import dateutils
from pluss.util.cache import Cache
from pluss.util.config import Config
from pluss.util.ratelimit import ratelimited

GPLUS_API_ACTIVITIES_ENDPOINT = 'https://www.googleapis.com/plus/v1/people/%s/activities/public'

ATOM_CACHE_KEY_TEMPLATE = 'pluss--atom--1--%s'

@ratelimited
@app.route('/atom/<gplus_id>')
def user_atom(gplus_id):
    return atom(gplus_id)

@ratelimited
@app.route('/atom/<gplus_id>/<page_id>')
def page_atom(gplus_id, page_id):
    return atom(gplus_id, page_id)

def atom(gplus_id, page_id=None):
    """Return an Atom-format feed for the given G+ id, possibly from cache."""

    if len(gplus_id) != 21:
        return 'Invalid G+ user ID (must be exactly 21 digits).', 404 # Not Found
    if page_id and len(page_id) != 21:
        return 'Invalid G+ page ID (must be exactly 21 digits).', 404 # Not Found

    cache_key = ATOM_CACHE_KEY_TEMPLATE % gplus_id
    if page_id:
        cache_key = '%s-%s' % (cache_key, page_id)

    response = Cache.get(cache_key) # A frozen Response object
    if response is None:
        try:
            response = generate_atom(gplus_id, page_id)
        except oauth2.UnavailableException as e:
            app.logger.warning("Feed request failed - %s", e.message)
            flask.abort(e.status)
        response.freeze()
        Cache.set(cache_key, response, time=Config.get('cache', 'stream-expire'))
    return response

def generate_atom(gplus_id, page_id):
    """Generate an Atom-format feed for the given G+ id."""
    # If no page id specified, use the special value 'me' which refers to the
    # stream for the owner of the OAuth2 token.
    request = requests.Request('POST', GPLUS_API_ACTIVITIES_ENDPOINT % (page_id or 'me'),
        data={'maxResults': 10, 'userIp': flask.request.remote_addr})
    api_response = oauth2.authed_request_for_id(gplus_id, request)
    result = api_response.json()

    if page_id:
        request_url = full_url_for('page_atom', gplus_id=gplus_id, page_id=page_id)
    else:
        request_url = full_url_for('user_atom', gplus_id=gplus_id)

    params = {
        'server_url': full_url_for('main'),
        'feed_id': page_id or gplus_id,
        'request_url': request_url,
    }

    items = result.get(items)
    if not items:
        params['last_update'] = dateutils.to_atom_format(datetime.datetime.today())
        body = flask.render_template('atom/empty.xml', **params)
    else:
        last_update = max(dateutils.from_iso_format(item['updated']) for item in items)
        params['last_update'] = dateutils.to_http_format(last_update)
        params['items'] = process_feed_items(items)
        body = flask.render_template('atom/feed.xml', **params)

    response = flask.make_response(body)
    response.headers['Content-Type'] = 'application/atom+xml'
    return response

def process_feed_items(api_items):
    """Generate a list of items for use in an Atom feed template from an API result."""
    return [process_timeline_item(item) for item in api_items]

def process_feed_item(api_item):
    """Generate a single item for use in an Atom feed template from an API result."""
    # Begin with the fields shared by all feed items.
    item = {
        'id': api_item['id'],
        'permalink':  api_item['url'],
        'published': dateutils.from_iso_format(api_item['published']),
        'updated': dateutils.from_iso_format(api_item['updated']),
        'actor': parse_actor(api_item['actor']),
    }

    # Choose which processor to use for this feed item
    verb_processor = {
        'post': process_post,
        'share': process_share,
        'checkin': process_checkin,
    }.get(api_item['verb'], process_unknown)

    item.update(verb_processor(api_item))
    return item

def process_post(api_item):
    """Process a standard post."""
    html = api_item['content']
    attachments = process_attachments(api_item.get('attachments'))

    if html:
        title = create_title(html)
    elif attachments:
        title = attachments[0]['title']
    else:
        title = 'A G+ Post'

    content = flask.render_template('atom/post.xml', html=html, attachments=attachments)
    return {'content': content, 'title': title}

def process_share(api_item):
    """Process a shared item."""
    raise NotImplementedError

def process_checkin(api_item):
    """Process a Google Places check-in."""
    raise NotImplementedError

def process_unknown(api_item):
    """Process an item of unknown type."""
    raise NotImplementedError

def process_actor(api_actor):
    """Parse an actor definition from an API result."""
    return {
        'id': api_actor.get('id'),
        'name': api_actor.get('displayName'),
        'url': api_actor.get('url'),
        'image_url': api_actor.get('image', {}).get('url'),
    }

# vim: set ts=4 sts=4 sw=4 et:
