#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import html
import json
import os
import re
import ssl
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PLATFORM_ROOT.parent
sys.path.insert(0, str(PLATFORM_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

import server  # noqa: E402
from backfill_advisor_highlights import highlight_for  # noqa: E402


AUTOMATION_USER = "main-agent-advisor-abc-reconcile-v1"
PRUNE_ARCHIVE = PLATFORM_ROOT / "data" / "advisor_official_profile_prune_2026-07-02T101435Z0000"
GOODNOTES_HTML = (
    PROJECT_ROOT
    / "03_导师检索"
    / "01_GoodNotes同步资料"
    / "530_Teacher_View_510_Marked_Advisors_2026-06-29.html"
)
RELATED_TABLES = [
    "advisors",
    "advisor_contacts",
    "advisor_reviews",
    "outreach_targets",
    "outreach_events",
    "ai_conversations",
    "ai_messages",
]
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
CONTACT_COLUMNS_WITHOUT_ID = [
    "advisor_id",
    "contact_type",
    "contact_value",
    "source_url",
    "evidence_text",
    "confidence",
    "is_primary",
    "primary_advisor_id",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
]
LOW_VALUE_DOMAINS = {
    "openalex.org",
    "scholar.google.com",
    "dblp.org",
    "semanticscholar.org",
    "researchgate.net",
    "linkedin.com",
    "pubmed.ncbi.nlm.nih.gov",
}
LOW_VALUE_MARKERS = (
    "/citations?",
    "/scholar?",
    "/publication/",
    "/paper/",
    "openalex.org",
    "pubmed.ncbi.nlm.nih.gov",
)
SPECIFIC_TITLE_PATTERNS = (
    (
        re.compile(r"\bdistinguished professor\b|\bchair professor\b|\bendowed professor\b|\bnamed professor\b", re.I),
        "star",
        "Distinguished / 杰出",
        "Distinguished Professor",
    ),
    (re.compile(r"\bassociate professor\b", re.I), "associate", "Associate / 中期", "Associate Professor"),
    (re.compile(r"\bassistant professor\b", re.I), "ap", "AP / 早期", "Assistant Professor"),
    (re.compile(r"\bfull professor\b", re.I), "full", "Full / 资深", "Full Professor"),
)
BROAD_PROFESSOR_PATTERN = re.compile(r"\bprofessor\b", re.I)


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def strip_tags(value: str) -> str:
    value = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", value)
    value = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return clean_text(html.unescape(value))


def js_string(value: str) -> str:
    try:
        return json.loads('"' + value.replace('"', '\\"') + '"')
    except json.JSONDecodeError:
        return value


def normalized_name(value: str) -> str:
    value = re.sub(r"（.*?）|\(.*?\)", "", value)
    value = unicodedata.normalize("NFKD", value)
    value = re.sub(r"[^a-zA-Z]+", " ", value).strip().lower()
    return re.sub(r"\s+", " ", value)


def english_part(value: str) -> str:
    parts = [part.strip() for part in str(value or "").split("/") if part.strip()]
    return parts[-1] if parts else clean_text(value)


def chinese_part(value: str) -> str:
    parts = [part.strip() for part in str(value or "").split("/") if part.strip()]
    return parts[0] if parts else ""


def norm_tokens(value: str) -> list[str]:
    return [token for token in normalized_name(value).split() if len(token) > 1]


def host_for(url: str) -> str:
    parsed = urllib.parse.urlparse(clean_text(url))
    return parsed.netloc.lower().split(":")[0].removeprefix("www.")


def site_key(host: str) -> str:
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 3 and parts[-2:] == ["github", "io"]:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def school_host(host: str) -> bool:
    return ".edu" in host or ".ac." in host or host.endswith(".ca")


def low_value_url(url: str) -> bool:
    lower = clean_text(url).lower()
    if not lower.startswith(("http://", "https://")):
        return True
    host = host_for(lower)
    key = site_key(host)
    if host in LOW_VALUE_DOMAINS or key in LOW_VALUE_DOMAINS:
        return True
    if any(marker in lower for marker in LOW_VALUE_MARKERS):
        return True
    return lower.endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx"))


def raw_json(row: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = json.loads(row.get("raw_json") or "{}")
    except json.JSONDecodeError:
        raw = {}
    return raw


def stage_url(raw: dict[str, Any]) -> str:
    return clean_text(raw.get("stageEvidenceUrl") or raw.get("stage_evidence_url"))


def pages_checked(raw: dict[str, Any]) -> int:
    value = clean_text(raw.get("evidencePagesChecked") or raw.get("evidence_pages_checked") or "0")
    try:
        return int(float(value))
    except ValueError:
        return 0


def infer_stage(text: str, fallback_key: str = "", fallback_label: str = "") -> tuple[str, str, str]:
    matches: list[tuple[int, str, str, str]] = []
    for pattern, key, label, evidence_title in SPECIFIC_TITLE_PATTERNS:
        match = pattern.search(text)
        if match:
            matches.append((match.start(), key, label, evidence_title))
    if matches:
        _pos, key, label, evidence_title = sorted(matches, key=lambda item: item[0])[0]
        return key, label, evidence_title
    if BROAD_PROFESSOR_PATTERN.search(text):
        return "full", "Full / 资深", "Professor"
    if fallback_key and fallback_key != "nonfaculty":
        return fallback_key, fallback_label or fallback_key, ""
    return "faculty_unknown", "Faculty / 职级未知", ""


def professor_signal(text: str) -> bool:
    return bool(re.search(r"\bassistant professor\b|\bassociate professor\b|\bfull professor\b|\bprofessor\b|\bfaculty\b", text, re.I))


def classify_backup_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = raw_json(row)
    url = stage_url(raw)
    stage_key = clean_text(row.get("stage_key") or raw.get("stageKey"))
    reliability = clean_text(row.get("evidence_reliability") or raw.get("evidenceReliability"))
    source_type = clean_text(raw.get("stageSourceType") or raw.get("stage_source_type"))
    evidence = clean_text(raw.get("stageEvidence"))
    host = host_for(url) if url else ""
    pages = pages_checked(raw)
    has_professor = professor_signal(evidence)
    if not url or low_value_url(url):
        return {"admit": False, "class": "excluded", "reason": "缺少可用主页 URL 或 URL 属于低价值/文件来源"}
    if school_host(host):
        if stage_key != "nonfaculty" or has_professor:
            return {"admit": True, "class": "A/B", "reason": "学校官网或学校托管主页可作为导师主页证据"}
        return {"admit": False, "class": "excluded", "reason": "学校页面存在，但当前证据仍显示非独立导师或非 faculty"}
    if stage_key == "nonfaculty" and not has_professor:
        return {"admit": False, "class": "excluded", "reason": "外部主页证据显示非导师路径，未纳入"}
    if source_type == "page_text" and (reliability in {"高", "中"} or pages > 0):
        return {"admit": True, "class": "C", "reason": "外部个人主页已有本地页面文本证据"}
    if source_type == "homepage_accessible" and reliability in {"高", "中"} and pages > 0:
        return {"admit": True, "class": "C", "reason": "外部个人主页可访问且已有中/高可靠度证据"}
    return {"admit": False, "class": "excluded", "reason": "外部主页证据不足，保留归档待人工核实"}


def parse_goodnotes_rows() -> list[dict[str, str]]:
    if not GOODNOTES_HTML.exists():
        return []
    text = GOODNOTES_HTML.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\{id:"(?P<old_id>[^"]+)", name:"(?P<name>(?:\\.|[^"])*)", '
        r'priority:"(?P<priority>(?:\\.|[^"])*)", school:"(?P<school>(?:\\.|[^"])*)", '
        r'dept:"(?P<dept>(?:\\.|[^"])*)", city:"(?P<city>(?:\\.|[^"])*)", '
        r'status:"(?P<status>(?:\\.|[^"])*)", score:"(?P<score>(?:\\.|[^"])*)", '
        r'note:"(?P<note>(?:\\.|[^"])*)", url:"(?P<url>(?:\\.|[^"])*)"\}'
    )
    return [{key: js_string(value) for key, value in match.groupdict().items()} for match in pattern.finditer(text)]


def fetch_page(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 ApplicantAdvisorVerifier/1.0",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.2",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            content_type = response.headers.get("content-type", "")
            body = response.read(350_000)
    except urllib.error.URLError as error:
        if "CERTIFICATE_VERIFY_FAILED" not in str(error):
            return {"ok": False, "url": url, "error": str(error)}
        try:
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                final_url = response.geturl()
                content_type = response.headers.get("content-type", "")
                body = response.read(350_000)
        except (urllib.error.URLError, TimeoutError, OSError) as fallback_error:
            return {"ok": False, "url": url, "error": str(fallback_error)}
    except (TimeoutError, OSError) as error:
        return {"ok": False, "url": url, "error": str(error)}
    encoding = "utf-8"
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.I)
    if match:
        encoding = match.group(1).strip()
    text = body.decode(encoding, errors="replace")
    plain = strip_tags(text)
    return {"ok": True, "url": final_url, "content_type": content_type, "text": plain}


def contains_name(text: str, name: str) -> bool:
    tokens = norm_tokens(name)
    if not tokens:
        return False
    lower = normalized_name(text)
    if " ".join(tokens) in lower:
        return True
    if len(tokens) >= 2:
        return tokens[0] in lower and tokens[-1] in lower
    return tokens[0] in lower


def contains_institution(text: str, institution: str) -> bool:
    institution = english_part(institution)
    lower = clean_text(text).lower()
    norm_inst = clean_text(institution).lower()
    if norm_inst and norm_inst in lower:
        return True
    aliases = {
        "university of california, santa barbara": ("ucsb", "santa barbara"),
        "university of california, los angeles": ("ucla",),
        "university of california, santa cruz": ("ucsc",),
        "university of texas at austin": ("ut austin", "utexas", "the university of texas"),
        "georgia institute of technology": ("georgia tech",),
        "the ohio state university": ("ohio state",),
        "university of massachusetts amherst": ("umass amherst", "u mass amherst"),
        "carnegie mellon university": ("carnegie mellon", "cmu"),
        "new york university": ("nyu",),
        "penn state university": ("penn state",),
        "virginia tech": ("virginia polytechnic", "virginia tech"),
        "university of virginia": ("uva", "u va", "virginia"),
    }
    for alias in aliases.get(norm_inst, ()):
        if alias in lower:
            return True
    parts = [part for part in re.split(r"[^a-z]+", norm_inst) if len(part) > 3 and part not in {"university", "college"}]
    return bool(parts and any(part in lower for part in parts[:2]))


def verification_snippet(text: str, name: str, institution: str) -> str:
    lower = clean_text(text).lower()
    anchors = norm_tokens(name) + [english_part(institution).lower()]
    indices = [lower.find(anchor) for anchor in anchors if anchor and lower.find(anchor) >= 0]
    start = max(0, min(indices) - 120) if indices else 0
    return clean_text(text[start : start + 360])


def verify_page(url: str, name: str, institution: str, timeout: int) -> dict[str, Any]:
    if not url or low_value_url(url):
        return {"verified": False, "reason": "URL 为空、文件或低价值来源", "url": url}
    fetched = fetch_page(url, timeout)
    if not fetched.get("ok"):
        return {"verified": False, "reason": f"页面不可访问：{fetched.get('error', '')}", "url": url}
    text = fetched.get("text", "")
    host = host_for(fetched.get("url", url))
    name_ok = contains_name(text, name)
    institution_ok = contains_institution(text, institution)
    title_ok = professor_signal(text)
    if school_host(host) and name_ok and (title_ok or institution_ok):
        key, label, title = infer_stage(text)
        return {
            "verified": True,
            "class": "A/B",
            "reason": "学校官网/学校托管主页页面可访问，并能匹配姓名和 faculty 线索",
            "url": fetched.get("url", url),
            "stage_key": key,
            "stage_label": label,
            "title": title,
            "snippet": verification_snippet(text, name, institution),
        }
    if name_ok and institution_ok and title_ok:
        key, label, title = infer_stage(text)
        return {
            "verified": True,
            "class": "C",
            "reason": "外部个人主页页面可访问，并能匹配姓名、当前学校和 faculty 职称",
            "url": fetched.get("url", url),
            "stage_key": key,
            "stage_label": label,
            "title": title,
            "snippet": verification_snippet(text, name, institution),
        }
    return {
        "verified": False,
        "reason": f"页面可访问但证据不足：name={name_ok}, institution={institution_ok}, title={title_ok}",
        "url": fetched.get("url", url),
        "snippet": verification_snippet(text, name, institution),
    }


def urls_from_text(value: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"https?://[^\s，。；;）)]+", value or ""):
        url = match.group(0).strip().rstrip(".,")
        if url not in urls:
            urls.append(url)
    return urls


def verify_goodnotes_row(row: dict[str, str], timeout: int) -> dict[str, Any]:
    candidates: list[str] = []
    for url in [row.get("url", ""), *urls_from_text(row.get("note", ""))]:
        url = clean_text(url)
        if url and url not in candidates:
            candidates.append(url)
    failures: list[dict[str, Any]] = []
    for url in candidates:
        verification = verify_page(url, row.get("name", ""), english_part(row.get("school", "")), timeout)
        if verification.get("verified"):
            if url != row.get("url"):
                verification["verified_from_alternate_url"] = url
            return verification
        failures.append(verification)
    if failures:
        last = failures[-1]
        last["attempted_urls"] = candidates
        return last
    return {"verified": False, "reason": "没有可复核 URL", "attempted_urls": candidates}


def category_for_goodnotes(row: dict[str, str]) -> str:
    text = clean_text(" ".join([row.get("dept", ""), row.get("note", ""), row.get("priority", "")])).lower()
    if any(word in text for word in ("evaluation", "benchmark", "评测", "基准")):
        return "Core evaluation"
    if any(word in text for word in ("persona", "agent", "对话", "role")):
        return "Agent/persona"
    if any(word in text for word in ("hci", "交互", "human", "social", "社会")):
        return "HCI/social"
    if any(word in text for word in ("recommend", "推荐", "user", "用户")):
        return "Recommender/user"
    if any(word in text for word in ("education", "student", "learning", "教育")):
        return "Education/HCI"
    if any(word in text for word in ("nlp", "natural language", "语言", "llm")):
        return "NLP/LLM-adjacent"
    return "NLP/LLM-adjacent"


def pool_for_goodnotes(row: dict[str, str]) -> tuple[str, str]:
    priority = clean_text(row.get("priority"))
    if priority.startswith("P1"):
        return "P1 核心 LLM Evaluation/Benchmarking", "p1"
    if priority.startswith("P2"):
        return "P2 Agent / Persona / HCI 强相关", "p2"
    return "P3 相关", "p3"


def slug_name(value: str) -> str:
    slug = "-".join(norm_tokens(value))
    return slug[:80] or "advisor"


def goodnotes_id(row: dict[str, str]) -> str:
    old_id = clean_text(row.get("old_id")).lower().replace("_", "-")
    return f"goodnotes-{old_id}-{slug_name(row.get('name', ''))}"


def build_goodnotes_advisor(row: dict[str, str], verification: dict[str, Any], rank: int) -> dict[str, Any]:
    name = re.sub(r"（.*?）|\(.*?\)", "", row.get("name", "")).strip()
    school = english_part(row.get("school", ""))
    school_zh = chinese_part(row.get("school", ""))
    city = english_part(row.get("city", ""))
    city_zh = chinese_part(row.get("city", ""))
    pool, pool_class = pool_for_goodnotes(row)
    stage_key = verification.get("stage_key") or "faculty_unknown"
    stage_label = verification.get("stage_label") or "Faculty / 职级未知"
    evidence_reliability = "高" if verification.get("class") == "A/B" else "中"
    raw = {
        "id": goodnotes_id(row),
        "num": rank,
        "rank": rank,
        "name": name,
        "rawName": row.get("name", ""),
        "institution": school,
        "institutionZh": school_zh,
        "firstInstitution": school,
        "firstInstitutionZh": school_zh,
        "city": city,
        "cityZh": city_zh,
        "state": "",
        "stateZh": "",
        "initialPool": pool,
        "poolClass": pool_class,
        "primaryCategory": category_for_goodnotes(row),
        "categories": category_for_goodnotes(row),
        "matchedKeywords": "GoodNotes 人工标记导师；按 ABC 规则回填，需后续二轮深查研究匹配和招生状态",
        "source": "GoodNotes marked advisor with verified page",
        "evidence": [verification.get("snippet") or verification.get("reason") or ""],
        "verificationStatus": "GoodNotes 人工标记来源；主页真实性已按已有 URL 复核，研究匹配和招生状态仍需二轮核实",
        "stageKey": stage_key,
        "stageLabel": stage_label,
        "stageEvidenceLevel": evidence_reliability,
        "stageEvidence": verification.get("snippet") or verification.get("reason") or "",
        "stageEvidenceUrl": verification.get("url") or row.get("url", ""),
        "stageSourceType": "goodnotes_verified_page",
        "phdAdvisingStatus": "可能具备 PhD advising path，需项目页确认",
        "phdAdvisingEvidenceLevel": "低",
        "phdAdvisingEvidence": "GoodNotes 旧名单保留，尚未逐项核实 PhD advising path",
        "phdAdvisingUrl": verification.get("url") or row.get("url", ""),
        "recruitingStatus": "未知",
        "recruitingEvidenceLevel": "低",
        "recruitingEvidence": "尚未找到目标申请季的明确招生信号",
        "recruitingUrl": verification.get("url") or row.get("url", ""),
        "studentBackgroundStatus": "未知",
        "studentBackgroundEvidenceLevel": "低",
        "studentBackgroundEvidence": "尚未二轮核实 current / former students 背景",
        "studentBackgroundUrl": verification.get("url") or row.get("url", ""),
        "evidenceReliability": "高（学校官网/学校托管主页）" if evidence_reliability == "高" else "中（个人主页强证据）",
        "evidencePagesChecked": "1",
        "links": [{"label": "主页", "url": verification.get("url") or row.get("url", "")}],
        "goodnotesOldId": row.get("old_id", ""),
        "goodnotesStatus": row.get("status", ""),
        "goodnotesPriority": row.get("priority", ""),
        "goodnotesNote": row.get("note", ""),
        "advisorAdmissionEvidence": "按 ABC 规则纳入主库；不单列 A/B/C 标签，证据可靠度承载来源强度",
    }
    raw["advisorHighlights"] = highlight_for(raw, stage_label)
    raw["advisorHighlightsGeneratedBy"] = AUTOMATION_USER
    raw["advisorHighlightsGeneratedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw["advisorHighlightsVersion"] = "local-rule-v1"
    return {
        "id": raw["id"],
        "rank": rank,
        "name": name,
        "institution": school,
        "institution_zh": school_zh,
        "city": city,
        "state": "",
        "pool": pool,
        "category": raw["primaryCategory"],
        "stage_key": stage_key,
        "stage_label": stage_label,
        "school_tier": "",
        "school_tier_label": "",
        "evidence_reliability": evidence_reliability,
        "recruiting_status": raw["recruitingStatus"],
        "student_background_status": raw["studentBackgroundStatus"],
        "raw_json": json.dumps(raw, ensure_ascii=False),
    }


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


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


def quote_ident(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def table_rows(conn: server.DbConnection, table: str) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in conn.execute(f"select * from {quote_ident(table)}").fetchall()]


def ensure_apply_safety(args: argparse.Namespace, update_count: int, insert_count: int) -> None:
    if not args.apply:
        return
    if args.confirm_update_count != update_count:
        raise SystemExit(f"--confirm-update-count {args.confirm_update_count} 与实际更新/恢复数 {update_count} 不一致")
    if args.confirm_insert_count != insert_count:
        raise SystemExit(f"--confirm-insert-count {args.confirm_insert_count} 与实际新增数 {insert_count} 不一致")
    if not args.target_database:
        raise SystemExit("--apply 必须提供 --target-database")
    if server.current_db_backend() != "mysql":
        raise SystemExit("--apply 只允许在 MySQL 后端执行")
    kwargs = server.mysql_connection_kwargs()
    if kwargs.get("database") != args.target_database:
        raise SystemExit(f"目标数据库不匹配：{kwargs.get('database')} != {args.target_database}")
    if args.require_localhost and kwargs.get("host", "").lower() not in server.LOCAL_HOSTS:
        raise SystemExit(f"拒绝写入非本机 MySQL：{kwargs.get('host')}")


def advisor_insert_values(row: dict[str, Any]) -> list[Any]:
    return [row.get(column, "") for column in ADVISOR_COLUMNS]


def upsert_advisors(conn: server.DbConnection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = ADVISOR_COLUMNS
    sql = (
        "insert into advisors ("
        + ", ".join(quote_ident(column) for column in columns)
        + ") values ("
        + ", ".join("?" for _ in columns)
        + ") "
    )
    if conn.backend == "mysql":
        update_columns = [column for column in columns if column != "id"]
        sql += "on duplicate key update " + ", ".join(f"{quote_ident(column)} = values({quote_ident(column)})" for column in update_columns)
    else:
        update_columns = [column for column in columns if column != "id"]
        sql += "on conflict(id) do update set " + ", ".join(f"{quote_ident(column)} = excluded.{quote_ident(column)}" for column in update_columns)
    conn.executemany(sql, [advisor_insert_values(row) for row in rows])


def insert_restored_contacts(conn: server.DbConnection, contact_rows: list[dict[str, Any]]) -> int:
    if not contact_rows:
        return 0
    available = server.table_columns(conn, "advisor_contacts")
    columns = [column for column in CONTACT_COLUMNS_WITHOUT_ID if column in available]
    sql = (
        "insert into advisor_contacts ("
        + ", ".join(quote_ident(column) for column in columns)
        + ") values ("
        + ", ".join("?" for _ in columns)
        + ")"
    )
    inserted = 0
    for row in contact_rows:
        exists = conn.execute(
            "select id from advisor_contacts where advisor_id = ? and contact_value = ?",
            (row.get("advisor_id"), row.get("contact_value")),
        ).fetchone()
        if exists:
            continue
        conn.execute(sql, [row.get(column) for column in columns])
        inserted += 1
    return inserted


def rerank_from_original_order(conn: server.DbConnection, backup_rows: list[dict[str, Any]], extra_ids: list[str]) -> None:
    order: list[str] = []
    for row in sorted(backup_rows, key=lambda item: int(item.get("rank") or 0)):
        row_id = row.get("id")
        if row_id and row_id not in order:
            order.append(row_id)
    for row_id in extra_ids:
        if row_id not in order:
            order.append(row_id)
    current_ids = {row["id"] for row in conn.execute("select id from advisors").fetchall()}
    final = [row_id for row_id in order if row_id in current_ids]
    for row in conn.execute("select id from advisors order by `rank`, id").fetchall():
        if row["id"] not in final:
            final.append(row["id"])
    for rank, advisor_id in enumerate(final, start=1):
        conn.execute("update advisors set `rank` = ? where id = ?", (rank, advisor_id))
        raw_row = conn.execute("select raw_json from advisors where id = ?", (advisor_id,)).fetchone()
        if raw_row:
            raw = json.loads(raw_row["raw_json"] or "{}")
            raw["num"] = rank
            raw["rank"] = rank
            conn.execute("update advisors set raw_json = ? where id = ?", (json.dumps(raw, ensure_ascii=False), advisor_id))


def prepare_restored_row(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    prepared = {column: row.get(column, "") for column in ADVISOR_COLUMNS}
    raw = raw_json(prepared)
    raw.setdefault("id", prepared["id"])
    raw.setdefault("name", prepared["name"])
    raw.setdefault("institution", prepared.get("institution", ""))
    stage_text = clean_text(raw.get("stageEvidence"))
    if prepared.get("stage_key") == "nonfaculty" and professor_signal(stage_text):
        stage_key, stage_label, _title = infer_stage(stage_text, "", "")
        prepared["stage_key"] = stage_key
        prepared["stage_label"] = stage_label
        raw["stageKey"] = stage_key
        raw["stageLabel"] = stage_label
        raw["stageEvidence"] = stage_text.replace("页面文本出现非导师路径职称：", "页面文本出现 faculty 职称：", 1)
    if decision["class"] == "A/B":
        prepared["evidence_reliability"] = "高" if prepared.get("evidence_reliability") != "高" else prepared["evidence_reliability"]
        raw["evidenceReliability"] = "高（学校官网/学校托管主页）"
    else:
        prepared["evidence_reliability"] = "中" if prepared.get("evidence_reliability") != "高" else prepared["evidence_reliability"]
        raw["evidenceReliability"] = "中（个人主页强证据）" if prepared["evidence_reliability"] == "中" else "高（个人主页强证据）"
    raw["advisorAdmissionEvidence"] = f"{decision['reason']}；按 ABC 规则纳入主库，不单列 A/B/C 标签"
    raw["advisorAdmissionUpdatedBy"] = AUTOMATION_USER
    raw["advisorAdmissionUpdatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not clean_text(raw.get("advisorHighlights")):
        raw["advisorHighlights"] = highlight_for(raw, prepared.get("stage_label", ""))
        raw["advisorHighlightsGeneratedBy"] = AUTOMATION_USER
        raw["advisorHighlightsGeneratedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        raw["advisorHighlightsVersion"] = "local-rule-v1"
    prepared["raw_json"] = json.dumps(raw, ensure_ascii=False)
    return prepared


def export_package(conn: server.DbConnection, archive_dir: Path) -> dict[str, Any]:
    advisors = table_rows(conn, "advisors")
    contacts = table_rows(conn, "advisor_contacts")
    package = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "created_by": AUTOMATION_USER,
        "tables": {
            "advisors": advisors,
            "advisor_contacts": contacts,
        },
    }
    path = archive_dir / "cloud_sync_advisor_pool.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(package, handle, ensure_ascii=False)
    return {"path": str(path), "advisors": len(advisors), "advisor_contacts": len(contacts)}


def build_plan(args: argparse.Namespace, archive_dir: Path) -> dict[str, Any]:
    backup_rows = read_jsonl(PRUNE_ARCHIVE / "backup_before_apply" / "advisors.jsonl")
    backup_contacts = read_jsonl(PRUNE_ARCHIVE / "backup_before_apply" / "advisor_contacts.jsonl")
    if not backup_rows:
        raise SystemExit(f"找不到清洗前 advisors 备份：{PRUNE_ARCHIVE}")
    backup_by_id = {row["id"]: row for row in backup_rows}
    backup_by_name: dict[str, list[dict[str, Any]]] = {}
    for row in backup_rows:
        backup_by_name.setdefault(normalized_name(row.get("name", "")), []).append(row)

    with server.connect() as conn:
        server.ensure_base_schema(conn)
        current_rows = table_rows(conn, "advisors")
        current_ids = {row["id"] for row in current_rows}
        current_names = {normalized_name(row.get("name", "")) for row in current_rows}

    restored: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    admission_rows: list[dict[str, Any]] = []
    for row in backup_rows:
        if row["id"] in current_ids:
            continue
        decision = classify_backup_row(row)
        report_row = {
            "id": row["id"],
            "name": row.get("name", ""),
            "institution": row.get("institution", ""),
            "stage_key": row.get("stage_key", ""),
            "evidence_reliability": row.get("evidence_reliability", ""),
            "url": stage_url(raw_json(row)),
            "admission_class": decision["class"],
            "reason": decision["reason"],
        }
        if decision["admit"]:
            restored.append(prepare_restored_row(row, decision))
            admission_rows.append(report_row)
        else:
            excluded.append(report_row)

    goodnotes_rows = parse_goodnotes_rows()
    goodnotes_report: list[dict[str, Any]] = []
    new_goodnotes: list[dict[str, Any]] = []
    next_rank = max([int(row.get("rank") or 0) for row in backup_rows] + [0]) + 1
    for old in goodnotes_rows:
        key = normalized_name(old.get("name", ""))
        matched = backup_by_name.get(key, [])
        if matched:
            matched_row = matched[0]
            status = "current" if matched_row["id"] in current_ids else ("restored" if matched_row["id"] in {row["id"] for row in restored} else "archived")
            goodnotes_report.append(
                {
                    "old_id": old.get("old_id", ""),
                    "name": old.get("name", ""),
                    "old_url": old.get("url", ""),
                    "match_status": status,
                    "matched_id": matched_row["id"],
                    "matched_institution": matched_row.get("institution", ""),
                }
            )
            if status == "archived" and args.verify_goodnotes_urls:
                verification = verify_goodnotes_row(old, args.timeout)
                if verification.get("verified"):
                    prepared = prepare_restored_row(
                        matched_row,
                        {"class": verification.get("class", "C"), "reason": verification.get("reason", "GoodNotes URL 复核通过")},
                    )
                    raw = raw_json(prepared)
                    raw["stageEvidenceUrl"] = verification.get("url") or old.get("url", "")
                    raw["stageEvidence"] = verification.get("snippet") or raw.get("stageEvidence", "")
                    raw["stageSourceType"] = "goodnotes_verified_page"
                    raw["goodnotesOldId"] = old.get("old_id", "")
                    raw["goodnotesStatus"] = old.get("status", "")
                    raw["goodnotesPriority"] = old.get("priority", "")
                    raw["goodnotesNote"] = old.get("note", "")
                    if verification.get("stage_key"):
                        prepared["stage_key"] = verification["stage_key"]
                        prepared["stage_label"] = verification["stage_label"]
                        raw["stageKey"] = verification["stage_key"]
                        raw["stageLabel"] = verification["stage_label"]
                    prepared["raw_json"] = json.dumps(raw, ensure_ascii=False)
                    restored.append(prepared)
                    goodnotes_report[-1]["match_status"] = "restored_by_goodnotes_verification"
                    goodnotes_report[-1]["verification"] = verification
                else:
                    goodnotes_report[-1]["verification"] = verification
            continue
        if key in current_names:
            goodnotes_report.append({"old_id": old.get("old_id", ""), "name": old.get("name", ""), "match_status": "current_name_only"})
            continue
        verification = {"verified": False, "reason": "未启用 GoodNotes URL 联网复核"}
        if args.verify_goodnotes_urls:
            verification = verify_goodnotes_row(old, args.timeout)
        if verification.get("verified"):
            advisor = build_goodnotes_advisor(old, verification, next_rank)
            next_rank += 1
            new_goodnotes.append(advisor)
            goodnotes_report.append(
                {
                    "old_id": old.get("old_id", ""),
                    "name": old.get("name", ""),
                    "old_url": old.get("url", ""),
                    "match_status": "new_goodnotes_verified",
                    "new_id": advisor["id"],
                    "verification": verification,
                }
            )
        else:
            goodnotes_report.append(
                {
                    "old_id": old.get("old_id", ""),
                    "name": old.get("name", ""),
                    "old_url": old.get("url", ""),
                    "match_status": "not_added",
                    "verification": verification,
                }
            )

    restored_by_id: dict[str, dict[str, Any]] = {}
    for row in restored:
        restored_by_id[row["id"]] = row
    restored = list(restored_by_id.values())
    restore_ids = {row["id"] for row in restored}
    restored_contacts = [row for row in backup_contacts if row.get("advisor_id") in restore_ids]
    return {
        "backup_rows": backup_rows,
        "restore_rows": restored,
        "new_goodnotes_rows": new_goodnotes,
        "restore_contacts": restored_contacts,
        "excluded": excluded,
        "admissions": admission_rows,
        "goodnotes_report": goodnotes_report,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    archive_dir = Path(args.archive_dir) if args.archive_dir else PLATFORM_ROOT / "data" / f"advisor_abc_reconcile_{utc_slug()}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    plan = build_plan(args, archive_dir)
    update_rows = plan["restore_rows"]
    insert_rows = plan["new_goodnotes_rows"]
    ensure_apply_safety(args, len(update_rows), len(insert_rows))

    write_jsonl(archive_dir / "restore_advisors.jsonl", update_rows)
    write_jsonl(archive_dir / "new_goodnotes_advisors.jsonl", insert_rows)
    write_jsonl(archive_dir / "restore_contacts.jsonl", plan["restore_contacts"])
    write_jsonl(archive_dir / "excluded_advisors.jsonl", plan["excluded"])
    write_jsonl(archive_dir / "goodnotes_report.jsonl", plan["goodnotes_report"])
    write_csv(
        archive_dir / "excluded_advisors.csv",
        plan["excluded"],
        ["id", "name", "institution", "stage_key", "evidence_reliability", "url", "admission_class", "reason"],
    )

    backup_paths: dict[str, str] = {}
    export_info: dict[str, Any] = {}
    before_counts: dict[str, int] = {}
    after_counts: dict[str, int] = {}
    inserted_contacts = 0
    with server.connect() as conn:
        server.ensure_base_schema(conn)
        for table in ["advisors", "advisor_contacts", "advisor_reviews", "outreach_targets", "outreach_events", "documents", "application_programs"]:
            before_counts[table] = int(conn.execute(f"select count(*) as c from {quote_ident(table)}").fetchone()["c"])
        if args.apply:
            backup_dir = archive_dir / "backup_before_apply"
            backup_dir.mkdir(parents=True, exist_ok=True)
            for table in RELATED_TABLES:
                path = backup_dir / f"{table}.jsonl"
                write_jsonl(path, table_rows(conn, table))
                backup_paths[table] = str(path)
            upsert_advisors(conn, update_rows + insert_rows)
            inserted_contacts = insert_restored_contacts(conn, plan["restore_contacts"])
            server.sync_advisor_contact_primary(conn)
            rerank_from_original_order(conn, plan["backup_rows"], [row["id"] for row in insert_rows])
        for table in ["advisors", "advisor_contacts", "advisor_reviews", "outreach_targets", "outreach_events", "documents", "application_programs"]:
            after_counts[table] = int(conn.execute(f"select count(*) as c from {quote_ident(table)}").fetchone()["c"])
        if args.apply:
            export_info = export_package(conn, archive_dir)

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "definition": "A/B/C 进入主库；不新增前台 A/B/C 标签，通过证据可靠度和审计字段体现来源强度。",
        "archive_dir": str(archive_dir),
        "verify_goodnotes_urls": bool(args.verify_goodnotes_urls),
        "restore_count": len(update_rows),
        "new_goodnotes_count": len(insert_rows),
        "restore_contact_candidates": len(plan["restore_contacts"]),
        "inserted_contacts": inserted_contacts,
        "excluded_count": len(plan["excluded"]),
        "admission_class_counts": dict(Counter(row.get("admission_class") for row in plan["admissions"])),
        "excluded_reason_counts": dict(Counter(row.get("reason") for row in plan["excluded"]).most_common()),
        "goodnotes_status_counts": dict(Counter(row.get("match_status") for row in plan["goodnotes_report"]).most_common()),
        "before_counts": before_counts,
        "after_counts": after_counts,
        "backup_paths": backup_paths,
        "export": export_info,
        "samples_restore": [
            {
                "id": row["id"],
                "name": row["name"],
                "institution": row.get("institution", ""),
                "evidence_reliability": row.get("evidence_reliability", ""),
                "stage_key": row.get("stage_key", ""),
            }
            for row in (update_rows + insert_rows)[:20]
        ],
    }
    (archive_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="按 A/B/C 新规则回填导师主库，并准备云端同步包。")
    parser.add_argument("--apply", action="store_true", help="写入本地 MySQL；默认只 dry-run 输出归档")
    parser.add_argument("--verify-goodnotes-urls", action="store_true", help="联网打开旧 GoodNotes 主页 URL 以确认可新增/恢复")
    parser.add_argument("--timeout", type=int, default=8, help="单个 URL 访问超时秒数")
    parser.add_argument("--archive-dir", default="", help="归档输出目录")
    parser.add_argument("--target-database", default="", help="apply 必填：确认数据库名")
    parser.add_argument("--require-localhost", action="store_true", help="apply 时要求 MySQL host 是本机地址")
    parser.add_argument("--confirm-update-count", type=int, default=-1, help="apply 必填：确认恢复/更新导师数量")
    parser.add_argument("--confirm-insert-count", type=int, default=-1, help="apply 必填：确认新增导师数量")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
