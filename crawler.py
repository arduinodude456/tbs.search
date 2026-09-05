import json
import os
import random
import time
from collections import deque
from datetime import datetime, timezone
from urllib import robotparser
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# KONFIGURATION
# ============================================================

# Zusätzliche feste Startseiten
START_URLS = [
    #"https://de.wikipedia.org/"
]

# Wiby als Seed-Quelle
WIBY_SURPRISE_URL = "https://wiby.me/"

# Wie viele zufällige Wiby-Seeds pro Lauf?
WIBY_SEEDS_PER_RUN = 5

# Maximale Anzahl Seiten, die dieser Lauf verarbeitet
MAX_PAGES_PER_RUN = 1000

# Maximale Linktiefe
MAX_DEPTH = 4

# Pause zwischen Requests
REQUEST_DELAY = 1.0

# Timeout
REQUEST_TIMEOUT = 20

# Index
INDEX_FILE = "sites.json"

# User-Agent
USER_AGENT = (
    "TBS-SearchBot/1.0 "
    "(compatible; "
    "+https://github.com/arduinodude456/tbs.search)"
)


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,"
        "application/xhtml+xml,"
        "application/xml;q=0.9,"
        "*/*;q=0.8"
    )
})


# ============================================================
# ROBOTS CACHE
# ============================================================

robots_cache = {}


# ============================================================
# STATISTIK
# ============================================================

stats = {
    "processed": 0,
    "updated": 0,
    "unchanged": 0,
    "errors": 0,
    "robots": 0,
    "forbidden": 0,
    "rate_limited": 0,
    "discovered": 0,
    "wiby_seeds": 0,
}


# ============================================================
# ZEIT
# ============================================================

def utc_now():

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

    try:

        url, _ = urldefrag(url)

        parsed = urlparse(url)

        if parsed.scheme not in (
            "http",
            "https"
        ):
            return None

        if not parsed.hostname:
            return None

        hostname = parsed.hostname.lower()

        # Standardports entfernen
        if (
            (parsed.scheme == "http" and parsed.port == 80)
            or
            (parsed.scheme == "https" and parsed.port == 443)
        ):
            netloc = hostname
        else:
            netloc = parsed.netloc.lower()

        result = (
            parsed.scheme.lower()
            + "://"
            + netloc
            + parsed.path
        )

        if parsed.query:
            result += "?" + parsed.query

        return result

    except Exception:

        return None


# ============================================================
# ROBOTS.TXT
# ============================================================

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


    try:

        response = session.get(
            robots_url,
            timeout=REQUEST_TIMEOUT
        )


        # ----------------------------------------------------
        # KEINE ROBOTS.TXT
        # ----------------------------------------------------

        if response.status_code == 404:

            parser = robotparser.RobotFileParser()

            parser.set_url(
                robots_url
            )

            # Keine Regeln
            parser.parse([])

            robots_cache[origin] = parser

            print(
                "Keine robots.txt:",
                origin
            )

            return parser


        # ----------------------------------------------------
        # SERVERFEHLER
        # ----------------------------------------------------

        if response.status_code >= 500:

            print(
                "robots.txt momentan nicht erreichbar:",
                robots_url,
                response.status_code
            )

            robots_cache[origin] = None

            return None


        # ----------------------------------------------------
        # SONSTIGE FEHLER
        # ----------------------------------------------------

        if response.status_code >= 400:

            print(
                "robots.txt HTTP-Fehler:",
                robots_url,
                response.status_code
            )

            robots_cache[origin] = None

            return None


        # ----------------------------------------------------
        # ROBOTS PARSEN
        # ----------------------------------------------------

        parser = robotparser.RobotFileParser()

        parser.set_url(
            robots_url
        )

        parser.parse(
            response.text.splitlines()
        )

        robots_cache[origin] = parser

        return parser


    except requests.RequestException as error:

        print(
            "robots.txt Fehler:",
            robots_url
        )

        print(error)

        robots_cache[origin] = None

        return None


