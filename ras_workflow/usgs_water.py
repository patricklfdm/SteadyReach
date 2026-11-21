"""Versioned USGS Water Data queries. Ratings use the separate STAC service."""
import json
from urllib.parse import urlencode, urljoin, urlsplit

HOST = 'https://api.waterdata.usgs.gov'
COLLECTIONS = HOST + '/ogcapi/v1/collections/'


def query(collection, **parameters):
    return COLLECTIONS + collection + '/items?' + urlencode(dict(f='json', **parameters))


def pages(url, fetch):
    """Follow only the same collection. Each caller retains the raw page bytes."""
    original = urlsplit(url)
    seen = set()
    while url:
        parts = urlsplit(url)
        if (parts.scheme, parts.netloc, parts.path) != (original.scheme, original.netloc, original.path):
            raise ValueError('Unexpected USGS pagination destination')
        if url in seen or len(seen) >= 150:
            raise ValueError('USGS pagination repeated or exceeded the page budget')
        seen.add(url)
        raw = fetch(url)
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get('features'), list):
            raise ValueError('USGS returned an unexpected feature collection')
        yield url, raw, data
        links = [link['href'] for link in data.get('links', []) if link.get('rel') == 'next']
        if len(links) > 1:
            raise ValueError('Ambiguous USGS pagination')
        url = urljoin(url, links[0]) if links else None
