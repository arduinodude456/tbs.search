import json
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from urllib import robotparser

import requests
from bs4 import BeautifulSoup


# ============================================================
# KONFIGURATION
# ============================================================

START_URLS = [
    "https://de.wikipedia.org/"
]

# Maximale Anzahl NEUER/AKTUALISIERTER Seiten pro Lauf
MAX_PAGES_PER_RUN = 1000

# Maximale Linktiefe
MAX_DEPTH = 3

# Pause zwischen Requests
REQUEST_DELAY = 1.0

# HTTP Timeout
REQUEST_TIMEOUT = 20

# Bestehender Index
INDEX_FILE = "sites.json"

# User-Agent
USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; TBSSearchBot/1.0; "
    "+https://github.com/arduinodude456/tbs.search)"
)


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml"
})


# ============================================================
# ZEIT
# ============================================================

def utc_now():
    """
    Aktuelle UTC-Zeit im ISO-8601-Format.
    """

    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ============================================================
# URL NORMALISIERUNG
# ============================================================

def normalize_url(url):

    if not url:
        return None

    # Fragment entfernen
    url, _ = urldefrag(url)

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if parsed.scheme not in (
        "http",
        "https"
    ):
        return None

    if not parsed.netloc:
        return None

    # Hostname vereinheitlichen
    hostname = parsed.hostname

    if not hostname:
        return None

    hostname = hostname.lower()

    # Standardports entfernen
    port = parsed.port

    if (
        (parsed.scheme == "http" and port == 80)
        or
        (parsed.scheme == "https" and port == 443)
    ):
        netloc = hostname
    else:
        netloc = parsed.netloc.lower()

    # URL neu zusammensetzen
    normalized = (
        parsed.scheme.lower()
        + "://"
        + netloc
        + parsed.path
    )

    if parsed.query:
        normalized += "?" + parsed.query

    return normalized


# ============================================================
# ERLAUBTE DOMAINS
# ============================================================

ALLOWED_DOMAINS = set()


def initialize_domains():

    global ALLOWED_DOMAINS

    ALLOWED_DOMAINS = set()

    for start in START_URLS:

        normalized = normalize_url(start)

        if not normalized:
            continue

        hostname = urlparse(
            normalized
        ).hostname

        if hostname:
            ALLOWED_DOMAINS.add(
                hostname.lower()
            )


def is_allowed_domain(url):

    hostname = urlparse(
        url
    ).hostname

    if not hostname:
        return False

    hostname = hostname.lower()

    return hostname in ALLOWED_DOMAINS


# ============================================================
# ROBOTS.TXT
# ============================================================

robots_cache = {}


def get_robots_parser(url):

    parsed = urlparse(url)

    origin = (
        parsed.scheme
        + "://"
        + parsed.netloc
    )

    robots_url = origin + "/robots.txt"

    if origin in robots_cache:
        return robots_cache[origin]

    parser = robotparser.RobotFileParser()

    parser.set_url(
        robots_url
    )

    try:

        parser.read()

        robots_cache[origin] = parser

        return parser

    except Exception as error:

        print(
            f"robots.txt konnte nicht geladen werden: "
            f"{robots_url}"
        )

        print(error)

        # Bei einem technischen Fehler
        # wird der Zugriff nicht automatisch
        # blockiert.

        robots_cache[origin] = None

        return None


def can_fetch(url):

    parser = get_robots_parser(url)

    if parser is None:
        return True

    try:

        return parser.can_fetch(
            USER_AGENT,
            url
        )

    except Exception:

        return True


# ============================================================
# TEXT BEREINIGEN
# ============================================================

def clean_text(text):

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# HTML ANALYSIEREN
# ============================================================

