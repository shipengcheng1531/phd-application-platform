#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import ssl
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
DOCUMENT_UPLOAD_DIR = DATA_DIR / "document_uploads"
AI_TOOL_CACHE_DIR = DATA_DIR / "ai_tool_cache"
DB_PATH = DATA_DIR / "platform.sqlite3"
SEED_HTML_FILENAME = "demo_advisors.html"
PLATFORM_SEED_HTML = ROOT / "seed" / SEED_HTML_FILENAME
LEGACY_SEED_HTML = PLATFORM_SEED_HTML
SEED_HTML_ENV = "PHD_PLATFORM_SEED_HTML"
DB_BACKEND_ENV = "PHD_PLATFORM_DB_BACKEND"
AI_API_KEY_ENV = "PHD_PLATFORM_AI_API_KEY"
AI_KEY_ENV_ONLY_ENV = "PHD_PLATFORM_AI_KEY_ENV_ONLY"
AI_REQUEST_TIMEOUT_ENV = "PHD_PLATFORM_AI_REQUEST_TIMEOUT_SECONDS"
AI_SSL_CERT_FILE_ENV = "PHD_PLATFORM_AI_SSL_CERT_FILE"
PLATFORM_ENV_ENV = "PHD_PLATFORM_ENV"
PLATFORM_BIND_HOST_ENV = "PHD_PLATFORM_BIND_HOST"
SUPPORTED_DB_BACKENDS = {"sqlite", "mysql"}


def load_env_file(path: Path, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or (key in os.environ and not override):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


load_env_file(ROOT / ".env")
load_env_file(ROOT / ".env.local", override=True)


REVIEW_FIELDS = {"interest", "queryStatus", "reviewStatus", "note"}
INTEREST_VALUES = {"高兴趣", "有兴趣", "待判断", "不感兴趣"}
LEGACY_INTEREST_ALIASES = {
    "很有兴趣": "高兴趣",
    "高": "高兴趣",
    "一般": "有兴趣",
    "中": "有兴趣",
    "低": "不感兴趣",
    "不保留": "不感兴趣",
    "排除": "不感兴趣",
    "未看": "",
}
QUERY_STATUS_VALUES = {"待请求", "请求查询", "已查询"}
LEGACY_QUERY_STATUS_ALIASES = {
    "需查询": "请求查询",
}
SESSION_COOKIE = "phd_platform_session"
MAX_DOCUMENT_UPLOAD_BYTES = 50 * 1024 * 1024
SESSIONS: dict[str, str] = {}
ADVISOR_REVIEW_LOCKS: dict[str, threading.RLock] = {}
ADVISOR_REVIEW_LOCKS_GUARD = threading.Lock()
UTC_NOW_LOCK = threading.Lock()
LAST_UTC_NOW: datetime | None = None
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
OUTREACH_STATUSES = {"待联系", "已发送", "已回复", "准备中", "需跟进", "已面试", "已申请", "暂停", "不继续", "已取消"}
OUTREACH_RESPONSE_STATUSES = {"待回复", "积极", "中性", "拒绝", "未回复", "自动回复", "待判断"}
OUTREACH_STAGES = {"跟进中", "已面试", "已申请", "准备套磁", "首次邮件", "等待回复", "面试中", "申请中", "结束"}
OUTREACH_PRIORITIES = {"高", "中", "低", ""}
OUTREACH_EVENT_TYPES = {"准备", "已发送邮件", "收到回复", "跟进", "面试", "申请", "备注"}
OUTREACH_FILTER_ALIASES = {
    "status": {
        "待联系": ["待联系", "准备中"],
        "已发送": ["已发送"],
        "已回复": ["已回复", "需跟进", "已面试", "已申请"],
    },
    "response": {
        "待回复": ["待回复", "未回复", "待判断", "自动回复"],
        "积极": ["积极"],
        "中性": ["中性"],
        "拒绝": ["拒绝"],
    },
    "stage": {
        "跟进中": ["跟进中", "准备套磁", "首次邮件", "等待回复", "结束"],
        "已面试": ["已面试", "面试中"],
        "已申请": ["已申请", "申请中"],
    },
}
CONTACT_TYPES = {"导师邮箱", "Lab 邮箱", "项目邮箱", "Contact Form", "其他"}
CONTACT_CONFIDENCES = {"高", "中", "低", "待确认"}
DEFAULT_AI_REQUEST_TIMEOUT_SECONDS = 180
AI_ADVISOR_CHAT_TITLE_PREFIX = "AI助手："
AI_INITIAL_MAX_TOKENS = 700
AI_FOLLOWUP_MAX_TOKENS = 1200
AI_HISTORY_MESSAGE_LIMIT = 12
AI_CV_CONTEXT_CHARS = 6000
AI_ADVISOR_EVIDENCE_LIMIT = 5
AI_ADVISOR_LINK_LIMIT = 6
DEFAULT_AI_TOOLS_ENABLED = 0
DEFAULT_AI_ALLOW_SEARCH_PAGES = 0
DEFAULT_AI_TOOL_MAX_RESULTS = 5
DEFAULT_AI_TOOL_TIMEOUT_SECONDS = 8
DEFAULT_AI_TOOL_CACHE_TTL_SECONDS = 24 * 60 * 60
AI_TOOL_MAX_FETCH_BYTES = 700_000
AI_TOOL_TEXT_CHARS = 5000
AI_TOOL_CONTEXT_CHARS = 12000
AI_TOOL_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) ApplicantPlatformAITools/0.1"
AI_TOOL_MAX_REDIRECTS = 5
SEARCH_TRIGGER_WORDS = ("查", "搜索", "检索", "最新", "最近", "实时", "today", "current", "search", "lookup", "find")
WEATHER_TRIGGER_WORDS = ("天气", "气温", "降雨", "下雨", "带伞", "weather", "temperature", "rain")
LITERATURE_TRIGGER_WORDS = ("文献", "论文", "paper", "publication", "publications", "scholar", "semantic scholar", "google scholar")
SCHOOL_LOCATION_TRIGGER_WORDS = ("学校", "大学", "项目", "城市", "地区", "生活成本", "消费", "租房", "治安", "cost of living", "rent", "safety", "city", "school", "university")
ADVISOR_CATEGORY_SORT = [
    "Core evaluation",
    "Agent/persona",
    "NLP/LLM-adjacent",
    "HCI/social",
    "Recommender/user",
    "Education/HCI",
    "AI/ML adjacent",
    "Trustworthy/robust",
    "Software/systems adjacent",
    "CS faculty fallback",
]
ADVISOR_STAGE_SORT = [
    "ap",
    "associate",
    "full",
    "star",
    "faculty_unknown",
    "nonfaculty",
    "unknown",
]
PROGRAM_STATUSES = {"候选", "准备中", "已申请", "已提交", "已拒绝", "已录取", "不申请", ""}
PROGRAM_PRIORITIES = {"高", "中", "低", ""}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
GENERIC_BINARY_MIMES = {"", "application/octet-stream", "binary/octet-stream"}
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NS}}}"
MAX_PREVIEW_CHARS = 300_000
DOCUMENT_TYPES = [
    ("CV", "CV"),
    ("SOP", "SOP / Statement of Purpose"),
    ("Research Statement", "Research Statement"),
    ("Personal Statement", "Personal Statement"),
    ("套磁信", "套磁信 / Cold Email"),
    ("推荐信", "推荐信相关"),
    ("Writing Sample", "Writing Sample"),
    ("Diversity Statement", "Diversity Statement"),
    ("成绩单", "成绩单 / Transcript"),
    ("语言成绩", "语言成绩 / TOEFL/IELTS"),
    ("GRE", "GRE"),
    ("作品集/补充材料", "作品集 / 补充材料"),
    ("其他", "其他"),
]
DOCUMENT_TYPE_VALUES = {value for value, _label in DOCUMENT_TYPES}


SQLITE_SCHEMA = """
create table if not exists advisors (
  id text primary key,
  rank integer not null,
  name text not null,
  institution text,
  institution_zh text,
  city text,
  state text,
  pool text,
  category text,
  stage_key text,
  stage_label text,
  school_tier text,
  school_tier_label text,
  evidence_reliability text,
  recruiting_status text,
  student_background_status text,
  raw_json text not null
);

create table if not exists advisor_reviews (
  advisor_id text not null,
  reviewer text not null,
  decision text default '',
  interest text default '',
  score integer,
  review_status text default '',
  note text default '',
  updated_at text not null,
  primary key (advisor_id, reviewer),
  foreign key (advisor_id) references advisors(id) on delete cascade
);

create table if not exists advisor_contacts (
  id integer primary key autoincrement,
  advisor_id text not null,
  contact_type text not null default '导师邮箱',
  contact_value text not null,
  source_url text default '',
  evidence_text text default '',
  confidence text default '待确认',
  is_primary integer default 0,
  created_by text default '',
  updated_by text default '',
  created_at text not null,
  updated_at text not null,
  unique (advisor_id, contact_value),
  foreign key (advisor_id) references advisors(id) on delete cascade
);

create index if not exists idx_advisor_contacts_advisor on advisor_contacts(advisor_id, is_primary);
create index if not exists idx_advisor_contacts_value on advisor_contacts(contact_value);

create table if not exists documents (
  id integer primary key autoincrement,
  doc_type text not null,
  title text not null,
  version_label text not null,
  status text default 'draft',
  owner text default '',
  uploaded_by text default '',
  original_filename text default '',
  stored_filename text default '',
  file_path text default '',
  file_size integer default 0,
  mime_type text default '',
  created_at text default '',
  updated_at text not null,
  notes text default ''
);

create table if not exists outreach_targets (
  advisor_id text primary key,
  is_active integer default 1,
  status text default '待联系',
  response_status text default '待回复',
  stage text default '跟进中',
  priority text default '',
  tags text default '',
  last_contact_at text default '',
  next_action_at text default '',
  next_action text default '',
  notes text default '',
  created_by text default '',
  updated_by text default '',
  created_at text not null,
  updated_at text not null,
  foreign key (advisor_id) references advisors(id) on delete cascade
);

create table if not exists outreach_events (
  id integer primary key autoincrement,
  advisor_id text not null,
  event_type text not null,
  event_at text not null,
  summary text default '',
  detail text default '',
  created_by text default '',
  created_at text not null,
  foreign key (advisor_id) references advisors(id) on delete cascade
);

create table if not exists application_programs (
  id integer primary key autoincrement,
  school text not null,
  department text default '',
  program_name text not null,
  degree text default 'PhD',
  deadline text default '',
  status text default '候选',
  priority text default '',
  requirements text default '',
  notes text default '',
  created_by text default '',
  updated_by text default '',
  created_at text not null,
  updated_at text not null
);

create table if not exists ai_settings (
  id integer primary key check (id = 1),
  enabled integer default 0,
  provider_name text default '',
  endpoint_url text default '',
  model_name text default '',
  api_key text default '',
  temperature real default 0.2,
  tools_enabled integer default 0,
  allow_search_pages integer default 0,
  tool_max_results integer default 5,
  tool_timeout_seconds integer default 8,
  tool_cache_ttl_seconds integer default 86400,
  updated_by text default '',
  updated_at text default ''
);

create table if not exists ai_conversations (
  id integer primary key autoincrement,
  advisor_id text not null,
  title text not null,
  system_context text not null,
  created_by text default '',
  created_at text not null,
  updated_at text not null,
  foreign key (advisor_id) references advisors(id) on delete cascade
);

create table if not exists ai_messages (
  id integer primary key autoincrement,
  conversation_id integer not null,
  role text not null,
  content text not null,
  created_by text default '',
  created_at text not null,
  foreign key (conversation_id) references ai_conversations(id) on delete cascade
);
"""


