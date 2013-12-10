import os

import flask

from pluss.util import db
from pluss.util.config import Config

def full_url_for(*args, **kwargs):
    base = 'http://' + Config.get('server', 'host')
    return  base + flask.url_for(*args, **kwargs)


db.init(os.path.expanduser(os.path.expandvars(Config.get('database', 'path'))))

app = flask.Flask("pluss")
import pluss.handlers
