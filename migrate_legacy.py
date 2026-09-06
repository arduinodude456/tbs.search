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

    if not url:
        return None

    return url.strip()


def shard_for_url(url):

    return hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()[:2]


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

    if isinstance(old_data, dict):

        if "sites" in old_data:
            old_data = old_data["sites"]

        else:
            old_data = list(
                old_data.values()
            )

    if not isinstance(old_data, list):

        raise SystemExit(
            "FEHLER: Unbekanntes sites.json-Format."
        )

    print(
        f"Gefundene alte Einträge: "
        f"{len(old_data)}"
    )

    os.makedirs(PAGES_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # --------------------------------------------------------
    # Backup
    # --------------------------------------------------------

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
    # Migration
    # --------------------------------------------------------

    shards = {}

    migrated = 0

    now = int(time.time())

    for old in old_data:

        if not isinstance(old, dict):
            continue

        url = normalize_url(
            old.get("url")
        )

        if not url:
            continue

        page = {
            "url": url,
            "title": old.get("title", ""),
            "description": old.get(
                "description",
                ""
            ),
            "headings": old.get(
                "headings",
                []
            ),
            "text": old.get(
                "text",
                ""
            ),
            "links": old.get(
                "links",
                []
            ),
            "etag": old.get("etag"),
            "last_modified": old.get(
                "last_modified"
            ),
            "indexed": old.get(
                "indexed",
                now
            ),
            "updated": old.get(
                "updated",
                now
            ),
            "checked": old.get(
                "checked",
                now
            )
        }

        shard = shard_for_url(url)

        shards.setdefault(
            shard,
            []
        ).append(page)

        migrated += 1

    # --------------------------------------------------------
    # Schreiben
    # --------------------------------------------------------

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

        os.replace(tmp, path)

    print()
    print("================================")
    print("Migration abgeschlossen")
    print(f"Migriert: {migrated}")
    print(f"Shards: {len(shards)}")
    print("sites.json wurde NICHT verändert.")
    print("================================")


if __name__ == "__main__":
    migrate()
