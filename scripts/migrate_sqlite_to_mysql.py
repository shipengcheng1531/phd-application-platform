#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tarfile
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
DEFAULT_SQLITE_PATH = PLATFORM_ROOT / "data" / "platform.sqlite3"
DEFAULT_BACKUP_DIR = PLATFORM_ROOT / "data" / "backups"
DEFAULT_UPLOAD_DIR = PLATFORM_ROOT / "data" / "document_uploads"
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


TABLES: list[dict] = [
    {
        "name": "advisors",
        "columns": [
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
        ],
        "update_columns": [
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
        ],
    },
    {
        "name": "advisor_reviews",
        "columns": ["advisor_id", "reviewer", "decision", "interest", "score", "review_status", "note", "updated_at"],
        "update_columns": ["decision", "interest", "score", "review_status", "note", "updated_at"],
    },
    {
        "name": "advisor_contacts",
        "columns": [
            "id",
            "advisor_id",
            "contact_type",
            "contact_value",
            "source_url",
            "evidence_text",
            "confidence",
            "is_primary",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ],
        "update_columns": [
            "advisor_id",
            "contact_type",
            "contact_value",
            "source_url",
            "evidence_text",
            "confidence",
            "is_primary",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ],
    },
    {
        "name": "documents",
        "columns": [
            "id",
            "doc_type",
            "title",
            "version_label",
            "status",
            "owner",
            "uploaded_by",
            "original_filename",
            "stored_filename",
            "file_path",
            "file_size",
            "mime_type",
            "created_at",
            "updated_at",
            "notes",
        ],
        "update_columns": [
            "doc_type",
            "title",
            "version_label",
            "status",
            "owner",
            "uploaded_by",
            "original_filename",
            "stored_filename",
            "file_path",
            "file_size",
            "mime_type",
            "created_at",
            "updated_at",
            "notes",
        ],
    },
    {
        "name": "outreach_targets",
        "columns": [
            "advisor_id",
            "is_active",
            "status",
            "response_status",
            "stage",
            "priority",
            "tags",
            "last_contact_at",
            "next_action_at",
            "next_action",
            "notes",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ],
        "update_columns": [
            "is_active",
            "status",
            "response_status",
            "stage",
            "priority",
            "tags",
            "last_contact_at",
            "next_action_at",
            "next_action",
            "notes",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ],
    },
    {
        "name": "outreach_events",
        "columns": ["id", "advisor_id", "event_type", "event_at", "summary", "detail", "created_by", "created_at"],
        "update_columns": ["advisor_id", "event_type", "event_at", "summary", "detail", "created_by", "created_at"],
    },
    {
        "name": "application_programs",
        "columns": [
            "id",
            "school",
            "department",
            "program_name",
            "degree",
            "deadline",
            "status",
            "priority",
            "requirements",
            "notes",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ],
        "update_columns": [
            "school",
            "department",
            "program_name",
            "degree",
            "deadline",
            "status",
            "priority",
            "requirements",
            "notes",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ],
    },
    {
        "name": "ai_settings",
        "columns": [
            "id",
            "enabled",
            "provider_name",
            "endpoint_url",
            "model_name",
            "api_key",
            "temperature",
            "tools_enabled",
            "allow_search_pages",
            "tool_max_results",
            "tool_timeout_seconds",
            "tool_cache_ttl_seconds",
            "updated_by",
            "updated_at",
        ],
        "update_columns": [
            "enabled",
            "provider_name",
            "endpoint_url",
            "model_name",
            "api_key",
            "temperature",
            "tools_enabled",
            "allow_search_pages",
            "tool_max_results",
            "tool_timeout_seconds",
            "tool_cache_ttl_seconds",
            "updated_by",
            "updated_at",
        ],
    },
    {
        "name": "ai_conversations",
        "columns": ["id", "advisor_id", "title", "system_context", "created_by", "created_at", "updated_at"],
        "update_columns": ["advisor_id", "title", "system_context", "created_by", "created_at", "updated_at"],
    },
    {
        "name": "ai_messages",
        "columns": ["id", "conversation_id", "role", "content", "created_by", "created_at"],
        "update_columns": ["conversation_id", "role", "content", "created_by", "created_at"],
    },
]


