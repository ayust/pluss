`pluss` - A feed generator for Google+
======================================

What is `pluss`?
----------------

`pluss` is a lightweight web server which serves [Atom][6]-format feeds based on [Google+][5] public post streams. It's very similar to [`plusfeed`][7], but it's designed to run on a regular server as a `tornado` app, rather than on AppEngine.

It works similarly to a proxy server - you request the feed url via HTTP from the `pluss` server, it fetches a copy of the specified user's Google+ public posts stream, translates it into Atom format, and serves it back to you.

`pluss` will also cache its feed results for a given user if `memcache` is available, thus reducing overall bandwidth usage, especially if multiple different clients are accessing the same feed. *(Feeds are cached for 15 minutes, so it may take a few minutes after a new post is shared for it to show up in the feed if caching is enabled.)*

Dependencies
------------

Note that it is *possible* that `pluss` might work with earlier versions of some of these packages, but I do not plan to support anything less than what is listed here. Caveat emptor.

 - [Python][3] 2.7+
 - [`tornado`][1] 1.0.1+ (should be forwards-compatible with Tornado 2.x)
 - [`BeautifulSoup`][2] 3.2+
 - [`python-memcache`][4] 1.45+

Installation
------------

Right now `pluss` isn't a PyPi package, so there's no `setup.py` or the like. Just clone the repository and you should have something that can run straight out of the box.

Setup and Usage
---------------

Currently `pluss` doesn't have any real configuration - just run it:

    $ python pluss.py

By default, `pluss` listens on all interfaces, port 7587. ('PLUS' on a phone keypad.)

If you want to modify this behavior right now, you'll have to edit `pluss.py` - it's not too scary though, just a standard Tornado application.

Once `pluss` is running, feeds are available at the following endpoint:

    http://example.com:7587/atom/<21-digit google user id>

If you want to force a refresh of a given feed, pass `?flush=1` as a GET parameter to the feed URL to bypass `memcache` and force a re-query of the Google+ stream. (Google might not like it if you do this too often, nor might your server resources.)

Notes
-----

 - `pluss` will write out a `app.pid` file to the directory it's started in, and will remove it when it terminates.
 - `pluss` currently runs in the foreground (it's not really productionized yet), but you can background it with `nohup` easily enough, or run it in `screen`/`tmux`.
 - If `memcache` is available as a module in Python, `pluss` assumes there is a memcache server running on `127.0.0.1:11211` - if your memcache server is located elsewhere, you'll need to edit `util/cache.py` to change this.

Special Thanks
--------------

Though `pluss` was written basically from the ground up, there were a few portions which were inspired by or assisted by the work of others. The [`plusfeed`][7] codebase was extremely helpful in corroborating and speeding along some of my own exploration of Google+ data parsing and Atom feed generation. There are also two files, `util/route.py` and `util/pid.py`, which were utility code openly shared by individuals in blog posts - you can find the original authors and links to the sources within the files themselves as comments.

 [1]: http://www.tornadoweb.org/
 [2]: http://www.crummy.com/software/BeautifulSoup/
 [3]: http://python.org/
 [4]: http://www.tummy.com/Community/software/python-memcached/
 [5]: http://plus.google.com
 [6]: http://en.wikipedia.org/wiki/Atom_%28standard%29
 [7]: https://github.com/russellbeattie/plusfeed
