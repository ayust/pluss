pluss - A feed generator for Google+
======================================

What is pluss?
----------------

`pluss` is a lightweight web server which serves [Atom][2]-format feeds based on [Google+][1] public post streams. It's very similar to [`plusfeed`][3], but it's designed to run on a regular server as a Flask app, rather than on AppEngine. It also uses the official Google+ API to fetch its content.

It works similarly to a proxy server - you request the feed url via HTTP from the `pluss` server, it fetches a copy of the specified user's Google+ public posts stream, translates it into Atom format, and serves it back to you.

`pluss` will only proxy feeds for users who have given it authorization (which is acquired via OAuth2). Revoking authorization will result in the removal of the feed for that user.

`pluss` will also cache its feed results for a given user if `memcache` is available, thus reducing overall bandwidth usage, especially if multiple different clients are accessing the same feed. *(Feeds are cached for 15 minutes, so it may take a few minutes after a new post is shared for it to show up in the feed if caching is enabled, or for a feed with revoked access to disappear.)*

A running pluss server is available for general usage [here](http://pluss.aiiane.com).

Dependencies
------------

pluss' major dependencies are:

 * Flask
 * requests
 * python-memcached (technically optional, but highly recommended)

The included `requirements.txt` includes these, and also the packages necessary to run pluss within a high-performance gunicorn server.

Installation
------------

Right now `pluss` isn't a PyPi package, so there's no `setup.py` or the like. Just clone the repository and you should have everything you need to run a server.

Configuration
-------------

Before running `pluss`, you'll need to create a `pluss.cfg` configuration file for it. There is an example configuration file named `pluss.example.cfg`. All of the fields
in the example configuration are required fields - you can change the values, but omission is not allowed.

At a bare minimum, you'll need to change the values of the keys in the `[oauth]` section to your own Google API OAuth2 credentials:

    [oauth]
    client-id = 123456789000.apps.googleusercontent.com
	client-secret = aBcDeFg_hIjKlMn_oPqRstUv

(The proper values to use can be found in the [Google APIs Console][5] under the 'API Access' section.)

You'll also want to set the `host` field in the `[server]` section to match the hostname pluss will be serving under.

Usage
-----

A debug version of pluss can be started by simply running `main.py` - it'll boot up on port 54321.

For production environments, you probably want to point a WSGI server (e.g. gunicorn) at `main:app`.

Notes
-----

 - `pluss` will ignore the setting for enabling caching if `import memcache` fails (but will write out a message to the log to let you know it's doing so).
 - `pluss` is subject to normal Google API rate limits. If you want further access control of who can use your `pluss` server, use external measures (e.g. firewall rules, a reverse proxy doing authentication, etc).

Special Thanks
--------------

Though `pluss` was written basically from the ground up, there were a few portions which were inspired by or assisted by the work of others. The [`plusfeed`][3] codebase was extremely helpful in corroborating and speeding along some of my own original exploration of Google+ data parsing and Atom feed generation (though a significant amount of that was then reworked when the official Google+ API was made available).

Licensing
---------

`pluss` was originally created by [Amber Yust][4].

As specified in detail in the included `LICENSE` file, this software is released under the MIT License. That basically means you can do essentially whatever you want with it as long as you keep the `LICENSE` file around (i.e. don't mislead people as to the original source/availability of this software).

 [1]: http://plus.google.com
 [2]: http://en.wikipedia.org/wiki/Atom_%28standard%29
 [3]: https://github.com/russellbeattie/plusfeed
 [4]: https://github.com/ayust
 [5]: https://code.google.com/apis/console/
