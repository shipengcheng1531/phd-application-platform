#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ADVISOR_COLUMNS = [
    "id",
    "rank",
    "name",
    "institution",
    "institution_zh",
    "city",
    "state",
    "pool",
    "category",
    "stage_key",
    "stage_label",
    "school_tier",
    "school_tier_label",
    "evidence_reliability",
    "recruiting_status",
    "student_background_status",
    "raw_json",
]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def quote_ident(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def read_package(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    tables = payload.get("tables") or {}
    advisors = tables.get("advisors") or []
    contacts = tables.get("advisor_contacts") or []
    if not isinstance(advisors, list) or not isinstance(contacts, list):
        raise SystemExit("package tables.advisors / tables.advisor_contacts must be lists")
    advisor_ids = [row.get("id") for row in advisors]
    if len(advisor_ids) != len(set(advisor_ids)):
        raise SystemExit("package contains duplicate advisor ids")
    return payload


def add_platform_root(path: Path) -> None:
    sys.path.insert(0, str(path))


def backup_mysql(server_module: Any, backup_dir: Path, label: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    kwargs = server_module.mysql_connection_kwargs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"phd_workspace_before_{label}_{stamp}.sql.gz"
    env = os.environ.copy()
    env["MYSQL_PWD"] = kwargs["password"]
    command = [
        "mysqldump",
        "-h",
        str(kwargs["host"]),
        "-P",
        str(kwargs["port"]),
        "-u",
        str(kwargs["user"]),
        "--single-transaction",
        "--routines",
        "--triggers",
        str(kwargs["database"]),
    ]
    with gzip.open(backup_path, "wb") as output:
        subprocess.run(command, check=True, stdout=output, stderr=subprocess.PIPE, env=env)
    backup_path.chmod(0o600)
    return backup_path


def service_action(service: str, action: str) -> None:
    if not service:
        return
    subprocess.run(["systemctl", action, service], check=True)


def db_counts(conn: Any) -> dict[str, int]:
    tables = [
        "advisors",
        "advisor_contacts",
        "advisor_reviews",
        "outreach_targets",
        "outreach_events",
        "documents",
        "application_programs",
    ]
    return {table: int(conn.execute(f"select count(*) as c from {quote_ident(table)}").fetchone()["c"]) for table in tables}


def upsert_advisors(conn: Any, rows: list[dict[str, Any]]) -> None:
    sql = (
        "insert into advisors ("
        + ", ".join(quote_ident(column) for column in ADVISOR_COLUMNS)
        + ") values ("
        + ", ".join("?" for _ in ADVISOR_COLUMNS)
        + ") on duplicate key update "
        + ", ".join(f"{quote_ident(column)} = values({quote_ident(column)})" for column in ADVISOR_COLUMNS if column != "id")
    )
    conn.executemany(sql, [[row.get(column, "") for column in ADVISOR_COLUMNS] for row in rows])


def replace_contacts(server_module: Any, conn: Any, rows: list[dict[str, Any]]) -> None:
    conn.execute("delete from advisor_contacts")
    if not rows:
        return
    available = server_module.table_columns(conn, "advisor_contacts")
    columns = [column for column in rows[0].keys() if column in available]
    sql = (
        "insert into advisor_contacts ("
        + ", ".join(quote_ident(column) for column in columns)
        + ") values ("
        + ", ".join("?" for _ in columns)
        + ")"
    )
    conn.executemany(sql, [[row.get(column) for column in columns] for row in rows])
    server_module.sync_advisor_contact_primary(conn)


def advisors_not_in_package(conn: Any, advisor_ids: set[str]) -> list[str]:
    existing = [row["id"] for row in conn.execute("select id from advisors").fetchall()]
    return [advisor_id for advisor_id in existing if advisor_id not in advisor_ids]


def chunked(values: list[str], size: int = 300) -> list[list[str]]:
    return [values[start : start + size] for start in range(0, len(values), size)]


def count_rows_for_advisors(conn: Any, table: str, advisor_ids: list[str]) -> int:
    total = 0
    for chunk in chunked(advisor_ids):
        placeholders = ",".join("?" for _ in chunk)
        total += int(
            conn.execute(
                f"select count(*) as c from {quote_ident(table)} where advisor_id in ({placeholders})",
                chunk,
            ).fetchone()["c"]
        )
    return total


def count_ai_messages_for_advisors(conn: Any, advisor_ids: list[str]) -> int:
    total = 0
    for chunk in chunked(advisor_ids):
        placeholders = ",".join("?" for _ in chunk)
        total += int(
            conn.execute(
                f"""
                select count(*) as c
                from ai_messages m
                join ai_conversations c on c.id = m.conversation_id
                where c.advisor_id in ({placeholders})
                """,
                chunk,
            ).fetchone()["c"]
        )
    return total


def collaboration_dependency_report(conn: Any, advisor_ids: list[str]) -> dict[str, Any]:
    counts = {
        "advisor_reviews": 0,
        "outreach_targets": 0,
        "outreach_events": 0,
        "ai_conversations": 0,
        "ai_messages": 0,
    }
    if not advisor_ids:
        return {"advisor_count": 0, "counts": counts, "total_linked_rows": 0, "samples": []}
    for table in ["advisor_reviews", "outreach_targets", "outreach_events", "ai_conversations"]:
        counts[table] = count_rows_for_advisors(conn, table, advisor_ids)
    counts["ai_messages"] = count_ai_messages_for_advisors(conn, advisor_ids)
    samples: list[dict[str, Any]] = []
    for chunk in chunked(advisor_ids):
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            select *
            from (
              select
                a.id,
                a.name,
                (select count(*) from advisor_reviews r where r.advisor_id = a.id) as advisor_reviews,
                (select count(*) from outreach_targets o where o.advisor_id = a.id) as outreach_targets,
                (select count(*) from outreach_events e where e.advisor_id = a.id) as outreach_events,
                (select count(*) from ai_conversations c where c.advisor_id = a.id) as ai_conversations,
                (
                  select count(*)
                  from ai_messages m
                  join ai_conversations c on c.id = m.conversation_id
                  where c.advisor_id = a.id
                ) as ai_messages
              from advisors a
              where a.id in ({placeholders})
            ) linked
            where advisor_reviews > 0
               or outreach_targets > 0
               or outreach_events > 0
               or ai_conversations > 0
               or ai_messages > 0
            limit 20
            """,
            chunk,
        ).fetchall()
        samples.extend(dict(row) for row in rows)
        if len(samples) >= 20:
            samples = samples[:20]
            break
    return {
        "advisor_count": len(advisor_ids),
        "counts": counts,
        "total_linked_rows": sum(counts.values()),
        "samples": samples,
    }


def delete_advisors(conn: Any, to_delete: list[str]) -> int:
    for start in range(0, len(to_delete), 300):
        chunk = to_delete[start : start + 300]
        placeholders = ",".join("?" for _ in chunk)
        conn.execute(f"delete from advisors where id in ({placeholders})", chunk)
    return len(to_delete)


def validate(conn: Any) -> dict[str, Any]:
    rows = conn.execute("select raw_json from advisors").fetchall()
    empty_highlights = 0
    for row in rows:
        raw = json.loads(row["raw_json"] or "{}")
        if not str(raw.get("advisorHighlights") or "").strip():
            empty_highlights += 1
    rank = conn.execute("select min(`rank`) as mn, max(`rank`) as mx from advisors").fetchone()
    return {
        "counts": db_counts(conn),
        "rank_minmax": [rank["mn"], rank["mx"]],
        "empty_highlights": empty_highlights,
        "orphan_contacts": int(
            conn.execute(
                "select count(*) as c from advisor_contacts c left join advisors a on a.id = c.advisor_id where a.id is null"
            ).fetchone()["c"]
        ),
        "multi_primary": int(
            conn.execute(
                "select count(*) as c from (select advisor_id from advisor_contacts where is_primary = 1 group by advisor_id having count(*) > 1) x"
            ).fetchone()["c"]
        ),
        "goodnotes_new": int(conn.execute("select count(*) as c from advisors where id like ?", ("goodnotes-%",)).fetchone()["c"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import advisor pool JSON package into MySQL.")
    parser.add_argument("--package", required=True)
    parser.add_argument("--platform-root", default="/opt/phd-platform")
    parser.add_argument("--env-file", default="/etc/phd-platform.env")
    parser.add_argument("--backup-dir", default="/root/phd-platform-db-backups")
    parser.add_argument("--label", default="advisor_abc_sync")
    parser.add_argument("--service", default="phd-platform.service")
    parser.add_argument("--stop-service", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--confirm-advisors", type=int, required=True)
    parser.add_argument("--confirm-contacts", type=int, required=True)
    parser.add_argument("--allow-delete-linked-collaboration", action="store_true")
    parser.add_argument("--confirm-linked-delete-count", type=int)
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    add_platform_root(Path(args.platform_root))
    import server  # noqa: PLC0415

    package = read_package(Path(args.package))
    advisors = package["tables"]["advisors"]
    contacts = package["tables"]["advisor_contacts"]
    if len(advisors) != args.confirm_advisors:
        raise SystemExit(f"advisor count mismatch: {len(advisors)} != {args.confirm_advisors}")
    if len(contacts) != args.confirm_contacts:
        raise SystemExit(f"contact count mismatch: {len(contacts)} != {args.confirm_contacts}")
    kwargs = server.mysql_connection_kwargs()
    if kwargs["database"] != args.target_database:
        raise SystemExit(f"target database mismatch: {kwargs['database']} != {args.target_database}")

    stopped = False
    backup_path = ""
    try:
        backup_path = str(backup_mysql(server, Path(args.backup_dir), args.label))
        if args.stop_service:
            service_action(args.service, "stop")
            stopped = True
        with server.connect() as conn:
            server.ensure_base_schema(conn)
            before = db_counts(conn)
            to_delete = advisors_not_in_package(conn, {row["id"] for row in advisors})
            delete_dependency_report = collaboration_dependency_report(conn, to_delete)
            linked_rows = int(delete_dependency_report["total_linked_rows"])
            if args.apply and linked_rows:
                if not args.allow_delete_linked_collaboration:
                    raise SystemExit(
                        "refusing to delete advisors with linked collaboration data; "
                        f"linked_rows={linked_rows}; rerun only if intentional with "
                        "--allow-delete-linked-collaboration --confirm-linked-delete-count"
                    )
                if args.confirm_linked_delete_count != linked_rows:
                    raise SystemExit(
                        "linked collaboration delete count mismatch: "
                        f"{args.confirm_linked_delete_count} != {linked_rows}"
                    )
            if args.apply:
                upsert_advisors(conn, advisors)
                replace_contacts(server, conn, contacts)
                deleted = delete_advisors(conn, to_delete)
            else:
                deleted = 0
            after = validate(conn)
    finally:
        if stopped:
            service_action(args.service, "start")

    print(
        json.dumps(
            {
                "ok": True,
                "apply": args.apply,
                "backup": backup_path,
                "package": str(args.package),
                "package_counts": {"advisors": len(advisors), "advisor_contacts": len(contacts)},
                "before_counts": before,
                "advisors_not_in_package": len(to_delete),
                "delete_dependency_report": delete_dependency_report,
                "deleted_advisors_not_in_package": deleted,
                "after": after,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
