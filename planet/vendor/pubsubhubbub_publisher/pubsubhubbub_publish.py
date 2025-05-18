#!/usr/bin/env python3
#
# Copyright 2009 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Simple Publisher client for PubSubHubbub.

Example usage:

  from pubsubhubbub_publisher import publish
  try:
    publish('http://pubsubhubbub.appspot.com',
            'http://example.com/feed1/atom.xml',
            'http://example.com/feed2/atom.xml',
            'http://example.com/feed3/atom.xml')
  except PublishError as e:
    # handle exception...

Set the 'http_proxy' environment variable on *nix or Windows to use an
HTTP proxy.
"""

__author__ = 'bslatkin@gmail.com (Brett Slatkin)'

import urllib.request
import urllib.parse
import urllib.error


class PublishError(Exception):
    """An error occurred while trying to publish to the hub."""
    pass


URL_BATCH_SIZE = 100


def publish(hub, *urls):
    """Publishes an event to a hub.

    Args:
        hub: The hub to publish the event to.
        **urls: One or more URLs to publish to. If only a single URL argument is
          passed and that item is an iterable that is not a string, the contents of
          that iterable will be used to produce the list of published URLs. If
          more than URL_BATCH_SIZE URLs are supplied, this function will batch them
          into chunks across multiple requests.

    Raises:
        PublishError if anything went wrong during publishing.
    """
    if len(urls) == 1 and not isinstance(urls[0], str):
        urls = list(urls[0])

    for i in range(0, len(urls), URL_BATCH_SIZE):
        chunk = urls[i:i+URL_BATCH_SIZE]
        data = urllib.parse.urlencode(
            {'hub.url': chunk, 'hub.mode': 'publish'}, doseq=True)
        try:
            response = urllib.request.urlopen(hub, data.encode('utf-8'))
        except (IOError, urllib.error.HTTPError) as e:
            if hasattr(e, 'code') and e.code == 204:
                continue
            error = ''
            if hasattr(e, 'read'):
                error = e.read()
            raise PublishError(f'{e}, Response: "{error}"')
