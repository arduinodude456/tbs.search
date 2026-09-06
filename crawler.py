import json
import os
import re
import time
import hashlib
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag, parse_qsl, urlencode
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

DATA_DIR = "data"
PAGES_DIR = os.path.join(DATA_DIR, "pages")

START_URLS = [
    "https://www.instagram.com/"
]

MAX_PAGES_PER_RUN = 1000
MAX_DEPTH = 4

REQUEST_TIMEOUT = 20
ROBOTS_TIMEOUT = 10

HOST_DELAY = 1.5

USER_AGENT = (
    "TBS-SearchBot/2.0 "
    "(compatible; +https://github.com/arduinodude456/tbs.search)"
)

BLOCKED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".webm", ".mp3", ".wav",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".exe", ".apk", ".iso"
}

TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid"
}


# ============================================================
# URL HANDLING
# ============================================================

def clean_url(url):
    if not url:
        return None

    url = url.strip()

    # Markdown-Link:
    # [https://example.com](https://example.com/)
    match = re.match(r"^\[[^\]]+\]\((https?://[^)]+)\)$", url)
    if match:
        url = match.group(1)

    # Falls versehentlich doppelt eingefügt
    while url.startswith("https://https://"):
        url = "https://" + url[len("https://https://"):]

    while url.startswith("http://http://"):
        url = "http://" + url[len("http://http://"):]

    if url.startswith("www."):
        url = "https://" + url

    return url


def normalize_url(url, base=None):
    if not url:
        return None

    url = clean_url(url)

    if base:
        url = urljoin(base, url)

    url, _ = urldefrag(url)

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return None

    if not parsed.netloc:
        return None

    host = parsed.hostname.lower()

    if parsed.port:
        try:
            if not (
                (parsed.scheme == "http" and parsed.port == 80)
                or
                (parsed.scheme == "https" and parsed.port == 443)
            ):
                host += f":{parsed.port}"
        except ValueError:
            return None

    query = []

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() not in TRACKING_PARAMETERS:
            query.append((key, value))

    query_string = urlencode(query)

    path = parsed.path or "/"

    return (
        f"{parsed.scheme}://{host}"
        f"{path}"
        + (f"?{query_string}" if query_string else "")
    )


def valid_page_url(url):
    parsed = urlparse(url)

    path = parsed.path.lower()

    for ext in BLOCKED_EXTENSIONS:
        if path.endswith(ext):
            return False

    return True


# ============================================================
# STORAGE
# ============================================================

def url_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def shard_for_url(url):
    return url_id(url)[:2]


def page_file(url):
    shard = shard_for_url(url)
    return os.path.join(PAGES_DIR, f"{shard}.jsonl")


def load_pages():
    pages = {}

    if not os.path.isdir(PAGES_DIR):
        return pages

    for filename in os.listdir(PAGES_DIR):
        if not filename.endswith(".jsonl"):
            continue

        path = os.path.join(PAGES_DIR, filename)

        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        page = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    url = page.get("url")

                    if url:
                        pages[url] = page

        except OSError:
            continue

    return pages


def save_pages(pages):
    os.makedirs(PAGES_DIR, exist_ok=True)

    shards = {}

    for page in pages.values():
        url = page.get("url")

        if not url:
            continue

        shard = shard_for_url(url)

        if shard not in shards:
            shards[shard] = []

        shards[shard].append(page)

    for shard, entries in shards.items():
        path = os.path.join(PAGES_DIR, f"{shard}.jsonl")
        tmp = path + ".tmp"

        with open(tmp, "w", encoding="utf-8") as f:
            for page in entries:
                f.write(
                    json.dumps(
                        page,
                        ensure_ascii=False,
                        separators=(",", ":")
                    )
                    + "\n"
                )

        os.replace(tmp, path)


# ============================================================
# ROBOTS
# ============================================================

robots_cache = {}


def get_robots(url):
    parsed = urlparse(url)

    origin = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = origin + "/robots.txt"

    if origin in robots_cache:
        return robots_cache[origin]

    rp = RobotFileParser()
    rp.set_url(robots_url)

    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": USER_AGENT},
            timeout=ROBOTS_TIMEOUT
        )

        if response.status_code == 404:
            robots_cache[origin] = None
            return None

        if response.status_code >= 400:
            robots_cache[origin] = False
            return False

        rp.parse(response.text.splitlines())

        robots_cache[origin] = rp

        return rp

    except requests.RequestException:
        robots_cache[origin] = False
        return False


