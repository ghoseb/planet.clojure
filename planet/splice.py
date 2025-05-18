""" Splice together a planet from a cache of feed entries """
import glob
import os
import time
import shutil
import pickle
import traceback
import sys
from xml.dom import minidom
import planet
from planet import config
import feedparser
from planet import reconstitute
from planet import shell
from planet.reconstitute import createTextElement, date
from planet.spider import filename
from planet import idindex
import logging
from datetime import datetime

posted_urls_file = 'posted_urls.pickle'

def splice():
    """ Splice together a planet from a cache of entries """
    import planet
    log = planet.logger

    log.info("Loading cached data")
    cache = config.cache_directory()
    dir = [(os.stat(file).st_mtime, file) for file in glob.glob(cache+"/*")
        if not os.path.isdir(file)]
    dir.sort()
    dir.reverse()

    max_items = max([config.items_per_page(templ)
        for templ in config.template_files() or ['Planet']])

    doc = minidom.parseString('<feed xmlns="http://www.w3.org/2005/Atom"/>')
    feed = doc.documentElement

    # insert feed information
    createTextElement(feed, 'title', config.name())
    date(feed, 'updated', time.gmtime())    
    gen = createTextElement(feed, 'generator', config.generator())
    gen.setAttribute('uri', config.generator_uri())

    author = doc.createElement('author')
    createTextElement(author, 'name', config.owner_name())
    createTextElement(author, 'email', config.owner_email())
    feed.appendChild(author)

    if config.feed():
        createTextElement(feed, 'id', config.feed())
        link = doc.createElement('link')
        link.setAttribute('rel', 'self')
        link.setAttribute('href', config.feed())
        if config.feedtype():
            link.setAttribute('type', "application/%s+xml" % config.feedtype())
        feed.appendChild(link)

    if config.pubsubhubbub_hub():
        hub = doc.createElement('link')
        hub.setAttribute('rel', 'hub')
        hub.setAttribute('href', config.pubsubhubbub_hub())
        feed.appendChild(hub)

    if config.link():
        link = doc.createElement('link')
        link.setAttribute('rel', 'alternate')
        link.setAttribute('href', config.link())
        feed.appendChild(link)

    # insert subscription information
    sub_ids = []
    feed.setAttribute('xmlns:planet', planet.xmlns)
    sources = config.cache_sources_directory()
    for sub in config.subscriptions():
        data = feedparser.parse(filename(sources, sub))
        if 'id' in data.feed:
            sub_ids.append(data.feed.id)
        if not data.feed:
            continue

        # warn on missing links
        if 'planet_message' not in data.feed:
            if 'links' not in data.feed:
                data.feed['links'] = []

            for link in data.feed.links:
                if link.rel == 'self':
                    break
            else:
                log.debug('missing self link for ' + sub)

            for link in data.feed.links:
                if link.rel == 'alternate' and 'html' in link.type:
                    break
            else:
                log.debug('missing html link for ' + sub)

        xdoc = minidom.parseString('''<planet:source xmlns:planet="%s"
             xmlns="http://www.w3.org/2005/Atom"/>\n''' % planet.xmlns)
        reconstitute.source(xdoc.documentElement, data.feed, None, None)
        feed.appendChild(xdoc.documentElement)

    index = idindex.open()

    # insert entry information
    items = 0
    count = {}
    atomNS = 'http://www.w3.org/2005/Atom'
    new_feed_items = config.new_feed_items()

    posted_urls = set()
    if config.post_to_twitter():
        if os.path.exists(posted_urls_file):
            try:
                with open(posted_urls_file, 'rb') as f:
                    posted_urls = pickle.load(f)
            except Exception as ex:
                log.error("Error reading posted_urls %s", ex)

    for mtime, file in dir:
        if index is not None:
            base = os.path.basename(file)
            if base in index and index[base] not in sub_ids:
                continue

        try:
            entry = minidom.parse(file)

            # verify that this entry is currently subscribed to and that the
            # number of entries contributed by this feed does not exceed
            # config.new_feed_items
            entry.normalize()
            sources = entry.getElementsByTagNameNS(atomNS, 'source')
            if sources:
                ids = sources[0].getElementsByTagName('id')
                if ids:
                    id = ids[0].childNodes[0].nodeValue
                    count[id] = count.get(id, 0) + 1
                    if new_feed_items and count[id] > new_feed_items:
                        continue

                    if id not in sub_ids:
                        ids = sources[0].getElementsByTagName('planet:id')
                        if not ids:
                            continue
                        id = ids[0].childNodes[0].nodeValue
                        if id not in sub_ids:
                            log.warning('Skipping: ' + id)
                        if id not in sub_ids:
                            continue

            # Twitter integration
            if config.post_to_twitter():
                url = None
                twitter = None
                title = "Untitled post..."
                links = entry.getElementsByTagName('link')
                if links:
                    for link in links:
                        if (link.hasAttribute('rel') and 
                            link.hasAttribute('type') and 
                            link.hasAttribute('href')):
                            if (link.getAttribute('rel') == 'alternate' and
                                link.getAttribute('type') == 'text/html'):
                                url = link.getAttribute('href')
                                break

                titles = entry.getElementsByTagName('title')
                if titles:
                    title = titles[0].firstChild.nodeValue.strip()
                handles = entry.getElementsByTagName('planet:twitter')
                if handles:
                    twitter = handles[0].firstChild.nodeValue

                if url is not None and url not in posted_urls:
                    txt_append = ''
                    if twitter:
                        txt_append = " (by " + ' & '.join(["@"+tw for tw in twitter.strip().split(',')]) + ")"
                    max_title_len = 280 - 20 - len(txt_append)
                    if len(title) > max_title_len:
                        title = title[:max_title_len]
                    txt = title + txt_append + "\n" + url
                    
                    log.debug("Text to post '%s'", txt)
                    try:
                        posted_urls.add(url)
                        config.twitter_api.update_status(txt)
                    except Exception as ex:
                        log.error("Error posting to Twitter: %s", ex)
    
            # add entry to feed
            feed.appendChild(entry.documentElement)
            items = items + 1
            if items >= max_items:
                break
        except Exception as ex:
            log.error("Error parsing %s: %s", file, ex)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback,
                                    limit=2, file=sys.stdout)

    if config.post_to_twitter():
        with open(posted_urls_file, 'wb') as f:
            pickle.dump(posted_urls, f, protocol=pickle.HIGHEST_PROTOCOL)
            
    if index:
        index.close()

    return doc

