"""Shared fixtures: a local feed server running in a background thread.

The server runs in its own thread and event loop so both async code
(fetch_all) and code that calls asyncio.run itself (main.run) can use it.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
from aiohttp import web

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>RSS Blog</title><link>https://rss.example/</link>
  <item><title>First Clojure post</title><link>https://rss.example/1</link>
    <guid isPermaLink="false">rss-1</guid><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate>
    <description>About (defn foo [])</description></item>
  <item><title>Python post</title><link>https://rss.example/2</link>
    <guid isPermaLink="false">rss-2</guid><pubDate>Tue, 03 Nov 2026 10:00:00 GMT</pubDate>
    <description>Nothing relevant here</description></item>
  <item><title>Second Clojure post</title><link>https://rss.example/3</link>
    <guid isPermaLink="false">rss-3</guid><pubDate>Wed, 04 Nov 2026 10:00:00 GMT</pubDate>
    <description>More Clojure</description></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Blog</title><id>urn:atom-blog</id>
  <link rel="alternate" type="text/html" href="https://atom.example/"/>
  <updated>2026-11-05T12:00:00Z</updated>
  <author><name>Ada</name></author>
  <entry>
    <title type="html">Tips &amp;amp; &lt;b&gt;tricks&lt;/b&gt;</title>
    <id>urn:atom-1</id><link rel="alternate" href="https://atom.example/1"/>
    <published>2026-01-01T00:00:00Z</published>
    <updated>2026-11-05T12:00:00Z</updated>
    <content type="html">&lt;p onclick="evil()"&gt;Hello&lt;/p&gt;
      &lt;script&gt;alert(1)&lt;/script&gt;
      &lt;a href="javascript:alert(2)"&gt;x&lt;/a&gt;
      &lt;img src="https://atom.example/i.png" alt="Clojure logo"&gt;</content>
  </entry>
</feed>"""


Counts = dict[str, int]

HITS = web.AppKey("hits", Counts)  # path -> requests served
IN_FLIGHT = web.AppKey("in_flight", Counts)  # host -> current
PEAK = web.AppKey("peak", Counts)  # host -> max concurrent
STARTS = web.AppKey("starts", dict[str, list[float]])  # path -> monotonic start times


def _app() -> web.Application:
    app = web.Application()
    app[HITS] = {}
    app[IN_FLIGHT] = {}
    app[PEAK] = {}
    app[STARTS] = {}

    def count(request: web.Request) -> None:
        for key in {request.path, request.path_qs}:
            app[HITS][key] = app[HITS].get(key, 0) + 1

    async def rss(request: web.Request) -> web.Response:
        count(request)
        if request.headers.get("If-None-Match") == '"v1"':
            return web.Response(status=304, headers={"ETag": '"v1"'})
        return web.Response(body=RSS, content_type="application/rss+xml", headers={"ETag": '"v1"'})

    async def atom(request: web.Request) -> web.Response:
        count(request)
        return web.Response(body=ATOM, content_type="application/atom+xml")

    async def hang(_request: web.Request) -> web.Response:
        await asyncio.sleep(30)
        return web.Response(text="late")

    async def drip(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse()
        await resp.prepare(request)
        for _ in range(300):
            await resp.write(b" ")
            await asyncio.sleep(0.1)
        return resp

    async def big(_request: web.Request) -> web.Response:
        return web.Response(body=b"x" * 2_000_000, content_type="application/xml")

    async def slow(request: web.Request) -> web.Response:
        host = request.host.split(":")[0]
        app[IN_FLIGHT][host] = app[IN_FLIGHT].get(host, 0) + 1
        app[PEAK][host] = max(app[PEAK].get(host, 0), app[IN_FLIGHT][host])
        try:
            await asyncio.sleep(0.2)
        finally:
            app[IN_FLIGHT][host] -= 1
        return web.Response(text="ok")

    async def missing(request: web.Request) -> web.Response:
        count(request)
        return web.Response(status=404)

    async def stamp(request: web.Request) -> web.Response:
        app[STARTS].setdefault(request.path, []).append(time.monotonic())
        return web.Response(text="ok")

    async def limited_once(request: web.Request) -> web.Response:
        """429 on the first request for each query string, then the feed."""
        count(request)
        if app[HITS][request.path_qs] == 1:
            return web.Response(status=429, headers={"Retry-After": "1"})
        return web.Response(body=ATOM, content_type="application/atom+xml")

    async def always_429(request: web.Request) -> web.Response:
        count(request)
        return web.Response(status=429)

    app.router.add_get("/rss.xml", rss)
    app.router.add_get("/atom.xml", atom)
    app.router.add_get("/hang", hang)
    app.router.add_get("/drip", drip)
    app.router.add_get("/big", big)
    app.router.add_get("/missing", missing)
    app.router.add_get("/slow", slow)
    app.router.add_get("/stamp", stamp)
    app.router.add_get("/limited-once", limited_once)
    app.router.add_get("/always-429", always_429)
    return app


class FeedServer:
    def __init__(self) -> None:
        self.app = _app()
        self.loop = asyncio.new_event_loop()
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self.port = int(self._sock.getsockname()[1])
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        runner = web.AppRunner(self.app)
        self.loop.run_until_complete(runner.setup())
        self.loop.run_until_complete(web.SockSite(runner, self._sock).start())
        self._ready.set()
        self.loop.run_forever()

    def start(self) -> FeedServer:
        self._thread.start()
        self._ready.wait(5)
        return self

    def url(self, path: str, host: str = "127.0.0.1") -> str:
        return f"http://{host}:{self.port}{path}"

    @property
    def peak(self) -> Counts:
        return self.app[PEAK]

    @property
    def hits(self) -> Counts:
        """Requests served, by path and by path + query string."""
        return self.app[HITS]

    @property
    def starts(self) -> dict[str, list[float]]:
        return self.app[STARTS]


@pytest.fixture(scope="session")
def server() -> FeedServer:
    return FeedServer().start()
