#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PLATFORM_ROOT.parent
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


AUTOMATION_USER = "main-agent-official-profile-prune-v1"
RELATED_TABLES = [
    "advisors",
    "advisor_contacts",
    "advisor_reviews",
    "outreach_targets",
    "outreach_events",
    "ai_conversations",
    "ai_messages",
]
DELETE_RESTORE_ORDER = [
    "ai_messages",
    "ai_conversations",
    "outreach_events",
    "outreach_targets",
    "advisor_reviews",
    "advisor_contacts",
    "advisors",
]
INSERT_RESTORE_ORDER = [
    "advisors",
    "advisor_contacts",
    "advisor_reviews",
    "outreach_targets",
    "outreach_events",
    "ai_conversations",
    "ai_messages",
]
PROFILE_URL_FIELDS = ("stageEvidenceUrl", "stage_evidence_url")
LOW_VALUE_DOMAINS = {
    "openalex.org",
    "scholar.google.com",
    "dblp.org",
    "semanticscholar.org",
    "researchgate.net",
    "linkedin.com",
    "pubmed.ncbi.nlm.nih.gov",
}
LOW_VALUE_URL_MARKERS = (
    "/citations?",
    "/scholar?",
    "/publication/",
    "/paper/",
    "openalex.org",
    "pubmed.ncbi.nlm.nih.gov",
)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def table_rows(conn: server.DbConnection, table: str) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in conn.execute(f"select * from {table}").fetchall()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_restore_script(path: Path) -> None:
    script = f'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ARCHIVE_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = ARCHIVE_DIR.parents[1]
BACKUP_DIR = ARCHIVE_DIR / "backup_before_apply"
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


DELETE_ORDER = {json.dumps(DELETE_RESTORE_ORDER, ensure_ascii=False, indent=2)}
INSERT_ORDER = {json.dumps(INSERT_RESTORE_ORDER, ensure_ascii=False, indent=2)}
LOCAL_HOSTS = {json.dumps(sorted(server.LOCAL_HOSTS), ensure_ascii=False)}