MYSQL_SCHEMA = [
    """
    create table if not exists advisors (
      id varchar(160) primary key,
      `rank` int not null,
      name varchar(255) not null,
      institution varchar(255) default '',
      institution_zh varchar(255) default '',
      city varchar(120) default '',
      state varchar(80) default '',
      pool varchar(120) default '',
      category varchar(160) default '',
      stage_key varchar(80) default '',
      stage_label varchar(160) default '',
      school_tier varchar(80) default '',
      school_tier_label varchar(160) default '',
      evidence_reliability varchar(40) default '',
      recruiting_status varchar(160) default '',
      student_background_status varchar(160) default '',
      raw_json longtext not null,
      index idx_advisors_rank (`rank`),
      index idx_advisors_stage (stage_key),
      index idx_advisors_tier (school_tier),
      index idx_advisors_category (category),
      index idx_advisors_pool (pool)
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists advisor_reviews (
      advisor_id varchar(160) not null,
      reviewer varchar(120) not null,
      decision varchar(40) default '',
      interest varchar(120) default '',
      score int null,
      review_status varchar(120) default '',
      note text null,
      updated_at varchar(40) not null,
      primary key (advisor_id, reviewer),
      constraint fk_advisor_reviews_advisor foreign key (advisor_id) references advisors(id) on delete cascade
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists advisor_contacts (
      id bigint primary key auto_increment,
      advisor_id varchar(160) not null,
      contact_type varchar(40) not null default '导师邮箱',
      contact_value varchar(500) not null,
      source_url varchar(800) default '',
      evidence_text text null,
      confidence varchar(20) default '待确认',
      is_primary tinyint default 0,
      primary_advisor_id varchar(160) default null,
      created_by varchar(120) default '',
      updated_by varchar(120) default '',
      created_at varchar(40) not null,
      updated_at varchar(40) not null,
      unique key uniq_advisor_contact_value (advisor_id, contact_value),
      unique key uniq_advisor_contacts_primary (primary_advisor_id),
      index idx_advisor_contacts_advisor (advisor_id, is_primary),
      index idx_advisor_contacts_value (contact_value),
      constraint fk_advisor_contacts_advisor foreign key (advisor_id) references advisors(id) on delete cascade
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists documents (
      id bigint primary key auto_increment,
      doc_type varchar(120) not null,
      title varchar(255) not null,
      version_label varchar(40) not null,
      status varchar(80) default 'draft',
      owner varchar(120) default '',
      uploaded_by varchar(120) default '',
      original_filename varchar(255) default '',
      stored_filename varchar(255) default '',
      file_path varchar(500) default '',
      file_size bigint default 0,
      mime_type varchar(160) default '',
      created_at varchar(40) default '',
      updated_at varchar(40) not null,
      notes text null,
      index idx_documents_type (doc_type),
      index idx_documents_created (created_at)
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists outreach_targets (
      advisor_id varchar(160) primary key,
      is_active tinyint default 1,
      status varchar(40) default '待联系',
      response_status varchar(40) default '待回复',
      stage varchar(40) default '跟进中',
      priority varchar(10) default '',
      tags varchar(500) default '',
      last_contact_at varchar(40) default '',
      next_action_at varchar(40) default '',
      next_action text null,
      notes text null,
      created_by varchar(120) default '',
      updated_by varchar(120) default '',
      created_at varchar(40) not null,
      updated_at varchar(40) not null,
      index idx_outreach_active_status (is_active, status),
      constraint fk_outreach_targets_advisor foreign key (advisor_id) references advisors(id) on delete cascade
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists outreach_events (
      id bigint primary key auto_increment,
      advisor_id varchar(160) not null,
      event_type varchar(40) not null,
      event_at varchar(40) not null,
      summary varchar(500) default '',
      detail text null,
      created_by varchar(120) default '',
      created_at varchar(40) not null,
      index idx_outreach_events_advisor (advisor_id, event_at),
      constraint fk_outreach_events_advisor foreign key (advisor_id) references advisors(id) on delete cascade
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists application_programs (
      id bigint primary key auto_increment,
      school varchar(255) not null,
      department varchar(255) default '',
      program_name varchar(255) not null,
      degree varchar(40) default 'PhD',
      deadline varchar(40) default '',
      status varchar(40) default '候选',
      priority varchar(10) default '',
      requirements text null,
      notes text null,
      created_by varchar(120) default '',
      updated_by varchar(120) default '',
      created_at varchar(40) not null,
      updated_at varchar(40) not null,
      index idx_programs_status_deadline (status, deadline),
      index idx_programs_priority (priority)
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists ai_settings (
      id int primary key,
      enabled tinyint default 0,
      provider_name varchar(120) default '',
      endpoint_url varchar(500) default '',
      model_name varchar(160) default '',
      api_key text null,
      temperature double default 0.2,
      tools_enabled tinyint default 0,
      allow_search_pages tinyint default 0,
      tool_max_results int default 5,
      tool_timeout_seconds int default 8,
      tool_cache_ttl_seconds int default 86400,
      updated_by varchar(120) default '',
      updated_at varchar(40) default ''
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists ai_conversations (
      id bigint primary key auto_increment,
      advisor_id varchar(160) not null,
      title varchar(255) not null,
      system_context longtext not null,
      created_by varchar(120) default '',
      created_at varchar(40) not null,
      updated_at varchar(40) not null,
      index idx_ai_conversations_advisor (advisor_id, updated_at),
      constraint fk_ai_conversations_advisor foreign key (advisor_id) references advisors(id) on delete cascade
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
    """
    create table if not exists ai_messages (
      id bigint primary key auto_increment,
      conversation_id bigint not null,
      role varchar(40) not null,
      content longtext not null,
      created_by varchar(120) default '',
      created_at varchar(40) not null,
      index idx_ai_messages_conversation (conversation_id, id),
      constraint fk_ai_messages_conversation foreign key (conversation_id) references ai_conversations(id) on delete cascade
    ) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci
    """,
]

MYSQL_DOCUMENT_COLUMN_ADDITIONS = {
    "original_filename": "varchar(255) default ''",
    "stored_filename": "varchar(255) default ''",
    "file_path": "varchar(500) default ''",
    "file_size": "bigint default 0",
    "mime_type": "varchar(160) default ''",
    "uploaded_by": "varchar(120) default ''",
    "created_at": "varchar(40) default ''",
}

SQLITE_DOCUMENT_COLUMN_ADDITIONS = {
    "original_filename": "text default ''",
    "stored_filename": "text default ''",
    "file_path": "text default ''",
    "file_size": "integer default 0",
    "mime_type": "text default ''",
    "uploaded_by": "text default ''",
    "created_at": "text default ''",
}

MYSQL_AI_MESSAGE_COLUMN_ADDITIONS = {
    "created_by": "varchar(120) default ''",
}

SQLITE_AI_MESSAGE_COLUMN_ADDITIONS = {
    "created_by": "text default ''",
}

MYSQL_AI_SETTINGS_COLUMN_ADDITIONS = {
    "tools_enabled": "tinyint default 0",
    "allow_search_pages": "tinyint default 0",
    "tool_max_results": "int default 5",
    "tool_timeout_seconds": "int default 8",
    "tool_cache_ttl_seconds": "int default 86400",
}

SQLITE_AI_SETTINGS_COLUMN_ADDITIONS = {
    "tools_enabled": "integer default 0",
    "allow_search_pages": "integer default 0",
    "tool_max_results": "integer default 5",
    "tool_timeout_seconds": "integer default 8",
    "tool_cache_ttl_seconds": "integer default 86400",
}


def utc_now() -> str:
    global LAST_UTC_NOW
    with UTC_NOW_LOCK:
        now = datetime.now(timezone.utc)
        if LAST_UTC_NOW is not None and now <= LAST_UTC_NOW:
            now = LAST_UTC_NOW + timedelta(microseconds=1)
        LAST_UTC_NOW = now
        return now.isoformat(timespec="microseconds")


class DbRow:
    def __init__(self, columns: list[str], values) -> None:
        self._columns = columns
        self._values = tuple(values)
        self._data: dict[str, object] = {}
        for index, column in enumerate(columns):
            if column not in self._data:
                self._data[column] = self._values[index]

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._data[key]

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def __iter__(self):
        return iter(self._data)


class DbCursor:
    def __init__(self, cursor) -> None:
        self._cursor = cursor
        self._columns = [description[0] for description in (cursor.description or [])]

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return DbRow(self._columns, row)

    def fetchall(self) -> list[DbRow]:
        return [DbRow(self._columns, row) for row in self._cursor.fetchall()]


class DbConnection:
    def __init__(self, raw_conn, backend: str) -> None:
        self.raw_conn = raw_conn
        self.backend = backend

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc, _traceback) -> None:
        if exc_type:
            self.raw_conn.rollback()
        else:
            self.raw_conn.commit()
        self.raw_conn.close()

    def _sql(self, sql: str) -> str:
        if self.backend == "mysql":
            return qmark_to_pyformat(sql)
        return sql

    def execute(self, sql: str, params=()) -> DbCursor:
        cursor = self.raw_conn.cursor()
        cursor.execute(self._sql(sql), params or ())
        return DbCursor(cursor)

    def executemany(self, sql: str, params_list) -> DbCursor:
        cursor = self.raw_conn.cursor()
        cursor.executemany(self._sql(sql), params_list)
        return DbCursor(cursor)

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.raw_conn.executescript(script)
            return
        for statement in sql_script_statements(script):
            self.execute(statement)


def sql_script_statements(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def qmark_to_pyformat(sql: str) -> str:
    result: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if quote:
            result.append(char)
            if char == quote:
                if quote in {"'", '"'} and next_char == quote:
                    result.append(next_char)
                    index += 2
                    continue
                quote = None
            elif char == "\\" and quote in {"'", '"'} and next_char:
                result.append(next_char)
                index += 2
                continue
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            result.append(char)
            index += 1
            continue
        if char == "-" and next_char == "-":
            end = sql.find("\n", index + 2)
            if end == -1:
                result.append(sql[index:])
                break
            result.append(sql[index:end])
            index = end
            continue
        if char == "/" and next_char == "*":
            end = sql.find("*/", index + 2)
            if end == -1:
                result.append(sql[index:])
                break
            result.append(sql[index : end + 2])
            index = end + 2
            continue
        if char == "?":
            result.append("%s")
        else:
            result.append(char)
        index += 1
    return "".join(result)


def current_db_backend() -> str:
    backend = os.environ.get(DB_BACKEND_ENV, "mysql").strip().lower() or "mysql"
    if backend not in SUPPORTED_DB_BACKENDS:
        raise RuntimeError(f"{DB_BACKEND_ENV} 只支持 sqlite 或 mysql，当前是 {backend!r}")
    return backend


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def platform_environment() -> str:
    return os.environ.get(PLATFORM_ENV_ENV, "").strip().lower()


def platform_bind_host() -> str:
    return os.environ.get(PLATFORM_BIND_HOST_ENV, "127.0.0.1").strip() or "127.0.0.1"


def production_mode() -> bool:
    return platform_environment() in {"prod", "production"} or env_flag(AI_KEY_ENV_ONLY_ENV)


def database_ai_key_allowed() -> bool:
    if os.environ.get(AI_API_KEY_ENV, "").strip():
        return False
    if production_mode():
        return False
    return platform_bind_host() in LOCAL_HOSTS


def mysql_schema_sql() -> str:
    return ";\n\n".join(statement.strip() for statement in MYSQL_SCHEMA) + ";\n"


def sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_case_order(column: str, ordered_values: list[str], default_rank: int = 999) -> str:
    parts = [f"case {column}"]
    for index, value in enumerate(ordered_values):
        parts.append(f"when {sql_string_literal(value)} then {index}")
    parts.append(f"else {default_rank} end")
    return " ".join(parts)


def advisor_default_order_sql() -> str:
    category_order = sql_case_order("a.category", ADVISOR_CATEGORY_SORT)
    stage_order = sql_case_order("a.stage_key", ADVISOR_STAGE_SORT)
    return f"{category_order}, {stage_order}, a.`rank`"


def advisor_category_order_sql(column: str) -> str:
    return sql_case_order(column, ADVISOR_CATEGORY_SORT)


def configured_ai_api_key(settings) -> str:
    env_key = os.environ.get(AI_API_KEY_ENV, "").strip()
    if env_key:
        return env_key
    if database_ai_key_allowed():
        return str(settings["api_key"] or "").strip()
    return ""


def mysql_connection_kwargs() -> dict:
    host = os.environ.get("PHD_PLATFORM_MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("PHD_PLATFORM_MYSQL_PORT", "3306") or "3306")
    database = os.environ.get("PHD_PLATFORM_MYSQL_DATABASE", "phd_workspace").strip() or "phd_workspace"
    user = os.environ.get("PHD_PLATFORM_MYSQL_USER", "phd_app").strip() or "phd_app"
    password = os.environ.get("PHD_PLATFORM_MYSQL_PASSWORD", "")
    if not user or not password:
        raise RuntimeError("MySQL 模式必须设置 PHD_PLATFORM_MYSQL_PASSWORD；如需临时使用 SQLite，请显式设置 PHD_PLATFORM_DB_BACKEND=sqlite")
    return {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
        "charset": "utf8mb4",
        "autocommit": False,
    }


def connect(backend: str | None = None) -> DbConnection:
    selected_backend = backend or current_db_backend()
    if selected_backend == "sqlite":
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("pragma foreign_keys = on")
        return DbConnection(conn, "sqlite")
    try:
        import pymysql
    except ImportError as error:
        raise RuntimeError("PHD_PLATFORM_DB_BACKEND=mysql 需要安装 PyMySQL：python3 -m pip install PyMySQL") from error
    return DbConnection(pymysql.connect(**mysql_connection_kwargs()), "mysql")


def safe_filename(value: str) -> str:
    name = Path(value or "document").name.strip()
    name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", name)
    name = name.strip("._") or "document"
    return name[:160]


def table_columns(conn: DbConnection, table: str) -> set[str]:
    if conn.backend == "mysql":
        rows = conn.execute(
            """
            select column_name as name
            from information_schema.columns
            where table_schema = database() and table_name = ?
            """,
            (table,),
        ).fetchall()
        return {row["name"] for row in rows}
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return {row["name"] for row in rows}


def table_indexes(conn: DbConnection, table: str) -> set[str]:
    if conn.backend == "mysql":
        rows = conn.execute(f"show index from `{table}`").fetchall()
        return {str(row["Key_name"]) for row in rows}
    rows = conn.execute(f"pragma index_list({table})").fetchall()
    return {str(row["name"]) for row in rows}


def ensure_document_schema(conn: DbConnection) -> None:
    columns = table_columns(conn, "documents")
    additions = MYSQL_DOCUMENT_COLUMN_ADDITIONS if conn.backend == "mysql" else SQLITE_DOCUMENT_COLUMN_ADDITIONS
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"alter table documents add column {name} {ddl}")
    missing_created_at = conn.execute(
        "select id from documents where coalesce(created_at, '') = '' limit 1"
    ).fetchone()
    if missing_created_at:
        conn.execute("update documents set created_at = updated_at where coalesce(created_at, '') = ''")


def ensure_ai_message_schema(conn: DbConnection) -> None:
    columns = table_columns(conn, "ai_messages")
    additions = MYSQL_AI_MESSAGE_COLUMN_ADDITIONS if conn.backend == "mysql" else SQLITE_AI_MESSAGE_COLUMN_ADDITIONS
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"alter table ai_messages add column {name} {ddl}")
    missing_created_by = conn.execute(
        "select id from ai_messages where role = 'assistant' and coalesce(created_by, '') = '' limit 1"
    ).fetchone()
    if missing_created_by:
        conn.execute("update ai_messages set created_by = 'AI' where role = 'assistant' and coalesce(created_by, '') = ''")


def ensure_ai_settings_schema(conn: DbConnection) -> None:
    columns = table_columns(conn, "ai_settings")
    additions = MYSQL_AI_SETTINGS_COLUMN_ADDITIONS if conn.backend == "mysql" else SQLITE_AI_SETTINGS_COLUMN_ADDITIONS
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"alter table ai_settings add column {name} {ddl}")


def ensure_advisor_contact_schema(conn: DbConnection) -> None:
    duplicate_primary = conn.execute(
        """
        select advisor_id
        from advisor_contacts
        where is_primary = 1
        group by advisor_id
        having count(*) > 1
        limit 1
        """
    ).fetchone()
    if duplicate_primary:
        conn.execute(
            """
            update advisor_contacts
            set is_primary = 0
            where is_primary = 1
              and id not in (
                select id
                from (
                  select min(id) as id
                  from advisor_contacts
                  where is_primary = 1
                  group by advisor_id
                ) primary_contacts
              )
            """
        )
    if conn.backend == "mysql":
        columns = table_columns(conn, "advisor_contacts")
        if "primary_advisor_id" not in columns:
            conn.execute(
                "alter table advisor_contacts add column primary_advisor_id varchar(160) default null"
            )
        sync_advisor_contact_primary(conn)
        if "uniq_advisor_contacts_primary" not in table_indexes(conn, "advisor_contacts"):
            conn.execute("alter table advisor_contacts add unique key uniq_advisor_contacts_primary (primary_advisor_id)")
        return
    if "uniq_advisor_contacts_primary" not in table_indexes(conn, "advisor_contacts"):
        conn.execute(
            """
            create unique index if not exists uniq_advisor_contacts_primary
            on advisor_contacts(advisor_id)
            where is_primary = 1
            """
        )


def sync_advisor_contact_primary(conn: DbConnection, advisor_id: str | None = None) -> None:
    if conn.backend != "mysql":
        return
    if advisor_id:
        needs_sync = conn.execute(
            """
            select id
            from advisor_contacts
            where advisor_id = ?
              and (
                (is_primary = 1 and coalesce(primary_advisor_id, '') <> advisor_id)
                or (is_primary = 0 and primary_advisor_id is not null)
              )
            limit 1
            """,
            (advisor_id,),
        ).fetchone()
        if not needs_sync:
            return
        conn.execute("update advisor_contacts set primary_advisor_id = null where advisor_id = ?", (advisor_id,))
        conn.execute("update advisor_contacts set primary_advisor_id = advisor_id where advisor_id = ? and is_primary = 1", (advisor_id,))
        return
    needs_sync = conn.execute(
        """
        select id
        from advisor_contacts
        where (is_primary = 1 and coalesce(primary_advisor_id, '') <> advisor_id)
           or (is_primary = 0 and primary_advisor_id is not null)
        limit 1
        """
    ).fetchone()
    if not needs_sync:
        return
    conn.execute("update advisor_contacts set primary_advisor_id = null")
    conn.execute("update advisor_contacts set primary_advisor_id = advisor_id where is_primary = 1")


def ensure_base_schema(conn: DbConnection) -> None:
    if conn.backend == "mysql":
        for statement in MYSQL_SCHEMA:
            conn.execute(statement)
        ensure_ai_settings_schema(conn)
        ensure_advisor_contact_schema(conn)
        ensure_ai_message_schema(conn)
        return
    conn.executescript(SQLITE_SCHEMA)
    ensure_ai_settings_schema(conn)
    ensure_advisor_contact_schema(conn)
    ensure_ai_message_schema(conn)


def ensure_ai_settings_row(conn: DbConnection) -> None:
    row = conn.execute("select 1 from ai_settings where id = ?", (1,)).fetchone()
    if not row:
        conn.execute("insert into ai_settings (id, enabled, temperature) values (?, ?, ?)", (1, 0, 0.2))


def upsert_advisor_review(conn: DbConnection, values: tuple) -> None:
    if conn.backend == "mysql":
        conn.execute(
            """
            insert into advisor_reviews (
              advisor_id, reviewer, interest, review_status, note, updated_at
            ) values (?, ?, ?, ?, ?, ?)
            on duplicate key update
              interest = values(interest),
              review_status = values(review_status),
              note = values(note),
              updated_at = values(updated_at)
            """,
            values,
        )
        return
    conn.execute(
        """
        insert into advisor_reviews (
          advisor_id, reviewer, interest, review_status, note, updated_at
        ) values (?, ?, ?, ?, ?, ?)
        on conflict(advisor_id, reviewer) do update set
          interest = excluded.interest,
          review_status = excluded.review_status,
          note = excluded.note,
          updated_at = excluded.updated_at
        """,
        values,
    )


def parse_cookies(header: str | None) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if not header:
        return cookies
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def configured_accounts(host: str) -> dict[str, str]:
    accounts_json = os.environ.get("PHD_PLATFORM_ACCOUNTS", "").strip()
    if accounts_json:
        accounts = json.loads(accounts_json)
        if not isinstance(accounts, dict) or not accounts or not all(
            isinstance(k, str) and k.strip()
            and isinstance(v, str) and v.strip()
            and not v.startswith("REPLACE_WITH_")
            for k, v in accounts.items()
        ):
            raise RuntimeError("PHD_PLATFORM_ACCOUNTS 必须是 JSON 对象，例如 {\"Applicant\":\"password\"}")
        return accounts
    raise RuntimeError("启动前必须在私有配置中设置 PHD_PLATFORM_ACCOUNTS；没有默认账号密码")


def configured_seed_html() -> Path:
    configured = os.environ.get(SEED_HTML_ENV, "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    if PLATFORM_SEED_HTML.exists():
        return PLATFORM_SEED_HTML
    return LEGACY_SEED_HTML


def extract_seed_records() -> list[dict]:
    seed_html = configured_seed_html()
    if not seed_html.exists():
        raise RuntimeError(
            f"seed html does not exist: {seed_html}. Set {SEED_HTML_ENV} or place {SEED_HTML_FILENAME} under {ROOT / 'seed'}."
        )
    html = seed_html.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="candidate-data" type="application/json">([\s\S]*?)</script>',
        html,
    )
    if not match:
        raise RuntimeError(f"cannot find candidate-data in {seed_html}")
    return json.loads(match.group(1))


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        ensure_base_schema(conn)
        ensure_ai_settings_row(conn)
        ensure_document_schema(conn)
        count = conn.execute("select count(*) from advisors").fetchone()[0]
        if count:
            return

        records = extract_seed_records()
        conn.executemany(
            """
            insert into advisors (
              id, `rank`, name, institution, institution_zh, city, state, pool,
              category, stage_key, stage_label, school_tier, school_tier_label,
              evidence_reliability, recruiting_status, student_background_status,
              raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row.get("num") or row.get("rank") or 0,
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
                for row in records
            ],
        )
        conn.executemany(
            """
            insert into documents (doc_type, title, version_label, status, owner, updated_at, notes)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Research Statement", "Research Statement 主线草稿", "v0", "待起草", "Applicant", utc_now(), "后续用于管理多轮文书版本。"),
                ("SOP", "Statement of Purpose 素材整合", "v0", "待整理", "Applicant", utc_now(), "先从现有素材库导入。"),
                ("CV", "PhD-oriented CV", "v0", "待改写", "Applicant", utc_now(), "基于源 CV 创建申请版。"),
            ],
        )


def json_response(handler: BaseHTTPRequestHandler, payload, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def not_found(handler: BaseHTTPRequestHandler) -> None:
    json_response(handler, {"error": "not_found"}, HTTPStatus.NOT_FOUND)


def unauthorized(handler: BaseHTTPRequestHandler) -> None:
    json_response(handler, {"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)


def static_target(name: str) -> tuple[Path | None, str]:
    safe_name = name.strip("/") or "index.html"
    target = (STATIC_DIR / safe_name).resolve()
    if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists() or target.is_dir():
        return None, ""
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
    }
    return target, content_types.get(target.suffix, "text/plain; charset=utf-8")


def normalize_interest_value(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in INTEREST_VALUES:
        return text
    if text in LEGACY_INTEREST_ALIASES:
        return LEGACY_INTEREST_ALIASES[text]
    return None


def normalize_query_status_value(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in QUERY_STATUS_VALUES:
        return text
    if text in LEGACY_QUERY_STATUS_ALIASES:
        return LEGACY_QUERY_STATUS_ALIASES[text]
    return None


def expand_advisor_filter_values(key: str, values: list[str]) -> list[str]:
    aliases_by_key = {
        "interest": {
            "高兴趣": ["高兴趣", "很有兴趣", "高"],
            "有兴趣": ["有兴趣", "一般", "中"],
            "待判断": ["", "待判断"],
            "不感兴趣": ["不感兴趣", "低", "不保留", "排除"],
        },
        "queryStatus": {
            "待请求": ["", "待请求"],
            "请求查询": ["请求查询", "需查询"],
            "已查询": ["已查询"],
        },
    }
    normalizer = normalize_interest_value if key == "interest" else normalize_query_status_value if key == "queryStatus" else None
    if not normalizer:
        return values
    aliases = aliases_by_key[key]
    expanded: list[str] = []
    for value in values:
        normalized = normalizer(value)
        if not normalized:
            continue
        for candidate in aliases.get(normalized, [normalized]):
            if candidate not in expanded:
                expanded.append(candidate)
    return expanded


def review_filter_option_counts(conn: DbConnection) -> dict[str, list[dict]]:
    rows = conn.execute(
        """
        select r.interest, r.review_status
        from advisors a
        """
        + latest_review_join_sql()
    ).fetchall()
    interest_order = ["待判断", "高兴趣", "有兴趣", "不感兴趣"]
    query_order = ["待请求", "请求查询", "已查询"]
    interest_counts = {value: 0 for value in sorted(INTEREST_VALUES, key=lambda item: interest_order.index(item))}
    query_counts = {value: 0 for value in sorted(QUERY_STATUS_VALUES, key=lambda item: query_order.index(item))}
    for row in rows:
        interest = normalize_interest_value(row["interest"] or "") or "待判断"
        query_status = normalize_query_status_value(row["review_status"] or "") or "待请求"
        if interest in interest_counts:
            interest_counts[interest] += 1
        if query_status in query_counts:
            query_counts[query_status] += 1
    return {
        "interests": [{"value": value, "label": value, "count": count} for value, count in interest_counts.items()],
        "queryStatuses": [{"value": value, "label": value, "count": count} for value, count in query_counts.items()],
    }


def advisor_filters(query: dict[str, list[str]], params: list) -> str:
    clauses = []
    search = (query.get("search", [""])[0] or "").strip()
    if search:
        like = f"%{search.lower()}%"
        clauses.append(
            "(lower(a.name) like ? or lower(a.institution) like ? or lower(a.institution_zh) like ? "
            "or lower(a.category) like ? or lower(a.pool) like ?)"
        )
        params.extend([like, like, like, like, like])
    for key, column in [
        ("stage", "a.stage_key"),
        ("tier", "a.school_tier"),
        ("pool", "a.pool"),
        ("category", "a.category"),
        ("state", "a.state"),
        ("recruiting", "a.recruiting_status"),
        ("student", "a.student_background_status"),
        ("interest", "coalesce(r.interest, '')"),
        ("queryStatus", "coalesce(r.review_status, '')"),
    ]:
        raw_values = query.get(key, [])
        if key == "queryStatus":
            raw_values = raw_values + query.get("review_status", [])
        values = [value.strip() for value in raw_values if value.strip()]
        values = expand_advisor_filter_values(key, values)
        if values:
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{column} in ({placeholders})")
            params.extend(values)
    outreach_values = [value.strip() for value in query.get("outreach", []) if value.strip()]
    if outreach_values:
        outreach_clauses = []
        if "已加入" in outreach_values:
            outreach_clauses.append("coalesce(o.is_active, 0) = 1")
        if "未加入" in outreach_values:
            outreach_clauses.append("coalesce(o.is_active, 0) = 0")
        if outreach_clauses:
            clauses.append("(" + " or ".join(outreach_clauses) + ")")
    return " where " + " and ".join(clauses) if clauses else ""


def latest_review_join_sql() -> str:
    return """
                left join advisor_reviews r
                  on r.advisor_id = a.id
                 and not exists (
                   select 1
                   from advisor_reviews r2
                   where r2.advisor_id = r.advisor_id
                     and (
                       coalesce(r2.updated_at, '') > coalesce(r.updated_at, '')
                       or (
                         coalesce(r2.updated_at, '') = coalesce(r.updated_at, '')
                         and r2.reviewer > r.reviewer
                       )
                     )
                 )
    """


def latest_advisor_review(conn: DbConnection, advisor_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        select interest, review_status, note
        from advisor_reviews
        where advisor_id = ?
        order by coalesce(updated_at, '') desc, reviewer desc
        limit 1
        """,
        (advisor_id,),
    ).fetchone()