def apply(doc):
    output_dir = config.output_dir()
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    log = planet.logger

    planet_filters = config.filters('Planet')

    # Go-go-gadget-template
    for template_file in config.template_files():
        output_file = shell.run(template_file, doc)

        # run any template specific filters
        if config.filters(template_file) != planet_filters:
            with open(output_file, encoding='utf-8') as f:
                output = f.read()
            for filter in config.filters(template_file):
                if filter in planet_filters:
                    continue
                if filter.find('>') > 0:
                    # tee'd output
                    filter, dest = filter.split('>', 1)
                    tee = shell.run(filter.strip(), output, mode="filter")
                    if tee:
                        output_dir = planet.config.output_dir()
                        dest_file = os.path.join(output_dir, dest.strip())
                        with open(dest_file, 'w', encoding='utf-8') as f:
                            f.write(tee)
                else:
                    # pipe'd output
                    output = shell.run(filter, output, mode="filter")
                    if not output:
                        os.unlink(output_file)
                        break
            else:
                with open(output_file, 'w', encoding='utf-8') as handle:
                    handle.write(output)

    # Process bill of materials
    for copy_file in config.bill_of_materials():
        dest = os.path.join(output_dir, copy_file)
        for template_dir in config.template_directories():
            source = os.path.join(template_dir, copy_file)
            if os.path.exists(source):
                break
        else:
            log.error('Unable to locate %s', copy_file)
            log.info("Template search path:")
            for template_dir in config.template_directories():
                log.info("    %s", os.path.realpath(template_dir))
            continue

        mtime = os.stat(source).st_mtime
        if not os.path.exists(dest) or os.stat(dest).st_mtime < mtime:
            dest_dir = os.path.split(dest)[0]
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)

            log.info("Copying %s to %s", source, dest)
            if os.path.exists(dest):
                os.chmod(dest, 0o644)
            shutil.copyfile(source, dest)
            shutil.copystat(source, dest)

def splicePlanet():
    """Splice all feeds together"""
    logging.info("Splicing feeds...")
    template_files = config.template_files()
    if not template_files:
        logging.error("No template files found")
        return

    output_dir = config.output_dir()
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    cache_dir = config.cache_directory()
    if not os.path.exists(cache_dir):
        logging.error("Cache directory not found")
        return

    entries = []
    for feed in config.parser.sections():
        if feed.startswith('Feed '):
            feed_file = os.path.join(cache_dir, feed.replace(' ', '_') + '.xml')
            if os.path.exists(feed_file):
                with open(feed_file, 'r', encoding='utf-8') as f:
                    data = feedparser.parse(f.read())
                    if not data.bozo:
                        for entry in data.entries:
                            entries.append(entry)

    entries.sort(key=lambda x: time.mktime(x.get('updated_parsed', x.get('published_parsed', (0, 0, 0, 0, 0, 0, 0, 0, 0)))), reverse=True)

    for template_file in template_files:
        try:
            applyTemplate(template_file, entries)
        except Exception as e:
            logging.error("Error applying template %s: %s", template_file, str(e))

def applyTemplate(template_file, entries):
    """Apply a template to the entries"""
    logging.info("Applying template %s", template_file)
    template_dir = os.path.dirname(template_file)
    if template_dir:
        sys.path.insert(1, template_dir)

    template_name = os.path.splitext(os.path.basename(template_file))[0]
    template_module = __import__(template_name)

    output_dir = config.output_dir()
    output_file = os.path.join(output_dir, template_name + '.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(template_module.render(entries))
