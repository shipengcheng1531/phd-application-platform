#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CANONICAL_STAGE_LABELS = {
    "ap": "AP / 早期",
    "associate": "Associate / 中期",
    "full": "Full / 资深",
    "star": "Distinguished / 杰出",
    "faculty_unknown": "Faculty / 职级未知",
    "unknown": "Unknown / 待核实",
}


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def parse_args() -> argparse.Namespace:
    default_platform_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Normalize advisor stage labels by stage_key.")
    parser.add_argument("--platform-root", default=str(default_platform_root))
    parser.add_argument("--env-file", default="")
    parser.add_argument("--archive-dir", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--target-database", default="")
    parser.add_argument("--require-localhost", action="store_true")
    parser.add_argument("--confirm-update-count", type=int, default=-1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    platform_root = Path(args.platform_root).resolve()
    if args.env_file:
        load_env_file(Path(args.env_file))
    sys.path.insert(0, str(platform_root))
    import server  # noqa: PLC0415

    if args.apply:
        if args.confirm_update_count < 0:
            raise SystemExit("--apply requires --confirm-update-count")
        if not args.target_database:
            raise SystemExit("--apply requires --target-database")
        if server.current_db_backend() != "mysql":
            raise SystemExit("--apply only supports MySQL backend for this task")
        kwargs = server.mysql_connection_kwargs()
        if kwargs.get("database") != args.target_database:
            raise SystemExit(f"target database mismatch: {kwargs.get('database')} != {args.target_database}")
        if args.require_localhost and kwargs.get("host", "").lower() not in server.LOCAL_HOSTS:
            raise SystemExit(f"refusing non-local MySQL host: {kwargs.get('host')}")

    archive_dir = Path(args.archive_dir) if args.archive_dir else platform_root / "data" / f"advisor_stage_label_canonicalize_{utc_slug()}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    with server.connect() as conn:
        server.ensure_base_schema(conn)
        rows = [
            dict(row)
            for row in conn.execute(
                "select id, name, institution, stage_key, stage_label, raw_json from advisors order by `rank`, id"
            ).fetchall()
        ]
        before_counts = [
            dict(row)
            for row in conn.execute(
                "select stage_key, stage_label, count(*) as c from advisors group by stage_key, stage_label order by stage_key, stage_label"
            ).fetchall()
        ]
        updates: list[dict[str, Any]] = []
        backup_rows: list[dict[str, Any]] = []
        for row in rows:
            key = str(row.get("stage_key") or "").strip()
            canonical = CANONICAL_STAGE_LABELS.get(key)
            if not canonical:
                continue
            raw = json.loads(row.get("raw_json") or "{}")
            current_raw_label = str(raw.get("stageLabel") or raw.get("stage_label") or "").strip()
            if row.get("stage_label") == canonical and current_raw_label == canonical:
                continue
            backup_rows.append(row)
            raw["stageKey"] = key
            raw["stageLabel"] = canonical
            raw["stage_label"] = canonical
            updates.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "institution": row["institution"],
                    "stage_key": key,
                    "old_stage_label": row.get("stage_label") or "",
                    "new_stage_label": canonical,
                    "old_raw_stage_label": current_raw_label,
                    "new_raw_json": json.dumps(raw, ensure_ascii=False),
                }
            )

        if args.apply and args.confirm_update_count != len(updates):
            raise SystemExit(f"confirm update count mismatch: {args.confirm_update_count} != {len(updates)}")

        write_jsonl(archive_dir / "backup_stage_labels.jsonl", backup_rows)
        write_jsonl(archive_dir / "planned_updates.jsonl", updates)

        if args.apply:
            for update in updates:
                conn.execute(
                    "update advisors set stage_label = ?, raw_json = ? where id = ?",
                    (update["new_stage_label"], update["new_raw_json"], update["id"]),
                )

        after_counts = [
            dict(row)
            for row in conn.execute(
                "select stage_key, stage_label, count(*) as c from advisors group by stage_key, stage_label order by stage_key, stage_label"
            ).fetchall()
        ]

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "archive_dir": str(archive_dir),
        "total_advisors": len(rows),
        "update_count": len(updates),
        "before_counts": before_counts,
        "after_counts": after_counts,
        "old_label_counts_in_updates": dict(Counter(update["old_stage_label"] for update in updates).most_common()),
        "new_label_counts_in_updates": dict(Counter(update["new_stage_label"] for update in updates).most_common()),
        "sample_updates": updates[:20],
    }
    (archive_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