def advisor_review_lock(advisor_id: str) -> threading.RLock:
    with ADVISOR_REVIEW_LOCKS_GUARD:
        lock = ADVISOR_REVIEW_LOCKS.get(advisor_id)
        if lock is None:
            lock = threading.RLock()
            ADVISOR_REVIEW_LOCKS[advisor_id] = lock
        return lock


def contact_row_to_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "advisorId": row["advisor_id"],
        "contactType": row["contact_type"] or "导师邮箱",
        "value": row["contact_value"] or "",
        "sourceUrl": row["source_url"] or "",
        "evidenceText": row["evidence_text"] or "",
        "confidence": row["confidence"] or "待确认",
        "isPrimary": bool(row["is_primary"]),
        "createdBy": row["created_by"] or "",
        "updatedBy": row["updated_by"] or "",
        "createdAt": row["created_at"] or "",
        "updatedAt": row["updated_at"] or "",
    }


def is_email_contact(value: str) -> bool:
    return bool(re.search(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))


def normalize_contact_value(contact_type: str, value: str) -> str:
    normalized = clean_text(value, 500)
    if is_email_contact(normalized) or contact_type in {"导师邮箱", "Lab 邮箱", "项目邮箱"}:
        return normalized.lower()
    return normalized


def is_integrity_error(error: Exception) -> bool:
    return isinstance(error, sqlite3.IntegrityError) or error.__class__.__name__ == "IntegrityError"


def contact_summary(contacts: list[dict]) -> dict:
    primary = next((contact for contact in contacts if contact.get("isPrimary")), None)
    email = next((contact for contact in contacts if is_email_contact(contact.get("value", ""))), None)
    selected = primary or email or (contacts[0] if contacts else None)
    return {
        "contactCount": len(contacts),
        "hasEmail": any(is_email_contact(contact.get("value", "")) for contact in contacts),
        "primaryContact": selected.get("value", "") if selected else "",
        "primaryContactType": selected.get("contactType", "") if selected else "",
    }


def advisor_contacts(conn: DbConnection, advisor_id: str) -> list[dict]:
    rows = conn.execute(
        """
        select *
        from advisor_contacts
        where advisor_id = ?
        order by is_primary desc, contact_type, id
        """,
        (advisor_id,),
    ).fetchall()
    return [contact_row_to_payload(row) for row in rows]


