pluss - A feed generator for Google+
======================================

What is pluss?
----------------

`pluss` is a lightweight web server which serves [Atom][6]-format feeds based on [Google+][5] public post streams. It's very similar to [`plusfeed`][7], but it's designed to run on a regular server as a `tornado` app, rather than on AppEngine. It also uses the official Google+ API to fetch its content.

It works similarly to a proxy server - you request the feed url via HTTP from the `pluss` server, it fetches a copy of the specified user's Google+ public posts stream, translates it into Atom format, and serves it back to you.

`pluss` will only proxy feeds for users who have given it authorization (which is acquired via OAuth2). Revoking authorization will result in the removal of the feed for that user.

`pluss` will also cache its feed results for a given user if `memcache` is available, thus reducing overall bandwidth usage, especially if multiple different clients are accessing the same feed. *(Feeds are cached for 15 minutes, so it may take a few minutes after a new post is shared for it to show up in the feed if caching is enabled, or for a feed with revoked access to disappear.)*

A running pluss server is available for general usage [here](http://pluss.aiiane.com).

Dependencies
------------

Note that it is *possible* that `pluss` might work with earlier versions of some of these packages, but I do not plan to support anything less than what is listed here. Caveat emptor.

 - [Python][3] 2.7+
 - [`BeautifulSoup`][2] 3.2+
 - [`python-memcache`][4] 1.45+ (optional, but required for `memcached` support which is highly recommended)

([`tornado`][1] version 2.0 is already bundled with `pluss` for simplicity.)

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

(The proper values to use can be found in the [Google APIs Console][9] under the 'API Access' section.)

You can also tweak any other portions of the config file - by default, `pluss` runs on all interfaces at port 7587. (`PLUS` on a phone keypad.)

Usage
-----

To start the `pluss` server, simply run `pluss.py`

    $ python pluss.py

(Invoking `pluss.py` directly should also work on systems supporting shebangs.)

Once `pluss` is running, you should be able to access it in a browser:

    http://example.com:7587

Notes
-----

 - `pluss` will write out a `app.pid` file to the path specified in the config file, and will remove it when it terminates.
 - `pluss` currently runs in the foreground (it's not really productionized yet), but you can background it with `nohup` easily enough, or run it in `screen`/`tmux`.
 - `pluss` will ignore the setting for enabling caching if `import memcache` fails (but will write out a message to the log to let you know it's doing so).
 - `pluss` is subject to normal Google API rate limits. If you want further access control of who can use your `pluss` server, use external measures (e.g. firewall rules, a reverse proxy doing authentication, etc).

Special Thanks
--------------

Though `pluss` was written basically from the ground up, there were a few portions which were inspired by or assisted by the work of others. The [`plusfeed`][7] codebase was extremely helpful in corroborating and speeding along some of my own original exploration of Google+ data parsing and Atom feed generation (though a significant amount of that was then reworked when the official Google+ API was made available). There are also two files, `util/route.py` and `util/pid.py`, which were utility code openly shared by individuals in blog posts - you can find the original authors and links to the sources within the files themselves as comments.

Licensing
---------

`pluss` was originally created by [Amber Yust][8].

As specified in detail in the included `LICENSE` file, this software is released under the MIT License. That basically means you can do essentially whatever you want with it as long as you keep the `LICENSE` file around (i.e. don't mislead people as to the original source/availability of this software).

 [1]: http://www.tornadoweb.org/
 [2]: http://www.crummy.com/software/BeautifulSoup/
 [3]: http://python.org/
 [4]: http://www.tummy.com/Community/software/python-memcached/
 [5]: http://plus.google.com
 [6]: http://en.wikipedia.org/wiki/Atom_%28standard%29
 [7]: https://github.com/russellbeattie/plusfeed
 [8]: https://github.com/ayust
 [9]: https://code.google.com/apis/console/
