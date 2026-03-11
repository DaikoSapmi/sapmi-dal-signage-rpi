#!/usr/bin/env python3
import json
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, unquote, urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent / 'web'
DATA_PATH = ROOT / 'data' / 'news.json'
CONFIG_PATH = ROOT / 'data' / 'config.json'

DEFAULT_SOURCES = [
    {'name': 'NRK Sápmi', 'url': 'https://www.nrk.no/sapmi/oddasat.rss'},
    {'name': 'Yle Sápmi', 'url': 'https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_SAPMI'},
    {'name': 'SVT Norrbotten', 'url': 'https://www.svt.se/nyheter/lokalt/norrbotten/rss.xml'},
    {'name': 'Ávvir', 'url': 'https://avvir.no/feed/'},
    {'name': 'Ságat', 'url': 'https://www.sagat.no/atom.xml'},
]

IMAGE_FALLBACK_SOURCES = {'Ávvir', 'SVT Norrbotten', 'iFinnmark'}


def fetch_xml(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (SamiNewsBoard/1.0)'})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        return r.read().decode('utf-8', errors='replace')


def text_of(elem, tag_names):
    for tag in tag_names:
        node = elem.find(tag)
        if node is not None and node.text:
            return node.text.strip()
    return ''


def parse_date(value: str):
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S'):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def pick_image(item_elem, summary_text=''):
    # enclosure/media:content/media:thumbnail first
    media_namespaces = [
        '{http://search.yahoo.com/mrss/}content',
        '{http://search.yahoo.com/mrss/}thumbnail',
        'enclosure',
    ]
    for tag in media_namespaces:
        for node in item_elem.findall(tag):
            url = node.attrib.get('url', '').strip()
            if url and ('.jpg' in url or '.jpeg' in url or '.png' in url or '.webp' in url):
                return url

    # image in html content/description
    if summary_text:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary_text, flags=re.IGNORECASE)
        if m:
            return m.group(1)

    return ''


def extract_meta_title_from_html(html: str) -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
        r'<title>(.*?)</title>',
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return re.sub(r'\s+', ' ', m.group(1)).strip()
    return ''


def extract_meta_image_from_html(html: str) -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ''


def fallback_meta_from_article(url: str):
    try:
        html = fetch_xml(url)
        return extract_meta_title_from_html(html), extract_meta_image_from_html(html)
    except Exception:
        return '', ''


def load_sources():
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        except Exception:
            cfg = {}

    srcs = cfg.get('sources') or DEFAULT_SOURCES
    normalized = []
    for s in srcs:
        if not isinstance(s, dict):
            continue
        name = s.get('name', '').strip()
        url = s.get('url', '').strip()
        max_items = s.get('maxItems')
        if name and url:
            normalized.append({'name': name, 'url': url, 'maxItems': max_items})

    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({'sources': DEFAULT_SOURCES}, ensure_ascii=False, indent=2), encoding='utf-8')

    return normalized


def extract_first_href(html_text: str) -> str:
    m = re.search(r'href=["\']([^"\']+)["\']', html_text or '', flags=re.IGNORECASE)
    return m.group(1).strip() if m else ''


def resolve_google_link(link: str, summary: str = '') -> str:
    # Google News RSS may contain opaque redirect links; try to resolve to final publisher URL.
    if 'news.google.com' in (link or ''):
        href = extract_first_href(summary)
        if href and href.startswith('http') and 'news.google.com' not in href:
            return href

        try:
            q = parse_qs(urlparse(link).query)
            if q.get('url'):
                return q['url'][0]
        except Exception:
            pass

        # Network resolve (follows redirects)
        try:
            req = urllib.request.Request(link, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=12, context=ssl.create_default_context()) as resp:
                final = resp.geturl()
                if final:
                    return final
        except Exception:
            pass
    return link


def parse_ifinnmark_html(source: str, page_url: str, html_text: str, max_items=None):
    items = []
    seen = set()
    limit = max_items if isinstance(max_items, int) and max_items > 0 else 1000

    # Find article URLs like .../s/5-81-2406649
    for m in re.finditer(r'href="([^"]+/s/\d+-\d+-\d+)"', html_text):
        href = m.group(1)
        url = urljoin(page_url, href)
        if url in seen:
            continue
        seen.add(url)

        slug = href.strip('/').split('/s/')[0].split('/')[-1]
        title = unquote(slug).replace('-', ' ').strip()
        if title:
            title = title[:1].upper() + title[1:]

        items.append({
            'source': source,
            'title': title or url,
            'url': url,
            'published_at': '',
            'summary': '',
            'image_url': '',
        })

        if len(items) >= limit:
            break

    return items