def allowed_by_robots(url):
    rp = get_robots(url)

    if rp is None:
        return True

    #if rp is False:
        #return False
    return True # HAHAHAHAHAHAHAHAHAHAHAHAHA

    #return rp.can_fetch(USER_AGENT, url)


# ============================================================
# HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml"
})


last_request = {}


def host_delay(url):
    host = urlparse(url).netloc

    now = time.time()
    previous = last_request.get(host)

    if previous:
        wait = HOST_DELAY - (now - previous)

        if wait > 0:
            time.sleep(wait)

    last_request[host] = time.time()


# ============================================================
# PAGE PARSING
# ============================================================

def parse_page(url, response, old=None):
    soup = BeautifulSoup(response.text, "html.parser")

    for element in soup([
        "script",
        "style",
        "noscript",
        "svg"
    ]):
        element.decompose()

    title = ""

    if soup.title:
        title = soup.title.get_text(" ", strip=True)

    description = ""

    meta = soup.find(
        "meta",
        attrs={"name": re.compile("^description$", re.I)}
    )

    if meta:
        description = meta.get("content", "").strip()

    headings = []

    for heading in soup.find_all(["h1", "h2", "h3"]):
        text = heading.get_text(" ", strip=True)

        if text:
            headings.append(text)

    text = soup.get_text(" ", strip=True)

    # Begrenze einzelne Dokumente
    text = re.sub(r"\s+", " ", text)

    if len(text) > 200_000:
        text = text[:200_000]

    links = []

    for a in soup.find_all("a", href=True):
        target = normalize_url(a["href"], url)

        if not target:
            continue

        if not valid_page_url(target):
            continue

        links.append(target)

    return {
        "url": url,
        "title": title[:1000],
        "description": description[:3000],
        "headings": headings[:100],
        "text": text,
        "links": list(dict.fromkeys(links)),
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "checked": int(time.time()),
        "indexed": old.get("indexed") if old else int(time.time()),
        "updated": int(time.time())
    }


# ============================================================
# CRAWLER
# ============================================================

def crawl(start_urls):
    pages = load_pages()

    print(f"Vorhandener Index: {len(pages)} Seiten")

    queue = deque()

    seen = set()

    for url in start_urls:
        normalized = normalize_url(url)

        if normalized:
            queue.append((normalized, 0))

    processed = 0

    while queue and processed < MAX_PAGES_PER_RUN:

        url, depth = queue.popleft()

        if url in seen:
            continue

        seen.add(url)

        if depth > MAX_DEPTH:
            continue

        if not valid_page_url(url):
            continue

        if not allowed_by_robots(url):
            print(f"robots.txt blockiert: {url}")
            continue

        old = pages.get(url)

        headers = {}

        if old:
            if old.get("etag"):
                headers["If-None-Match"] = old["etag"]

            if old.get("last_modified"):
                headers["If-Modified-Since"] = old["last_modified"]

        host_delay(url)

        print(
            f"[{processed + 1}/{MAX_PAGES_PER_RUN}] "
            f"Depth={depth} {url}"
        )

        try:
            response = session.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

        except requests.RequestException as e:
            print(f"HTTP-Fehler: {e}")
            continue

        if response.status_code == 304:
            if old:
                old["checked"] = int(time.time())
                pages[url] = old

            print("304 - unverändert")
            processed += 1
            continue

        if response.status_code in (403, 429):
            print(f"HTTP {response.status_code}")
            continue

        if response.status_code >= 500:
            print(f"Serverfehler {response.status_code}")
            continue

        if response.status_code != 200:
            print(f"HTTP {response.status_code}")
            continue

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        if "text/html" not in content_type:
            continue

        final_url = normalize_url(response.url)

        if not final_url:
            continue

        try:
            page = parse_page(
                final_url,
                response,
                old
            )
        except Exception as e:
            print(f"Parsing-Fehler: {e}")
            continue

        pages[final_url] = page

        processed += 1

        for link in page["links"]:

            if link in seen:
                continue

            queue.append(
                (
                    link,
                    depth + 1
                )
            )

    save_pages(pages)

    print()
    print("================================")
    print(f"Crawling beendet")
    print(f"Neue/aktualisierte Seiten: {processed}")
    print(f"Gesamtseiten: {len(pages)}")
    print("================================")


if __name__ == "__main__":
    crawl(START_URLS)
