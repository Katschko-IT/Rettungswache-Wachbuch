import calendar
import csv
import hashlib
import ipaddress
import io
import socket
from datetime import datetime, timezone as datetime_timezone
from urllib.parse import urlparse

import certifi
import feedparser
import urllib3
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from .models import FeedItem, FeedSource


def fetch_source(source):
    parsed_url = urlparse(source.url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname not in settings.FEED_ALLOWED_HOSTS
        or parsed_url.username
        or parsed_url.password
    ):
        raise ValueError("Quelle ist nicht in der erlaubten HTTPS-Hostliste.")
    if parsed_url.port not in {None, 443}:
        raise ValueError("Feed-Quellen dürfen nur HTTPS-Port 443 verwenden.")
    resolved = socket.getaddrinfo(parsed_url.hostname, 443, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(item[4][0] for item in resolved))
    if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise ValueError("Feed-Quelle zeigt nicht ausschließlich auf globale IP-Adressen.")
    target = parsed_url.path or "/"
    if parsed_url.query:
        target = f"{target}?{parsed_url.query}"
    timeout = urllib3.Timeout(connect=5, read=20)
    connection_error = None
    for address in addresses:
        pool = urllib3.HTTPSConnectionPool(
            address,
            port=443,
            assert_hostname=parsed_url.hostname,
            server_hostname=parsed_url.hostname,
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(),
            timeout=timeout,
            maxsize=1,
        )
        try:
            response = pool.request(
                "GET",
                target,
                headers={
                    "Host": parsed_url.hostname,
                    "User-Agent": "Wachbuch/1.0",
                },
                preload_content=False,
                redirect=False,
                retries=False,
            )
        except urllib3.exceptions.HTTPError as exc:
            connection_error = exc
            pool.close()
            continue
        try:
            if 300 <= response.status < 400:
                raise ValueError("Weiterleitungen sind für Feed-Quellen deaktiviert.")
            if response.status >= 400:
                raise ValueError(f"Quelle antwortet mit HTTP {response.status}.")
            content = bytearray()
            for chunk in response.stream(64 * 1024):
                content.extend(chunk)
                if len(content) > settings.FEED_MAX_BYTES:
                    raise ValueError("Quelle überschreitet das Größenlimit.")
            return bytes(content)
        finally:
            response.release_conn()
            pool.close()
    raise ValueError(f"Feed-Quelle ist nicht erreichbar: {connection_error}")


def sync_source(source):
    try:
        payload = fetch_source(source)
        if source.kind == FeedSource.Kind.NEWS_RSS:
            count = sync_rss(source, payload)
        elif source.kind == FeedSource.Kind.CLOSURE_CSV:
            count = sync_closure_csv(source, payload)
        else:
            raise ValueError("Unbekannter Quelltyp.")
        source.last_success_at = timezone.now()
        source.last_error = ""
        source.save(update_fields=["last_success_at", "last_error"])
        return count
    except Exception as exc:
        source.last_error_at = timezone.now()
        source.last_error = str(exc)[:300]
        source.save(update_fields=["last_error_at", "last_error"])
        raise


def upsert_feed_item(source, external_id, **fields):
    now = timezone.now()
    item, created = FeedItem.objects.get_or_create(
        source=source,
        external_id=external_id,
        defaults={
            **fields,
            "first_imported_at": now,
            "last_seen_at": now,
        },
    )
    if not created:
        for key, value in fields.items():
            setattr(item, key, value)
        item.last_seen_at = now
        item.save()
    return item, created


@transaction.atomic
def sync_rss(source, payload):
    parsed = feedparser.parse(payload)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"RSS konnte nicht gelesen werden: {parsed.bozo_exception}")
    count = 0
    for entry in parsed.entries[:100]:
        link = safe_item_url(str(entry.get("link", "")))
        external_id = str(entry.get("id") or link or hashlib.sha256(
            str(entry.get("title", "")).encode("utf-8")
        ).hexdigest())[:300]
        published = None
        if entry.get("published_parsed"):
            published = datetime.fromtimestamp(
                calendar.timegm(entry.published_parsed), tz=datetime_timezone.utc
            )
        upsert_feed_item(
            source,
            external_id,
            title=strip_tags(str(entry.get("title", "")))[:300],
            summary=strip_tags(str(entry.get("summary", "")))[:1500],
            url=link[:600],
            published_at=published,
        )
        count += 1
    return count


def safe_item_url(value):
    parsed = urlparse(value)
    if (
        parsed.scheme == "https"
        and parsed.hostname in settings.FEED_ALLOWED_HOSTS
        and parsed.port in {None, 443}
    ):
        return value[:600]
    return ""


@transaction.atomic
def sync_closure_csv(source, payload):
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    expected = {"gid", "strasse", "beginn", "ende", "art_arb"}
    if not reader.fieldnames or not expected.issubset(set(reader.fieldnames)):
        raise ValueError("CSV-Schema der Verkehrsmeldungen ist unerwartet.")
    seen = []
    count = 0
    for row in reader:
        external_id = str(row.get("gid", "")).strip()
        if not external_id:
            continue
        seen.append(external_id)
        street = row.get("strasse", "").strip() or "Verkehrsmeldung"
        district = row.get("ortsteil", "").strip()
        title = f"{street} - {district}" if district else street
        summary_parts = [
            row.get("art_arb", "").strip(),
            row.get("art_vb", "").strip(),
            row.get("vonbis", "").strip(),
        ]
        upsert_feed_item(
            source,
            external_id,
            title=title[:300],
            summary=" | ".join(part for part in summary_parts if part)[:1500],
            url="https://open-data.bielefeld.de/dataset/verkehrsmeldungen",
            starts_on=parse_csv_date(row.get("beginn")),
            ends_on=parse_csv_date(row.get("ende")),
        )
        count += 1
    source.items.exclude(external_id__in=seen).delete()
    return count


def parse_csv_date(value):
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y/%m/%d").date()