def parse_page(url, html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    # --------------------------------------------------------
    # Unbrauchbare Elemente entfernen
    # --------------------------------------------------------

    for element in soup.find_all([
        "script",
        "style",
        "noscript",
        "svg",
        "canvas",
        "iframe",
        "template"
    ]):

        element.decompose()


    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = ""

    if soup.title:

        title = clean_text(
            soup.title.get_text(
                " ",
                strip=True
            )
        )


    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = ""

    description_tag = soup.find(
        "meta",
        attrs={
            "name": "description"
        }
    )

    if description_tag:

        description = clean_text(
            description_tag.get(
                "content",
                ""
            )
        )


    # --------------------------------------------------------
    # KEYWORDS
    # --------------------------------------------------------

    keywords = ""

    keywords_tag = soup.find(
        "meta",
        attrs={
            "name": "keywords"
        }
    )

    if keywords_tag:

        keywords = clean_text(
            keywords_tag.get(
                "content",
                ""
            )
        )


    # --------------------------------------------------------
    # HEADINGS
    # --------------------------------------------------------

    headings = []

    for tag in soup.find_all([
        "h1",
        "h2",
        "h3"
    ]):

        heading = clean_text(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if heading:

            headings.append(
                heading
            )


    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )


    # Indexgröße begrenzen
    text = text[:30000]


    # --------------------------------------------------------
    # LINKS
    # --------------------------------------------------------

    links = set()

    for anchor in soup.find_all(
        "a",
        href=True
    ):

        href = anchor.get(
            "href"
        )

        absolute = urljoin(
            url,
            href
        )

        absolute = normalize_url(
            absolute
        )

        if not absolute:
            continue

        if not is_allowed_domain(
            absolute
        ):
            continue

        links.add(
            absolute
        )


    return {
        "url": url,
        "title": title,
        "description": description,
        "keywords": keywords,
        "headings": headings,
        "text": text,
        "links": list(links)
    }


# ============================================================
# INDEX LADEN
# ============================================================

def load_index():

    if not os.path.exists(
        INDEX_FILE
    ):

        print(
            "Noch keine sites.json vorhanden."
        )

        return {
            "version": 2,
            "generated": "",
            "pages": []
        }


    try:

        with open(
            INDEX_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)


        if not isinstance(
            data,
            dict
        ):

            raise ValueError(
                "Index ist kein JSON-Objekt."
            )


        if not isinstance(
            data.get("pages"),
            list
        ):

            data["pages"] = []


        return data


    except Exception as error:

        print(
            "FEHLER beim Laden von sites.json:"
        )

        print(error)

        raise


# ============================================================
# INDEX IN DICTIONARY UMWANDELN
# ============================================================

def build_page_map(data):

    page_map = {}

    for page in data.get(
        "pages",
        []
    ):

        if not isinstance(
            page,
            dict
        ):
            continue

        url = normalize_url(
            page.get("url")
        )

        if not url:
            continue

        page["url"] = url

        page_map[url] = page


    return page_map


# ============================================================
# HTTP CACHE HEADER
# ============================================================

def make_cache_headers(old_page):

    headers = {}


    etag = old_page.get(
        "etag"
    )

    if etag:

        headers[
            "If-None-Match"
        ] = etag


    last_modified = old_page.get(
        "last_modified"
    )

    if last_modified:

        headers[
            "If-Modified-Since"
        ] = last_modified


    return headers


# ============================================================
# SEITE HERUNTERLADEN
# ============================================================

def fetch_page(url, old_page=None):

    if not can_fetch(url):

        print(
            "robots.txt blockiert:",
            url
        )

        return {
            "status": "robots"
        }


    headers = make_cache_headers(
        old_page or {}
    )


    try:

        response = session.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )


    except requests.RequestException as error:

        print(
            "HTTP-Fehler:",
            url
        )

        print(error)

        return {
            "status": "error"
        }


    # --------------------------------------------------------
    # 304 = NICHT GEÄNDERT
    # --------------------------------------------------------

    if response.status_code == 304:

        print(
            "304 Not Modified:",
            url
        )

        return {
            "status": "not_modified"
        }


    # --------------------------------------------------------
    # Andere HTTP-Fehler
    # --------------------------------------------------------

    if response.status_code >= 400:

        print(
            f"HTTP {response.status_code}:",
            url
        )

        return {
            "status": "error"
        }


    # --------------------------------------------------------
    # Content-Type prüfen
    # --------------------------------------------------------

    content_type = response.headers.get(
        "content-type",
        ""
    ).lower()


    if "text/html" not in content_type:

        print(
            "Übersprungen - kein HTML:",
            url
        )

        return {
            "status": "not_html"
        }


    # --------------------------------------------------------
    # Finale URL
    # --------------------------------------------------------

    final_url = normalize_url(
        response.url
    )

    if not final_url:

        return {
            "status": "error"
        }


    if not is_allowed_domain(
        final_url
    ):

        print(
            "Redirect außerhalb erlaubter Domain:",
            final_url
        )

        return {
            "status": "external"
        }


    # --------------------------------------------------------
    # Cache-Informationen
    # --------------------------------------------------------

    etag = response.headers.get(
        "ETag"
    )

    last_modified = response.headers.get(
        "Last-Modified"
    )


    return {
        "status": "ok",
        "url": final_url,
        "html": response.text,
        "etag": etag,
        "last_modified": last_modified
    }


# ============================================================
# SEITE AKTUALISIEREN
# ============================================================

