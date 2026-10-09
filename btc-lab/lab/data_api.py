"""Polymarket Data API v2, with rows in the v1 shape the lab already reads.

v1 retires on 24 Oct 2026. v2 wraps rows in {"data": [...], "pagination":
{"has_more", "next_cursor"}}, names fields in snake_case and pages with an
opaque cursor instead of an offset (v1 stopped at 10,000 rows). Field names
below were read from live v1 and v2 answers for the same wallet on 9 Oct 2026.
"""
from urllib.parse import urlencode

BASE = 'https://data-api.polymarket.com/v2/'
_RENAME = {
    'token_id': 'asset',
    'current_size': 'size',
    'user_id': 'proxyWallet',
    'user_name': 'userName',
    'volume': 'vol',
    'verified': 'verifiedBadge',
}


def _camel(key):
    head, *rest = key.split('_')
    return head + ''.join(part[:1].upper() + part[1:] for part in rest)


def v1_row(row):
    """One v2 row with v1 keys. Unknown keys are camel-cased, nothing is dropped."""
    if not isinstance(row, dict):
        return row
    out = {}
    for key, value in row.items():
        out[_RENAME.get(key) or _camel(key)] = value
    return out


def page(raw):
    """(rows, next_cursor). A bare v1 list is accepted as one last page."""
    if isinstance(raw, list):
        return raw, None
    if not isinstance(raw, dict):
        raise ValueError('Invalid Data API response')
    rows = raw.get('data') or []
    if not isinstance(rows, list):
        raise ValueError('Invalid Data API rows')
    pagination = raw.get('pagination') or {}
    cursor = pagination.get('next_cursor') if pagination.get('has_more', True) else None
    return [v1_row(row) for row in rows], cursor or None


def url(path, **params):
    clean = {k: v for k, v in params.items() if v is not None}
    return BASE + path.lstrip('/') + ('?' + urlencode(clean) if clean else '')


def fetch_rows(fetch, path, **params):
    """One page: rows in v1 shape and the cursor of the next page."""
    return page(fetch(url(path, **params)))


def fetch_all(fetch, path, max_pages, **params):
    """Follow the cursor. Returns (rows, complete)."""
    rows = []
    cursor = None
    for _ in range(max_pages):
        batch, cursor = fetch_rows(fetch, path, cursor=cursor, **params)
        rows.extend(batch)
        if not cursor:
            return rows, True
    return rows, False
