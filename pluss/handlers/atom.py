import re

import flask
import jinja2
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
    """Display an Atom-format feed for a user id."""
    return atom(gplus_id)

@ratelimited
@app.route('/atom/<gplus_id>/<page_id>')
def page_atom(gplus_id, page_id):
    """Display an Atom-format feed for a page, using a user's key."""
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
        Cache.set(cache_key, response, time=Config.getint('cache', 'stream-expire'))
    return response

def generate_atom(gplus_id, page_id):
    """Generate an Atom-format feed for the given G+ id."""
    # If no page id specified, use the special value 'me' which refers to the
    # stream for the owner of the OAuth2 token.
    request = requests.Request('GET', GPLUS_API_ACTIVITIES_ENDPOINT % (page_id or 'me'),
        params={'maxResults': 10, 'userIp': flask.request.remote_addr})
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

    items = result.get('items')
    if not items:
        params['last_update'] = dateutils.to_atom_format(datetime.datetime.today())
        body = flask.render_template('atom/empty.xml', **params)
    else:
        last_update = max(dateutils.from_iso_format(item['updated']) for item in items)
        params['last_update'] = last_update
        params['items'] = process_feed_items(items)
        params['actor'] = params['items'][0]['actor']
        params['to_atom_date'] = dateutils.to_atom_format
        body = flask.render_template('atom/feed.xml', **params)

    response = flask.make_response(body)
    response.headers['Content-Type'] = 'application/atom+xml'
    return response

def process_feed_items(api_items):
    """Generate a list of items for use in an Atom feed template from an API result."""
    return [process_feed_item(item) for item in api_items]

def process_feed_item(api_item):
    """Generate a single item for use in an Atom feed template from an API result."""
    # Begin with the fields shared by all feed items.
    item = {
        'id': api_item['id'],
        'permalink':  api_item['url'],
        'published': dateutils.from_iso_format(api_item['published']),
        'updated': dateutils.from_iso_format(api_item['updated']),
        'actor': process_actor(api_item['actor']),
    }

    # Choose which processor to use for this feed item
    verb_processor = {
        'post': process_post,
        'share': process_share,
        'checkin': process_checkin,
    }.get(api_item['verb'], process_unknown)

    item.update(verb_processor(api_item))
    return item

def process_post(api_item, nested=False):
    """Process a standard post."""
    obj = api_item['object']
    html = obj.get('content')
    attachments = process_attachments(obj.get('attachments'))

    # Normally, create the title from the post text
    title = create_title(html)
    # If that doesn't work, fall back to the first attachment's title
    if not title and attachments:
        title = attachments[0]['title']
    # If that also doesn't work, use a default title
    if not title:
        title = 'A G+ Post'

    content = flask.render_template('atom/post.html', html=html, attachments=attachments)
    result = {
        'content': content,
        'title': title,
    }
    if nested:
        # These extra fields are only used in nested calls (e.g. shares)
        result['actor'] = process_actor(obj.get('actor'))
        result['url'] = obj.get('url')
    return result

def process_share(api_item):
    """Process a shared item."""
    html = api_item.get('annotation')
    original = process_post(api_item, nested=True)

    # Normally, create the title from the resharer's note
    # If that doesn't work, fall back to the shared item's title
    title = create_title(html) or original['title']
    content = flask.render_template('atom/share.html', html=html, original=original)
    return {
        'content': content,
        'title': title,
    }

def process_checkin(api_item):
    """Process a check-in."""
    actor = process_actor(api_item.get('actor'))
    original = process_post(api_item, nested=True)

    content = flask.render_template('atom/checkin.html', actor=actor, original=original)
    return {
        'content': content,
        'title': original['title'],
    }

def process_unknown(api_item):
    """Process an item of unknown type."""
    # Try parsing it as a regular post
    original = process_post(api_item)
    if original['content']:
        return original

    # If that fails, just use a link to the post.
    content = '<a href="%(url)s">%(url)s</a>' % {'url': api_item.get('url')}
    return {
        'content': content,
        'title': 'A G+ Activity',
    }

def process_actor(api_actor):
    """Parse an actor definition from an API result."""
    api_actor = api_actor or {}
    return {
        'id': api_actor.get('id'),
        'name': api_actor.get('displayName'),
        'url': api_actor.get('url'),
        'image_url': api_actor.get('image', {}).get('url'),
    }

def process_attachments(attachments):
    """Parse a list of attachments from an API result."""
    results = []
    attachments = attachments or []
    type_processors = {
        'article': process_attached_article,
        'photo': process_attached_photo,
        'album': process_attached_album,
        'video': process_attached_video,
        'event': process_attached_event,
    }
    for attachment in attachments:
        item_type = attachment.get('objectType')
        processor = type_processors.get(item_type)
        if processor:
            results.append(processor(attachment))
        else:
            descriptor = '[attachment with unsupported type "%s"]' % item_type
            results.append({
                'html': descriptor,
                'title': descriptor,
            })
    return results

def process_attached_article(attachment):
    """Parse an attached article."""
    title = attachment.get('displayName') or attachment.get('url')
    html = flask.render_template('atom/article.html', article=attachment, title=title)
    return {
        'html': html,
        'title': title,
    }

def process_attached_photo(attachment):
    """Process an attached individual photo."""
    title = attachment['image'].get('displayName')
    html = flask.render_template('atom/photo.html', photo=attachment)
    return {
        'html': html,
        'title': title,
    }

def process_attached_video(attachment):
    """Process an attached video."""
    title = attachment.get('displayName') or attachment.get('url')
    html = flask.render_template('atom/video.html', video=attachment)
    return {
        'html': html,
        'title': title,
    }

def process_attached_album(attachment):
    """Process an attached photo album."""
    title = attachment.get('displayName')
    thumbnails = attachment.get('thumbnails', [])

    if len(thumbnails) > 1:
        thumbnails[0]['first'] = True
        big_size = thumbnails[0].get('image', {}).get('height', 0)
        small_size = thumbnails[1].get('image', {}).get('height', 1)
        offset = big_size % small_size
        max_offset = (big_size // small_size) + 1
        if offset > max_offset:
            offset = offset - small_size
        if abs(offset) > max_offset:
            offset = 0
        offset = -offset
    else:
        offset = 0

    html = flask.render_template('atom/album.html', album=attachment, offset=offset)
    return {
        'html': html,
        'title': title,
    }

def process_attached_event(attachment):
    """Process an attached G+ event."""
    title = attachment.get('displayName')
    html = flask.render_template('atom/event.html', event=attachment)
    return {
        'html': html,
        'title': title,
    }

def create_title(html):
    """Attempt to devise a title for an arbitrary piece of html content."""
    if not html:
        return None

    # Try just the text before the first line break, and see if that gives a decent title.
    # If it does, use that, otherwise, use the full text.
    first_line = re.split(r'<br\s*/?>', html)[0]
    first_line_text = jinja2.Markup(first_line).striptags()
    if len(first_line_text) > 3:
        text = first_line_text
    else:
        text = jinja2.Markup(html).striptags()

    # If we're already at 100 characters or less, we're good.
    if len(text) <= 100:
        return text

    # Trim things down, avoiding breaking words.
    shortened = text[:97]
    if ' ' in shortened[-10:]:
        shortened = shortened.rsplit(' ', 1)[0]
    return shortened + '...'

# vim: set ts=4 sts=4 sw=4 et:
