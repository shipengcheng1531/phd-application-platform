#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PLATFORM_ROOT.parent
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


AUTOMATION_USER = "main-agent-advisor-highlights-v1"
HIGHLIGHT_FIELDS = (
    "advisorHighlights",
    "advisor_highlights",
    "highlights",
    "fitHighlights",
    "fit_highlights",
    "keyPoints",
    "key_points",
)

PHD_PLATFORM_ANGLES = {
    category: "申请人自行填写并核实的研究方向"
    for category in (
        "Core evaluation", "Agent/persona", "NLP/LLM-adjacent", "HCI/social",
        "Recommender/user", "Education/HCI", "AI/ML adjacent", "Trustworthy/robust",
        "Software/systems adjacent", "CS faculty fallback",
    )
}

CATEGORY_PREFIX = {
    "Core evaluation": "研究匹配较强",
    "Agent/persona": "方向相邻偏强",
    "NLP/LLM-adjacent": "方向相邻",
    "HCI/social": "方向相邻",
    "Recommender/user": "相关性中等",
    "Education/HCI": "相关性中等",
    "AI/ML adjacent": "相关性中等",
    "Trustworthy/robust": "研究匹配较强",
    "Software/systems adjacent": "相关性偏宽",
    "CS faculty fallback": "相关性偏宽",
}

DEFAULT_TOPICS = {
    "Core evaluation": "LLM 评测与 benchmark",
    "Agent/persona": "agent / persona 与对话系统",
    "NLP/LLM-adjacent": "NLP / LLM 方法与应用",
    "HCI/social": "人机交互与社会计算场景",
    "Recommender/user": "用户建模与推荐系统",
    "Education/HCI": "教育技术与学习场景",
    "AI/ML adjacent": "AI/ML 方法与鲁棒性",
    "Trustworthy/robust": "可信 AI 与鲁棒性",
    "Software/systems adjacent": "软件系统与工具链",
    "CS faculty fallback": "宽口径 CS faculty 线索",
}

PITCHES = {
    category: "申请人经历与导师研究之间经核实的具体交集"
    for category in PHD_PLATFORM_ANGLES
}

TOPIC_RULES = (
    (r"\bbenchmark|benchmarking|leaderboard", "benchmark / leaderboard"),
    (r"\bevaluat|评测|evaluation", "模型评测"),
    (r"judge|llm-as-a-judge|llm as a judge", "LLM-as-a-judge"),
    (r"role[- ]?play|persona|character|dialogue|conversation|chatbot", "角色扮演 / 对话评测"),
    (r"agent|tool[- ]?use|web[- ]?agent|planning", "agent / tool-use"),
    (r"robust|distribution|domain generalization|shift|consistency", "鲁棒性与分布变化"),
    (r"trust|safe|safety|bias|fairness|ethic|moral|hate", "可信、安全与价值评测"),
    (r"reasoning|logic|commonsense|multi[- ]?hop", "推理能力评测"),
    (r"multilingual|cross[- ]?lingual|language", "跨语言评测"),
    (r"multimodal|vision|image|video", "多模态评测"),
    (r"education|learning|student|tutor", "教育场景评测"),
    (r"recommend|personalization|user model|user modeling", "用户建模 / 推荐"),
    (r"social|hci|human[- ]?computer|interaction", "HCI / 社会互动"),
    (r"security|vulnerab|privacy|attack", "安全场景评测"),
    (r"health|medical|clinical|biomed", "垂直领域评测"),
)


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def has_highlight(raw: dict[str, Any]) -> bool:
    for field in HIGHLIGHT_FIELDS:
        value = raw.get(field)
        if isinstance(value, list) and any(clean_text(item) for item in value):
            return True
        if isinstance(value, str) and clean_text(value):
            return True
    return False


def evidence_titles(raw: dict[str, Any]) -> list[str]:
    rows = raw.get("evidence") or raw.get("paperEvidence") or raw.get("paper_evidence") or []
    titles: list[str] = []
    for row in rows:
        text = clean_text(row)
        text = re.sub(r"^\d{4}\s*[·\-:]\s*", "", text)
        text = text.strip(" -·")
        if text and text not in titles:
            titles.append(text)
    return titles[:4]


def source_text(raw: dict[str, Any]) -> str:
    parts = [
        raw.get("matchedKeywords", ""),
        raw.get("primaryCategory", ""),
        raw.get("categories", ""),
        raw.get("research_pool", ""),
        raw.get("stageEvidence", ""),
        raw.get("phdAdvisingEvidence", ""),
        raw.get("studentBackgroundEvidence", ""),
    ]
    parts.extend(evidence_titles(raw))
    return clean_text(" ".join(clean_text(part) for part in parts if clean_text(part))).lower()


