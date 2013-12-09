import flask

from pluss.util.config import Config

def full_url_for(*args, **kwargs):
    base = 'http://' + Config.get('server', 'host')
    return  base + flask.url_for(*args, **kwargs)

app = flask.Flask("pluss")
