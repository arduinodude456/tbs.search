import json
import os
import re
import hashlib
from collections import defaultdict


PAGES_DIR = "data/pages"
INDEX_DIR = "data/index"

TERMS_DIR = os.path.join(INDEX_DIR, "terms")
DOCS_DIR = os.path.join(INDEX_DIR, "docs")

WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]{2,}")

MAX_WORDS_PER_DOCUMENT = 5000


def normalize_word(word):
    return word.lower().strip()


def document_id(url):
    return int(
        hashlib.sha256(
            url.encode("utf-8")
        ).hexdigest()[:12],
        16
    )


def document_shard(doc_id):
    return f"{doc_id % 256:02x}"


def load_documents():

    documents = {}

    if not os.path.isdir(PAGES_DIR):
        return documents

    for filename in os.listdir(PAGES_DIR):

        if not filename.endswith(".jsonl"):
            continue

        path = os.path.join(
            PAGES_DIR,
            filename
        )

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:

                try:
                    page = json.loads(line)
                except json.JSONDecodeError:
                    continue

                url = page.get("url")

                if not url:
                    continue

                documents[document_id(url)] = page

    return documents


def words_for_page(page):

    parts = [
        page.get("title", ""),
        page.get("description", ""),
        " ".join(page.get("headings", [])),
        page.get("text", "")
    ]

    text = " ".join(parts)

    words = set()

    for match in WORD_RE.finditer(text):

        word = normalize_word(match.group(0))

        if len(word) < 2:
            continue

        words.add(word)

        if len(words) >= MAX_WORDS_PER_DOCUMENT:
            break

    return words


def build():

    os.makedirs(TERMS_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)

    documents = load_documents()

    print(f"Dokumente: {len(documents)}")

    inverted = defaultdict(set)

    document_output = defaultdict(dict)

    for doc_id, page in documents.items():

        document_output[
            document_shard(doc_id)
        ][str(doc_id)] = {
            "url": page["url"],
            "title": page.get("title", ""),
            "description": page.get("description", ""),
            "updated": page.get("updated", 0)
        }

        for word in words_for_page(page):
            inverted[word].add(doc_id)

    # --------------------------------------------------------
    # Dokument-Shards
    # --------------------------------------------------------

    for shard, docs in document_output.items():

        path = os.path.join(
            DOCS_DIR,
            f"{shard}.json"
        )

        tmp = path + ".tmp"

        with open(
            tmp,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                docs,
                f,
                ensure_ascii=False,
                separators=(",", ":")
            )

        os.replace(tmp, path)

    # --------------------------------------------------------
    # Wort-Shards
    # --------------------------------------------------------

    term_shards = defaultdict(dict)

    for word, ids in inverted.items():

        shard = hashlib.sha256(
            word.encode("utf-8")
        ).hexdigest()[:2]

        term_shards[shard][word] = sorted(ids)

    for shard, terms in term_shards.items():

        path = os.path.join(
            TERMS_DIR,
            f"{shard}.json"
        )

        tmp = path + ".tmp"

        with open(
            tmp,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                terms,
                f,
                ensure_ascii=False,
                separators=(",", ":")
            )

        os.replace(tmp, path)

    # --------------------------------------------------------
    # Manifest
    # --------------------------------------------------------

    manifest = {
        "version": 1,
        "documents": len(documents),
        "term_shards": len(term_shards),
        "document_shards": len(document_output)
    }

    manifest_path = os.path.join(
        INDEX_DIR,
        "manifest.json"
    )

    with open(
        manifest_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            manifest,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("Index erfolgreich gebaut.")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    build()