def detect_topics(raw: dict[str, Any], category: str) -> list[str]:
    text = source_text(raw)
    topics: list[str] = []
    for pattern, label in TOPIC_RULES:
        if re.search(pattern, text, flags=re.I) and label not in topics:
            topics.append(label)
    if not topics:
        topics.append(DEFAULT_TOPICS.get(category, "导师近期研究主题"))
    return topics[:2]


def stage_key(raw: dict[str, Any]) -> str:
    return clean_text(raw.get("stageKey") or raw.get("stage_key"))


def stage_note(raw: dict[str, Any], stage_label: str) -> str:
    key = stage_key(raw)
    label = clean_text(stage_label or raw.get("stageLabel") or raw.get("stage_label"))
    text = f"{key} {label}".lower()
    if key == "ap" or "assistant" in text or "ap /" in text:
        return "作为早期导师，适合放入重点机会池；"
    if key == "associate" or "associate" in text:
        return "作为中期导师，研究线相对稳定；"
    if key == "full" or "full" in text or "professor" in text:
        return "作为资深导师，资源与竞争都更高；"
    if key == "star" or "distinguished" in text or "chair" in text or "大 pi" in text:
        return "属于高冲刺导师，适合在切口很具体时联系；"
    if key == "faculty_unknown" or "faculty" in text:
        return "官网确认 faculty 但职级仍需核实；"
    return "职级信息仍需人工核实；"


def reliability_note(raw: dict[str, Any]) -> str:
    reliability = clean_text(raw.get("evidenceReliability") or raw.get("evidence_reliability"))
    if reliability == "低":
        return "联系前建议再核对主页和近期论文。"
    return ""


def applicant_angle_phrase(angle: str) -> str:
    if re.match(r"^[A-Za-z0-9]", angle):
        return f"Applicant 当前申请叙事中的 {angle}"
    return f"Applicant 当前申请叙事中的{angle}"


def highlight_for(raw: dict[str, Any], stage_label: str) -> str:
    category = clean_text(raw.get("primaryCategory") or raw.get("category"))
    topics = "、".join(detect_topics(raw, category))
    prefix = CATEGORY_PREFIX.get(category, "相关性待复核")
    angle = PHD_PLATFORM_ANGLES.get(category, "申请人自行填写并核实的研究方向")
    pitch = PITCHES.get(category, "可验证的研究交集")
    note = reliability_note(raw)
    return (
        f"{prefix}：公开证据涉及{topics}，可对接 {applicant_angle_phrase(angle)}。"
        f"{stage_note(raw, stage_label)}套磁可从「{pitch}」切入。{note}"
    ).strip()