def advisor_contacts_map(conn: DbConnection, advisor_ids: list[str]) -> dict[str, list[dict]]:
    ids = [advisor_id for advisor_id in advisor_ids if advisor_id]
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        select *
        from advisor_contacts
        where advisor_id in ({placeholders})
        order by advisor_id, is_primary desc, contact_type, id
        """,
        ids,
    ).fetchall()
    result: dict[str, list[dict]] = {}
    for row in rows:
        result.setdefault(row["advisor_id"], []).append(contact_row_to_payload(row))
    return result


def attach_contacts(payload: dict, contacts: list[dict]) -> dict:
    payload["contacts"] = contacts
    payload.update(contact_summary(contacts))
    return payload


def row_to_advisor_list_item(row: sqlite3.Row, contacts: list[dict] | None = None) -> dict:
    contact_meta = contact_summary(contacts or [])
    outreach_active = bool(row["outreach_active"])
    return {
        "id": row["id"],
        "num": row["rank"],
        "rank": row["rank"],
        "name": row["name"] or "",
        "institution": row["institution"] or "",
        "institutionZh": row["institution_zh"] or "",
        "firstInstitution": row["institution"] or "",
        "firstInstitutionZh": row["institution_zh"] or "",
        "city": row["city"] or "",
        "state": row["state"] or "",
        "primaryCategory": row["category"] or "",
        "schoolTier": row["school_tier"] or "",
        "schoolTierLabel": row["school_tier_label"] or "",
        "stageKey": row["stage_key"] or "",
        "stageLabel": row["stage_label"] or "",
        "reviewer": row["reviewer"] or "",
        "interest": row["interest"] or "",
        "queryStatus": row["review_status"] or "",
        "reviewStatus": row["review_status"] or "",
        "note": row["note"] or "",
        "updatedAt": row["updated_at"] or "",
        "outreachActive": outreach_active,
        "outreachStatus": row["outreach_status"] or "",
        "outreachResponseStatus": row["outreach_response_status"] or "",
        "outreachStage": row["outreach_stage"] or "",
        "outreachNextAction": row["outreach_next_action"] or "",
        **contact_meta,
    }


def row_to_advisor(row: sqlite3.Row, contacts: list[dict] | None = None) -> dict:
    raw = json.loads(row["raw_json"])
    keys = set(row.keys())
    outreach_active = bool(row["outreach_active"]) if "outreach_active" in keys else False
    raw.pop("score", None)
    raw.update(
        {
            "reviewer": row["reviewer"] or "",
            "interest": row["interest"] or "",
            "queryStatus": row["review_status"] or "",
            "reviewStatus": row["review_status"] or "",
            "note": row["note"] or "",
            "updatedAt": row["updated_at"] or "",
            "stageKey": row["stage_key"] if "stage_key" in keys and row["stage_key"] else raw.get("stageKey", ""),
            "stageLabel": row["stage_label"] if "stage_label" in keys and row["stage_label"] else raw.get("stageLabel", ""),
            "outreachActive": outreach_active,
            "outreachStatus": row["outreach_status"] if "outreach_status" in keys and row["outreach_status"] else "",
            "outreachResponseStatus": row["outreach_response_status"] if "outreach_response_status" in keys and row["outreach_response_status"] else "",
            "outreachStage": row["outreach_stage"] if "outreach_stage" in keys and row["outreach_stage"] else "",
            "outreachNextAction": row["outreach_next_action"] if "outreach_next_action" in keys and row["outreach_next_action"] else "",
        }
    )
    return attach_contacts(raw, contacts or [])


def normalize_date_text(value: str) -> str:
    return str(value or "").strip()[:40]


def clean_text(value: str, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def outreach_row_to_payload(
    row: sqlite3.Row,
    events: list[sqlite3.Row] | None = None,
    contacts: list[dict] | None = None,
) -> dict:
    raw = json.loads(row["raw_json"])
    contact_rows = contacts or []
    contact_meta = contact_summary(contact_rows)
    payload = {
        "advisorId": row["advisor_id"],
        "active": bool(row["is_active"]),
        "status": row["status"] or "待联系",
        "responseStatus": row["response_status"] or "待回复",
        "stage": row["stage"] or "跟进中",
        "priority": row["priority"] or "",
        "tags": row["tags"] or "",
        "lastContactAt": row["last_contact_at"] or "",
        "nextActionAt": row["next_action_at"] or "",
        "nextAction": row["next_action"] or "",
        "notes": row["notes"] or "",
        "createdBy": row["created_by"] or "",
        "updatedBy": row["updated_by"] or "",
        "createdAt": row["created_at"] or "",
        "updatedAt": row["updated_at"] or "",
        "advisor": {
            "id": raw.get("id") or row["advisor_id"],
            "num": raw.get("num") or raw.get("rank") or "",
            "name": raw.get("name", ""),
            "institution": raw.get("firstInstitution") or raw.get("institution", ""),
            "institutionZh": raw.get("firstInstitutionZh") or raw.get("institutionZh", ""),
            "city": raw.get("city", ""),
            "state": raw.get("state", ""),
            "stageLabel": raw.get("stageLabel", ""),
            "schoolTierLabel": raw.get("schoolTierLabel", ""),
            "locationLabelEn": raw.get("locationLabelEn", ""),
            "locationLabelZh": raw.get("locationLabelZh", ""),
            "primaryCategory": raw.get("primaryCategory", ""),
            "matchedKeywords": raw.get("matchedKeywords", ""),
            "advisorHighlights": raw.get("advisorHighlights") or raw.get("advisor_highlights") or raw.get("highlights") or raw.get("fitHighlights") or raw.get("fit_highlights") or raw.get("keyPoints") or raw.get("key_points") or [],
            "links": raw.get("links") or [],
            "evidence": raw.get("evidence") or [],
            "contacts": contact_rows,
            **contact_meta,
        },
    }
    if events is not None:
        payload["events"] = [outreach_event_to_payload(event) for event in events]
    return payload


def outreach_event_to_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "advisorId": row["advisor_id"],
        "eventType": row["event_type"],
        "eventAt": row["event_at"],
        "summary": row["summary"] or "",
        "detail": row["detail"] or "",
        "createdBy": row["created_by"] or "",
        "createdAt": row["created_at"] or "",
    }


def program_row_to_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "school": row["school"] or "",
        "department": row["department"] or "",
        "programName": row["program_name"] or "",
        "degree": row["degree"] or "PhD",
        "deadline": row["deadline"] or "",
        "status": row["status"] or "候选",
        "priority": row["priority"] or "",
        "requirements": row["requirements"] or "",
        "notes": row["notes"] or "",
        "createdBy": row["created_by"] or "",
        "updatedBy": row["updated_by"] or "",
        "createdAt": row["created_at"] or "",
        "updatedAt": row["updated_at"] or "",
    }


def ai_settings_to_payload(row: sqlite3.Row) -> dict:
    keys = row.keys()
    env_key_present = bool(os.environ.get(AI_API_KEY_ENV, "").strip())
    database_key_allowed = database_ai_key_allowed()
    database_key_present = bool(str(row["api_key"] or "").strip())
    key_source = "env" if env_key_present else ("database" if database_key_allowed and database_key_present else "")
    has_key = bool(configured_ai_api_key(row))
    enabled = bool(row["enabled"])
    endpoint = row["endpoint_url"] or ""
    model = row["model_name"] or ""
    return {
        "enabled": enabled,
        "providerName": row["provider_name"] or "",
        "endpointUrl": endpoint,
        "modelName": model,
        "temperature": row["temperature"] if row["temperature"] is not None else "",
        "hasApiKey": has_key,
        "keySource": key_source,
        "keyManagedByEnv": env_key_present,
        "databaseKeyAllowed": database_key_allowed,
        "databaseKeyBlocked": database_key_present and not database_key_allowed and not env_key_present,
        "available": enabled and has_key and bool(endpoint) and bool(model),
        "toolsEnabled": bool(row["tools_enabled"]) if "tools_enabled" in keys else bool(DEFAULT_AI_TOOLS_ENABLED),
        "allowSearchPages": bool(row["allow_search_pages"]) if "allow_search_pages" in keys else bool(DEFAULT_AI_ALLOW_SEARCH_PAGES),
        "toolMaxResults": int(row["tool_max_results"]) if "tool_max_results" in keys and row["tool_max_results"] else DEFAULT_AI_TOOL_MAX_RESULTS,
        "toolTimeoutSeconds": int(row["tool_timeout_seconds"]) if "tool_timeout_seconds" in keys and row["tool_timeout_seconds"] else DEFAULT_AI_TOOL_TIMEOUT_SECONDS,
        "toolCacheTtlSeconds": int(row["tool_cache_ttl_seconds"]) if "tool_cache_ttl_seconds" in keys and row["tool_cache_ttl_seconds"] else DEFAULT_AI_TOOL_CACHE_TTL_SECONDS,
        "updatedBy": row["updated_by"] or "",
        "updatedAt": row["updated_at"] or "",
    }


def ai_conversation_to_payload(row: sqlite3.Row, messages: list[sqlite3.Row] | None = None) -> dict:
    payload = {
        "id": row["id"],
        "advisorId": row["advisor_id"],
        "title": row["title"],
        "createdBy": row["created_by"] or "",
        "createdAt": row["created_at"] or "",
        "updatedAt": row["updated_at"] or "",
    }
    if messages is not None:
        payload["messages"] = [ai_message_to_payload(message) for message in messages]
    return payload


def ai_message_to_payload(row: sqlite3.Row) -> dict:
    keys = row.keys()
    return {
        "id": row["id"],
        "conversationId": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "createdBy": row["created_by"] if "created_by" in keys else "",
        "createdAt": row["created_at"],
    }


def limited_ai_list(value: object, limit: int) -> list:
    if not isinstance(value, list):
        return []
    return value[:limit]


def first_nonempty_raw_value(raw: dict, keys: list[str]) -> object:
    for key in keys:
        value = raw.get(key)
        if value:
            return value
    return ""


def advisor_context_for_ai(row: sqlite3.Row, cv_context: dict | None = None) -> tuple[str, str]:
    raw = json.loads(row["raw_json"])
    title = f"{AI_ADVISOR_CHAT_TITLE_PREFIX}{raw.get('name', row['id'])}"
    links = raw.get("links") or []
    evidence = raw.get("evidence") or []
    highlights = first_nonempty_raw_value(
        raw,
        [
            "advisorHighlights",
            "advisor_highlights",
            "highlights",
            "fitHighlights",
            "fit_highlights",
            "keyPoints",
            "key_points",
        ],
    )
    context = {
        "advisor_id": row["id"],
        "name": raw.get("name", ""),
        "institution": raw.get("firstInstitution") or raw.get("institution", ""),
        "institution_zh": raw.get("firstInstitutionZh") or raw.get("institutionZh", ""),
        "city": raw.get("city", ""),
        "state": raw.get("state", ""),
        "research_pool": raw.get("primaryCategory", ""),
        "matched_keywords": raw.get("matchedKeywords", ""),
        "stage_label": raw.get("stageLabel", ""),
        "stage_evidence": raw.get("stageEvidence", ""),
        "phd_advising_status": raw.get("phdAdvisingStatus", ""),
        "recruiting_status": raw.get("recruitingStatus", ""),
        "student_background_status": raw.get("studentBackgroundStatus", ""),
        "evidence_reliability": raw.get("evidenceReliability", ""),
        "advisor_highlights": highlights,
        "known_contacts": first_nonempty_raw_value(raw, ["contacts", "contactInfo", "contact_info"]),
        "known_links": limited_ai_list(links, AI_ADVISOR_LINK_LIMIT),
        "paper_evidence": limited_ai_list(evidence, AI_ADVISOR_EVIDENCE_LIMIT),
        "applicant_latest_cv": cv_context or {"status": "未找到最新CV"},
    }
    return title, json.dumps(context, ensure_ascii=False, indent=2)


def ai_request_timeout_seconds() -> int:
    raw = os.environ.get(AI_REQUEST_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_AI_REQUEST_TIMEOUT_SECONDS
    try:
        return max(30, min(int(raw), 600))
    except ValueError:
        return DEFAULT_AI_REQUEST_TIMEOUT_SECONDS


def ai_ssl_context() -> ssl.SSLContext | None:
    cert_file = os.environ.get(AI_SSL_CERT_FILE_ENV, "").strip() or os.environ.get("SSL_CERT_FILE", "").strip()
    if cert_file:
        path = Path(cert_file).expanduser()
        if not path.exists():
            raise RuntimeError(f"AI SSL 证书文件不存在：{path}")
        return ssl.create_default_context(cafile=str(path))
    try:
        import certifi  # type: ignore
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def normalize_ai_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError("AI API 地址无效，请填写 https://... 形式的 Base URL 或 Chat Completions Endpoint")
    path = parsed.path.rstrip("/")
    if "/docs/" in path:
        raise RuntimeError("AI API 地址填成了文档页面，请改用 https://api.kkrich.ltd/v1")
    if not path:
        path = "/v1/chat/completions"
    elif path.endswith("/chat/completions"):
        pass
    elif path.endswith("/v1"):
        path = f"{path}/chat/completions"
    else:
        raise RuntimeError("AI API 地址需要是 Base URL（例如 https://api.kkrich.ltd/v1）或完整 Chat Completions Endpoint")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))


def row_value(row: sqlite3.Row, key: str, default=None):
    return row[key] if key in row.keys() and row[key] is not None else default


def ai_tool_config(settings: sqlite3.Row) -> dict:
    return {
        "enabled": bool(row_value(settings, "tools_enabled", DEFAULT_AI_TOOLS_ENABLED)),
        "allow_search_pages": bool(row_value(settings, "allow_search_pages", DEFAULT_AI_ALLOW_SEARCH_PAGES)),
        "max_results": max(1, min(int(row_value(settings, "tool_max_results", DEFAULT_AI_TOOL_MAX_RESULTS) or DEFAULT_AI_TOOL_MAX_RESULTS), 8)),
        "timeout": max(3, min(int(row_value(settings, "tool_timeout_seconds", DEFAULT_AI_TOOL_TIMEOUT_SECONDS) or DEFAULT_AI_TOOL_TIMEOUT_SECONDS), 20)),
        "cache_ttl": max(300, min(int(row_value(settings, "tool_cache_ttl_seconds", DEFAULT_AI_TOOL_CACHE_TTL_SECONDS) or DEFAULT_AI_TOOL_CACHE_TTL_SECONDS), 7 * 24 * 60 * 60)),
    }


def has_any(text: str, words: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(word.lower() in lower for word in words)


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>'\"）)]+", text or "")


def load_ai_advisor_context(context: str) -> dict:
    try:
        data = json.loads(context or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def clean_query_text(text: str, limit: int = 240) -> str:
    value = re.sub(r"https?://\S+", " ", text or "")
    value = re.sub(r"[，。！？、；：,.!?;:]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def guess_weather_location(text: str, advisor_context: dict) -> str:
    prefix_pattern = r"^(?:能不能|能否|可以|能|帮我|请|查一下|查询|看看|看一下|告诉我|今天|明天|现在|当前|today|current)\s*"
    patterns = [
        r"(?:查一下|查询|看看|看一下|告诉我)?\s*([\u4e00-\u9fffA-Za-z .'-]{2,40})\s*(?:的)?天气",
        r"weather\s+(?:in|for)\s+([A-Za-z .'-]{2,60})",
        r"([A-Za-z .'-]{2,60})\s+weather",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            location = match.group(1).strip()
            previous = None
            while previous != location:
                previous = location
                location = re.sub(prefix_pattern, "", location, flags=re.IGNORECASE).strip()
            location = re.sub(r"(?:的|天气|weather)$", "", location, flags=re.IGNORECASE).strip()
            if location and location not in {"今天", "明天", "现在", "当前"}:
                return location
    return str(advisor_context.get("city") or advisor_context.get("institution") or "").strip()


def ai_tool_cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return AI_TOOL_CACHE_DIR / f"{digest}.json"


def cached_tool_get(key: str, ttl_seconds: int) -> object | None:
    path = ai_tool_cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(data.get("created_at", 0)) > ttl_seconds:
        return None
    return data.get("value")


def cached_tool_set(key: str, value: object) -> None:
    AI_TOOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = ai_tool_cache_path(key)
    payload = {"created_at": time.time(), "value": value}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def assert_safe_external_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("只允许抓取 http/https 外部链接")
    host = parsed.hostname or ""
    if host.lower() in LOCAL_HOSTS:
        raise RuntimeError("禁止抓取本机地址")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as error:
        raise RuntimeError(f"无法解析域名：{host}") from error
    for address in addresses:
        ip_text = address[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            raise RuntimeError("无法校验目标 IP")
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise RuntimeError("禁止抓取内网、本机或保留地址")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def safe_external_opener():
    context = ai_ssl_context()
    handlers = [NoRedirectHandler()]
    if context is not None:
        handlers.append(HTTPSHandler(context=context))
    return build_opener(*handlers)


def read_safe_external_url(url: str, timeout: int) -> tuple[bytes, str]:
    current_url = assert_safe_external_url(url)
    opener = safe_external_opener()
    for _redirect_count in range(AI_TOOL_MAX_REDIRECTS + 1):
        request = Request(current_url, headers={"User-Agent": AI_TOOL_USER_AGENT}, method="GET")
        try:
            with opener.open(request, timeout=timeout) as response:
                final_url = assert_safe_external_url(response.geturl())
                content_type = response.headers.get("Content-Type", "")
                raw = response.read(AI_TOOL_MAX_FETCH_BYTES + 1)
                if final_url != current_url:
                    assert_safe_external_url(final_url)
                return raw, content_type
        except HTTPError as error:
            if error.code not in {301, 302, 303, 307, 308}:
                raise
            location = error.headers.get("Location", "")
            if not location:
                raise RuntimeError("外部链接重定向缺少 Location")
            current_url = assert_safe_external_url(urljoin(current_url, location))
    raise RuntimeError("外部链接重定向次数过多")


def fetch_url_bytes(url: str, timeout: int, cache_ttl: int) -> tuple[bytes, str]:
    safe_url = assert_safe_external_url(url)
    cache_key = f"fetch:{safe_url}"
    cached = cached_tool_get(cache_key, cache_ttl)
    if isinstance(cached, dict) and "body" in cached:
        return str(cached["body"]).encode("utf-8", errors="replace"), str(cached.get("content_type") or "")
    raw, content_type = read_safe_external_url(safe_url, timeout)
    if len(raw) > AI_TOOL_MAX_FETCH_BYTES:
        raw = raw[:AI_TOOL_MAX_FETCH_BYTES]
    text = raw.decode("utf-8", errors="replace")
    cached_tool_set(cache_key, {"body": text, "content_type": content_type})
    return text.encode("utf-8"), content_type


def fetch_json(url: str, timeout: int, cache_ttl: int) -> dict:
    raw, _content_type = fetch_url_bytes(url, timeout, cache_ttl)
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error:
        raise RuntimeError("接口没有返回 JSON") from error
    return data if isinstance(data, dict) else {"data": data}


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n", text)
    text = re.sub(r"(?is)<.*?>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def ai_tool_weather(query: str, advisor_context: dict, config: dict) -> dict:
    location = guess_weather_location(query, advisor_context)
    if not location:
        return {"tool": "weather_lookup", "ok": False, "message": "未识别到天气查询地点"}
    geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
        {"name": location, "count": 1, "language": "zh", "format": "json"}
    )
    geo = fetch_json(geocode_url, config["timeout"], config["cache_ttl"])
    results = geo.get("results") or []
    if not results:
        return {"tool": "weather_lookup", "ok": False, "message": f"未找到地点：{location}", "source": geocode_url}
    place = results[0]
    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urlencode(
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        }
    )
    weather = fetch_json(forecast_url, config["timeout"], max(300, min(config["cache_ttl"], 1800)))
    return {
        "tool": "weather_lookup",
        "ok": True,
        "location": {
            "name": place.get("name"),
            "admin1": place.get("admin1"),
            "country": place.get("country"),
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
        },
        "current": weather.get("current", {}),
        "daily": weather.get("daily", {}),
        "sources": [geocode_url, forecast_url],
    }


def semantic_scholar_search(query: str, config: dict) -> list[dict]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urlencode(
        {
            "query": query,
            "limit": config["max_results"],
            "fields": "title,year,authors,venue,url,abstract,citationCount",
        }
    )
    data = fetch_json(url, config["timeout"], config["cache_ttl"])
    papers = []
    for item in data.get("data") or []:
        papers.append(
            {
                "title": item.get("title", ""),
                "year": item.get("year", ""),
                "venue": item.get("venue", ""),
                "url": item.get("url", ""),
                "citationCount": item.get("citationCount", ""),
                "authors": [author.get("name", "") for author in item.get("authors", [])[:4]],
                "abstract": (item.get("abstract") or "")[:700],
                "source": url,
            }
        )
    return papers


def crossref_search(query: str, config: dict) -> list[dict]:
    url = "https://api.crossref.org/works?" + urlencode(
        {
            "query.bibliographic": query,
            "rows": config["max_results"],
            "select": "title,author,published-print,published-online,URL,container-title,is-referenced-by-count,abstract",
        }
    )
    data = fetch_json(url, config["timeout"], config["cache_ttl"])
    papers = []
    for item in ((data.get("message") or {}).get("items") or []):
        title = item.get("title") or [""]
        authors = item.get("author") or []
        year_parts = (item.get("published-print") or item.get("published-online") or {}).get("date-parts") or []
        year = year_parts[0][0] if year_parts and year_parts[0] else ""
        papers.append(
            {
                "title": title[0] if title else "",
                "year": year,
                "venue": (item.get("container-title") or [""])[0],
                "url": item.get("URL", ""),
                "citationCount": item.get("is-referenced-by-count", ""),
                "authors": [f"{author.get('given', '')} {author.get('family', '')}".strip() for author in authors[:4]],
                "abstract": html_to_text(item.get("abstract") or "")[:700],
                "source": url,
            }
        )
    return papers


def name_tokens(value: str) -> set[str]:
    return {part.lower() for part in re.findall(r"[A-Za-z]+", value or "") if len(part) > 2}


def paper_matches_advisor(paper: dict, advisor_name: str) -> bool:
    tokens = name_tokens(advisor_name)
    if not tokens:
        return True
    author_text = " ".join(paper.get("authors") or []).lower()
    return bool(tokens & name_tokens(author_text))


def ai_tool_literature(query: str, advisor_context: dict, config: dict) -> dict:
    advisor_name = str(advisor_context.get("name") or "").strip()
    institution = str(advisor_context.get("institution") or "").strip()
    search_query = f"{advisor_name} {institution}".strip() if advisor_name else clean_query_text(query)
    if has_any(query, ("llm", "benchmark", "evaluation", "agent", "robustness")):
        search_query = f"{search_query} {clean_query_text(query, 80)}".strip()
    if not search_query:
        return {"tool": "literature_lookup", "ok": False, "message": "缺少文献检索关键词"}
    errors: list[str] = []
    papers: list[dict] = []
    try:
        papers.extend(semantic_scholar_search(search_query, config))
    except Exception as error:
        errors.append(f"Semantic Scholar: {error}")
    if len(papers) < 2:
        try:
            papers.extend(crossref_search(search_query, config))
        except Exception as error:
            errors.append(f"Crossref: {error}")
    seen: set[str] = set()
    unique = []
    for paper in papers:
        if advisor_name and not paper_matches_advisor(paper, advisor_name):
            continue
        key = (paper.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(paper)
    known_evidence = advisor_context.get("paper_evidence") or []
    return {
        "tool": "literature_lookup",
        "ok": bool(unique or known_evidence),
        "query": search_query,
        "papers": unique[: config["max_results"]],
        "known_paper_evidence_from_platform": known_evidence,
        "errors": errors,
    }


def parse_duckduckgo_results(raw_html: str, max_results: int) -> list[dict]:
    results: list[dict] = []
    pattern = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
    for url, title_html in pattern.findall(raw_html):
        title = html_to_text(title_html)
        parsed = urlparse(html_lib.unescape(url))
        actual = parse_qs(parsed.query).get("uddg", [""])[0] if "duckduckgo.com" in parsed.netloc else html_lib.unescape(url)
        if title and actual.startswith("http"):
            results.append({"title": title, "url": actual})
        if len(results) >= max_results:
            break
    return results


def parse_bing_results(raw_html: str, max_results: int) -> list[dict]:
    results: list[dict] = []
    pattern = re.compile(r'<li class="b_algo".*?<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?</h2>', re.I | re.S)
    for url, title_html in pattern.findall(raw_html):
        title = html_to_text(title_html)
        url = html_lib.unescape(url)
        if title and url.startswith("http"):
            results.append({"title": title, "url": url})
        if len(results) >= max_results:
            break
    return results


def query_tokens(value: str) -> set[str]:
    stop = {"the", "and", "for", "with", "about", "what", "how", "this", "that", "大学", "学校", "查询", "搜索", "一下"}
    return {token.lower() for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{3,}", value or "") if token.lower() not in stop}


def filter_relevant_search_results(query: str, results: list[dict]) -> list[dict]:
    tokens = query_tokens(query)
    if not tokens:
        return results
    filtered = []
    for item in results:
        haystack = f"{item.get('title', '')} {item.get('url', '')}".lower()
        matches = sum(1 for token in tokens if token.lower() in haystack)
        if matches >= min(2, len(tokens)):
            filtered.append(item)
    return filtered


def ai_tool_web_search(query: str, config: dict) -> dict:
    if not config["allow_search_pages"]:
        return {"tool": "web_search", "ok": False, "message": "系统设置未允许抓取搜索结果页"}
    search_query = clean_query_text(query)
    if not search_query:
        return {"tool": "web_search", "ok": False, "message": "缺少搜索关键词"}
    sources = []
    url = "https://duckduckgo.com/html/?" + urlencode({"q": search_query})
    raw, _content_type = fetch_url_bytes(url, config["timeout"], config["cache_ttl"])
    sources.append(url)
    results = parse_duckduckgo_results(raw.decode("utf-8", errors="replace"), config["max_results"])
    if not results:
        url = "https://www.bing.com/search?" + urlencode({"q": search_query, "setlang": "en-US", "cc": "US"})
        raw, _content_type = fetch_url_bytes(url, config["timeout"], config["cache_ttl"])
        sources.append(url)
        results = parse_bing_results(raw.decode("utf-8", errors="replace"), config["max_results"])
    results = filter_relevant_search_results(search_query, results)
    return {"tool": "web_search", "ok": bool(results), "query": search_query, "results": results, "sources": sources}


def ai_tool_web_fetch(urls: list[str], config: dict) -> dict:
    pages = []
    errors = []
    for url in urls[: config["max_results"]]:
        try:
            raw, content_type = fetch_url_bytes(url, config["timeout"], config["cache_ttl"])
            text = html_to_text(raw.decode("utf-8", errors="replace"))[:AI_TOOL_TEXT_CHARS]
            pages.append({"url": url, "contentType": content_type, "text": text})
        except Exception as error:
            errors.append({"url": url, "error": str(error)})
    return {"tool": "web_fetch", "ok": bool(pages), "pages": pages, "errors": errors}


def ai_tool_school_location(query: str, advisor_context: dict, config: dict) -> dict:
    target = str(advisor_context.get("institution") or "").strip()
    if not target or not any(word in query for word in ("这个学校", "学校", "大学", "university", "school")):
        target = clean_query_text(query)
    wiki_url = "https://en.wikipedia.org/w/api.php?" + urlencode(
        {"action": "query", "list": "search", "srsearch": target, "format": "json", "srlimit": 1}
    )
    try:
        data = fetch_json(wiki_url, config["timeout"], config["cache_ttl"])
        hits = ((data.get("query") or {}).get("search") or [])
        if not hits:
            return {"tool": "school_location_lookup", "ok": False, "query": target, "message": "Wikipedia 未找到匹配", "source": wiki_url}
        title = hits[0]["title"]
        summary_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"))
        summary = fetch_json(summary_url, config["timeout"], config["cache_ttl"])
        return {
            "tool": "school_location_lookup",
            "ok": True,
            "query": target,
            "title": title,
            "extract": summary.get("extract", ""),
            "url": (summary.get("content_urls") or {}).get("desktop", {}).get("page", summary_url),
            "sources": [wiki_url, summary_url],
        }
    except Exception as error:
        return {"tool": "school_location_lookup", "ok": False, "query": target, "message": str(error), "source": wiki_url}


def run_ai_tools(settings: sqlite3.Row, user_content: str, advisor_context: dict) -> str:
    config = ai_tool_config(settings)
    if not config["enabled"]:
        return ""
    results: list[dict] = []
    urls = extract_urls(user_content)
    try:
        if urls:
            results.append(ai_tool_web_fetch(urls, config))
        if has_any(user_content, WEATHER_TRIGGER_WORDS):
            results.append(ai_tool_weather(user_content, advisor_context, config))
        if has_any(user_content, LITERATURE_TRIGGER_WORDS):
            results.append(ai_tool_literature(user_content, advisor_context, config))
        if has_any(user_content, SCHOOL_LOCATION_TRIGGER_WORDS):
            results.append(ai_tool_school_location(user_content, advisor_context, config))
        if (
            config["allow_search_pages"]
            and has_any(user_content, SEARCH_TRIGGER_WORDS + SCHOOL_LOCATION_TRIGGER_WORDS)
            and not has_any(user_content, WEATHER_TRIGGER_WORDS)
        ):
            results.append(ai_tool_web_search(user_content, config))
    except Exception as error:
        results.append({"tool": "tool_router", "ok": False, "message": str(error)})
    if not results:
        return ""
    payload = {
        "policy": "以下是平台后端实时工具查询结果。回答时必须区分工具已查到的信息和仍需人工核实的信息；涉及事实结论时给出来源链接；不要声称自己直接联网，而应说明基于平台工具结果。",
        "results": results,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return text[:AI_TOOL_CONTEXT_CHARS]


def chat_content_from_json(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("AI API 没有返回 choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or choices[0].get("text") or ""
    if isinstance(content, list):
        content = "".join(str(part.get("text", "") if isinstance(part, dict) else part) for part in content)
    if not content:
        raise RuntimeError("AI API 没有返回可读内容")
    return str(content).strip()


def chat_content_from_sse(raw: bytes) -> str:
    chunks: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        event_data = line.removeprefix("data:").strip()
        if not event_data or event_data == "[DONE]":
            continue
        try:
            data = json.loads(event_data)
        except json.JSONDecodeError:
            continue
        for choice in data.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content") or choice.get("text") or ""
            if content:
                chunks.append(str(content))
    content = "".join(chunks).strip()
    if not content:
        raise RuntimeError("AI API 流式返回中没有可读内容")
    return content


def call_chat_completion(settings: sqlite3.Row, messages: list[dict], max_tokens: int | None = None) -> str:
    endpoint = normalize_ai_endpoint(settings["endpoint_url"] or "")
    model = (settings["model_name"] or "").strip()
    api_key = configured_ai_api_key(settings)
    if not endpoint or not model or not api_key:
        raise RuntimeError("AI API 配置不完整")
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if settings["temperature"] is not None and str(settings["temperature"]).strip() != "":
        payload["temperature"] = float(settings["temperature"])
    if max_tokens:
        payload["max_tokens"] = max_tokens
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=ai_request_timeout_seconds(), context=ai_ssl_context()) as response:
            raw = response.read()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"AI API 返回错误：{error.code} {detail}") from error
    except URLError as error:
        raise RuntimeError(f"AI API 无法连接：{error.reason}") from error
    except TimeoutError as error:
        raise RuntimeError("AI API 请求超时") from error
    text = raw.decode("utf-8", errors="replace").lstrip()
    if text.startswith("data:"):
        return chat_content_from_sse(raw)
    try:
        return chat_content_from_json(json.loads(text))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"AI API 返回格式无法解析：{text[:200]}") from error


def advisor_ai_system_message(context: str) -> str:
    return (
        "你是 Applicant PhD 申请项目里的导师匹配与套磁助手。"
        "本对话绑定一位导师，并附带系统中已有的导师事实和 Applicant 最新 CV 摘要。"
        "回答必须服务于博士申请决策：研究匹配、套磁切入点、风险、待核实事实。"
        "必须严格区分已知信息、基于已知信息的推断、待确认信息；不要编造主页、招生、学生背景或联系方式。"
        "如果系统消息里提供“平台工具查询结果”，你可以基于这些结果回答实时天气、文献、学校、城市、生活成本等问题；"
        "引用事实时必须说明来源链接或说明来源不足。"
        "如果没有平台工具结果，不要声称自己可以实时联网。"
        "输出使用中文，保留英文专有名词。\n\n"
        f"绑定上下文 JSON：\n{context}"
    )


def initial_advisor_ai_messages(context: str) -> list[dict]:
    system = (
        advisor_ai_system_message(context)
    )
    user = (
        "请基于绑定导师的已知信息和 Applicant 最新 CV 摘要，生成首次导师匹配反馈。"
        "必须严格使用下面的编号标题和换行格式，不要输出“结论：”“看点：”“下一步：”这种短摘要标题：\n\n"
        "1. 匹配分析：\n"
        "- 第一条必须概括导师已知证据与 Applicant CV 摘要中的匹配点；明确写出证据来自导师信息、论文证据、还是 CV 摘要。\n"
        "- 第二条说明可以合理推断出的匹配叙事，以及哪些部分仍然待确认。\n"
        "- 如信息很少，也要写清“已知证据仅显示...”和“待确认...”，不要编造事实。\n\n"
        "2. 导师看点：\n"
        "- 机会：写一个最值得利用的套磁或申请切入点。\n"
        "- 风险：写一个最影响是否投入精力的不确定性或红旗。\n"
        "- 核查点：写一个最应该马上查证的事实。\n\n"
        "3. 下一步建议：\n"
        "- 给 2-3 条具体动作，优先包括官方主页 / 实验室页 / Google Scholar / 近两年论文 / 招生状态 / 联系方式等核查。\n"
        "- 如果值得进入套磁准备，明确说明可强调 Applicant 哪个经历与导师哪个方向连接。\n\n"
        "所有正文条目都必须以短横线开头；每个条目单独成行；每个标题后必须换行。"
        "整体控制在 700 个中文字符以内，保持信息密度，不要空泛评价。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def document_row_to_payload(row: sqlite3.Row) -> dict:
    file_path = row["file_path"] or ""
    file_size = int(row["file_size"] or 0)
    return {
        "id": row["id"],
        "docType": row["doc_type"],
        "title": row["title"],
        "versionLabel": row["version_label"],
        "status": row["status"] or "",
        "owner": row["owner"] or "",
        "uploadedBy": row["uploaded_by"] or row["owner"] or "",
        "originalFilename": row["original_filename"] or "",
        "fileSize": file_size,
        "mimeType": row["mime_type"] or "",
        "hasFile": bool(file_path),
        "createdAt": row["created_at"] or row["updated_at"] or "",
        "updatedAt": row["updated_at"] or "",
        "notes": row["notes"] or "",
    }


def document_types_payload(conn: sqlite3.Connection) -> list[dict]:
    counts = {
        row["doc_type"]: row["count"]
        for row in conn.execute(
            "select doc_type, count(*) as count from documents where coalesce(file_path, '') != '' group by doc_type"
        ).fetchall()
    }
    return [
        {"value": value, "label": label, "count": counts.get(value, 0)}
        for value, label in DOCUMENT_TYPES
    ]


def next_document_version(conn: sqlite3.Connection, doc_type: str) -> str:
    rows = conn.execute("select version_label from documents where doc_type = ?", (doc_type,)).fetchall()
    max_version = 0
    for row in rows:
        match = re.search(r"(\d+)", row["version_label"] or "")
        if match:
            max_version = max(max_version, int(match.group(1)))
    return f"V{max_version + 1}"


def resolve_document_file(file_path: str) -> Path | None:
    if not file_path:
        return None
    target = (DATA_DIR / file_path).resolve()
    data_root = DATA_DIR.resolve()
    if data_root != target and data_root not in target.parents:
        return None
    return target


def file_extension(name: str) -> str:
    suffix = Path(name or "").suffix.lower()
    return suffix[1:] if suffix.startswith(".") else suffix


def document_content_type(filename: str, stored_mime: str | None) -> str:
    guessed = mimetypes.guess_type(filename or "")[0] or ""
    stored = (stored_mime or "").strip().lower()
    if stored in GENERIC_BINARY_MIMES:
        return guessed or "application/octet-stream"
    return stored or guessed or "application/octet-stream"


def html_lines(text: str) -> str:
    return "<br>".join(html_lib.escape(line) for line in text.splitlines()) or "&nbsp;"


def docx_text_from_node(node: ET.Element) -> str:
    parts: list[str] = []
    for child in node.iter():
        if child.tag == f"{W}t":
            parts.append(child.text or "")
        elif child.tag == f"{W}tab":
            parts.append("\t")
        elif child.tag in {f"{W}br", f"{W}cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def docx_paragraph_style(paragraph: ET.Element) -> str:
    p_pr = paragraph.find(f"{W}pPr")
    style_node = p_pr.find(f"{W}pStyle") if p_pr is not None else None
    if style_node is None:
        return ""
    return style_node.attrib.get(f"{W}val", "")


def docx_paragraph_html(paragraph: ET.Element) -> str:
    text = docx_text_from_node(paragraph)
    if not text:
        return ""
    style = docx_paragraph_style(paragraph).lower()
    content = html_lines(text)
    if "heading1" in style or style == "title":
        return f"<h1>{content}</h1>"
    if "heading2" in style or "subtitle" in style:
        return f"<h2>{content}</h2>"
    if "heading3" in style:
        return f"<h3>{content}</h3>"
    return f"<p>{content}</p>"


def docx_table_html(table: ET.Element) -> str:
    rows_html: list[str] = []
    for row in table.findall(f"{W}tr"):
        cells_html: list[str] = []
        for cell in row.findall(f"{W}tc"):
            cell_parts = [
                docx_text_from_node(paragraph)
                for paragraph in cell.findall(f"{W}p")
            ]
            cell_text = "\n".join(part for part in cell_parts if part)
            cells_html.append(f"<td>{html_lines(cell_text)}</td>")
        if cells_html:
            rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
    if not rows_html:
        return ""
    return f"<table>{''.join(rows_html)}</table>"


def docx_body_html(target: Path) -> tuple[str, bool]:
    with zipfile.ZipFile(target) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError:
            return "<div class=\"empty\">这个 Word 文件缺少正文内容，无法生成预览。</div>", False
    root = ET.fromstring(document_xml)
    body = root.find(f"{W}body")
    if body is None:
        return "<div class=\"empty\">这个 Word 文件没有可读取的正文。</div>", False

    blocks: list[str] = []
    total_chars = 0
    truncated = False
    for child in body:
        if child.tag == f"{W}p":
            text = docx_text_from_node(child)
            total_chars += len(text)
            if total_chars > MAX_PREVIEW_CHARS:
                truncated = True
                break
            block = docx_paragraph_html(child)
        elif child.tag == f"{W}tbl":
            text = docx_text_from_node(child)
            total_chars += len(text)
            if total_chars > MAX_PREVIEW_CHARS:
                truncated = True
                break
            block = docx_table_html(child)
        else:
            block = ""
        if block:
            blocks.append(block)

    if not blocks:
        blocks.append("<div class=\"empty\">这个 Word 文件没有提取到可预览文本。</div>")
    if truncated:
        blocks.append("<div class=\"preview-note\">预览内容较长，系统只显示前一部分；完整内容请打开原文件。</div>")
    return "\n".join(blocks), truncated


def docx_body_text(target: Path, limit: int = AI_CV_CONTEXT_CHARS) -> str:
    with zipfile.ZipFile(target) as archive:
        document_xml = archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    body = root.find(f"{W}body")
    if body is None:
        return ""

    parts: list[str] = []
    total_chars = 0
    for child in body:
        if child.tag == f"{W}p":
            text = docx_text_from_node(child)
        elif child.tag == f"{W}tbl":
            rows: list[str] = []
            for row in child.findall(f"{W}tr"):
                cells = [
                    docx_text_from_node(cell)
                    for cell in row.findall(f"{W}tc")
                ]
                row_text = " | ".join(cell for cell in cells if cell)
                if row_text:
                    rows.append(row_text)
            text = "\n".join(rows)
        else:
            text = ""
        if not text:
            continue
        parts.append(text)
        total_chars += len(text)
        if total_chars >= limit:
            break
    return "\n".join(parts).strip()[:limit]


def document_text_for_ai(row: sqlite3.Row, limit: int = AI_CV_CONTEXT_CHARS) -> str:
    filename = row["original_filename"] or row["stored_filename"] or ""
    target = resolve_document_file(row["file_path"] or "")
    if target is None or not target.exists():
        return ""
    extension = file_extension(filename or target.name)
    try:
        if extension in {"docx", "docm"}:
            return docx_body_text(target, limit)
        if extension in {"txt", "md", "markdown"}:
            return target.read_text(encoding="utf-8", errors="replace").strip()[:limit]
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError, ET.ParseError):
        return ""
    return ""


def latest_cv_context(conn) -> dict:
    row = conn.execute(
        """
        select * from documents
        where doc_type = ? and coalesce(file_path, '') != ''
        order by case when coalesce(created_at, '') = '' then updated_at else created_at end desc, id desc
        limit 1
        """,
        ("CV",),
    ).fetchone()
    if not row:
        return {"status": "未找到最新CV"}
    text = document_text_for_ai(row)
    context = {
        "status": "已找到最新CV",
        "title": row["title"] or "",
        "version_label": row["version_label"] or "",
        "document_status": row["status"] or "",
        "filename": row["original_filename"] or "",
        "updated_at": row["updated_at"] or row["created_at"] or "",
    }
    if text:
        context["text_excerpt"] = text
    else:
        context["text_excerpt"] = "当前文件格式暂未提取正文，已仅提供CV文件元数据。"
    return context


def preview_html_shell(title: str, subtitle: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_lib.escape(title)}</title>
  <style>
    :root {{
      --line: #d9e0e8;
      --text: #1d2939;
      --muted: #667085;
      --accent: #1769aa;
      --bg: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 22px;
      color: var(--text);
      background: var(--bg);
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 14px;
      line-height: 1.62;
    }}
    .preview-meta {{
      margin: 0 0 18px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }}
    h1, h2, h3 {{ margin: 18px 0 8px; line-height: 1.25; letter-spacing: 0; }}
    h1 {{ font-size: 24px; }}
    h2 {{ font-size: 19px; }}
    h3 {{ font-size: 16px; }}
    p {{ margin: 0 0 10px; white-space: normal; }}
    table {{
      width: 100%;
      margin: 12px 0;
      border-collapse: collapse;
      font-size: 13px;
    }}
    td {{
      border: 1px solid var(--line);
      padding: 8px 10px;
      vertical-align: top;
    }}
    .empty, .preview-note {{
      margin: 16px 0;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8fafc;
      color: var(--muted);
    }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
  <div class="preview-meta">{html_lib.escape(subtitle)}</div>
  <main>{body_html}</main>
</body>
</html>"""