def quote_ident(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def current_target() -> dict[str, str]:
    backend = server.current_db_backend()
    if backend == "mysql":
        return {{
            "backend": backend,
            "host": os.environ.get("PHD_PLATFORM_MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1",
            "database": os.environ.get("PHD_PLATFORM_MYSQL_DATABASE", "phd_workspace").strip() or "phd_workspace",
        }}
    return {{"backend": backend, "database": str(server.DB_PATH)}}


def enforce_target(args: argparse.Namespace, target: dict[str, str]) -> None:
    if args.target_database and args.target_database != target["database"]:
        raise SystemExit(f"目标数据库不匹配：当前 {{target['database']}}，参数 {{args.target_database}}")
    if args.require_localhost and target["backend"] == "mysql" and target["host"].lower() not in LOCAL_HOSTS:
        raise SystemExit(f"拒绝执行：当前 MySQL host 不是本机地址：{{target['host']}}")


def insert_rows(conn: server.DbConnection, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    columns = [column for column in rows[0].keys() if column in server.table_columns(conn, table)]
    if not columns:
        return 0
    sql = (
        f"insert into {{quote_ident(table)}} ("
        + ", ".join(quote_ident(column) for column in columns)
        + ") values ("
        + ", ".join("?" for _ in columns)
        + ")"
    )
    conn.executemany(sql, [[row.get(column) for column in columns] for row in rows])
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="从 prune 归档 backup_before_apply 恢复清洗前数据。")
    parser.add_argument("--confirm-restore", action="store_true", help="必须显式提供才会清空并恢复相关表")
    parser.add_argument("--target-database", default="", help="可选：要求当前目标数据库名匹配后才执行")
    parser.add_argument("--require-localhost", action="store_true", help="MySQL 模式下要求 host 是本机地址")
    args = parser.parse_args()
    if not args.confirm_restore:
        raise SystemExit("拒绝执行：请显式加 --confirm-restore")
    if not BACKUP_DIR.exists():
        raise SystemExit(f"备份目录不存在：{{BACKUP_DIR}}")
    target = current_target()
    enforce_target(args, target)
    with server.connect() as conn:
        server.ensure_base_schema(conn)
        for table in DELETE_ORDER:
            conn.execute(f"delete from {{quote_ident(table)}}")
        restored = {{}}
        for table in INSERT_ORDER:
            restored[table] = insert_rows(conn, table, read_jsonl(BACKUP_DIR / f"{{table}}.jsonl"))
    print(json.dumps({{"ok": True, "target": target, "restored": restored}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def current_target() -> dict[str, str]:
    backend = server.current_db_backend()
    if backend == "mysql":
        return {
            "backend": backend,
            "host": os.environ.get("PHD_PLATFORM_MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1",
            "database": os.environ.get("PHD_PLATFORM_MYSQL_DATABASE", "phd_workspace").strip() or "phd_workspace",
        }
    return {"backend": backend, "database": str(server.DB_PATH)}


def enforce_apply_safety(args: argparse.Namespace, remove_count: int) -> None:
    if not args.apply:
        return
    if args.confirm_remove_count is None:
        raise SystemExit(f"拒绝执行 --apply：必须提供 --confirm-remove-count {remove_count}")
    if args.confirm_remove_count != remove_count:
        raise SystemExit(f"拒绝执行 --apply：确认删除数量 {args.confirm_remove_count} 与实际 {remove_count} 不一致")
    target = current_target()
    if not args.target_database:
        raise SystemExit(f"拒绝执行 --apply：必须提供 --target-database {target['database']}")
    if args.target_database != target["database"]:
        raise SystemExit(f"拒绝执行 --apply：当前目标 {target['database']} 与参数 {args.target_database} 不一致")
    if args.require_localhost and target["backend"] == "mysql" and target["host"].lower() not in server.LOCAL_HOSTS:
        raise SystemExit(f"拒绝执行 --apply：当前 MySQL host 不是本机地址：{target['host']}")


def enforce_apply_preflight(args: argparse.Namespace) -> None:
    if not args.apply:
        return
    if args.confirm_remove_count is None:
        raise SystemExit("拒绝执行 --apply：必须先 dry-run 确认删除数量，再提供 --confirm-remove-count")
    if not args.target_database:
        raise SystemExit("拒绝执行 --apply：必须提供 --target-database")


def site_key(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 3 and parts[-2:] == ["github", "io"]:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def official_school_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if not host:
        return False
    key = site_key(url)
    if key in LOW_VALUE_DOMAINS or host in LOW_VALUE_DOMAINS:
        return False
    lower = url.lower()
    if any(marker in lower for marker in LOW_VALUE_URL_MARKERS):
        return False
    if lower.endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
        return False
    return ".edu" in host or ".ac." in host or host.endswith(".ca")


def official_profile_url(raw: dict[str, Any]) -> str:
    for key in PROFILE_URL_FIELDS:
        value = clean_text(raw.get(key))
        if official_school_url(value):
            return value.split("#", 1)[0].rstrip("/")
    return ""


def classify(row: dict[str, Any]) -> dict[str, Any]:
    raw = json.loads(row.get("raw_json") or "{}")
    stage_key = clean_text(row.get("stage_key") or raw.get("stageKey") or raw.get("stage_key"))
    stage_source_type = clean_text(raw.get("stageSourceType") or raw.get("stage_source_type"))
    source = clean_text(raw.get("source"))
    url = official_profile_url(raw)
    stage_url = clean_text(raw.get("stageEvidenceUrl") or raw.get("stage_evidence_url"))
    evidence_pages_checked = clean_text(raw.get("evidencePagesChecked") or raw.get("evidence_pages_checked"))

    if stage_key == "nonfaculty":
        keep = False
        reason = "stage_key=nonfaculty，明确不是导师"
    elif url:
        keep = True
        reason = "存在学校官网 stageEvidenceUrl，可作为导师官网主页证据"
    elif stage_url:
        keep = False
        reason = "stageEvidenceUrl 存在，但不是学校官网类 URL"
    else:
        keep = False
        reason = "缺少学校官网导师主页 URL"

    return {
        "advisor_id": row["id"],
        "rank": row["rank"],
        "name": row["name"],
        "institution": row.get("institution", ""),
        "stage_key": stage_key,
        "evidence_reliability": row.get("evidence_reliability", ""),
        "official_profile_url": url,
        "stage_evidence_url": stage_url,
        "stage_source_type": stage_source_type,
        "source": source,
        "evidence_pages_checked": evidence_pages_checked,
        "keep": keep,
        "reason": reason,
    }


def related_counts(conn: server.DbConnection, advisor_ids: list[str]) -> dict[str, int]:
    if not advisor_ids:
        return {table: 0 for table in RELATED_TABLES}
    placeholders = ",".join(["?"] * len(advisor_ids))
    counts = {"advisors": len(advisor_ids)}
    for table in ["advisor_contacts", "advisor_reviews", "outreach_targets", "outreach_events", "ai_conversations"]:
        counts[table] = int(
            conn.execute(f"select count(*) as c from {table} where advisor_id in ({placeholders})", advisor_ids).fetchone()["c"]
        )
    conversation_ids = [
        int(row["id"])
        for row in conn.execute(f"select id from ai_conversations where advisor_id in ({placeholders})", advisor_ids).fetchall()
    ]
    if conversation_ids:
        conv_placeholders = ",".join(["?"] * len(conversation_ids))
        counts["ai_messages"] = int(
            conn.execute(
                f"select count(*) as c from ai_messages where conversation_id in ({conv_placeholders})",
                conversation_ids,
            ).fetchone()["c"]
        )
    else:
        counts["ai_messages"] = 0
    return counts


def archive_outputs(
    conn: server.DbConnection,
    archive_dir: Path,
    classified: list[dict[str, Any]],
    removed_ids: list[str],
    apply: bool,
) -> dict[str, str]:
    archive_dir.mkdir(parents=True, exist_ok=True)
    kept = [item for item in classified if item["keep"]]
    removed = [item for item in classified if not item["keep"]]

    paths = {
        "summary": str(archive_dir / "summary.json"),
        "kept_jsonl": str(archive_dir / "kept_advisors.jsonl"),
        "removed_jsonl": str(archive_dir / "removed_advisors.jsonl"),
        "removed_csv": str(archive_dir / "removed_advisors.csv"),
        "kept_ids": str(archive_dir / "kept_ids.txt"),
        "removed_ids": str(archive_dir / "removed_ids.txt"),
    }
    write_jsonl(Path(paths["kept_jsonl"]), kept)
    write_jsonl(Path(paths["removed_jsonl"]), removed)
    write_csv(
        Path(paths["removed_csv"]),
        removed,
        [
            "advisor_id",
            "rank",
            "name",
            "institution",
            "stage_key",
            "evidence_reliability",
            "reason",
            "stage_evidence_url",
            "source",
        ],
    )
    Path(paths["kept_ids"]).write_text("\n".join(item["advisor_id"] for item in kept) + "\n", encoding="utf-8")
    Path(paths["removed_ids"]).write_text("\n".join(item["advisor_id"] for item in removed) + "\n", encoding="utf-8")

    if apply:
        backup_dir = archive_dir / "backup_before_apply"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for table in RELATED_TABLES:
            write_jsonl(backup_dir / f"{table}.jsonl", table_rows(conn, table))
        paths["backup_dir"] = str(backup_dir)
        restore_script = archive_dir / "restore_from_backup.py"
        write_restore_script(restore_script)
        paths["restore_script"] = str(restore_script)

    return paths


def delete_removed_advisors(conn: server.DbConnection, removed_ids: list[str]) -> None:
    chunk_size = 300
    for start in range(0, len(removed_ids), chunk_size):
        chunk = removed_ids[start : start + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        conn.execute(f"delete from advisors where id in ({placeholders})", chunk)


def rerank_remaining_advisors(conn: server.DbConnection) -> None:
    rows = conn.execute("select id from advisors order by `rank`, id").fetchall()
    for index, row in enumerate(rows, start=1):
        conn.execute("update advisors set `rank` = ? where id = ?", (index, row["id"]))


def run(args: argparse.Namespace) -> dict[str, Any]:
    enforce_apply_preflight(args)
    archive_dir = Path(args.archive_dir).expanduser() if args.archive_dir else default_archive_dir()
    with server.connect() as conn:
        server.ensure_base_schema(conn)
        rows = [row_to_dict(row) for row in conn.execute("select * from advisors order by `rank`, id").fetchall()]
        classified = [classify(row) for row in rows]
        kept = [item for item in classified if item["keep"]]
        removed = [item for item in classified if not item["keep"]]
        removed_ids = [item["advisor_id"] for item in removed]
        enforce_apply_safety(args, len(removed_ids))
        paths = archive_outputs(conn, archive_dir, classified, removed_ids, apply=args.apply)

        before_counts = {
            "advisors": int(conn.execute("select count(*) as c from advisors").fetchone()["c"]),
            "advisor_contacts": int(conn.execute("select count(*) as c from advisor_contacts").fetchone()["c"]),
            "advisor_reviews": int(conn.execute("select count(*) as c from advisor_reviews").fetchone()["c"]),
            "outreach_targets": int(conn.execute("select count(*) as c from outreach_targets").fetchone()["c"]),
            "outreach_events": int(conn.execute("select count(*) as c from outreach_events").fetchone()["c"]),
            "ai_conversations": int(conn.execute("select count(*) as c from ai_conversations").fetchone()["c"]),
            "ai_messages": int(conn.execute("select count(*) as c from ai_messages").fetchone()["c"]),
        }
        removed_related_counts = related_counts(conn, removed_ids)

        if args.apply and removed_ids:
            delete_removed_advisors(conn, removed_ids)
            if args.rerank:
                rerank_remaining_advisors(conn)

        after_counts = {
            "advisors": int(conn.execute("select count(*) as c from advisors").fetchone()["c"]),
            "advisor_contacts": int(conn.execute("select count(*) as c from advisor_contacts").fetchone()["c"]),
            "advisor_reviews": int(conn.execute("select count(*) as c from advisor_reviews").fetchone()["c"]),
            "outreach_targets": int(conn.execute("select count(*) as c from outreach_targets").fetchone()["c"]),
            "outreach_events": int(conn.execute("select count(*) as c from outreach_events").fetchone()["c"]),
            "ai_conversations": int(conn.execute("select count(*) as c from ai_conversations").fetchone()["c"]),
            "ai_messages": int(conn.execute("select count(*) as c from ai_messages").fetchone()["c"]),
        }

        stage_counts_kept = Counter(item["stage_key"] or "空" for item in kept)
        stage_counts_removed = Counter(item["stage_key"] or "空" for item in removed)
        reason_counts_removed = Counter(item["reason"] for item in removed)
        source_counts_removed = Counter(item["source"] or "空" for item in removed)
        summary = {
            "mode": "apply" if args.apply else "dry-run",
            "definition": "只保留存在学校官网 stageEvidenceUrl 且不是 nonfaculty 的导师；OpenAlex 论文作者候选不算导师，除非已有学校官网主页证据。",
            "automation_user": AUTOMATION_USER,
            "archive_dir": str(archive_dir),
            "before_counts": before_counts,
            "after_counts": after_counts,
            "kept_advisors": len(kept),
            "removed_advisors": len(removed),
            "removed_related_counts": removed_related_counts,
            "kept_stage_counts": dict(stage_counts_kept.most_common()),
            "removed_stage_counts": dict(stage_counts_removed.most_common()),
            "removed_reason_counts": dict(reason_counts_removed.most_common()),
            "removed_source_counts_top": dict(source_counts_removed.most_common(20)),
            "examples_kept": kept[:20],
            "examples_removed": removed[:20],
            "paths": paths,
            "rerank": bool(args.apply and args.rerank),
        }
        Path(paths["summary"]).write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return summary


def default_archive_dir() -> Path:
    stamp = server.utc_now().replace(":", "").replace("+", "Z")
    return PLATFORM_ROOT / "data" / f"advisor_official_profile_prune_{stamp}"


def main() -> None:
    parser = argparse.ArgumentParser(description="按学校官网主页证据清洗导师池。默认 dry-run，不写数据库。")
    parser.add_argument("--apply", action="store_true", help="真正删除不符合定义的导师；默认只输出归档和报告")
    parser.add_argument("--confirm-remove-count", type=int, default=None, help="apply 必填：确认本次将删除的导师数量")
    parser.add_argument("--target-database", default="", help="apply 必填：确认当前目标数据库名")
    parser.add_argument("--require-localhost", action="store_true", help="apply 时要求 MySQL host 是本机地址")
    parser.add_argument("--archive-dir", default="", help="归档输出目录；默认写入 07_协作平台/data/advisor_official_profile_prune_*")
    parser.add_argument("--no-rerank", dest="rerank", action="store_false", help="apply 后不重排剩余导师 rank")
    parser.set_defaults(rerank=True)
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
