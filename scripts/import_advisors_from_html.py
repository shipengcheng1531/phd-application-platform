#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PLATFORM_ROOT.parent
DB_PATH = PLATFORM_ROOT / "data" / "platform.sqlite3"
BACKUP_DIR = PLATFORM_ROOT / "data" / "backups"
SEED_HTML_FILENAME = "demo_advisors.html"
PLATFORM_SEED_HTML = PLATFORM_ROOT / "seed" / SEED_HTML_FILENAME
LEGACY_SEED_HTML = PLATFORM_SEED_HTML
SEED_HTML_ENV = "PHD_PLATFORM_SEED_HTML"


def default_source() -> Path:
    configured = os.environ.get(SEED_HTML_ENV, "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    if PLATFORM_SEED_HTML.exists():
        return PLATFORM_SEED_HTML
    return LEGACY_SEED_HTML


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def extract_records(source: Path) -> list[dict]:
    html = source.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="candidate-data" type="application/json">([\s\S]*?)</script>',
        html,
    )
    if not match:
        raise RuntimeError(f"cannot find candidate-data in {source}")
    records = json.loads(match.group(1))
    if not isinstance(records, list):
        raise RuntimeError("candidate-data must be a list")
    return records


def backup_database() -> Path:
    if not DB_PATH.exists():
        raise RuntimeError(f"database does not exist: {DB_PATH}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"platform_before_advisor_import_{stamp}.sqlite3"
    shutil.copy2(DB_PATH, backup)
    return backup


def advisor_tuple(row: dict) -> tuple:
    return (
        row["id"],
        int(row.get("num") or row.get("rank") or 0),
        row.get("name", ""),
        row.get("institution", ""),
        row.get("institutionZh") or row.get("firstInstitutionZh", ""),
        row.get("city", ""),
        row.get("state", ""),
        row.get("initialPool", ""),
        row.get("primaryCategory", ""),
        row.get("stageKey", ""),
        row.get("stageLabel", ""),
        row.get("schoolTier", ""),
        row.get("schoolTierLabel", ""),
        row.get("evidenceReliability", ""),
        row.get("recruitingStatus", ""),
        row.get("studentBackgroundStatus", ""),
        json.dumps(row, ensure_ascii=False),
    )


def import_records(records: list[dict], prune_missing: bool) -> dict[str, int]:
    ids = [row.get("id") for row in records if row.get("id")]
    if len(ids) != len(records):
        raise RuntimeError("all records must contain id")
    if len(set(ids)) != len(ids):
        raise RuntimeError("advisor ids are not unique")

    with connect() as conn:
        before = conn.execute("select count(*) from advisors").fetchone()[0]
        review_count = conn.execute("select count(*) from advisor_reviews").fetchone()[0]
        outreach_count = conn.execute("select count(*) from outreach_targets").fetchone()[0]
        conn.executemany(
            """
            insert into advisors (
              id, rank, name, institution, institution_zh, city, state, pool,
              category, stage_key, stage_label, school_tier, school_tier_label,
              evidence_reliability, recruiting_status, student_background_status,
              raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
              rank = excluded.rank,
              name = excluded.name,
              institution = excluded.institution,
              institution_zh = excluded.institution_zh,
              city = excluded.city,
              state = excluded.state,
              pool = excluded.pool,
              category = excluded.category,
              stage_key = excluded.stage_key,
              stage_label = excluded.stage_label,
              school_tier = excluded.school_tier,
              school_tier_label = excluded.school_tier_label,
              evidence_reliability = excluded.evidence_reliability,
              recruiting_status = excluded.recruiting_status,
              student_background_status = excluded.student_background_status,
              raw_json = excluded.raw_json
            """,
            [advisor_tuple(row) for row in records],
        )
        if prune_missing:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"delete from advisors where id not in ({placeholders})", ids)
        after = conn.execute("select count(*) from advisors").fetchone()[0]
        reviews_after = conn.execute("select count(*) from advisor_reviews").fetchone()[0]
        outreach_after = conn.execute("select count(*) from outreach_targets").fetchone()[0]
    return {
        "source_records": len(records),
        "advisors_before": before,
        "advisors_after": after,
        "reviews_before": review_count,
        "reviews_after": reviews_after,
        "outreach_before": outreach_count,
        "outreach_after": outreach_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=default_source())
    parser.add_argument("--prune-missing", action="store_true", help="delete advisors not present in the imported source")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    if not args.source.exists():
        raise RuntimeError(f"source does not exist: {args.source}")
    records = extract_records(args.source)
    backup = None if args.no_backup else backup_database()
    stats = import_records(records, prune_missing=args.prune_missing)
    payload = {
        "source": str(args.source),
        "backup": str(backup) if backup else "",
        **stats,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        raise
