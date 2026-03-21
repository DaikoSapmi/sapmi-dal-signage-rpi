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
CHANNELS_CONF_PATH = ROOT / 'data' / 'channels.conf'

DEFAULT_SOURCES = [
    {'name': 'NRK Sápmi', 'url': 'https://www.nrk.no/sapmi/oddasat.rss'},
    {'name': 'Yle Sápmi', 'url': 'https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_SAPMI'},
    {'name': 'SVT Norrbotten', 'url': 'https://www.svt.se/nyheter/lokalt/norrbotten/rss.xml'},
    {'name': 'Ávvir', 'url': 'https://avvir.no/feed/'},
    {'name': 'Ságat', 'url': 'https://www.sagat.no/atom.xml'},
]

IMAGE_FALLBACK_SOURCES = {'Ávvir', 'SVT Norrbotten', 'iFinnmark'}

# Known generic/placeholder logo images that should not be used as story media.
SVT_PLACEHOLDER_IMAGE_HASHES = {
    '2f93ba843f7e400a13c86112e65490896499522866cbeab7a04aa887efed39b6',
}


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


def _looks_like_image_url(url: str, node_type: str = '') -> bool:
    u = (url or '').lower()
    t = (node_type or '').lower()
    if not u:
        return False
    if any(ext in u for ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif')):
        return True
    # No file extension in URL is also common (e.g. VG CDN), rely on MIME/type hints.
    if t.startswith('image/') or t.startswith('img/'):
        return True
    return False


def is_unwanted_logo_image(url: str, source: str = '') -> bool:
    u = (url or '').lower()
    s = (source or '').lower()
    if not u:
        return False

    # SVT "Nyheter från dagen" and similar cards often use a generic SVT logo image.
    if 'svt' in s and 'svtstatic.se/image-news' in u:
        return any(h in u for h in SVT_PLACEHOLDER_IMAGE_HASHES)

    return False


def extract_credit_from_text(text: str) -> str:
    if not text:
        return ''

    # Common credit markers in NO/SE/FI/EN + Sami UI label.
    patterns = [
        r'(?:Foto|Bild|Kuva|Photo|Govva)\s*[:\-]\s*([^<\n\r]+)',
        r'(?:Fotograf|Photographer)\s*[:\-]\s*([^<\n\r]+)',
        r'©\s*([^<\n\r]+)',
    ]

    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            candidate = re.sub(r'\s+', ' ', m.group(1)).strip(' .;|')
            if candidate:
                return candidate
    return ''


def pick_credit(item_elem, summary_text: str = ''):
    # Prefer explicit media credit tags from RSS/MRSS/EBU
    credit_tags = [
        '{http://search.yahoo.com/mrss/}credit',
        '{urn:ebu}credit',
        'credit',
    ]

    for tag in credit_tags:
        for node in item_elem.findall(tag):
            txt = (node.text or '').strip()
            role = (node.attrib.get('role', '') or '').lower()
            if not txt:
                continue
            if role in ('photographer', 'photo', 'image', ''):
                return txt
            # If role is present but unknown, still keep first non-empty credit
            return txt

    # Fallback to common textual fields (may be byline/author/credit in some feeds)
    fallback_tags = ['author', '{http://purl.org/dc/elements/1.1/}creator', 'dc:creator']
    for tag in fallback_tags:
        node = item_elem.find(tag)
        if node is not None and (node.text or '').strip():
            return (node.text or '').strip()

    # Finally try to parse credit text from description/content HTML
    return extract_credit_from_text(summary_text)


def pick_image(item_elem, summary_text=''):
    # Try RSS/MRSS image fields first
    media_tags = [
        '{http://search.yahoo.com/mrss/}content',
        '{http://search.yahoo.com/mrss/}thumbnail',
        'enclosure',
        'image',
        'imgRegular',
        '{http://www.vg.no/namespace}img',
        '{http://www.vg.no/namespace}articleImg',
    ]

    for tag in media_tags:
        for node in item_elem.findall(tag):
            # image/imgRegular/vg:img can be text nodes, others often use url attr
            url = (node.attrib.get('url', '') or (node.text or '')).strip()
            node_type = node.attrib.get('type', '')
            if _looks_like_image_url(url, node_type):
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


def extract_meta_credit_from_html(html: str) -> str:
    patterns = [
        r'<meta[^>]+(?:property|name)=["\'](?:og:image:credit|twitter:image:credit|parsely-image-credit)["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image:credit|twitter:image:credit|parsely-image-credit)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.IGNORECASE)
        if m:
            return re.sub(r'\s+', ' ', m.group(1)).strip()

    # last-resort text scan for visible credit patterns
    return extract_credit_from_text(html)


def fallback_meta_from_article(url: str):
    try:
        html = fetch_xml(url)
        return (
            extract_meta_title_from_html(html),
            extract_meta_image_from_html(html),
            extract_meta_credit_from_html(html),
        )
    except Exception:
        return '', '', ''


def parse_channels_conf(path: Path):
    if not path.exists():
        return {'sources': [], 'display_count': 5}

    rows = []
    display_count = 5
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue

        # Settings: @display_count=5
        if line.startswith('@') and '=' in line:
            k, v = [p.strip() for p in line.split('=', 1)]
            if k.lower() == '@display_count':
                try:
                    n = int(v)
                    if n > 0:
                        display_count = n
                except Exception:
                    pass
            continue

        # Format: Name|URL|maxItems|enabled
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2:
            continue

        name, url = parts[0], parts[1]
        max_items = None
        enabled = True

        if len(parts) >= 3 and parts[2]:
            try:
                max_items = int(parts[2])
            except Exception:
                max_items = None

        if len(parts) >= 4 and parts[3]:
            enabled = parts[3].lower() not in ('0', 'false', 'no', 'off')

        if name and url and enabled:
            rows.append({'name': name, 'url': url, 'maxItems': max_items})

    return {'sources': rows, 'display_count': display_count}


def ensure_channels_conf_exists():
    if CHANNELS_CONF_PATH.exists():
        return

    CHANNELS_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Sápmi dál kanal-konfigurasjon',
        '# Innstillinger:',
        '# @display_count=5   (antall nyheter som vises i rotasjon)',
        '#',
        '# Kanaler: Én kanal per linje: Name|URL|maxItems|enabled',
        '# Eksempel: NRK Sápmi|https://www.nrk.no/sapmi/oddasat.rss|6|1',
        '# Sett enabled=0 for å slå av en kanal midlertidig',
        '@display_count=5',
        '',
    ]
    for s in DEFAULT_SOURCES:
        lines.append(f"{s['name']}|{s['url']}|6|1")

    CHANNELS_CONF_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def load_sources_and_settings():
    ensure_channels_conf_exists()

    # Foretrekk enkel nano-vennlig channels.conf hvis den finnes/er gyldig.
    conf = parse_channels_conf(CHANNELS_CONF_PATH)
    conf_sources = conf.get('sources', [])
    conf_display_count = conf.get('display_count', 5)
    if conf_sources:
        return conf_sources, conf_display_count

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

    return normalized, 5


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
            'image_credit': '',
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
            image_credit = pick_credit(item, summary)
            if title and link:
                items.append({
                    'source': source,
                    'title': title,
                    'url': link,
                    'published_at': date.isoformat() if date else '',
                    'summary': summary,
                    'image_url': image_url,
                    'image_credit': image_credit,
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
        image_credit = pick_credit(entry, summary)
        if title and link:
            items.append({
                'source': source,
                'title': title,
                'url': link,
                'published_at': date.isoformat() if date else '',
                'summary': summary,
                'image_url': image_url,
                'image_credit': image_credit,
            })
    return items


def main():
    all_items = []
    sources, display_count = load_sources_and_settings()
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
        title_meta, img, credit_meta = fallback_meta_from_article(item.get('url', ''))
        if img:
            item['image_url'] = img
        if credit_meta and not (item.get('image_credit') or '').strip():
            item['image_credit'] = credit_meta
        if title_meta and item.get('source') == 'iFinnmark':
            t = re.sub(r'\s*-\s*iFinnmark\s*$', '', title_meta, flags=re.IGNORECASE)
            item['title'] = t or item.get('title', '')
        checked += 1

    # Try to enrich missing credits for items that already have image (limited requests).
    credit_checked = 0
    for item in items:
        if credit_checked >= 60:
            break
        if not (item.get('image_url') or '').strip():
            continue
        if (item.get('image_credit') or '').strip():
            continue
        title_meta, img_meta, credit_meta = fallback_meta_from_article(item.get('url', ''))
        if credit_meta:
            item['image_credit'] = credit_meta
        credit_checked += 1

    # Remove known placeholder/logo-only images (e.g. SVT generic logo cards).
    items = [
        it for it in items
        if not is_unwanted_logo_image(it.get('image_url', ''), it.get('source', ''))
    ]

    # Keep only news that actually has image/media, so signage never rotates text-only items.
    items = [it for it in items if (it.get('image_url') or '').strip()]

    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'count': len(items),
        'display_count': display_count,
        'items': items[:120],
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Updated {DATA_PATH} with {payload["count"]} articles')


if __name__ == '__main__':
    main()