def docx_preview_html(target: Path, title: str, filename: str) -> str:
    try:
        body_html, _truncated = docx_body_html(target)
    except (zipfile.BadZipFile, ET.ParseError, OSError):
        body_html = "<div class=\"empty\">这个 Word 文件无法解析。请确认文件没有损坏，或下载原文件查看。</div>"
    subtitle = f"Word 预览 · {filename}"
    return preview_html_shell(title, subtitle, body_html)


def unsupported_word_preview_html(title: str, filename: str) -> str:
    body_html = (
        "<div class=\"empty\">旧版 .doc 文件不是开放 XML 格式，当前本地预览器无法稳定解析。"
        "请将文件另存为 .docx 或 PDF 后上传；原文件仍可通过“打开文件”查看。</div>"
    )
    return preview_html_shell(title, f"Word 预览 · {filename}", body_html)


def parse_multipart_form(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, dict]]:
    message = BytesParser(policy=email_policy).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    fields: dict[str, str] = {}
    files: dict[str, dict] = {}
    if not message.is_multipart():
        return fields, files
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name] = {
                "filename": filename,
                "content_type": part.get_content_type(),
                "data": payload,
            }
        else:
            charset = part.get_content_charset() or "utf-8"
            fields[name] = payload.decode(charset, errors="replace").strip()
    return fields, files


