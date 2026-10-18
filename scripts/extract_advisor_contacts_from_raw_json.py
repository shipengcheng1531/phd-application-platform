#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


EMAIL_PATTERN = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])")
GENERIC_LOCAL_PARTS = {
    "admissions",
    "apply",
    "contact",
    "cs",
    "grad",
    "gradadmissions",
    "graduate",
    "info",
    "office",
    "support",
    "webmaster",
}
GENERIC_LOCAL_PREFIXES = ("admission", "grad", "info", "support", "webmaster", "contact")
TEXT_SOURCE_FIELDS = [
    ("contactInfoEvidence", "contactInfoUrl"),
    ("stageEvidence", "stageEvidenceUrl"),
    ("phdAdvisingEvidence", "phdAdvisingUrl"),
    ("recruitingEvidence", "recruitingUrl"),
    ("studentBackgroundEvidence", "studentBackgroundUrl"),
    ("evidence", ""),
]


def snippet(text: str, email: str, radius: int = 180) -> str:
    index = text.lower().find(email.lower())
    if index < 0:
        return text[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(email) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def text_sources(raw: dict) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for text_key, url_key in TEXT_SOURCE_FIELDS:
        value = raw.get(text_key)
        if isinstance(value, list):
            for item in value:
                if item:
                    sources.append((str(item), ""))
            continue
        if value:
            sources.append((str(value), str(raw.get(url_key, "") if url_key else "")))
    sources.append((json.dumps(raw, ensure_ascii=False), ""))
    return sources


def name_tokens(raw: dict) -> set[str]:
    text = str(raw.get("name") or raw.get("rawName") or "")
    return {token.lower() for token in re.findall(r"[A-Za-z]{3,}", text)}


def classify_email(email: str, raw: dict) -> tuple[str, str]:
    local = email.split("@", 1)[0].lower()
    compact = re.sub(r"[^a-z0-9]", "", local)
    if compact in GENERIC_LOCAL_PARTS or any(compact.startswith(prefix) for prefix in GENERIC_LOCAL_PREFIXES):
        return "项目邮箱", "低"
    tokens = name_tokens(raw)
    if tokens and not any(token in compact or compact in token for token in tokens):
        return "其他", "低"
    return "导师邮箱", "中"


def extract_contacts(raw: dict) -> list[dict]:
    seen: set[str] = set()
    contacts: list[dict] = []
    for text, source_url in text_sources(raw):
        for match in EMAIL_PATTERN.finditer(text):
            email = match.group(1).strip().strip(".,;:)")
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            contact_type, confidence = classify_email(email, raw)
            contact_value = server.normalize_contact_value(contact_type, email)
            contacts.append(
                {
                    "contact_type": contact_type,
                    "contact_value": contact_value,
                    "source_url": source_url,
                    "evidence_text": snippet(text, email),
                    "confidence": confidence,
                    "is_primary": 0,
                }
            )
    advisor_email_candidates = [contact for contact in contacts if contact["contact_type"] == "导师邮箱"]
    if len(advisor_email_candidates) == 1:
        advisor_email_candidates[0]["is_primary"] = 1
    return contacts


def insert_contacts(conn: server.DbConnection, advisor_id: str, contacts: list[dict], created_by: str) -> dict:
    inserted = 0
    updated_existing = 0
    skipped = 0
    now = server.utc_now()
    for contact in contacts:
        contact_value = server.normalize_contact_value(contact["contact_type"], contact["contact_value"])
        existing = conn.execute(
            "select id from advisor_contacts where advisor_id = ? and contact_value = ?",
            (advisor_id, contact_value),
        ).fetchone()
        if existing:
            row_id = int(existing["id"])
            conn.execute(
                """
                update advisor_contacts
                set contact_type = ?, source_url = ?, evidence_text = ?, confidence = ?,
                    updated_by = ?, updated_at = ?
                where id = ? and advisor_id = ?
                """,
                (
                    contact["contact_type"],
                    contact["source_url"],
                    contact["evidence_text"],
                    contact["confidence"],
                    created_by,
                    now,
                    row_id,
                    advisor_id,
                ),
            )
            updated_existing += 1
        else:
            cursor = conn.execute(
                """
                insert into advisor_contacts (
                  advisor_id, contact_type, contact_value, source_url, evidence_text,
                  confidence, is_primary, created_by, updated_by, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    advisor_id,
                    contact["contact_type"],
                    contact_value,
                    contact["source_url"],
                    contact["evidence_text"],
                    contact["confidence"],
                    created_by,
                    created_by,
                    now,
                    now,
                ),
            )
            row_id = int(cursor.lastrowid)
            inserted += 1
        if contact["is_primary"]:
            conn.execute("update advisor_contacts set is_primary = 0 where advisor_id = ? and id <> ?", (advisor_id, row_id))
            conn.execute(
                "update advisor_contacts set is_primary = 1, updated_by = ?, updated_at = ? where id = ? and advisor_id = ?",
                (created_by, now, row_id, advisor_id),
            )
    server.sync_advisor_contact_primary(conn, advisor_id)
    return {"inserted": inserted, "updated_existing": updated_existing, "skipped_existing": skipped}


def run(apply: bool, limit: int) -> dict:
    report = {
        "mode": "apply" if apply else "dry-run",
        "advisors_scanned": 0,
        "advisors_with_contacts": 0,
        "contacts_found": 0,
        "inserted": 0,
        "updated_existing": 0,
        "skipped_existing": 0,
        "examples": [],
    }
    with server.connect() as conn:
        server.ensure_base_schema(conn)
        rows = conn.execute("select id, name, raw_json from advisors order by `rank`").fetchall()
        if limit > 0:
            rows = rows[:limit]
        for row in rows:
            report["advisors_scanned"] += 1
            raw = json.loads(row["raw_json"])
            contacts = extract_contacts(raw)
            if not contacts:
                continue
            report["advisors_with_contacts"] += 1
            report["contacts_found"] += len(contacts)
            if len(report["examples"]) < 12:
                report["examples"].append(
                    {
                        "advisor_id": row["id"],
                        "name": row["name"],
                        "contacts": [
                            {
                                "contact_type": contact["contact_type"],
                                "contact_value": contact["contact_value"],
                                "confidence": contact["confidence"],
                                "is_primary": contact["is_primary"],
                            }
                            for contact in contacts[:4]
                        ],
                    }
                )
            if apply:
                result = insert_contacts(conn, row["id"], contacts, "raw-json-email-extract")
                report["inserted"] += result["inserted"]
                report["updated_existing"] += result["updated_existing"]
                report["skipped_existing"] += result["skipped_existing"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="从 advisors.raw_json 证据片段中抽取邮箱线索到 advisor_contacts。")
    parser.add_argument("--apply", action="store_true", help="真正写入 advisor_contacts；默认只 dry-run")
    parser.add_argument("--limit", type=int, default=0, help="只扫描前 N 位导师，0 表示全量")
    args = parser.parse_args()
    print(json.dumps(run(args.apply, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
