import csv
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED = "https://nvidianews.nvidia.com/rss.xml"
OUTPUT = Path("data/news/nvda_events.csv")
FIELDS = [
    "published_at_utc", "source", "category",
    "headline", "url", "verified"
]


def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if OUTPUT.exists():
        with OUTPUT.open(
            encoding="utf-8-sig", newline=""
        ) as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != FIELDS:
                raise ValueError("Unexpected CSV columns")
            existing = list(reader)

    known = {
        row["url"] for row in existing if row["url"]
    }

    request = urllib.request.Request(
        FEED,
        headers={
            "User-Agent": "USStockResearch/1.0"
        }
    )
    with urllib.request.urlopen(
        request, timeout=30
    ) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    added = 0

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        published = parse_date(
            item.findtext("pubDate")
        )

        if not title or not url or not published:
            continue
        if url in known:
            continue

        categories = [
            (c.text or "").strip()
            for c in item.findall("category")
            if (c.text or "").strip()
        ]

        existing.append({
            "published_at_utc": published,
            "source": "NVIDIA Newsroom RSS",
            "category": (
                "; ".join(categories)
                if categories else "company_news"
            ),
            "headline": title,
            "url": url,
            "verified": "source_metadata_only",
        })
        known.add(url)
        added += 1

    existing.sort(
        key=lambda row: (
            row["published_at_utc"], row["url"]
        )
    )

    with OUTPUT.open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=FIELDS
        )
        writer.writeheader()
        writer.writerows(existing)

    print(
        f"Added {added} news items; "
        f"total {len(existing)}"
    )


if __name__ == "__main__":
    main()