def row_to_raw(row: Any) -> dict[str, Any]:
    raw = json.loads(row["raw_json"] or "{}")
    raw.setdefault("id", row["id"])
    raw.setdefault("name", row["name"])
    raw.setdefault("institution", row["institution"])
    raw.setdefault("primaryCategory", row["category"])
    raw.setdefault("stageKey", row["stage_key"])
    raw.setdefault("stageLabel", row["stage_label"])
    raw.setdefault("evidenceReliability", row["evidence_reliability"])
    return raw


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
    script = '''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ARCHIVE_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = ARCHIVE_DIR.parents[1]
BACKUP_FILE = ARCHIVE_DIR / "backup_before_apply" / "advisors_raw_json.jsonl"
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore advisor raw_json before highlight backfill.")
    parser.add_argument("--confirm-count", type=int, required=True)
    parser.add_argument("--target-database", required=True)
    args = parser.parse_args()
    kwargs = server.mysql_connection_kwargs() if server.current_db_backend() == "mysql" else {}
    if kwargs and kwargs.get("database") != args.target_database:
        raise SystemExit(f"target database mismatch: {kwargs.get('database')} != {args.target_database}")
    rows = []
    with BACKUP_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if len(rows) != args.confirm_count:
        raise SystemExit(f"confirm count mismatch: {len(rows)} != {args.confirm_count}")
    with server.connect() as conn:
        for row in rows:
            conn.execute("update advisors set raw_json = ? where id = ?", (row["raw_json"], row["id"]))
    print(json.dumps({"restored": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def load_rows(conn: server.DbConnection) -> list[Any]:
    return conn.execute(
        """
        select id, name, institution, category, stage_key, stage_label, evidence_reliability, raw_json
        from advisors
        order by id
        """
    ).fetchall()


def ensure_safe_target(args: argparse.Namespace, update_count: int) -> None:
    if not args.apply:
        return
    if args.confirm_count != update_count:
        raise SystemExit(f"--confirm-count {args.confirm_count} does not match update count {update_count}")
    backend = server.current_db_backend()
    if args.target_database:
        if backend != "mysql":
            raise SystemExit("--target-database is only valid for MySQL backend")
        kwargs = server.mysql_connection_kwargs()
        if kwargs.get("database") != args.target_database:
            raise SystemExit(f"target database mismatch: {kwargs.get('database')} != {args.target_database}")
    else:
        raise SystemExit("--apply requires --target-database")
    if args.require_localhost:
        host = server.mysql_connection_kwargs().get("host", "")
        if host not in server.LOCAL_HOSTS:
            raise SystemExit(f"refusing non-local MySQL host: {host}")


def build_archive(rows: list[Any], generated: list[dict[str, Any]], archive_dir: Path, apply: bool) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = archive_dir / "backup_before_apply"
    backup_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        backup_dir / "advisors_raw_json.jsonl",
        [
            {
                "id": row["id"],
                "name": row["name"],
                "institution": row["institution"],
                "raw_json": row["raw_json"],
            }
            for row in rows
        ],
    )
    write_jsonl(archive_dir / "generated_highlights.jsonl", generated)
    write_csv(
        archive_dir / "generated_highlights.csv",
        generated,
        ["id", "name", "institution", "category", "stage_key", "stage_label", "highlight"],
    )
    write_jsonl(archive_dir / "sample_30.jsonl", generated[:30])
    write_restore_script(archive_dir / "restore_from_backup.py")
    summary = {
        "created_at": utc_slug(),
        "apply": apply,
        "total_advisors": len(rows),
        "generated_count": len(generated),
        "category_counts": Counter(item["category"] for item in generated),
        "stage_counts": Counter(item["stage_key"] for item in generated),
        "archive_dir": str(archive_dir),
    }
    (archive_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill short advisor highlights using local advisor facts and Applicant CV positioning.")
    parser.add_argument("--apply", action="store_true", help="Write generated highlights into advisors.raw_json.")
    parser.add_argument("--overwrite-existing", action="store_true", help="Overwrite existing non-empty highlight fields.")
    parser.add_argument("--limit", type=int, default=0, help="Limit rows for dry-run sampling.")
    parser.add_argument("--archive-dir", default="", help="Optional archive directory.")
    parser.add_argument("--confirm-count", type=int, default=-1, help="Required with --apply; must match update count.")
    parser.add_argument("--target-database", default="", help="Required with --apply for MySQL safety.")
    parser.add_argument("--require-localhost", action="store_true", help="Refuse --apply unless MySQL host is local.")
    args = parser.parse_args()

    with server.connect() as conn:
        all_rows = load_rows(conn)
        rows = all_rows[: args.limit] if args.limit else all_rows
        generated: list[dict[str, Any]] = []
        updates: list[tuple[str, str]] = []
        skipped_existing = 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for row in rows:
            raw = row_to_raw(row)
            if has_highlight(raw) and not args.overwrite_existing:
                skipped_existing += 1
                continue
            highlight = highlight_for(raw, row["stage_label"])
            raw["advisorHighlights"] = highlight
            raw["advisorHighlightsGeneratedBy"] = AUTOMATION_USER
            raw["advisorHighlightsGeneratedAt"] = now
            raw["advisorHighlightsVersion"] = "local-rule-v1"
            generated.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "institution": row["institution"],
                    "category": row["category"],
                    "stage_key": row["stage_key"],
                    "stage_label": row["stage_label"],
                    "highlight": highlight,
                }
            )
            updates.append((json.dumps(raw, ensure_ascii=False), row["id"]))

        archive_dir = Path(args.archive_dir) if args.archive_dir else PLATFORM_ROOT / "data" / f"advisor_highlights_backfill_{utc_slug()}"
        build_archive(rows, generated, archive_dir, args.apply)
        ensure_safe_target(args, len(updates))
        if args.apply:
            for raw_json, advisor_id in updates:
                conn.execute("update advisors set raw_json = ? where id = ?", (raw_json, advisor_id))

    result = {
        "apply": args.apply,
        "total_loaded": len(rows),
        "generated_count": len(generated),
        "skipped_existing": skipped_existing,
        "archive_dir": str(archive_dir),
        "sample": generated[:5],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