def can_fetch(url):

    parser = get_robots_parser(url)

    if parser is None:
        return False

    try:

        allowed = parser.can_fetch(
            USER_AGENT,
            url
        )

        if not allowed:

            print(
                "ROBOTS BLOCK:",
                url
            )

        return allowed

    except Exception:

        return False


# ============================================================
# WIBY SURPRISE
# ============================================================

WIBY_SURPRISE_URL = "https://wiby.me/surprise/"


def get_wiby_surprise():

    try:

        response = session.get(
            WIBY_SURPRISE_URL,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        print(
            "Wiby HTTP:",
            response.status_code
        )

        response.raise_for_status()


        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )


        # ----------------------------------------------------
        # Alle Links untersuchen
        # ----------------------------------------------------

        candidates = []

        for anchor in soup.find_all(
            "a",
            href=True
        ):

            href = anchor.get(
                "href",
                ""
            ).strip()

            text = anchor.get_text(
                " ",
                strip=True
            ).lower()


            if not href:
                continue


            absolute = normalize_url(
                urljoin(
                    response.url,
                    href
                )
            )


            if not absolute:
                continue


            hostname = urlparse(
                absolute
            ).hostname


            if not hostname:
                continue


            # Wiby selbst ignorieren
            if hostname.lower() in (
                "wiby.me",
                "www.wiby.me"
            ):
                continue


            # Nur HTTP(S)
            if not absolute.startswith(
                ("http://", "https://")
            ):
                continue


            candidates.append(
                absolute
            )


        # ----------------------------------------------------
        # Doppelte entfernen
        # ----------------------------------------------------

        candidates = list(
            dict.fromkeys(
                candidates
            )
        )


        # ----------------------------------------------------
        # Ergebnis
        # ----------------------------------------------------

        if candidates:

            seed = random.choice(
                candidates
            )

            print(
                "Wiby Surprise Seed:",
                seed
            )

            return seed


        print(
            "Wiby: Keine externe URL gefunden."
        )

        return None


    except Exception as error:

        print(
            "Wiby Surprise Fehler:"
        )

        print(
            repr(error)
        )

        return None


def get_wiby_seeds():

    seeds = set()

    print()
    print(
        "Hole Wiby-Surprise-Seeds..."
    )


    attempts = 0

    max_attempts = max(
        WIBY_SEEDS_PER_RUN * 3,
        3
    )


    while (
        len(seeds)
        < WIBY_SEEDS_PER_RUN
        and
        attempts
        < max_attempts
    ):

        attempts += 1

        print(
            f"Wiby Versuch "
            f"{attempts}/{max_attempts}"
        )


        seed = get_wiby_surprise()


        if seed:

            if seed not in seeds:

                seeds.add(
                    seed
                )

                stats[
                    "wiby_seeds"
                ] += 1


        time.sleep(
            REQUEST_DELAY
        )


    print()
    print(
        "Wiby Seeds gefunden:",
        len(seeds)
    )


    return list(seeds)


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
            "version": 4,
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
                "sites.json ist kein Objekt."
            )


        if not isinstance(
            data.get("pages"),
            list
        ):

            data["pages"] = []


        return data


    except Exception as error:

        print(
            "Fehler beim Laden von sites.json:"
        )

        print(error)

        raise


# ============================================================
# INDEX MAP
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
# CACHE HEADERS
# ============================================================

def get_cache_headers(
    old_page
):

    headers = {}

    if not old_page:
        return headers


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
# HTTP REQUEST
# ============================================================

