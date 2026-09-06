import json
import os
import shutil
import time
import hashlib


LEGACY_FILE = "sites.json"

DATA_DIR = "data"
PAGES_DIR = os.path.join(DATA_DIR, "pages")
BACKUP_DIR = os.path.join(DATA_DIR, "legacy-backup")


def normalize_url(url):
    if not isinstance(url, str):
        return None

    url = url.strip()

    if not url:
        return None

    return url


def shard_for_url(url):
    return hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()[:2]


def convert_entry(key, value):
    """
    Unterstützt mehrere mögliche sites.json-Formate.
    """

    # --------------------------------------------------------
    # Fall 1:
    #
    # {
    #   "https://example.com": {
    #       "title": "...",
    #       ...
    #   }
    # }
    # --------------------------------------------------------

    if isinstance(value, dict):

        url = normalize_url(
            value.get("url")
        )

        if not url:
            url = normalize_url(key)

        if not url:
            return None

        return {
            "url": url,
            "title": value.get("title", ""),
            "description": value.get(
                "description",
                ""
            ),
            "headings": value.get(
                "headings",
                []
            ),
            "text": value.get(
                "text",
                ""
            ),
            "links": value.get(
                "links",
                []
            ),
            "etag": value.get("etag"),
            "last_modified": value.get(
                "last_modified"
            ),
            "indexed": value.get(
                "indexed",
                int(time.time())
            ),
            "updated": value.get(
                "updated",
                int(time.time())
            ),
            "checked": value.get(
                "checked",
                int(time.time())
            )
        }

    # --------------------------------------------------------
    # Fall 2:
    #
    # {
    #   "url": "...",
    #   "title": "...",
    #   ...
    # }
    # --------------------------------------------------------

    if isinstance(value, str):

        url = normalize_url(value)

        if not url:
            return None

        return {
            "url": url,
            "title": "",
            "description": "",
            "headings": [],
            "text": "",
            "links": [],
            "etag": None,
            "last_modified": None,
            "indexed": int(time.time()),
            "updated": int(time.time()),
            "checked": int(time.time())
        }

    return None


def migrate():

    if not os.path.exists(LEGACY_FILE):
        raise SystemExit(
            "FEHLER: sites.json wurde nicht gefunden."
        )

    print("Lese alten Index...")

    with open(
        LEGACY_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        old_data = json.load(f)

    print(
        "Altes JSON-Format:",
        type(old_data).__name__
    )

    # --------------------------------------------------------
    # Backup
    # --------------------------------------------------------

    os.makedirs(
        BACKUP_DIR,
        exist_ok=True
    )

    backup_name = (
        "sites-"
        + time.strftime("%Y%m%d-%H%M%S")
        + ".json"
    )

    backup_path = os.path.join(
        BACKUP_DIR,
        backup_name
    )

    shutil.copy2(
        LEGACY_FILE,
        backup_path
    )

    print(
        f"Backup erstellt: {backup_path}"
    )

    # --------------------------------------------------------
    # Daten extrahieren
    # --------------------------------------------------------

    entries = []

    if isinstance(old_data, list):

        print(
            f"Alte Liste: {len(old_data)} Einträge"
        )

        for item in old_data:

            if not isinstance(item, dict):
                continue

            url = normalize_url(
                item.get("url")
            )

            if not url:
                continue

            entries.append(
                (
                    url,
                    item
                )
            )

    elif isinstance(old_data, dict):

        # Falls das JSON so aussieht:
        #
        # {
        #   "sites": [...]
        # }

        if isinstance(
            old_data.get("sites"),
            list
        ):

            print(
                "Erkanntes Format: sites-Liste"
            )

            for item in old_data["sites"]:

                if not isinstance(item, dict):
                    continue

                url = normalize_url(
                    item.get("url")
                )

                if url:
                    entries.append(
                        (
                            url,
                            item
                        )
                    )

        else:

            # URL → Daten
            #
            # {
            #   "https://example.com": {...}
            # }

            print(
                "Erkanntes Format: URL → Daten"
            )

            for key, value in old_data.items():

                converted = convert_entry(
                    key,
                    value
                )

                if converted:
                    entries.append(
                        (
                            converted["url"],
                            converted
                        )
                    )

    else:

        raise SystemExit(
            "FEHLER: Unbekanntes sites.json-Format."
        )

    print(
        f"Erkannte Seiten: {len(entries)}"
    )

    # --------------------------------------------------------
    # Ausgabeordner
    # --------------------------------------------------------

    os.makedirs(
        PAGES_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Shards erstellen
    # --------------------------------------------------------

    shards = {}

    for url, data in entries:

        page = {
            "url": url,
            "title": data.get(
                "title",
                ""
            ),
            "description": data.get(
                "description",
                ""
            ),
            "headings": data.get(
                "headings",
                []
            ),
            "text": data.get(
                "text",
                ""
            ),
            "links": data.get(
                "links",
                []
            ),
            "etag": data.get(
                "etag"
            ),
            "last_modified": data.get(
                "last_modified"
            ),
            "indexed": data.get(
                "indexed",
                int(time.time())
            ),
            "updated": data.get(
                "updated",
                int(time.time())
            ),
            "checked": data.get(
                "checked",
                int(time.time())
            )
        }

        shard = shard_for_url(url)

        shards.setdefault(
            shard,
            []
        ).append(page)

    # --------------------------------------------------------
    # Schreiben
    # --------------------------------------------------------

    migrated = 0

    for shard, pages in shards.items():

        path = os.path.join(
            PAGES_DIR,
            f"{shard}.jsonl"
        )

        tmp = path + ".tmp"

        with open(
            tmp,
            "w",
            encoding="utf-8"
        ) as f:

            for page in pages:

                f.write(
                    json.dumps(
                        page,
                        ensure_ascii=False,
                        separators=(",", ":")
                    )
                    + "\n"
                )

                migrated += 1

        os.replace(
            tmp,
            path
        )

    # --------------------------------------------------------
    # Ergebnis
    # --------------------------------------------------------

    print()
    print("================================")
    print("Migration abgeschlossen")
    print(f"Erkannt: {len(entries)}")
    print(f"Migriert: {migrated}")
    print(f"Shards: {len(shards)}")
    print()
    print("sites.json wurde NICHT verändert.")
    print("================================")

    if migrated != len(entries):

        print()
        print(
            "WARNUNG: Nicht alle erkannten "
            "Einträge wurden migriert!"
        )


if __name__ == "__main__":
    migrate()
