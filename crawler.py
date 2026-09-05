import json
import re
import time
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup


# =========================
# EINSTELLUNGEN
# =========================

START_URLS = [
    "https://example.com/"
]

MAX_PAGES = 100
MAX_DEPTH = 3

OUTPUT_FILE = "sites.json"

USER_AGENT = "MySimpleSearchBot/1.0"


# =========================
# HILFSFUNKTIONEN
# =========================

def normalize_url(url):
    """Entfernt #fragmente und bereinigt die URL."""

    url, _ = urldefrag(url)

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return None

    return url


def extract_text(soup):
    """Extrahiert sichtbaren Text."""

    for element in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "nav",
        "footer"
    ]):
        element.decompose()

    text = soup.get_text(" ", strip=True)

    # Mehrfache Leerzeichen entfernen
    text = re.sub(r"\s+", " ", text)

    return text


def crawl_page(url):
    """Lädt und analysiert eine Webseite."""

    headers = {
        "User-Agent": USER_AGENT
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

    except requests.RequestException as error:
        print(f"Fehler: {url}")
        print(error)

        return None

    content_type = response.headers.get(
        "content-type",
        ""
    )

    if "text/html" not in content_type:
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # Titel
    title = ""

    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

    # Beschreibung
    description = ""

    description_tag = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    if description_tag:
        description = description_tag.get(
            "content",
            ""
        )

    # Text
    text = extract_text(soup)

    # Nicht zu große Datenbank erzeugen
    text = text[:20000]

    # Links extrahieren
    links = []

    for tag in soup.find_all(
        "a",
        href=True
    ):

        absolute_url = urljoin(
            url,
            tag["href"]
        )

        absolute_url = normalize_url(
            absolute_url
        )

        if absolute_url:
            links.append(
                absolute_url
            )

    return {
        "url": url,
        "title": title,
        "description": description,
        "text": text,
        "links": list(set(links))
    }


# =========================
# CRAWLER
# =========================

def crawl():

    queue = deque()

    visited = set()

    indexed_sites = []

    # Startseiten hinzufügen

    for url in START_URLS:

        normalized = normalize_url(url)

        if normalized:
            queue.append(
                (normalized, 0)
            )


    while queue and len(indexed_sites) < MAX_PAGES:

        url, depth = queue.popleft()

        if url in visited:
            continue

        visited.add(url)

        print(
            f"[{len(indexed_sites) + 1}/{MAX_PAGES}] "
            f"Crawle: {url}"
        )

        page = crawl_page(url)

        if not page:
            continue

        # Seite für Suchindex speichern

        indexed_sites.append({
            "url": page["url"],
            "title": page["title"],
            "description": page["description"],
            "text": page["text"]
        })

        # Neue Links hinzufügen

        if depth < MAX_DEPTH:

            for link in page["links"]:

                if link not in visited:

                    queue.append(
                        (link, depth + 1)
                    )

        # Höflichkeitspause

        time.sleep(1)


    # JSON-Datei schreiben

    data = {
        "pages": indexed_sites
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


    print()
    print(
        f"Fertig! "
        f"{len(indexed_sites)} Seiten "
        f"wurden indexiert."
    )


if __name__ == "__main__":
    crawl()