def update_page(
    page_map,
    url,
    depth
):

    old_page = page_map.get(
        url
    )


    result = fetch_page(
        url,
        old_page
    )


    status = result.get(
        "status"
    )


    # --------------------------------------------------------
    # NICHT GEÄNDERT
    # --------------------------------------------------------

    if status == "not_modified":

        if old_page:

            old_page[
                "checked"
            ] = utc_now()

        return {
            "changed": False,
            "new_links": [],
            "success": True
        }


    # --------------------------------------------------------
    # NICHT ERREICHBAR
    # --------------------------------------------------------

    if status != "ok":

        return {
            "changed": False,
            "new_links": [],
            "success": False
        }


    final_url = result["url"]


    page = parse_page(
        final_url,
        result["html"]
    )


    now = utc_now()


    # Cache-Daten speichern

    page["etag"] = (
        result.get("etag")
    )

    page["last_modified"] = (
        result.get("last_modified")
    )

    page["indexed"] = (
        old_page.get(
            "indexed",
            now
        )
        if old_page
        else now
    )

    page["updated"] = now

    page["checked"] = now


    # --------------------------------------------------------
    # Bestehende Seite aktualisieren
    # --------------------------------------------------------

    page_map[final_url] = {
        "url": page["url"],
        "title": page["title"],
        "description": page["description"],
        "keywords": page["keywords"],
        "headings": page["headings"],
        "text": page["text"],
        "etag": page["etag"],
        "last_modified": page["last_modified"],
        "indexed": page["indexed"],
        "updated": page["updated"],
        "checked": page["checked"]
    }


    return {
        "changed": True,
        "new_links": page["links"],
        "success": True
    }


# ============================================================
# INDEX SPEICHERN
# ============================================================

def save_index(
    data,
    page_map
):

    pages = list(
        page_map.values()
    )


    data["version"] = 2

    data["generated"] = utc_now()

    data["pages"] = pages


    temporary_file = (
        INDEX_FILE +
        ".tmp"
    )


    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            separators=(
                ",",
                ":"
            )
        )


    # Atomarer Austausch
    os.replace(
        temporary_file,
        INDEX_FILE
    )


# ============================================================
# CRAWLER
# ============================================================

def crawl():

    print()
    print(
        "========================================"
    )
    print(
        "TBS Search - Incremental Crawler"
    )
    print(
        "========================================"
    )


    initialize_domains()


    print(
        "Erlaubte Domains:"
    )

    for domain in sorted(
        ALLOWED_DOMAINS
    ):

        print(
            " -",
            domain
        )


    # --------------------------------------------------------
    # Alten Index laden
    # --------------------------------------------------------

    data = load_index()

    page_map = build_page_map(
        data
    )


    print()
    print(
        "Bereits indexierte Seiten:",
        len(page_map)
    )


    # --------------------------------------------------------
    # Queue
    # --------------------------------------------------------

    queue = deque()

    queued = set()


    for start_url in START_URLS:

        url = normalize_url(
            start_url
        )

        if not url:
            continue

        if url not in queued:

            queue.append(
                (url, 0)
            )

            queued.add(
                url
            )


    # --------------------------------------------------------
    # Statistiken
    # --------------------------------------------------------

    processed = 0

    updated = 0

    unchanged = 0

    errors = 0

    discovered = 0


    # --------------------------------------------------------
    # CRAWL
    # --------------------------------------------------------

    while queue:

        url, depth = queue.popleft()


        if processed >= MAX_PAGES_PER_RUN:

            print()
            print(
                "Maximale Seitenzahl erreicht."
            )

            break


        print()
        print(
            f"[{processed + 1}/"
            f"{MAX_PAGES_PER_RUN}] "
            f"Depth={depth}"
        )

        print(
            url
        )


        result = update_page(
            page_map,
            url,
            depth
        )


        processed += 1


        if result["success"]:

            if result["changed"]:

                updated += 1

            else:

                unchanged += 1


        else:

            errors += 1


        # ----------------------------------------------------
        # Neue Links
        # ----------------------------------------------------

        if depth < MAX_DEPTH:

            for link in result[
                "new_links"
            ]:

                if link in queued:

                    continue


                if link in page_map:

                    # Bereits bekannte Seiten
                    # werden nicht automatisch
                    # nochmals innerhalb desselben
                    # Laufs eingeplant.

                    continue


                queue.append(
                    (
                        link,
                        depth + 1
                    )
                )

                queued.add(
                    link
                )

                discovered += 1


        time.sleep(
            REQUEST_DELAY
        )


    # --------------------------------------------------------
    # Index speichern
    # --------------------------------------------------------

    save_index(
        data,
        page_map
    )


    # --------------------------------------------------------
    # Ergebnis
    # --------------------------------------------------------

    print()
    print(
        "========================================"
    )

    print(
        "Crawler abgeschlossen."
    )

    print(
        "========================================"
    )

    print(
        "Verarbeitet:",
        processed
    )

    print(
        "Aktualisiert:",
        updated
    )

    print(
        "Unverändert (304):",
        unchanged
    )

    print(
        "Fehler:",
        errors
    )

    print(
        "Neue URLs entdeckt:",
        discovered
    )

    print(
        "Gesamt im Index:",
        len(page_map)
    )

    print(
        "Index:",
        INDEX_FILE
    )

    print(
        "========================================"
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    crawl()