def fetch_page(
    url,
    old_page=None
):

    # --------------------------------------------------------
    # ROBOTS
    # --------------------------------------------------------

    if not can_fetch(url):

        stats["robots"] += 1

        return {
            "status": "robots"
        }


    headers = get_cache_headers(
        old_page
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
            "Request-Fehler:",
            url
        )

        print(error)

        return {
            "status": "error"
        }


    # --------------------------------------------------------
    # 304
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
    # 429
    # --------------------------------------------------------

    if response.status_code == 429:

        print(
            "429 Too Many Requests:",
            url
        )

        retry_after = response.headers.get(
            "Retry-After"
        )

        if retry_after:

            print(
                "Retry-After:",
                retry_after
            )

        stats[
            "rate_limited"
        ] += 1

        return {
            "status": "rate_limited"
        }


    # --------------------------------------------------------
    # 403
    # --------------------------------------------------------

    if response.status_code == 403:

        print(
            "403 Forbidden:",
            url
        )

        stats[
            "forbidden"
        ] += 1

        return {
            "status": "forbidden"
        }


    # --------------------------------------------------------
    # SONSTIGE HTTP-FEHLER
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
    # CONTENT TYPE
    # --------------------------------------------------------

    content_type = response.headers.get(
        "Content-Type",
        ""
    ).lower()


    if "text/html" not in content_type:

        print(
            "Nicht-HTML übersprungen:",
            url
        )

        return {
            "status": "not_html"
        }


    # --------------------------------------------------------
    # FINALE URL
    # --------------------------------------------------------

    final_url = normalize_url(
        response.url
    )

    if not final_url:

        return {
            "status": "error"
        }


    return {
        "status": "ok",
        "url": final_url,
        "html": response.text,
        "etag": response.headers.get(
            "ETag"
        ),
        "last_modified": response.headers.get(
            "Last-Modified"
        )
    }


# ============================================================
# HTML PARSEN
# ============================================================

def clean_text(
    text
):

    return " ".join(
        text.split()
    ).strip()


