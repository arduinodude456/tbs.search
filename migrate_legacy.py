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


def normalize_page(page):
    """
    Übernimmt eine alte Seite möglichst vollständig.
    """

    if not isinstance(page, dict):
        return None

    url = normalize_url(page.get("url"))

    if not url:
        return None

    now = int(time.time())

    return {
        "url": url,

        "title": page.get(
            "title",
            ""
        ),

        "description": page.get(
            "description",
            ""
        ),

        "headings": page.get(
            "headings",
            []
        ),

        "text": page.get(
            "text",
            ""
        ),

        "links": page.get(
            "links",
            []
        ),

        "etag": page.get(
            "etag"
        ),

        "last_modified": page.get(
            "last_modified"
        ),

        "indexed": page.get(
            "indexed",
            now
        ),

        "updated": page.get(
            "updated",
            now
        ),

        "checked": page.get(
            "checked",
            now
        )
    }


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


    # ---------------------------------------------------------
    # BACKUP
    # ---------------------------------------------------------

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


    # ---------------------------------------------------------
    # ALTES FORMAT ERKENNEN
    # ---------------------------------------------------------

    pages = []


    # FALL 1:
    #
    # {
    #     "pages": [
    #         {...},
    #         {...}
    #     ]
    # }
    #

    if isinstance(old_data, dict) and isinstance(
        old_data.get("pages"),
        list
    ):

        print(
            "Erkanntes Format: pages-Liste"
        )

        pages = old_data["pages"]


    # FALL 2:
    #
    # [
    #     {...},
    #     {...}
    # ]
    #

    elif isinstance(old_data, list):

        print(
            "Erkanntes Format: direkte Seiten-Liste"
        )

        pages = old_data


    # FALL 3:
    #
    # {
    #     "sites": [
    #         {...},
    #         {...}
    #     ]
    # }
    #

    elif isinstance(old_data, dict) and isinstance(
        old_data.get("sites"),
        list
    ):

        print(
            "Erkanntes Format: sites-Liste"
        )

        pages = old_data["sites"]


    else:

        raise SystemExit(
            """
FEHLER:
Das Format von sites.json konnte nicht erkannt werden.

Erwartet wurde beispielsweise:

{
    "pages": [
        ...
    ]
}
"""
        )


    print(
        f"Einträge in alter pages-Liste: {len(pages)}"
    )


    # ---------------------------------------------------------
    # SEITEN NORMALISIEREN
    # ---------------------------------------------------------

    normalized_pages = []

    invalid = 0


    for page in pages:

        normalized = normalize_page(
            page
        )


        if normalized is None:

            invalid += 1

            continue


        normalized_pages.append(
            normalized
        )


    print(
        f"Gültige Seiten: {len(normalized_pages)}"
    )


    if invalid:

        print(
            f"Ungültige Einträge übersprungen: {invalid}"
        )


    # ---------------------------------------------------------
    # DOPPELTE URLS ENTFERNEN
    # ---------------------------------------------------------

    unique_pages = {}


    for page in normalized_pages:

        unique_pages[
            page["url"]
        ] = page


    normalized_pages = list(
        unique_pages.values()
    )


    print(
        f"Eindeutige Seiten: {len(normalized_pages)}"
    )


    # ---------------------------------------------------------
    # SHARDS ERSTELLEN
    # ---------------------------------------------------------

    os.makedirs(
        PAGES_DIR,
        exist_ok=True
    )


    shards = {}


    for page in normalized_pages:

        shard = shard_for_url(
            page["url"]
        )


        shards.setdefault(
            shard,
            []
        ).append(page)


    # ---------------------------------------------------------
    # SHARDS SCHREIBEN
    # ---------------------------------------------------------

    migrated = 0


    for shard, shard_pages in shards.items():

        path = os.path.join(
            PAGES_DIR,
            f"{shard}.jsonl"
        )


        temp_path = (
            path + ".tmp"
        )


        with open(
            temp_path,
            "w",
            encoding="utf-8"
        ) as f:

            for page in shard_pages:

                f.write(
                    json.dumps(
                        page,
                        ensure_ascii=False,
                        separators=(
                            ",",
                            ":"
                        )
                    )
                    + "\n"
                )


                migrated += 1


        os.replace(
            temp_path,
            path
        )


    # ---------------------------------------------------------
    # ERGEBNIS
    # ---------------------------------------------------------

    print()

    print(
        "================================"
    )

    print(
        "Migration abgeschlossen"
    )

    print(
        f"Alte Einträge: {len(pages)}"
    )

    print(
        f"Gültige Seiten: {len(normalized_pages)}"
    )

    print(
        f"Migriert: {migrated}"
    )

    print(
        f"Shards: {len(shards)}"
    )

    print()

    print(
        "sites.json wurde NICHT verändert."
    )

    print(
        "================================"
    )


if __name__ == "__main__":

    migrate()