class AppHandler(BaseHTTPRequestHandler):
    server_version = "ApplicantPlatform/0.1"
    platform_accounts: dict[str, str] = {}
    cookie_secure = False

    def log_message(self, fmt: str, *args) -> None:
        return

    def current_session_user(self) -> str | None:
        cookies = parse_cookies(self.headers.get("Cookie"))
        token = cookies.get(SESSION_COOKIE)
        if not token:
            return None
        return SESSIONS.get(token)

    def require_auth(self) -> bool:
        if self.current_session_user():
            return True
        unauthorized(self)
        return False

    def send_session_cookie(self, token: str, max_age: int = 604800) -> None:
        secure = "; Secure" if self.cookie_secure else ""
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax{secure}",
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            return json_response(self, {"ok": True})
        if path == "/":
            return self.serve_static("index.html")
        if path.startswith("/static/"):
            return self.serve_static(path.removeprefix("/static/"))
        if path == "/api/session":
            return self.handle_session()
        if path.startswith("/api/") and not self.require_auth():
            return
        if path == "/api/summary":
            return self.handle_summary()
        if path == "/api/advisors":
            return self.handle_advisors(parse_qs(parsed.query))
        if path.startswith("/api/advisors/"):
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[3] == "contacts":
                return self.handle_advisor_contacts(parts[2])
            if len(parts) == 3:
                return self.handle_advisor(parts[2], parse_qs(parsed.query))
        if path == "/api/options":
            return self.handle_options()
        if path == "/api/ai/settings":
            return self.handle_ai_settings()
        if path.startswith("/api/ai/conversations/"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                return self.handle_ai_conversation(parts[3])
        if path == "/api/ai/conversations":
            return self.handle_ai_conversations(parse_qs(parsed.query))
        if path == "/api/outreach":
            return self.handle_outreach_list(parse_qs(parsed.query))
        if path.startswith("/api/outreach/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                return self.handle_outreach_detail(parts[2])
        if path == "/api/programs":
            return self.handle_programs(parse_qs(parsed.query))
        if path == "/api/documents":
            return self.handle_documents(parse_qs(parsed.query))
        if path.startswith("/api/documents/") and path.endswith("/preview"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                return self.handle_document_preview(parts[2])
        if path.startswith("/api/documents/") and path.endswith("/file"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                return self.handle_document_file(parts[2])
        return not_found(self)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            return self.handle_login()
        if parsed.path == "/api/logout":
            return self.handle_logout()
        if parsed.path.startswith("/api/") and not self.require_auth():
            return
        if parsed.path == "/api/reviews":
            return self.handle_save_review()
        if parsed.path.startswith("/api/advisors/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 4 and parts[3] == "contacts":
                return self.handle_save_advisor_contact(parts[2])
        if parsed.path == "/api/ai/settings":
            return self.handle_save_ai_settings()
        if parsed.path == "/api/ai/settings/test":
            return self.handle_test_ai_settings()
        if parsed.path.startswith("/api/ai/advisors/") and parsed.path.endswith("/conversations"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 5:
                return self.handle_create_advisor_ai_conversation(parts[3])
        if parsed.path.startswith("/api/ai/conversations/") and parsed.path.endswith("/messages"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 5:
                return self.handle_add_ai_message(parts[3])
        if parsed.path == "/api/outreach/toggle":
            return self.handle_toggle_outreach()
        if parsed.path.startswith("/api/outreach/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3:
                return self.handle_update_outreach(parts[2])
            if len(parts) == 4 and parts[3] == "events":
                return self.handle_add_outreach_event(parts[2])
        if parsed.path == "/api/programs":
            return self.handle_save_program()
        if parsed.path.startswith("/api/programs/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3:
                return self.handle_save_program(parts[2])
        if parsed.path == "/api/documents/upload":
            return self.handle_upload_document()
        return not_found(self)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") and not self.require_auth():
            return
        if parsed.path.startswith("/api/advisors/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 5 and parts[3] == "contacts":
                return self.handle_delete_advisor_contact(parts[2], parts[4])
        if parsed.path.startswith("/api/outreach/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 5 and parts[3] == "events":
                return self.handle_delete_outreach_event(parts[2], parts[4])
            if len(parts) == 3:
                return self.handle_deactivate_outreach(parts[2])
        if parsed.path.startswith("/api/programs/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3:
                return self.handle_delete_program(parts[2])
        if parsed.path.startswith("/api/documents/"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3:
                return self.handle_delete_document(parts[2])
        return not_found(self)

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_response(HTTPStatus.OK)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/" or parsed.path.startswith("/static/"):
            static_name = "index.html" if parsed.path == "/" else parsed.path.removeprefix("/static/")
            target, content_type = static_target(static_name)
            if not target:
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            return
        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def serve_static(self, name: str) -> None:
        target, content_type = static_target(name)
        if not target:
            return not_found(self)
        text_response(self, target.read_text(encoding="utf-8"), content_type=content_type)

    def handle_session(self) -> None:
        user = self.current_session_user()
        json_response(self, {"authenticated": bool(user), "user": user or ""})

    def handle_login(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        password = str(payload.get("password", ""))
        user = str(payload.get("user", "")).strip()
        expected_password = self.platform_accounts.get(user)
        if not expected_password or not hmac.compare_digest(password, expected_password):
            return unauthorized(self)
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = user
        body = json.dumps({"ok": True, "user": user}, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_session_cookie(token)
        self.end_headers()
        self.wfile.write(body)

    def handle_logout(self) -> None:
        cookies = parse_cookies(self.headers.get("Cookie"))
        token = cookies.get(SESSION_COOKIE)
        if token:
            SESSIONS.pop(token, None)
        body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_session_cookie("", max_age=0)
        self.end_headers()
        self.wfile.write(body)

    def handle_summary(self) -> None:
        with connect() as conn:
            total = conn.execute("select count(*) from advisors").fetchone()[0]
            ap = conn.execute("select count(*) from advisors where stage_key = 'ap'").fetchone()[0]
            reviewed = conn.execute(
                "select count(distinct advisor_id) from advisor_reviews "
                "where interest in ('高兴趣','很有兴趣','有兴趣','一般','待判断','不感兴趣','高','中','低','不保留','排除') "
                "or review_status in ('待请求','请求查询','需查询','已查询') or note != ''"
            ).fetchone()[0]
            interested = conn.execute(
                "select count(distinct advisor_id) from advisor_reviews "
                "where interest in ('高兴趣','很有兴趣','有兴趣','一般','高','中')"
            ).fetchone()[0]
            high_evidence = conn.execute("select count(*) from advisors where evidence_reliability in ('高','中')").fetchone()[0]
            outreach_active = conn.execute("select count(*) from outreach_targets where is_active = 1").fetchone()[0]
            outreach_sent = conn.execute("select count(*) from outreach_targets where is_active = 1 and status in ('已发送','已回复','需跟进','已面试','已申请')").fetchone()[0]
            outreach_replied = conn.execute(
                "select count(*) from outreach_targets where is_active = 1 and "
                "(status in ('已回复','需跟进','已面试','已申请') "
                "or stage in ('已面试','面试中','已申请','申请中') "
                "or response_status in ('积极','中性','拒绝'))"
            ).fetchone()[0]
            outreach_interviews = conn.execute(
                "select count(*) from outreach_targets where is_active = 1 and "
                "(stage in ('已面试','面试中') or status in ('已面试','面试中'))"
            ).fetchone()[0]
            outreach_positive = conn.execute("select count(*) from outreach_targets where is_active = 1 and response_status = '积极'").fetchone()[0]
            outreach_followups = conn.execute("select count(*) from outreach_targets where is_active = 1 and (stage = '跟进中' or status = '需跟进')").fetchone()[0]
            programs_total = conn.execute("select count(*) from application_programs").fetchone()[0]
            programs_active = conn.execute("select count(*) from application_programs where status not in ('不申请','已拒绝')").fetchone()[0]
            programs_submitted = conn.execute("select count(*) from application_programs where status in ('已申请','已提交')").fetchone()[0]
            programs_accepted = conn.execute("select count(*) from application_programs where status = '已录取'").fetchone()[0]
            documents_total = conn.execute("select count(*) from documents where coalesce(file_path, '') != ''").fetchone()[0]
            categories = conn.execute(
                "select category as value, category as label, count(*) as count "
                "from advisors where category != '' group by category "
                f"order by {advisor_category_order_sql('category')}"
            ).fetchall()
            stages = conn.execute(
                "select stage_key as value, stage_label as label, count(*) as count "
                "from advisors where stage_key != '' group by stage_key, stage_label"
            ).fetchall()
            tiers = conn.execute(
                "select school_tier as value, school_tier_label as label, count(*) as count "
                "from advisors where school_tier != '' group by school_tier, school_tier_label"
            ).fetchall()
            heatmap_items = conn.execute(
                """
                select
                  a.category,
                  a.stage_key,
                  a.stage_label,
                  a.school_tier,
                  a.school_tier_label,
                  coalesce(r.interest, '') as interest,
                  coalesce(o.is_active, 0) as outreach_active,
                  coalesce(o.response_status, '') as outreach_response_status,
                  coalesce(o.stage, '') as outreach_stage,
                  case
                    when coalesce(o.is_active, 0) = 1 then coalesce(nullif(o.status, ''), '待联系')
                    else '未加入'
                  end as outreach_status
                from advisors a
                left join outreach_targets o on o.advisor_id = a.id
                """
                + latest_review_join_sql()
            ).fetchall()
            outreach_statuses = conn.execute(
                "select status as value, status as label, count(*) as count from outreach_targets where is_active = 1 group by status order by count desc"
            ).fetchall()
            program_statuses = conn.execute(
                "select status as value, status as label, count(*) as count from application_programs group by status order by count desc"
            ).fetchall()
        json_response(
            self,
            {
                "total": total,
                "ap": ap,
                "reviewed": reviewed,
                "interested": interested,
                "highEvidence": high_evidence,
                "outreachActive": outreach_active,
                "outreachSent": outreach_sent,
                "outreachReplied": outreach_replied,
                "outreachInterviews": outreach_interviews,
                "outreachPositive": outreach_positive,
                "outreachFollowups": outreach_followups,
                "programsTotal": programs_total,
                "programsActive": programs_active,
                "programsSubmitted": programs_submitted,
                "programsAccepted": programs_accepted,
                "documentsTotal": documents_total,
                "categories": [dict(row) for row in categories],
                "stages": [dict(row) for row in stages],
                "tiers": [dict(row) for row in tiers],
                "advisorHeatmapItems": [
                    {
                        "category": row["category"] or "",
                        "stage": row["stage_key"] or "",
                        "stageLabel": row["stage_label"] or "",
                        "tier": row["school_tier"] or "",
                        "tierLabel": row["school_tier_label"] or "",
                        "interest": normalize_interest_value(row["interest"] or "") or "待判断",
                        "outreachStatus": row["outreach_status"] or "未加入",
                        "outreachActive": bool(row["outreach_active"]),
                        "outreachResponseStatus": (row["outreach_response_status"] or "") if row["outreach_active"] else "",
                        "outreachStage": (row["outreach_stage"] or "") if row["outreach_active"] else "",
                        "outreachCount": 1 if row["outreach_active"] else 0,
                    }
                    for row in heatmap_items
                ],
                "outreachStatuses": [dict(row) for row in outreach_statuses],
                "programStatuses": [dict(row) for row in program_statuses],
            },
        )

    def handle_options(self) -> None:
        fields = {
            "stages": "stage_key, stage_label",
            "tiers": "school_tier, school_tier_label",
            "categories": "category, category",
        }
        payload = {}
        with connect() as conn:
            for name, columns in fields.items():
                key_col, label_col = [part.strip() for part in columns.split(",")]
                order_sql = f"order by {advisor_category_order_sql(key_col)}" if name == "categories" else "order by count desc"
                rows = conn.execute(
                    f"select {key_col} as value, {label_col} as label, count(*) as count "
                    f"from advisors where {key_col} != '' group by {key_col}, {label_col} {order_sql}"
                ).fetchall()
                payload[name] = [dict(row) for row in rows]
            payload.update(review_filter_option_counts(conn))
        json_response(self, payload)

    def handle_advisors(self, query: dict[str, list[str]]) -> None:
        reviewer = self.current_session_user()
        if not reviewer:
            return unauthorized(self)
        view = (query.get("view", ["full"])[0] or "full").strip().lower()
        list_view = view == "list"
        max_limit = 500 if list_view else 3000
        limit = min(max(int(query.get("limit", ["80"])[0] or 80), 1), max_limit)
        offset = max(int(query.get("offset", ["0"])[0] or 0), 0)
        params: list = []
        where = advisor_filters(query, params)
        with connect() as conn:
            total_params = params.copy()
            total = conn.execute(
                """
                select count(*)
                from advisors a
                """
                + latest_review_join_sql()
                + """
                left join outreach_targets o on o.advisor_id = a.id
                """
                + where,
                total_params,
            ).fetchone()[0]
            if list_view:
                rows = conn.execute(
                    """
                    select
                      a.id,
                      a.`rank`,
                      a.name,
                      a.institution,
                      a.institution_zh,
                      a.city,
                      a.state,
                      a.category,
                      a.stage_key,
                      a.stage_label,
                      a.school_tier,
                      a.school_tier_label,
                      r.reviewer,
                      r.interest,
                      r.review_status,
                      r.note,
                      r.updated_at,
                      coalesce(o.is_active, 0) as outreach_active,
                      o.status as outreach_status,
                      o.response_status as outreach_response_status,
                      o.stage as outreach_stage,
                      o.next_action as outreach_next_action
                    from advisors a
                    """
                    + latest_review_join_sql()
                    + """
                    left join outreach_targets o on o.advisor_id = a.id
                    """
                    + where
                    + f" order by {advisor_default_order_sql()} limit ? offset ?",
                    params + [limit, offset],
                ).fetchall()
                advisor_ids = [row["id"] for row in rows]
                contacts_by_id = advisor_contacts_map(conn, advisor_ids)
                items = [row_to_advisor_list_item(row, contacts_by_id.get(row["id"], [])) for row in rows]
                return json_response(
                    self,
                    {
                        "total": total,
                        "items": items,
                        "limit": limit,
                        "offset": offset,
                        "hasMore": offset + len(items) < total,
                        "view": "list",
                    },
                )
            rows = conn.execute(
                """
                select
                  a.raw_json,
                  r.reviewer,
                  r.interest,
                  r.review_status,
                  r.note,
                  r.updated_at,
                  coalesce(o.is_active, 0) as outreach_active,
                  o.status as outreach_status,
                  o.response_status as outreach_response_status,
                  o.stage as outreach_stage,
                  o.next_action as outreach_next_action
                from advisors a
                """
                + latest_review_join_sql()
                + """
                left join outreach_targets o on o.advisor_id = a.id
                """
                + where
                + f" order by {advisor_default_order_sql()} limit ? offset ?",
                params + [limit, offset],
            ).fetchall()
            items = [row_to_advisor(row) for row in rows]
            contacts_by_id = advisor_contacts_map(conn, [item["id"] for item in items])
            for item in items:
                attach_contacts(item, contacts_by_id.get(item["id"], []))
        json_response(
            self,
            {
                "total": total,
                "items": items,
                "limit": limit,
                "offset": offset,
                "hasMore": offset + len(items) < total,
                "view": "full",
            },
        )

    def handle_advisor(self, advisor_id: str, query: dict[str, list[str]]) -> None:
        reviewer = self.current_session_user()
        if not reviewer:
            return unauthorized(self)
        with connect() as conn:
            row = conn.execute(
                """
                select
                  a.raw_json,
                  r.reviewer,
                  r.interest,
                  r.review_status,
                  r.note,
                  r.updated_at,
                  coalesce(o.is_active, 0) as outreach_active,
                  o.status as outreach_status,
                  o.response_status as outreach_response_status,
                  o.stage as outreach_stage,
                  o.next_action as outreach_next_action
                from advisors a
                """
                + latest_review_join_sql()
                + """
                left join outreach_targets o on o.advisor_id = a.id
                where a.id = ?
                """,
                (advisor_id,),
            ).fetchone()
            contacts = advisor_contacts(conn, advisor_id) if row else []
        if not row:
            return not_found(self)
        json_response(self, row_to_advisor(row, contacts))

    def handle_save_review(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        advisor_id = str(payload.get("advisorId", "")).strip()
        reviewer = self.current_session_user()
        if not reviewer:
            return unauthorized(self)
        if not advisor_id:
            return json_response(self, {"error": "advisorId_required"}, HTTPStatus.BAD_REQUEST)
        raw_fields = payload.get("fields")
        patch_fields: set[str] | None = None
        if raw_fields is not None:
            if not isinstance(raw_fields, list) or not all(isinstance(field, str) for field in raw_fields):
                return json_response(self, {"error": "unsupported_review_fields"}, HTTPStatus.BAD_REQUEST)
            allowed_fields = {"interest", "queryStatus", "reviewStatus", "note"}
            requested = {field for field in raw_fields}
            if not requested or any(field not in allowed_fields for field in requested):
                return json_response(self, {"error": "unsupported_review_fields"}, HTTPStatus.BAD_REQUEST)
            patch_fields = set(requested)
            if "reviewStatus" in patch_fields:
                patch_fields.add("queryStatus")
        with advisor_review_lock(advisor_id):
            with connect() as conn:
                exists = conn.execute("select 1 from advisors where id = ?", (advisor_id,)).fetchone()
                if not exists:
                    return not_found(self)
                base = latest_advisor_review(conn, advisor_id) if patch_fields is not None else None
                base_interest = normalize_interest_value(base["interest"] or "") if base else ""
                base_query_status = normalize_query_status_value(base["review_status"] or "") if base else ""
                interest = base_interest or ""
                query_status = base_query_status or ""
                note = (base["note"] or "") if base else ""
                if patch_fields is None:
                    interest = normalize_interest_value(str(payload.get("interest") or ""))
                    if interest is None:
                        return json_response(self, {"error": "unsupported_interest"}, HTTPStatus.BAD_REQUEST)
                    query_status = normalize_query_status_value(str(payload.get("queryStatus") or payload.get("reviewStatus") or ""))
                    if query_status is None:
                        return json_response(self, {"error": "unsupported_query_status"}, HTTPStatus.BAD_REQUEST)
                    note = str(payload.get("note") or "")
                elif "interest" in patch_fields:
                    interest = normalize_interest_value(str(payload.get("interest") or ""))
                    if interest is None:
                        return json_response(self, {"error": "unsupported_interest"}, HTTPStatus.BAD_REQUEST)
                if patch_fields is not None and "queryStatus" in patch_fields:
                    query_status = normalize_query_status_value(str(payload.get("queryStatus") or payload.get("reviewStatus") or ""))
                    if query_status is None:
                        return json_response(self, {"error": "unsupported_query_status"}, HTTPStatus.BAD_REQUEST)
                if patch_fields is not None and "note" in patch_fields:
                    note = str(payload.get("note") or "")
                now = utc_now()
                upsert_advisor_review(
                    conn,
                    (
                        advisor_id,
                        reviewer,
                        interest,
                        query_status,
                        note,
                        now,
                    ),
                )
        json_response(
            self,
            {
                "ok": True,
                "updatedAt": now,
                "review": {
                    "interest": interest,
                    "queryStatus": query_status,
                    "reviewStatus": query_status,
                    "note": note,
                    "reviewer": reviewer,
                    "updatedAt": now,
                },
            },
        )

    def handle_advisor_contacts(self, advisor_id: str) -> None:
        with connect() as conn:
            exists = conn.execute("select 1 from advisors where id = ?", (advisor_id,)).fetchone()
            if not exists:
                return not_found(self)
            contacts = advisor_contacts(conn, advisor_id)
        json_response(self, {"items": contacts, **contact_summary(contacts)})

    def handle_save_advisor_contact(self, advisor_id: str) -> None:
        payload = self.read_json_payload()
        user = self.current_session_user() or ""
        contact_id_raw = payload.get("id", "")
        contact_id: int | None = None
        if contact_id_raw not in {"", None}:
            try:
                contact_id = int(contact_id_raw)
            except (TypeError, ValueError):
                return json_response(self, {"error": "invalid_contact_id"}, HTTPStatus.BAD_REQUEST)
        contact_type = clean_text(payload.get("contactType", ""), 40) or "导师邮箱"
        source_url = clean_text(payload.get("sourceUrl", ""), 800)
        evidence_text = clean_text(payload.get("evidenceText", ""), 3000)
        confidence = clean_text(payload.get("confidence", ""), 20) or "待确认"
        is_primary = 1 if bool(payload.get("isPrimary")) else 0
        if contact_type not in CONTACT_TYPES:
            return json_response(self, {"error": "unsupported_contact_type"}, HTTPStatus.BAD_REQUEST)
        contact_value = normalize_contact_value(contact_type, payload.get("value", ""))
        if confidence not in CONTACT_CONFIDENCES:
            return json_response(self, {"error": "unsupported_contact_confidence"}, HTTPStatus.BAD_REQUEST)
        if not contact_value:
            return json_response(self, {"error": "contact_value_required"}, HTTPStatus.BAD_REQUEST)
        now = utc_now()
        try:
            with connect() as conn:
                exists = conn.execute("select 1 from advisors where id = ?", (advisor_id,)).fetchone()
                if not exists:
                    return not_found(self)
                if contact_id is not None:
                    existing = conn.execute(
                        "select id from advisor_contacts where id = ? and advisor_id = ?",
                        (contact_id, advisor_id),
                    ).fetchone()
                    if not existing:
                        return not_found(self)
                    duplicate = conn.execute(
                        """
                        select id
                        from advisor_contacts
                        where advisor_id = ? and contact_value = ? and id <> ?
                        """,
                        (advisor_id, contact_value, contact_id),
                    ).fetchone()
                    if duplicate:
                        return json_response(self, {"error": "contact_value_exists"}, HTTPStatus.CONFLICT)
                    if is_primary:
                        conn.execute("update advisor_contacts set is_primary = 0 where advisor_id = ?", (advisor_id,))
                    conn.execute(
                        """
                        update advisor_contacts
                        set contact_type = ?, contact_value = ?, source_url = ?, evidence_text = ?,
                            confidence = ?, is_primary = ?, updated_by = ?, updated_at = ?
                        where id = ? and advisor_id = ?
                        """,
                        (
                            contact_type,
                            contact_value,
                            source_url,
                            evidence_text,
                            confidence,
                            is_primary,
                            user,
                            now,
                            contact_id,
                            advisor_id,
                        ),
                    )
                    row_id = contact_id
                else:
                    existing = conn.execute(
                        "select id from advisor_contacts where advisor_id = ? and contact_value = ?",
                        (advisor_id, contact_value),
                    ).fetchone()
                    if is_primary:
                        conn.execute("update advisor_contacts set is_primary = 0 where advisor_id = ?", (advisor_id,))
                    if existing:
                        row_id = int(existing["id"])
                        conn.execute(
                            """
                            update advisor_contacts
                            set contact_type = ?, source_url = ?, evidence_text = ?, confidence = ?,
                                is_primary = ?, updated_by = ?, updated_at = ?
                            where id = ? and advisor_id = ?
                            """,
                            (contact_type, source_url, evidence_text, confidence, is_primary, user, now, row_id, advisor_id),
                        )
                    else:
                        cursor = conn.execute(
                            """
                            insert into advisor_contacts (
                              advisor_id, contact_type, contact_value, source_url, evidence_text,
                              confidence, is_primary, created_by, updated_by, created_at, updated_at
                            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                advisor_id,
                                contact_type,
                                contact_value,
                                source_url,
                                evidence_text,
                                confidence,
                                is_primary,
                                user,
                                user,
                                now,
                                now,
                            ),
                        )
                        row_id = int(cursor.lastrowid)
                sync_advisor_contact_primary(conn, advisor_id)
                contact = conn.execute("select * from advisor_contacts where id = ?", (row_id,)).fetchone()
                contacts = advisor_contacts(conn, advisor_id)
        except Exception as error:
            if is_integrity_error(error):
                return json_response(self, {"error": "contact_conflict"}, HTTPStatus.CONFLICT)
            raise
        json_response(self, {"ok": True, "item": contact_row_to_payload(contact), "contacts": contacts, **contact_summary(contacts)})

    def handle_delete_advisor_contact(self, advisor_id: str, contact_id: str) -> None:
        try:
            row_id = int(contact_id)
        except ValueError:
            return not_found(self)
        with connect() as conn:
            exists = conn.execute("select 1 from advisor_contacts where id = ? and advisor_id = ?", (row_id, advisor_id)).fetchone()
            if not exists:
                return not_found(self)
            conn.execute("delete from advisor_contacts where id = ? and advisor_id = ?", (row_id, advisor_id))
            sync_advisor_contact_primary(conn, advisor_id)
            contacts = advisor_contacts(conn, advisor_id)
        json_response(self, {"ok": True, "contacts": contacts, **contact_summary(contacts)})

    def read_json_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def handle_ai_settings(self) -> None:
        with connect() as conn:
            ensure_ai_settings_row(conn)
            row = conn.execute("select * from ai_settings where id = 1").fetchone()
        json_response(self, ai_settings_to_payload(row))

    def handle_save_ai_settings(self) -> None:
        payload = self.read_json_payload()
        user = self.current_session_user() or ""
        enabled = 1 if bool(payload.get("enabled")) else 0
        provider_name = clean_text(payload.get("providerName", ""), 120)
        endpoint_url = clean_text(payload.get("endpointUrl", ""), 500)
        model_name = clean_text(payload.get("modelName", ""), 160)
        temperature_raw = payload.get("temperature", "")
        if str(temperature_raw or "").strip() == "":
            temperature = None
        else:
            try:
                temperature = min(max(float(temperature_raw), 0), 2)
            except (TypeError, ValueError):
                return json_response(self, {"error": "invalid_temperature"}, HTTPStatus.BAD_REQUEST)
        api_key = str(payload.get("apiKey", "") or "").strip()
        clear_key = bool(payload.get("clearApiKey"))
        tools_enabled = 1 if bool(payload.get("toolsEnabled")) else 0
        allow_search_pages = 1 if bool(payload.get("allowSearchPages")) else 0
        try:
            tool_max_results = max(1, min(int(payload.get("toolMaxResults", DEFAULT_AI_TOOL_MAX_RESULTS)), 8))
            tool_timeout_seconds = max(3, min(int(payload.get("toolTimeoutSeconds", DEFAULT_AI_TOOL_TIMEOUT_SECONDS)), 20))
            tool_cache_ttl_seconds = max(300, min(int(payload.get("toolCacheTtlSeconds", DEFAULT_AI_TOOL_CACHE_TTL_SECONDS)), 7 * 24 * 60 * 60))
        except (TypeError, ValueError):
            return json_response(self, {"error": "invalid_ai_tool_settings"}, HTTPStatus.BAD_REQUEST)
        now = utc_now()
        with connect() as conn:
            ensure_ai_settings_row(conn)
            row = conn.execute("select * from ai_settings where id = 1").fetchone()
            env_key_present = bool(os.environ.get(AI_API_KEY_ENV, "").strip())
            db_key_allowed = database_ai_key_allowed()
            if env_key_present:
                next_key = ""
            elif not db_key_allowed:
                if api_key:
                    return json_response(
                        self,
                        {"error": "database_ai_key_disabled", "message": "当前环境不允许把 AI API Key 保存到数据库，请改用 PHD_PLATFORM_AI_API_KEY 环境变量。"},
                        HTTPStatus.BAD_REQUEST,
                    )
                next_key = ""
            else:
                next_key = "" if clear_key else (api_key if api_key else row["api_key"])
            conn.execute(
                """
                update ai_settings
                set enabled = ?, provider_name = ?, endpoint_url = ?, model_name = ?,
                    api_key = ?, temperature = ?, tools_enabled = ?, allow_search_pages = ?,
                    tool_max_results = ?, tool_timeout_seconds = ?, tool_cache_ttl_seconds = ?,
                    updated_by = ?, updated_at = ?
                where id = 1
                """,
                (
                    enabled,
                    provider_name,
                    endpoint_url,
                    model_name,
                    next_key,
                    temperature,
                    tools_enabled,
                    allow_search_pages,
                    tool_max_results,
                    tool_timeout_seconds,
                    tool_cache_ttl_seconds,
                    user,
                    now,
                ),
            )
            row = conn.execute("select * from ai_settings where id = 1").fetchone()
        json_response(self, {"ok": True, "settings": ai_settings_to_payload(row)})

    def handle_test_ai_settings(self) -> None:
        with connect() as conn:
            ensure_ai_settings_row(conn)
            settings = conn.execute("select * from ai_settings where id = 1").fetchone()
        if not settings or not ai_settings_to_payload(settings)["available"]:
            return json_response(self, {"error": "ai_not_configured"}, HTTPStatus.BAD_REQUEST)
        try:
            endpoint = normalize_ai_endpoint(settings["endpoint_url"] or "")
            answer = call_chat_completion(
                settings,
                [
                    {"role": "system", "content": "你是 API 连通性测试助手。请只用一句中文回复。"},
                    {"role": "user", "content": "请回复：连接正常"},
                ],
            )
        except RuntimeError as error:
            return json_response(self, {"error": "ai_call_failed", "message": str(error)}, HTTPStatus.BAD_GATEWAY)
        json_response(
            self,
            {
                "ok": True,
                "providerName": settings["provider_name"] or "",
                "modelName": settings["model_name"] or "",
                "endpointUrl": endpoint,
                "message": answer[:500],
            },
        )

    def handle_ai_conversations(self, query: dict[str, list[str]]) -> None:
        advisor_id = (query.get("advisorId", [""])[0] or "").strip()
        params: list[str] = []
        where = ""
        if advisor_id:
            where = " where advisor_id = ?"
            params.append(advisor_id)
        with connect() as conn:
            rows = conn.execute(
                "select * from ai_conversations"
                + where
                + " order by updated_at desc, id desc limit 80",
                params,
            ).fetchall()
        json_response(self, {"items": [ai_conversation_to_payload(row) for row in rows]})

    def handle_ai_conversation(self, conversation_id: str) -> None:
        try:
            row_id = int(conversation_id)
        except ValueError:
            return not_found(self)
        with connect() as conn:
            row = conn.execute("select * from ai_conversations where id = ?", (row_id,)).fetchone()
            if not row:
                return not_found(self)
            messages = conn.execute(
                "select * from ai_messages where conversation_id = ? order by id",
                (row_id,),
            ).fetchall()
        json_response(self, ai_conversation_to_payload(row, messages))

    def handle_create_advisor_ai_conversation(self, advisor_id: str) -> None:
        user = self.current_session_user() or ""
        with connect() as conn:
            settings = conn.execute("select * from ai_settings where id = 1").fetchone()
            if not settings or not ai_settings_to_payload(settings)["available"]:
                return json_response(self, {"error": "ai_not_configured"}, HTTPStatus.BAD_REQUEST)
            advisor = conn.execute("select id, raw_json from advisors where id = ?", (advisor_id,)).fetchone()
            if not advisor:
                return not_found(self)
            title, context = advisor_context_for_ai(advisor, latest_cv_context(conn))
            messages = initial_advisor_ai_messages(context)
            now = utc_now()
            cursor = conn.execute(
                """
                insert into ai_conversations (
                  advisor_id, title, system_context, created_by, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?)
                """,
                (advisor_id, title, context, user, now, now),
            )
            conversation_id = cursor.lastrowid
            try:
                answer = call_chat_completion(settings, messages, max_tokens=AI_INITIAL_MAX_TOKENS)
            except RuntimeError as error:
                conn.execute("delete from ai_conversations where id = ?", (conversation_id,))
                return json_response(self, {"error": "ai_call_failed", "message": str(error)}, HTTPStatus.BAD_GATEWAY)
            now = utc_now()
            conn.execute(
                "insert into ai_messages (conversation_id, role, content, created_by, created_at) values (?, ?, ?, ?, ?)",
                (conversation_id, "assistant", answer, "AI", now),
            )
            conn.execute("update ai_conversations set updated_at = ? where id = ?", (now, conversation_id))
            row = conn.execute("select * from ai_conversations where id = ?", (conversation_id,)).fetchone()
            stored_messages = conn.execute(
                "select * from ai_messages where conversation_id = ? order by id",
                (conversation_id,),
            ).fetchall()
        json_response(self, {"ok": True, "conversation": ai_conversation_to_payload(row, stored_messages)})

    def handle_add_ai_message(self, conversation_id: str) -> None:
        payload = self.read_json_payload()
        user_content = clean_text(payload.get("content", ""), 8000)
        if not user_content:
            return json_response(self, {"error": "content_required"}, HTTPStatus.BAD_REQUEST)
        client_created_at = clean_text(payload.get("clientCreatedAt", ""), 40)
        user = self.current_session_user() or ""
        try:
            row_id = int(conversation_id)
        except ValueError:
            return not_found(self)
        with connect() as conn:
            settings = conn.execute("select * from ai_settings where id = 1").fetchone()
            if not settings or not ai_settings_to_payload(settings)["available"]:
                return json_response(self, {"error": "ai_not_configured"}, HTTPStatus.BAD_REQUEST)
            conversation = conn.execute("select * from ai_conversations where id = ?", (row_id,)).fetchone()
            if not conversation:
                return not_found(self)
            context = conversation["system_context"]
            advisor = conn.execute(
                "select id, raw_json from advisors where id = ?",
                (conversation["advisor_id"],),
            ).fetchone()
            if advisor:
                _title, context = advisor_context_for_ai(advisor, latest_cv_context(conn))
            existing = conn.execute(
                "select role, content from ai_messages where conversation_id = ? order by id",
                (row_id,),
            ).fetchall()
        tool_context = run_ai_tools(settings, user_content, load_ai_advisor_context(context))
        recent_messages = existing[-AI_HISTORY_MESSAGE_LIMIT:]
        messages = [
            {
                "role": "system",
                "content": advisor_ai_system_message(context),
            }
        ]
        if tool_context:
            messages.append({"role": "system", "content": "平台工具查询结果：\n" + tool_context})
        messages.extend({"role": row["role"], "content": row["content"]} for row in recent_messages)
        messages.append({"role": "user", "content": user_content})
        try:
            answer = call_chat_completion(settings, messages, max_tokens=AI_FOLLOWUP_MAX_TOKENS)
        except RuntimeError as error:
            return json_response(self, {"error": "ai_call_failed", "message": str(error)}, HTTPStatus.BAD_GATEWAY)
        now = utc_now()
        user_created_at = client_created_at or now
        with connect() as conn:
            conversation = conn.execute("select * from ai_conversations where id = ?", (row_id,)).fetchone()
            if not conversation:
                return not_found(self)
            conn.execute("update ai_conversations set system_context = ? where id = ?", (context, row_id))
            conn.execute(
                "insert into ai_messages (conversation_id, role, content, created_by, created_at) values (?, 'user', ?, ?, ?)",
                (row_id, user_content, user, user_created_at),
            )
            conn.execute(
                "insert into ai_messages (conversation_id, role, content, created_by, created_at) values (?, 'assistant', ?, ?, ?)",
                (row_id, answer, "AI", now),
            )
            conn.execute("update ai_conversations set updated_at = ? where id = ?", (now, row_id))
            row = conn.execute("select * from ai_conversations where id = ?", (row_id,)).fetchone()
            stored_messages = conn.execute(
                "select * from ai_messages where conversation_id = ? order by id",
                (row_id,),
            ).fetchall()
        json_response(self, {"ok": True, "conversation": ai_conversation_to_payload(row, stored_messages)})

    def handle_outreach_list(self, query: dict[str, list[str]]) -> None:
        clauses = ["o.is_active = 1"]
        params: list[str] = []
        search = (query.get("search", [""])[0] or "").strip().lower()
        if search:
            like = f"%{search}%"
            clauses.append(
                "(lower(a.name) like ? or lower(a.institution) like ? or lower(a.institution_zh) like ? "
                "or lower(a.category) like ? or lower(o.tags) like ? or lower(o.notes) like ?)"
            )
            params.extend([like, like, like, like, like, like])
        for key, column in [
            ("advisorStage", "a.stage_key"),
            ("tier", "a.school_tier"),
            ("category", "a.category"),
            ("status", "o.status"),
            ("response", "o.response_status"),
            ("stage", "o.stage"),
            ("priority", "o.priority"),
        ]:
            values = [value.strip() for value in query.get(key, []) if value.strip()]
            alias_map = OUTREACH_FILTER_ALIASES.get(key, {})
            values = [alias for value in values for alias in alias_map.get(value, [value])]
            if values:
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{column} in ({placeholders})")
                params.extend(values)
        tag = (query.get("tag", [""])[0] or "").strip().lower()
        if tag:
            clauses.append("lower(o.tags) like ?")
            params.append(f"%{tag}%")
        where = " where " + " and ".join(clauses)
        with connect() as conn:
            rows = conn.execute(
                """
                select o.*, a.raw_json
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                """
                + where
                + """
                order by
                  case o.priority when '高' then 0 when '中' then 1 when '低' then 2 else 3 end,
                  case o.status
                    when '已回复' then 0
                    when '已发送' then 1
                    when '待联系' then 2
                    when '准备中' then 3
                    when '需跟进' then 4
                    else 5
                  end,
                  o.updated_at desc
                """,
                params,
            ).fetchall()
            status_rows = conn.execute(
                "select status as value, status as label, count(*) as count from outreach_targets where is_active = 1 group by status"
            ).fetchall()
            response_rows = conn.execute(
                "select response_status as value, response_status as label, count(*) as count from outreach_targets where is_active = 1 group by response_status"
            ).fetchall()
            stage_rows = conn.execute(
                "select stage as value, stage as label, count(*) as count from outreach_targets where is_active = 1 group by stage"
            ).fetchall()
            advisor_stage_rows = conn.execute(
                """
                select a.stage_key as value, a.stage_label as label, count(*) as count
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                where o.is_active = 1 and a.stage_key != ''
                group by a.stage_key, a.stage_label
                order by count desc
                """
            ).fetchall()
            tier_rows = conn.execute(
                """
                select a.school_tier as value, a.school_tier_label as label, count(*) as count
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                where o.is_active = 1 and a.school_tier != ''
                group by a.school_tier, a.school_tier_label
                order by count desc
                """
            ).fetchall()
            category_rows = conn.execute(
                """
                select a.category as value, a.category as label, count(*) as count
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                where o.is_active = 1 and a.category != ''
                group by a.category
                """
                + f" order by {advisor_category_order_sql('a.category')}"
            ).fetchall()
            contacts_by_id = advisor_contacts_map(conn, [row["advisor_id"] for row in rows])
            items = [outreach_row_to_payload(row, contacts=contacts_by_id.get(row["advisor_id"], [])) for row in rows]
        json_response(
            self,
            {
                "items": items,
                "filters": {
                    "advisorStages": [dict(row) for row in advisor_stage_rows],
                    "tiers": [dict(row) for row in tier_rows],
                    "categories": [dict(row) for row in category_rows],
                    "statuses": [dict(row) for row in status_rows],
                    "responses": [dict(row) for row in response_rows],
                    "stages": [dict(row) for row in stage_rows],
                },
            },
        )

    def handle_outreach_detail(self, advisor_id: str) -> None:
        with connect() as conn:
            row = conn.execute(
                """
                select o.*, a.raw_json
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                where o.advisor_id = ?
                """,
                (advisor_id,),
            ).fetchone()
            if not row:
                return not_found(self)
            events = conn.execute(
                "select * from outreach_events where advisor_id = ? order by event_at desc, id desc",
                (advisor_id,),
            ).fetchall()
            contacts = advisor_contacts(conn, advisor_id)
        json_response(self, outreach_row_to_payload(row, events, contacts))

    def handle_toggle_outreach(self) -> None:
        payload = self.read_json_payload()
        advisor_id = clean_text(payload.get("advisorId", ""), 120)
        active_value = payload.get("active")
        user = self.current_session_user() or ""
        if not advisor_id:
            return json_response(self, {"error": "advisorId_required"}, HTTPStatus.BAD_REQUEST)
        now = utc_now()
        with connect() as conn:
            advisor = conn.execute("select 1 from advisors where id = ?", (advisor_id,)).fetchone()
            if not advisor:
                return not_found(self)
            current = conn.execute("select * from outreach_targets where advisor_id = ?", (advisor_id,)).fetchone()
            activate = (not bool(current["is_active"])) if active_value is None and current else True
            if isinstance(active_value, bool):
                activate = active_value
            if activate:
                if current:
                    conn.execute(
                        """
                        update outreach_targets
                        set is_active = 1,
                            status = case when status = '已取消' then '待联系' else status end,
                            stage = case when stage = '' then '跟进中' else stage end,
                            response_status = case when response_status = '' then '待回复' else response_status end,
                            updated_by = ?, updated_at = ?
                        where advisor_id = ?
                        """,
                        (user, now, advisor_id),
                    )
                else:
                    conn.execute(
                        """
                        insert into outreach_targets (
                          advisor_id, is_active, status, response_status, stage,
                          created_by, updated_by, created_at, updated_at
                        ) values (?, 1, '待联系', '待回复', '跟进中', ?, ?, ?, ?)
                        """,
                        (advisor_id, user, user, now, now),
                    )
            else:
                if current:
                    conn.execute(
                        """
                        update outreach_targets
                        set is_active = 0, status = '已取消', updated_by = ?, updated_at = ?
                        where advisor_id = ?
                        """,
                        (user, now, advisor_id),
                    )
                else:
                    conn.execute(
                        """
                        insert into outreach_targets (
                          advisor_id, is_active, status, response_status, stage,
                          created_by, updated_by, created_at, updated_at
                        ) values (?, 0, '已取消', '待回复', '跟进中', ?, ?, ?, ?)
                        """,
                        (advisor_id, user, user, now, now),
                    )
            row = conn.execute(
                """
                select o.*, a.raw_json
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                where o.advisor_id = ?
                """,
                (advisor_id,),
            ).fetchone()
            contacts = advisor_contacts(conn, advisor_id)
        json_response(self, {"ok": True, "item": outreach_row_to_payload(row, contacts=contacts)})

    def handle_update_outreach(self, advisor_id: str) -> None:
        payload = self.read_json_payload()
        user = self.current_session_user() or ""
        raw_fields = payload.get("fields")
        patch_fields: set[str] | None = None
        if raw_fields is not None:
            allowed_fields = {
                "status",
                "responseStatus",
                "stage",
                "priority",
                "tags",
                "lastContactAt",
                "nextActionAt",
                "nextAction",
                "notes",
            }
            if not isinstance(raw_fields, list) or not all(isinstance(field, str) for field in raw_fields):
                return json_response(self, {"error": "unsupported_outreach_fields"}, HTTPStatus.BAD_REQUEST)
            requested = {field for field in raw_fields}
            if not requested or any(field not in allowed_fields for field in requested):
                return json_response(self, {"error": "unsupported_outreach_fields"}, HTTPStatus.BAD_REQUEST)
            patch_fields = requested
        now = utc_now()
        with connect() as conn:
            advisor = conn.execute("select 1 from advisors where id = ?", (advisor_id,)).fetchone()
            if not advisor:
                return not_found(self)
            current = conn.execute("select * from outreach_targets where advisor_id = ?", (advisor_id,)).fetchone()
            if not current:
                conn.execute(
                    """
                    insert into outreach_targets (
                      advisor_id, created_by, updated_by, created_at, updated_at
                    ) values (?, ?, ?, ?, ?)
                    """,
                    (advisor_id, user, user, now, now),
                )
                current = conn.execute("select * from outreach_targets where advisor_id = ?", (advisor_id,)).fetchone()
            status = current["status"] or "待联系"
            response_status = current["response_status"] or "待回复"
            stage = current["stage"] or "跟进中"
            priority = current["priority"] or ""
            tags = current["tags"] or ""
            last_contact_at = current["last_contact_at"] or ""
            next_action_at = current["next_action_at"] or ""
            next_action = current["next_action"] or ""
            notes = current["notes"] or ""
            if patch_fields is None or "status" in patch_fields:
                status = clean_text(payload.get("status", ""), 20) or "待联系"
            if patch_fields is None or "responseStatus" in patch_fields:
                response_status = clean_text(payload.get("responseStatus", ""), 20) or "待回复"
            if patch_fields is None or "stage" in patch_fields:
                stage = clean_text(payload.get("stage", ""), 20) or "跟进中"
            if patch_fields is None or "priority" in patch_fields:
                priority = clean_text(payload.get("priority", ""), 10)
            if status not in OUTREACH_STATUSES:
                return json_response(self, {"error": "unsupported_outreach_status"}, HTTPStatus.BAD_REQUEST)
            if response_status not in OUTREACH_RESPONSE_STATUSES:
                return json_response(self, {"error": "unsupported_response_status"}, HTTPStatus.BAD_REQUEST)
            if stage not in OUTREACH_STAGES:
                return json_response(self, {"error": "unsupported_outreach_stage"}, HTTPStatus.BAD_REQUEST)
            if priority not in OUTREACH_PRIORITIES:
                return json_response(self, {"error": "unsupported_priority"}, HTTPStatus.BAD_REQUEST)
            if patch_fields is None or "tags" in patch_fields:
                tags = clean_text(payload.get("tags", ""), 500)
            if patch_fields is None or "lastContactAt" in patch_fields:
                last_contact_at = normalize_date_text(payload.get("lastContactAt", ""))
            if patch_fields is None or "nextActionAt" in patch_fields:
                next_action_at = normalize_date_text(payload.get("nextActionAt", ""))
            if patch_fields is None or "nextAction" in patch_fields:
                next_action = clean_text(payload.get("nextAction", ""), 1000)
            if patch_fields is None or "notes" in patch_fields:
                notes = clean_text(payload.get("notes", ""), 4000)
            conn.execute(
                """
                update outreach_targets
                set is_active = ?, status = ?, response_status = ?, stage = ?, priority = ?,
                    tags = ?, last_contact_at = ?, next_action_at = ?, next_action = ?,
                    notes = ?, updated_by = ?, updated_at = ?
                where advisor_id = ?
                """,
                (
                    1,
                    status,
                    response_status,
                    stage,
                    priority,
                    tags,
                    last_contact_at,
                    next_action_at,
                    next_action,
                    notes,
                    user,
                    now,
                    advisor_id,
                ),
            )
            row = conn.execute(
                """
                select o.*, a.raw_json
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                where o.advisor_id = ?
                """,
                (advisor_id,),
            ).fetchone()
            contacts = advisor_contacts(conn, advisor_id)
        json_response(self, {"ok": True, "item": outreach_row_to_payload(row, contacts=contacts)})

    def handle_add_outreach_event(self, advisor_id: str) -> None:
        payload = self.read_json_payload()
        event_type = clean_text(payload.get("eventType", ""), 20) or "备注"
        if event_type not in OUTREACH_EVENT_TYPES:
            return json_response(self, {"error": "unsupported_event_type"}, HTTPStatus.BAD_REQUEST)
        user = self.current_session_user() or ""
        event_at = normalize_date_text(payload.get("eventAt", "")) or utc_now()
        summary = clean_text(payload.get("summary", ""), 500)
        detail = clean_text(payload.get("detail", ""), 4000)
        now = utc_now()
        with connect() as conn:
            advisor = conn.execute("select 1 from advisors where id = ?", (advisor_id,)).fetchone()
            if not advisor:
                return not_found(self)
            exists = conn.execute("select 1 from outreach_targets where advisor_id = ?", (advisor_id,)).fetchone()
            if not exists:
                conn.execute(
                    """
                    insert into outreach_targets (
                      advisor_id, is_active, status, response_status, stage,
                      created_by, updated_by, created_at, updated_at
                    ) values (?, 1, '待联系', '待回复', '跟进中', ?, ?, ?, ?)
                    """,
                    (advisor_id, user, user, now, now),
                )
            conn.execute(
                """
                insert into outreach_events (
                  advisor_id, event_type, event_at, summary, detail, created_by, created_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (advisor_id, event_type, event_at, summary, detail, user, now),
            )
            inferred = {
                "已发送邮件": ("已发送", "待回复", "跟进中", event_at),
                "收到回复": ("已回复", "中性", "跟进中", ""),
                "跟进": ("已发送", "待回复", "跟进中", event_at),
                "面试": ("已回复", "积极", "已面试", ""),
                "申请": ("已回复", "积极", "已申请", ""),
            }.get(event_type)
            if inferred:
                status, response_status, stage, last_contact_at = inferred
                last_contact_sql = ", last_contact_at = ?" if last_contact_at else ""
                params: list = [status, response_status, stage, user, now]
                if last_contact_at:
                    params.insert(3, last_contact_at)
                params.append(advisor_id)
                conn.execute(
                    f"""
                    update outreach_targets
                    set is_active = 1, status = ?, response_status = ?, stage = ?{last_contact_sql},
                        updated_by = ?, updated_at = ?
                    where advisor_id = ?
                    """,
                    params,
                )
            else:
                conn.execute(
                    "update outreach_targets set is_active = 1, updated_by = ?, updated_at = ? where advisor_id = ?",
                    (user, now, advisor_id),
                )
            row = conn.execute(
                """
                select o.*, a.raw_json
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                where o.advisor_id = ?
                """,
                (advisor_id,),
            ).fetchone()
            events = conn.execute(
                "select * from outreach_events where advisor_id = ? order by event_at desc, id desc",
                (advisor_id,),
            ).fetchall()
            contacts = advisor_contacts(conn, advisor_id)
        json_response(self, {"ok": True, "item": outreach_row_to_payload(row, events, contacts)})

    def handle_delete_outreach_event(self, advisor_id: str, event_id: str) -> None:
        try:
            row_id = int(event_id)
        except ValueError:
            return not_found(self)
        with connect() as conn:
            event = conn.execute(
                "select 1 from outreach_events where id = ? and advisor_id = ?",
                (row_id, advisor_id),
            ).fetchone()
            if not event:
                return not_found(self)
            conn.execute("delete from outreach_events where id = ? and advisor_id = ?", (row_id, advisor_id))
            row = conn.execute(
                """
                select o.*, a.raw_json
                from outreach_targets o
                join advisors a on a.id = o.advisor_id
                where o.advisor_id = ?
                """,
                (advisor_id,),
            ).fetchone()
            if not row:
                return not_found(self)
            events = conn.execute(
                "select * from outreach_events where advisor_id = ? order by event_at desc, id desc",
                (advisor_id,),
            ).fetchall()
            contacts = advisor_contacts(conn, advisor_id)
        json_response(self, {"ok": True, "item": outreach_row_to_payload(row, events, contacts)})

    def handle_deactivate_outreach(self, advisor_id: str) -> None:
        user = self.current_session_user() or ""
        now = utc_now()
        with connect() as conn:
            row = conn.execute("select 1 from outreach_targets where advisor_id = ?", (advisor_id,)).fetchone()
            if not row:
                return not_found(self)
            conn.execute(
                """
                update outreach_targets
                set is_active = 0, status = '已取消', updated_by = ?, updated_at = ?
                where advisor_id = ?
                """,
                (user, now, advisor_id),
            )
        json_response(self, {"ok": True})

    def handle_programs(self, query: dict[str, list[str]]) -> None:
        clauses: list[str] = []
        params: list[str] = []
        search = (query.get("search", [""])[0] or "").strip().lower()
        if search:
            like = f"%{search}%"
            clauses.append("(lower(school) like ? or lower(department) like ? or lower(program_name) like ? or lower(notes) like ?)")
            params.extend([like, like, like, like])
        for key, column in [("status", "status"), ("priority", "priority")]:
            values = [value.strip() for value in query.get(key, []) if value.strip()]
            if values:
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{column} in ({placeholders})")
                params.extend(values)
        where = " where " + " and ".join(clauses) if clauses else ""
        with connect() as conn:
            rows = conn.execute(
                "select * from application_programs"
                + where
                + """
                order by
                  case priority when '高' then 0 when '中' then 1 when '低' then 2 else 3 end,
                  case when deadline = '' then 1 else 0 end,
                  deadline,
                  updated_at desc
                """,
                params,
            ).fetchall()
        json_response(self, {"items": [program_row_to_payload(row) for row in rows]})

    def handle_save_program(self, program_id: str | None = None) -> None:
        payload = self.read_json_payload()
        user = self.current_session_user() or ""
        school = clean_text(payload.get("school", ""), 240)
        program_name = clean_text(payload.get("programName", ""), 240)
        if not school or not program_name:
            return json_response(self, {"error": "school_and_program_required"}, HTTPStatus.BAD_REQUEST)
        status = clean_text(payload.get("status", ""), 20) or "候选"
        priority = clean_text(payload.get("priority", ""), 10)
        if status not in PROGRAM_STATUSES:
            return json_response(self, {"error": "unsupported_program_status"}, HTTPStatus.BAD_REQUEST)
        if priority not in PROGRAM_PRIORITIES:
            return json_response(self, {"error": "unsupported_priority"}, HTTPStatus.BAD_REQUEST)
        now = utc_now()
        values = (
            school,
            clean_text(payload.get("department", ""), 240),
            program_name,
            clean_text(payload.get("degree", ""), 40) or "PhD",
            normalize_date_text(payload.get("deadline", "")),
            status,
            priority,
            clean_text(payload.get("requirements", ""), 4000),
            clean_text(payload.get("notes", ""), 4000),
            user,
            now,
        )
        with connect() as conn:
            if program_id:
                try:
                    row_id = int(program_id)
                except ValueError:
                    return not_found(self)
                exists = conn.execute("select 1 from application_programs where id = ?", (row_id,)).fetchone()
                if not exists:
                    return not_found(self)
                conn.execute(
                    """
                    update application_programs
                    set school = ?, department = ?, program_name = ?, degree = ?, deadline = ?,
                        status = ?, priority = ?, requirements = ?, notes = ?,
                        updated_by = ?, updated_at = ?
                    where id = ?
                    """,
                    values + (row_id,),
                )
            else:
                cursor = conn.execute(
                    """
                    insert into application_programs (
                      school, department, program_name, degree, deadline, status,
                      priority, requirements, notes, created_by, updated_by, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values[:9] + (user, user, now, now),
                )
                row_id = cursor.lastrowid
            row = conn.execute("select * from application_programs where id = ?", (row_id,)).fetchone()
        json_response(self, {"ok": True, "item": program_row_to_payload(row)})

    def handle_delete_program(self, program_id: str) -> None:
        try:
            row_id = int(program_id)
        except ValueError:
            return not_found(self)
        with connect() as conn:
            exists = conn.execute("select 1 from application_programs where id = ?", (row_id,)).fetchone()
            if not exists:
                return not_found(self)
            conn.execute("delete from application_programs where id = ?", (row_id,))
        json_response(self, {"ok": True})

    def handle_documents(self, query: dict[str, list[str]]) -> None:
        doc_type = (query.get("type", [""])[0] or "").strip()
        clauses = ["coalesce(file_path, '') != ''"]
        params: list = []
        if doc_type:
            clauses.append("doc_type = ?")
            params.append(doc_type)
        where = " where " + " and ".join(clauses)
        with connect() as conn:
            rows = conn.execute(
                "select * from documents"
                + where
                + " order by case when coalesce(created_at, '') = '' then updated_at else created_at end desc, id desc",
                params,
            ).fetchall()
            types = document_types_payload(conn)
        json_response(self, {"types": types, "items": [document_row_to_payload(row) for row in rows]})

    def handle_upload_document(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return json_response(self, {"error": "multipart_required"}, HTTPStatus.BAD_REQUEST)
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            return json_response(self, {"error": "empty_upload"}, HTTPStatus.BAD_REQUEST)
        if content_length > MAX_DOCUMENT_UPLOAD_BYTES:
            return json_response(self, {"error": "file_too_large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

        fields, files = parse_multipart_form(content_type, self.rfile.read(content_length))
        if "file" not in files:
            return json_response(self, {"error": "file_required"}, HTTPStatus.BAD_REQUEST)
        file_item = files["file"]
        original_filename = safe_filename(file_item.get("filename", ""))
        if not original_filename:
            return json_response(self, {"error": "filename_required"}, HTTPStatus.BAD_REQUEST)

        doc_type = fields.get("docType", "") or "其他"
        if doc_type not in DOCUMENT_TYPE_VALUES:
            return json_response(self, {"error": "unsupported_doc_type"}, HTTPStatus.BAD_REQUEST)

        title = fields.get("title", "") or Path(original_filename).stem or doc_type
        notes = fields.get("notes", "")
        uploader = self.current_session_user() or ""
        now = utc_now()
        suffix = Path(original_filename).suffix.lower()[:24]
        stored_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(8)}{suffix}"
        target = (DOCUMENT_UPLOAD_DIR / stored_filename).resolve()
        if DOCUMENT_UPLOAD_DIR.resolve() not in target.parents:
            return json_response(self, {"error": "invalid_file_path"}, HTTPStatus.BAD_REQUEST)

        target.write_bytes(file_item.get("data", b""))
        file_size = target.stat().st_size
        if file_size == 0:
            target.unlink(missing_ok=True)
            return json_response(self, {"error": "empty_file"}, HTTPStatus.BAD_REQUEST)

        mime_type = document_content_type(original_filename, file_item.get("content_type") or "")
        file_path = str(target.relative_to(DATA_DIR))
        with connect() as conn:
            version_label = next_document_version(conn, doc_type)
            cursor = conn.execute(
                """
                insert into documents (
                  doc_type, title, version_label, status, owner, uploaded_by,
                  original_filename, stored_filename, file_path, file_size,
                  mime_type, created_at, updated_at, notes
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_type,
                    title,
                    version_label,
                    "已上传",
                    uploader,
                    uploader,
                    original_filename,
                    stored_filename,
                    file_path,
                    file_size,
                    mime_type,
                    now,
                    now,
                    notes,
                ),
            )
            row = conn.execute("select * from documents where id = ?", (cursor.lastrowid,)).fetchone()
        json_response(self, {"ok": True, "item": document_row_to_payload(row)})

    def handle_document_file(self, document_id: str) -> None:
        try:
            doc_id = int(document_id)
        except ValueError:
            return not_found(self)
        with connect() as conn:
            row = conn.execute("select * from documents where id = ?", (doc_id,)).fetchone()
        if not row:
            return not_found(self)
        target = resolve_document_file(row["file_path"] or "")
        if not target or not target.exists() or not target.is_file():
            return not_found(self)
        filename = row["original_filename"] or row["title"] or target.name
        content_type = document_content_type(filename, row["mime_type"] or "")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(target.stat().st_size))
        self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        with target.open("rb") as source:
            shutil.copyfileobj(source, self.wfile)

    def handle_document_preview(self, document_id: str) -> None:
        try:
            doc_id = int(document_id)
        except ValueError:
            return not_found(self)
        with connect() as conn:
            row = conn.execute("select * from documents where id = ?", (doc_id,)).fetchone()
        if not row:
            return not_found(self)
        target = resolve_document_file(row["file_path"] or "")
        if not target or not target.exists() or not target.is_file():
            return not_found(self)

        filename = row["original_filename"] or row["title"] or target.name
        title = row["title"] or filename
        content_type = document_content_type(filename, row["mime_type"] or "")
        extension = file_extension(filename)

        if content_type == DOCX_MIME or extension in {"docx", "docm"}:
            return text_response(
                self,
                docx_preview_html(target, title, filename),
                content_type="text/html; charset=utf-8",
            )
        if extension == "doc":
            return text_response(
                self,
                unsupported_word_preview_html(title, filename),
                content_type="text/html; charset=utf-8",
            )
        if content_type == "application/pdf" or extension == "pdf":
            return self.handle_document_file(document_id)
        if content_type.startswith("image/") or content_type.startswith("text/"):
            return self.handle_document_file(document_id)
        return text_response(
            self,
            preview_html_shell(
                title,
                f"文件预览 · {filename}",
                "<div class=\"empty\">当前文件类型暂不支持内嵌预览。请使用“打开文件”查看原文件。</div>",
            ),
            content_type="text/html; charset=utf-8",
        )

    def handle_delete_document(self, document_id: str) -> None:
        try:
            doc_id = int(document_id)
        except ValueError:
            return not_found(self)
        with connect() as conn:
            row = conn.execute("select * from documents where id = ?", (doc_id,)).fetchone()
            if not row:
                return not_found(self)
            conn.execute("delete from documents where id = ?", (doc_id,))
        target = resolve_document_file(row["file_path"] or "")
        if target and target.exists() and target.is_file():
            target.unlink(missing_ok=True)
        json_response(self, {"ok": True})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    os.environ[PLATFORM_BIND_HOST_ENV] = args.host
    AppHandler.platform_accounts = configured_accounts(args.host)
    AppHandler.cookie_secure = os.environ.get("PHD_PLATFORM_COOKIE_SECURE", "") == "1"
    init_db()
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Applicant platform running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