def parse_page(
    url,
    html
):

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

    tag = soup.find(
        "meta",
        attrs={
            "name": "description"
        }
    )

    if tag:

        description = clean_text(
            tag.get(
                "content",
                ""
            )
        )


    # --------------------------------------------------------
    # KEYWORDS
    # --------------------------------------------------------

    keywords = ""

    tag = soup.find(
        "meta",
        attrs={
            "name": "keywords"
        }
    )

    if tag:

        keywords = clean_text(
            tag.get(
                "content",
                ""
            )
        )


    # --------------------------------------------------------
    # HEADINGS
    # --------------------------------------------------------

    headings = []

    for heading in soup.find_all([
        "h1",
        "h2",
        "h3"
    ]):

        text = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if text:

            headings.append(
                text
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


    # Maximale Indexgröße
    text = text[:50000]


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

        absolute = normalize_url(
            urljoin(
                url,
                href
            )
        )

        if not absolute:
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
# SEITE VERARBEITEN
# ============================================================

def process_page(
    page_map,
    url
):

    old_page = page_map.get(
        url
    )


    result = fetch_page(
        url,
        old_page
    )


    status = result[
        "status"
    ]


    # --------------------------------------------------------
    # 304
    # --------------------------------------------------------

    if status == "not_modified":

        if old_page:

            old_page[
                "checked"
            ] = utc_now()

        stats[
            "unchanged"
        ] += 1

        return []


    # --------------------------------------------------------
    # FEHLER
    # --------------------------------------------------------

    if status != "ok":

        stats[
            "errors"
        ] += 1

        return []


    # --------------------------------------------------------
    # PARSEN
    # --------------------------------------------------------


    final_url = result[
        "url"
    ]


    parsed = parse_page(
        final_url,
        result["html"]
    )


    now = utc_now()


    # --------------------------------------------------------
    # Metadaten
    # --------------------------------------------------------

    if old_page:

        indexed = old_page.get(
            "indexed",
            now
        )

    else:

        indexed = now


    parsed[
        "indexed"
    ] = indexed

    parsed[
        "updated"
    ] = now

    parsed[
        "checked"
    ] = now

    parsed[
        "etag"
    ] = result.get(
        "etag"
    )

    parsed[
        "last_modified"
    ] = result.get(
        "last_modified"
    )


    # Links nicht im Index speichern
    links = parsed.pop(
        "links",
        []
    )


    page_map[
        final_url
    ] = parsed


    # Redirect bereinigen

    if (
        old_page
        and final_url != url
        and url in page_map
    ):

        del page_map[url]


    stats[
        "updated"
    ] += 1


    print(
        "Indexiert:",
        final_url
    )


    return links


# ============================================================
# INDEX SPEICHERN
# ============================================================

def save_index(
    data,
    page_map
):

    data[
        "version"
    ] = 4

    data[
        "generated"
    ] = utc_now()

    data[
        "pages"
    ] = list(
        page_map.values()
    )


    temporary_file = (
        INDEX_FILE
        + ".tmp"
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
            indent=2
        )


    os.replace(
        temporary_file,
        INDEX_FILE
    )


# ============================================================
# CRAWL
# ============================================================

def crawl():

    print()
    print(
        "========================================"
    )

    print(
        "TBS Search Crawler v4"
    )

    print(
        "Incremental + Wiby Surprise"
    )

    print(
        "========================================"
    )


    # --------------------------------------------------------
    # Index
    # --------------------------------------------------------

    data = load_index()

    page_map = build_page_map(
        data
    )


    print(
        "Bereits indexiert:",
        len(page_map)
    )


    # --------------------------------------------------------
    # Queue
    # --------------------------------------------------------

    queue = deque()

    queued = set()


    # --------------------------------------------------------
    # Feste Startseiten
    # --------------------------------------------------------

    for start_url in START_URLS:

        url = normalize_url(
            start_url
        )

        if not url:
            continue

        if url in queued:
            continue

        queue.append(
            (
                url,
                0
            )
        )

        queued.add(
            url
        )


    # --------------------------------------------------------
    # Wiby Seeds
    # --------------------------------------------------------

    wiby_seeds = get_wiby_seeds()


    for seed in wiby_seeds:

        if seed in queued:
            continue

        queue.append(
            (
                seed,
                0
            )
        )

        queued.add(
            seed
        )


    print()
    print(
        "Seeds insgesamt:",
        len(queue)
    )


    # --------------------------------------------------------
    # CRAWL
    # --------------------------------------------------------

    while queue:

        url, depth = queue.popleft()


        if stats[
            "processed"
        ] >= MAX_PAGES_PER_RUN:

            print()
            print(
                "MAX_PAGES_PER_RUN erreicht."
            )

            break


        stats[
            "processed"
        ] += 1


        print()
        print(
            "----------------------------------------"
        )

        print(
            f"["
            f"{stats['processed']}/"
            f"{MAX_PAGES_PER_RUN}"
            f"] "
            f"Depth={depth}"
        )

        print(
            url
        )


        links = process_page(
            page_map,
            url
        )


        # ----------------------------------------------------
        # Tiefe erreicht
        # ----------------------------------------------------

        if depth >= MAX_DEPTH:

            time.sleep(
                REQUEST_DELAY
            )

            continue


        # ----------------------------------------------------
        # Neue Links
        # ----------------------------------------------------

        for link in links:

            if link in queued:
                continue


            # Bereits indexierte URLs müssen nicht
            # als neuer Crawl eingeplant werden.
            #
            # Sie bleiben im Index und werden bei
            # zukünftigen Läufen über ETag /
            # Last-Modified aktualisiert.

            if link in page_map:
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

            stats[
                "discovered"
            ] += 1


        time.sleep(
            REQUEST_DELAY
        )


    # --------------------------------------------------------
    # Speichern
    # --------------------------------------------------------

    save_index(
        data,
        page_map
    )


    # --------------------------------------------------------
    # Statistik
    # --------------------------------------------------------

    print()
    print(
        "========================================"
    )

    print(
        "CRAWLER ABGESCHLOSSEN"
    )

    print(
        "========================================"
    )

    print(
        "Verarbeitet:",
        stats["processed"]
    )

    print(
        "Aktualisiert:",
        stats["updated"]
    )

    print(
        "Unverändert (304):",
        stats["unchanged"]
    )

    print(
        "Robots blockiert:",
        stats["robots"]
    )

    print(
        "403 Forbidden:",
        stats["forbidden"]
    )

    print(
        "Rate Limited:",
        stats["rate_limited"]
    )

    print(
        "Sonstige Fehler:",
        stats["errors"]
    )

    print(
        "Neue URLs entdeckt:",
        stats["discovered"]
    )

    print(
        "Wiby Seeds:",
        stats["wiby_seeds"]
    )

    print(
        "Gesamt im Index:",
        len(page_map)
    )

    print(
        "========================================"
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    crawl()

    # --------------------------------------------------------
    # Metadaten
 
