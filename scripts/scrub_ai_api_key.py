#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def current_target() -> dict[str, str]:
    backend = server.current_db_backend()
    if backend == "mysql":
        return {
            "backend": backend,
            "host": os.environ.get("PHD_PLATFORM_MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1",
            "port": os.environ.get("PHD_PLATFORM_MYSQL_PORT", "3306").strip() or "3306",
            "database": os.environ.get("PHD_PLATFORM_MYSQL_DATABASE", "phd_workspace").strip() or "phd_workspace",
        }
    return {"backend": backend, "database": str(server.DB_PATH)}


def enforce_target(args: argparse.Namespace, target: dict[str, str]) -> None:
    if args.target_database and args.target_database != target["database"]:
        raise SystemExit(f"目标数据库不匹配：当前 {target['database']}，参数 {args.target_database}")
    if args.require_localhost and target["backend"] == "mysql" and target["host"].lower() not in LOCAL_HOSTS:
        raise SystemExit(f"拒绝执行：当前 MySQL host 不是本机地址：{target['host']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="清空 ai_settings.api_key，不输出任何密钥内容。")
    parser.add_argument("--dry-run", action="store_true", help="只输出当前数据库 Key 长度，不修改数据库")
    parser.add_argument("--target-database", default="", help="可选：要求当前目标数据库名匹配后才执行")
    parser.add_argument("--require-localhost", action="store_true", help="MySQL 模式下要求 host 是 127.0.0.1 / localhost / ::1")
    args = parser.parse_args()

    target = current_target()
    enforce_target(args, target)
    with server.connect() as conn:
        server.ensure_base_schema(conn)
        server.ensure_ai_settings_row(conn)
        before = conn.execute("select length(coalesce(api_key, '')) as c from ai_settings where id = 1").fetchone()["c"]
        if not args.dry_run:
            conn.execute("update ai_settings set api_key = '' where id = 1")
        after = before if args.dry_run else 0
    print(
        json.dumps(
            {
                "ok": True,
                "mode": "dry-run" if args.dry_run else "apply",
                "target": target,
                "api_key_length_before": int(before or 0),
                "api_key_length_after": int(after or 0),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