def sqlite_connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def backup_sqlite(path: Path, backup_dir: Path) -> Path:
    if not path.exists():
        raise RuntimeError(f"SQLite 数据库不存在：{path}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"platform_before_mysql_migration_{stamp}.sqlite3"
    source = sqlite3.connect(path)
    try:
        target = sqlite3.connect(backup)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return backup


def backup_uploads(upload_dir: Path, backup_dir: Path) -> tuple[Path | None, Path]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = backup_dir / f"document_uploads_manifest_before_mysql_migration_{stamp}.json"
    files = []
    if upload_dir.exists():
        for path in sorted(upload_dir.rglob("*")):
            if path.is_file():
                files.append(
                    {
                        "path": str(path.relative_to(upload_dir)),
                        "size": path.stat().st_size,
                        "mtime": int(path.stat().st_mtime),
                    }
                )
    manifest_path.write_text(json.dumps({"upload_dir": str(upload_dir), "files": files}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not upload_dir.exists():
        return None, manifest_path
    archive_path = backup_dir / f"document_uploads_before_mysql_migration_{stamp}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(upload_dir, arcname="document_uploads")
    return archive_path, manifest_path


def source_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {table["name"]: conn.execute(f"select count(*) from {table['name']}").fetchone()[0] for table in TABLES}


def mysql_connect():
    try:
        import pymysql
    except ImportError as error:
        raise RuntimeError("迁移到 MySQL 需要安装 PyMySQL：python3 -m pip install PyMySQL") from error
    return pymysql.connect(**server.mysql_connection_kwargs())


def ensure_mysql_schema(conn) -> None:
    with conn.cursor() as cursor:
        for statement in server.MYSQL_SCHEMA:
            cursor.execute(statement)
    server.ensure_ai_settings_schema(server.DbConnection(conn, "mysql"))
    server.ensure_advisor_contact_schema(server.DbConnection(conn, "mysql"))
    server.ensure_ai_message_schema(server.DbConnection(conn, "mysql"))
    conn.commit()


def sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"pragma table_info({table_name})").fetchall()}


def missing_column_default(table_name: str, column: str):
    if table_name == "ai_messages" and column == "created_by":
        return ""
    if table_name == "ai_settings":
        return {
            "tools_enabled": 0,
            "allow_search_pages": 0,
            "tool_max_results": 5,
            "tool_timeout_seconds": 8,
            "tool_cache_ttl_seconds": 86400,
        }.get(column)
    return None


def fetch_rows(source: sqlite3.Connection, table: dict, migrate_api_key: bool) -> list[tuple]:
    columns = table["columns"]
    source_columns = sqlite_table_columns(source, table["name"])
    select_columns = [column for column in columns if column in source_columns]
    order_by = " order by advisor_id, is_primary desc, id" if table["name"] == "advisor_contacts" else ""
    sql = f"select {', '.join(select_columns)} from {table['name']}{order_by}"
    rows = []
    primary_contact_seen: set[str] = set()
    for row in source.execute(sql).fetchall():
        values = []
        for column in columns:
            if column not in source_columns:
                values.append(missing_column_default(table["name"], column))
                continue
            if table["name"] == "ai_settings" and column == "api_key" and not migrate_api_key:
                values.append("")
            elif table["name"] == "advisor_contacts" and column == "contact_value":
                values.append(server.normalize_contact_value(row["contact_type"], row["contact_value"]))
            elif table["name"] == "advisor_contacts" and column == "is_primary":
                advisor_id = row["advisor_id"]
                is_primary = int(row["is_primary"] or 0)
                if is_primary and advisor_id in primary_contact_seen:
                    values.append(0)
                else:
                    values.append(is_primary)
                    if is_primary:
                        primary_contact_seen.add(advisor_id)
            else:
                values.append(row[column])
        rows.append(tuple(values))
    return rows


def upsert_sql(table: dict) -> str:
    columns = table["columns"]
    table_name = f"`{table['name']}`"
    column_sql = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    updates = ", ".join(f"`{column}` = values(`{column}`)" for column in table["update_columns"])
    return (
        f"insert into {table_name} ({column_sql}) "
        f"values ({placeholders}) "
        f"on duplicate key update {updates}"
    )


def migrate_table(source: sqlite3.Connection, target, table: dict, batch_size: int, migrate_api_key: bool) -> dict:
    rows = fetch_rows(source, table, migrate_api_key)
    sql = upsert_sql(table)
    inserted = 0
    with target.cursor() as cursor:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            if batch:
                cursor.executemany(sql, batch)
                inserted += len(batch)
    return {"source_rows": len(rows), "upserted_rows": inserted}


def target_count(conn, table_name: str) -> int:
    with conn.cursor() as cursor:
        cursor.execute(f"select count(*) from `{table_name}`")
        return int(cursor.fetchone()[0])


def target_counts(conn) -> dict[str, int]:
    return {table["name"]: target_count(conn, table["name"]) for table in TABLES}


def assert_target_empty(conn, allow_non_empty_target: bool) -> dict[str, int]:
    counts = target_counts(conn)
    non_empty = {table: count for table, count in counts.items() if count}
    if non_empty and not allow_non_empty_target:
        raise RuntimeError(
            "目标 MySQL 表不是空表，默认拒绝迁移以避免覆盖已有数据。"
            f"非空表：{json.dumps(non_empty, ensure_ascii=False)}。"
            "如确认要 upsert 到非空目标库，请加 --allow-non-empty-target。"
        )
    return counts


def migrate(
    sqlite_path: Path,
    backup_dir: Path,
    upload_dir: Path,
    batch_size: int,
    dry_run: bool,
    allow_non_empty_target: bool,
    migrate_api_key: bool,
) -> dict:
    with sqlite_connect(sqlite_path) as source:
        counts_before = source_counts(source)
        if dry_run:
            return {
                "mode": "dry-run",
                "sqlite_path": str(sqlite_path),
                "sqlite_counts": counts_before,
                "mysql_schema_tables": len(server.MYSQL_SCHEMA),
                "note": "dry-run 不连接 MySQL，也不写入数据。",
            }

        target = mysql_connect()
        try:
            ensure_mysql_schema(target)
            target_counts_before = assert_target_empty(target, allow_non_empty_target)
            backup = backup_sqlite(sqlite_path, backup_dir)
            upload_archive, upload_manifest = backup_uploads(upload_dir, backup_dir)
            tables = {}
            try:
                for table in TABLES:
                    tables[table["name"]] = migrate_table(source, target, table, batch_size, migrate_api_key)
                server.sync_advisor_contact_primary(server.DbConnection(target, "mysql"))
                target.commit()
            except Exception:
                target.rollback()
                raise
            counts_after = target_counts(target)
            return {
                "mode": "upsert",
                "sqlite_path": str(sqlite_path),
                "backup": str(backup),
                "uploads_backup": str(upload_archive) if upload_archive else "",
                "uploads_manifest": str(upload_manifest),
                "allow_non_empty_target": allow_non_empty_target,
                "migrated_api_key": migrate_api_key,
                "mysql": {
                    "host": server.mysql_connection_kwargs()["host"],
                    "port": server.mysql_connection_kwargs()["port"],
                    "database": server.mysql_connection_kwargs()["database"],
                    "user": server.mysql_connection_kwargs()["user"],
                },
                "tables": {
                    table["name"]: {
                        "sqlite_rows": counts_before[table["name"]],
                        "mysql_rows_before": target_counts_before[table["name"]],
                        "upserted_rows": tables[table["name"]]["upserted_rows"],
                        "mysql_rows_after": counts_after[table["name"]],
                    }
                    for table in TABLES
                },
            }
        finally:
            target.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="把 07_协作平台 SQLite 数据迁移到 MySQL。")
    parser.add_argument("--sqlite-path", type=Path, default=DEFAULT_SQLITE_PATH)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--upload-dir", type=Path, default=DEFAULT_UPLOAD_DIR)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true", help="只读取 SQLite 行数和 schema 信息，不连接 MySQL")
    parser.add_argument("--allow-non-empty-target", action="store_true", help="允许 upsert 到已有数据的 MySQL 目标库")
    parser.add_argument("--migrate-api-key", action="store_true", help="显式允许把 SQLite ai_settings.api_key 明文迁移到 MySQL")
    args = parser.parse_args()

    if args.batch_size <= 0:
        raise RuntimeError("--batch-size 必须大于 0")
    result = migrate(
        args.sqlite_path,
        args.backup_dir,
        args.upload_dir,
        args.batch_size,
        args.dry_run,
        args.allow_non_empty_target,
        args.migrate_api_key,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