def parse_feed(source: str, xml_text: str, max_items=None):
    items = []
    root = ET.fromstring(xml_text)
    ns = {
        'atom': 'http://www.w3.org/2005/Atom',
        'dc': 'http://purl.org/dc/elements/1.1/',
        'media': 'http://search.yahoo.com/mrss/',
    }

    limit = max_items if isinstance(max_items, int) and max_items > 0 else None

    # RSS
    channel = root.find('channel')
    if channel is not None:
        rss_items = channel.findall('item')
        if limit:
            rss_items = rss_items[:limit]
        for item in rss_items:
            title = text_of(item, ['title'])
            link = text_of(item, ['link'])
            pub = text_of(item, ['pubDate', 'dc:date'])
            date = parse_date(pub)
            summary = text_of(item, ['description'])
            link = resolve_google_link(link, summary) if source == 'iFinnmark' else link
            image_url = pick_image(item, summary)
            if title and link:
                items.append({
                    'source': source,
                    'title': title,
                    'url': link,
                    'published_at': date.isoformat() if date else '',
                    'summary': summary,
                    'image_url': image_url,
                })
        return items

    # Atom
    atom_entries = root.findall('atom:entry', ns) + root.findall('entry')
    if limit:
        atom_entries = atom_entries[:limit]
    for entry in atom_entries:
        title = text_of(entry, ['atom:title', 'title'])
        link = ''
        link_node = entry.find('atom:link', ns) or entry.find('link')
        if link_node is not None:
            link = link_node.attrib.get('href', '') or (link_node.text or '').strip()
        updated = text_of(entry, ['atom:updated', 'updated', 'atom:published', 'published'])
        date = parse_date(updated)
        summary = text_of(entry, ['atom:summary', 'summary', 'atom:content', 'content'])
        link = resolve_google_link(link, summary) if source == 'iFinnmark' else link
        image_url = pick_image(entry, summary)
        if title and link:
            items.append({
                'source': source,
                'title': title,
                'url': link,
                'published_at': date.isoformat() if date else '',
                'summary': summary,
                'image_url': image_url,
            })
    return items


def main():
    all_items = []
    sources = load_sources()
    for src in sources:
        source = src['name']
        url = src['url']
        max_items = src.get('maxItems')
        try:
            xml_text = fetch_xml(url)
            try:
                all_items.extend(parse_feed(source, xml_text, max_items=max_items))
            except Exception:
                # Fallback for sites exposing HTML list pages at "rss" URLs (e.g. iFinnmark)
                if 'ifinnmark.no/rss/' in url:
                    all_items.extend(parse_ifinnmark_html(source, url, xml_text, max_items=max_items))
        except Exception:
            continue

    # dedupe by url
    dedup = {}
    for item in all_items:
        dedup[item['url']] = item

    items = list(dedup.values())

    # Clean up noisy Google aggregator entries for iFinnmark
    cleaned = []
    for it in items:
        if it.get('source') == 'iFinnmark':
            t = (it.get('title') or '').strip().lower()
            u = (it.get('url') or '').lower()
            if t in ('ifinnmark - ifinnmark', 'ifinnmark'):
                continue
            if 'ifinnmark.no' not in u:
                continue
        cleaned.append(it)
    items = cleaned

    items.sort(key=lambda x: x.get('published_at', ''), reverse=True)

    # Fallback image scraping for sources where feeds often omit images
    checked = 0
    for item in items:
        if checked >= 120:
            break
        if item.get('image_url'):
            continue
        if item.get('source') not in IMAGE_FALLBACK_SOURCES:
            continue
        title_meta, img = fallback_meta_from_article(item.get('url', ''))
        if img:
            item['image_url'] = img
        if title_meta and item.get('source') == 'iFinnmark':
            t = re.sub(r'\s*-\s*iFinnmark\s*$', '', title_meta, flags=re.IGNORECASE)
            item['title'] = t or item.get('title', '')
        checked += 1

    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'count': len(items),
        'items': items[:120],
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Updated {DATA_PATH} with {payload["count"]} articles')


if __name__ == '__main__':
    main()
