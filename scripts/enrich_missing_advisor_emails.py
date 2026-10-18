#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import ssl
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = PLATFORM_ROOT.parent
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ApplicantAdvisorEmailEnricher/0.2"
AUTOMATION_USER = "main-agent-email-enrichment-v2"
SEARCH_ERROR_COUNTS: Counter[str] = Counter()
SEARCH_ERROR_EXAMPLES: list[str] = []
LOW_VALUE_DOMAINS = {
    "aihub.org",
    "openalex.org",
    "scholar.google.com",
    "dblp.org",
    "semanticscholar.org",
    "linkedin.com",
    "researchgate.net",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "github.com",
    "orcid.org",
    "ratemyprofessors.com",
    "stackforce.co",
}
LOW_VALUE_URL_MARKERS = (
    "/citations?",
    "/scholar?",
    "/publication/",
    "/paper/",
    "academicpositions.",
    "expertisefinder.com",
    "openalex.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ratemyprofessors.com",
)
INSTITUTION_DOMAIN_HINTS = {
    "arizona state university": {"asu.edu"},
    "brown university": {"brown.edu"},
    "carnegie mellon university": {"cmu.edu"},
    "case western reserve university": {"case.edu"},
    "columbia university": {"columbia.edu"},
    "cornell university": {"cornell.edu"},
    "duke university": {"duke.edu"},
    "emory university": {"emory.edu"},
    "george mason university": {"gmu.edu"},
    "harvard university": {"harvard.edu"},
    "illinois institute of technology": {"illinoistech.edu", "iit.edu"},
    "indiana university": {"iu.edu"},
    "indiana university of pennsylvania": {"iup.edu"},
    "iowa state university": {"iastate.edu"},
    "johns hopkins university": {"jhu.edu", "jh.edu", "jhmi.edu"},
    "kennesaw state university": {"kennesaw.edu"},
    "massachusetts institute of technology": {"mit.edu"},
    "naval postgraduate school": {"nps.edu"},
    "new york university": {"nyu.edu", "nyulangone.org"},
    "northeastern university": {"northeastern.edu", "neu.edu"},
    "northwestern university": {"northwestern.edu"},
    "ohio state university": {"osu.edu"},
    "old dominion university": {"odu.edu"},
    "oklahoma state university": {"okstate.edu"},
    "pennsylvania state university": {"psu.edu", "psu.edu"},
    "princeton university": {"princeton.edu"},
    "stanford university": {"stanford.edu"},
    "stony brook university": {"stonybrook.edu"},
    "temple university": {"temple.edu"},
    "texas a&m university": {"tamu.edu"},
    "texas state university": {"txstate.edu"},
    "texas tech university": {"ttu.edu"},
    "the ohio state university": {"osu.edu"},
    "tufts university": {"tufts.edu"},
    "university of arizona": {"arizona.edu"},
    "university of california san diego": {"ucsd.edu"},
    "university of california, berkeley": {"berkeley.edu"},
    "university of california, davis": {"ucdavis.edu"},
    "university of california, irvine": {"uci.edu"},
    "university of california, los angeles": {"ucla.edu"},
    "university of california, san diego": {"ucsd.edu"},
    "university of chicago": {"uchicago.edu"},
    "university of cincinnati": {"uc.edu"},
    "university of colorado boulder": {"colorado.edu"},
    "university of connecticut": {"uconn.edu"},
    "university of iowa": {"uiowa.edu"},
    "university of louisville": {"louisville.edu"},
    "university of maryland, baltimore": {"umaryland.edu"},
    "university of maryland, college park": {"umd.edu"},
    "university of michigan": {"umich.edu"},
    "university of michigan-ann arbor": {"umich.edu"},
    "university of michigan ann arbor": {"umich.edu"},
    "university of nebraska at omaha": {"unomaha.edu"},
    "university of nebraska-lincoln": {"unl.edu"},
    "university of north carolina at chapel hill": {"unc.edu"},
    "university of new hampshire": {"unh.edu"},
    "university of north texas": {"unt.edu"},
    "university of notre dame": {"nd.edu"},
    "university of oregon": {"uoregon.edu"},
    "university of pennsylvania": {"upenn.edu", "pennmedicine.org"},
    "university of rochester": {"rochester.edu"},
    "university of south carolina": {"sc.edu", "email.sc.edu"},
    "university of south florida": {"usf.edu"},
    "university of southern california": {"usc.edu"},
    "university of texas at san antonio": {"utsa.edu"},
    "the university of texas at austin": {"utexas.edu"},
    "university of washington": {"uw.edu", "washington.edu"},
    "university of wisconsin-madison": {"wisc.edu"},
    "virginia tech": {"vt.edu"},
}
INSTITUTION_TEXT_ALIASES = {
    "arizona state university": {"asu", "arizona state"},
    "carnegie mellon university": {"cmu", "carnegie mellon"},
    "case western reserve university": {"case western"},
    "columbia university": {"columbia"},
    "george mason university": {"gmu", "george mason"},
    "harvard university": {"harvard"},
    "illinois institute of technology": {"illinois tech", "iit"},
    "johns hopkins university": {"jhu", "johns hopkins"},
    "massachusetts institute of technology": {"mit"},
    "new york university": {"nyu", "new york university"},
    "northeastern university": {"northeastern"},
    "ohio state university": {"osu", "ohio state"},
    "princeton university": {"princeton"},
    "stanford university": {"stanford"},
    "stony brook university": {"stony brook"},
    "texas a&m university": {"texas a&m", "tamu"},
    "the ohio state university": {"osu", "ohio state"},
    "university of california san diego": {"ucsd"},
    "university of california, berkeley": {"uc berkeley", "berkeley"},
    "university of california, davis": {"uc davis", "ucdavis"},
    "university of california, irvine": {"uci", "uc irvine"},
    "university of california, los angeles": {"ucla"},
    "university of california, san diego": {"ucsd"},
    "university of chicago": {"uchicago"},
    "university of colorado boulder": {"cu boulder", "colorado boulder"},
    "university of maryland, baltimore": {"umaryland"},
    "university of maryland, college park": {"umd", "maryland college park"},
    "university of michigan": {"umich", "university of michigan"},
    "university of michigan-ann arbor": {"umich", "michigan ann arbor"},
    "university of michigan ann arbor": {"umich", "michigan ann arbor"},
    "university of north carolina at chapel hill": {"unc", "chapel hill"},
    "university of pennsylvania": {"upenn", "penn medicine"},
    "university of south carolina": {"usc columbia", "south carolina"},
    "university of southern california": {"usc", "southern california"},
    "university of washington": {"uw", "university of washington"},
    "university of wisconsin-madison": {"uw-madison", "wisconsin-madison"},
    "virginia tech": {"virginia tech"},
}
GENERIC_INSTITUTION_WORDS = {
    "and",
    "campus",
    "college",
    "institute",
    "school",
    "state",
    "the",
    "university",
}
GENERIC_LOCAL_PARTS = {
    "admin",
    "admission",
    "admissions",
    "advisor",
    "advising",
    "apply",
    "career",
    "careers",
    "chair",
    "contact",
    "cs",
    "cse",
    "department",
    "dept",
    "engineering",
    "faculty",
    "grad",
    "gradadmissions",
    "graduate",
    "hello",
    "help",
    "hr",
    "info",
    "jobs",
    "media",
    "news",
    "office",
    "phd",
    "privacy",
    "recruiting",
    "staff",
    "support",
    "undergrad",
    "webmaster",
}
GENERIC_LOCAL_PREFIXES = (
    "admission",
    "apply",
    "contact",
    "grad",
    "info",
    "office",
    "support",
    "webmaster",
)
FAKE_DOMAINS = {"example.com", "email.com", "domain.com", "mysite.com", "sentry.io"}
VALID_TLDS = {
    "edu",
    "com",
    "org",
    "net",
    "gov",
    "mil",
    "ca",
    "us",
    "uk",
    "au",
    "nz",
    "cn",
    "hk",
    "tw",
    "sg",
    "jp",
    "kr",
    "in",
    "il",
    "de",
    "fr",
    "it",
    "es",
    "nl",
    "ch",
    "se",
    "no",
    "dk",
    "fi",
    "br",
    "za",
    "io",
    "ai",
    "me",
    "co",
    "info",
    "dev",
}
TEXT_FIELDS = [
    ("stageEvidence", "stageEvidenceUrl"),
    ("phdAdvisingEvidence", "phdAdvisingUrl"),
    ("recruitingEvidence", "recruitingUrl"),
    ("studentBackgroundEvidence", "studentBackgroundUrl"),
    ("stage_evidence", "stage_evidence_url"),
    ("phd_advising_evidence", "phd_advising_url"),
    ("recruiting_evidence", "recruiting_url"),
    ("student_background_evidence", "student_background_url"),
    ("evidence_1", "evidence_1_url"),
    ("evidence_2", "evidence_2_url"),
    ("evidence_3", "evidence_3_url"),
]
URL_FIELDS = [
    "homepage",
    "homepageUrl",
    "stageEvidenceUrl",
    "phdAdvisingUrl",
    "recruitingUrl",
    "studentBackgroundUrl",
    "stage_evidence_url",
    "phd_advising_url",
    "recruiting_url",
    "student_background_url",
    "evidence_1_url",
    "evidence_2_url",
    "evidence_3_url",
]
EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])")
MAILTO_RE = re.compile(r"mailto:([^\"'?#>\s]+)", flags=re.I)
CFEMAIL_RE = re.compile(r'data-cfemail=["\']([0-9a-fA-F]+)["\']')
OBFUSCATED_RE = re.compile(
    r"\b([A-Za-z0-9._%+-]{1,64})\s*"
    r"(?:\[\s*at\s*\]|\(\s*at\s*\)|\{\s*at\s*\}|\s+at\s+|&#64;|@)\s*"
    r"([A-Za-z0-9][A-Za-z0-9.-]{0,253}?)\s*"
    r"(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\}|\s+dot\s+|&#46;|\.)\s*"
    r"([A-Za-z]{2,}(?:(?:\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\}|\s+dot\s+|&#46;|\.)\s*)[A-Za-z]{2,})*)",
    flags=re.I,
)


@dataclass
class SourceText:
    url: str
    text: str
    raw: str
    kind: str


@dataclass
class ContactCandidate:
    email: str
    contact_type: str
    confidence: str
    source_url: str
    evidence_text: str
    score: int
    reason: str
    source_kind: str


def ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return normalized.encode("ascii", "ignore").decode("ascii")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", ascii_fold(value).lower())


def clean_name(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"\s+\d{4}$", "", value)
    return value


def name_tokens(name: str) -> list[str]:
    tokens = [token.lower() for token in re.findall(r"[A-Za-z]+", ascii_fold(clean_name(name)))]
    ignored = {"de", "del", "den", "der", "di", "la", "le", "van", "von", "jr", "sr", "ii", "iii", "iv"}
    return [token for token in tokens if len(token) >= 2 and token not in ignored]


def email_is_valid(email: str) -> bool:
    email = email.strip().lower().strip(".,;:)]}>")
    if not EMAIL_RE.fullmatch(email):
        return False
    local, domain = email.split("@", 1)
    if not local or not domain or domain in FAKE_DOMAINS:
        return False
    if domain.rsplit(".", 1)[-1] not in VALID_TLDS:
        return False
    if domain.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf")):
        return False
    if local in {"email", "name", "user", "username", "yourname", "first.last"}:
        return False
    if "emailprotected" in compact(email) or "protectedemail" in compact(email):
        return False
    return True


def email_domain(email: str) -> str:
    return email.split("@", 1)[1].lower()


def host_site_key(host: str) -> str:
    host = host.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 3 and parts[-2:] == ["github", "io"]:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def site_key(url: str) -> str:
    return host_site_key(urllib.parse.urlparse(url).netloc)


def email_site_key(email_or_domain: str) -> str:
    domain = email_or_domain.split("@", 1)[-1].lower()
    return host_site_key(domain)


def low_value_url(url: str) -> bool:
    host = site_key(url)
    netloc = urllib.parse.urlparse(url).netloc.lower()
    if host in LOW_VALUE_DOMAINS:
        return True
    lower = url.lower()
    return any(marker in lower or marker in netloc for marker in LOW_VALUE_URL_MARKERS)


def officialish_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return ".edu" in host or ".ac." in host or host.endswith(".ca")


def academicish_domain(domain: str) -> bool:
    domain = domain.lower()
    return domain.endswith(".edu") or ".ac." in domain or domain.endswith(".ca")


def normalized_institution(value: str) -> str:
    value = ascii_fold(value).lower()
    value = value.replace("&", " and ")
    value = value.replace("–", "-").replace("—", "-")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return clean_text(value)


def institution_domain_hints(row: server.DbRow | dict, raw: dict) -> set[str]:
    institution = normalized_institution(str(row["institution"] or raw.get("institution", "") or ""))
    hints: set[str] = set()
    for key, domains in INSTITUTION_DOMAIN_HINTS.items():
        if key in institution:
            hints.update(email_site_key(domain) for domain in domains)
    return {hint for hint in hints if hint}


def institution_text_aliases(row: server.DbRow | dict, raw: dict) -> set[str]:
    institution = normalized_institution(str(row["institution"] or raw.get("institution", "") or ""))
    aliases: set[str] = set()
    if institution:
        aliases.add(institution)
    for key, values in INSTITUTION_TEXT_ALIASES.items():
        if key in institution:
            aliases.update(values)
    tokens = [token for token in institution.split() if len(token) >= 4 and token not in GENERIC_INSTITUTION_WORDS]
    if len(tokens) >= 2:
        aliases.add(" ".join(tokens))
    elif len(tokens) == 1 and len(tokens[0]) >= 6:
        aliases.add(tokens[0])
    return {alias for alias in aliases if alias}


def source_mentions_institution(row: server.DbRow | dict, raw: dict, source: SourceText, evidence: str) -> bool:
    haystack = normalized_institution(f"{source.url} {source.text[:8000]} {evidence}")
    if not haystack:
        return False
    aliases = institution_text_aliases(row, raw)
    for alias in aliases:
        normalized_alias = normalized_institution(alias)
        if normalized_alias and normalized_alias in haystack:
            return True
    institution = normalized_institution(str(row["institution"] or raw.get("institution", "") or ""))
    tokens = [token for token in institution.split() if len(token) >= 4 and token not in GENERIC_INSTITUTION_WORDS]
    if len(tokens) >= 2 and all(token in haystack for token in tokens):
        return True
    return False


def institution_alignment(
    email: str,
    row: server.DbRow | dict,
    raw: dict,
    source: SourceText,
    evidence: str,
) -> tuple[bool, bool, str]:
    hints = institution_domain_hints(row, raw)
    source_key = site_key(source.url)
    email_key = email_site_key(email)
    source_matches = bool(source_key and source_key in hints)
    email_matches = bool(email_key and email_key in hints)
    text_matches = source_mentions_institution(row, raw, source, evidence)
    matched = source_matches or email_matches or text_matches

    source_academic = bool(source_key and officialish_url(source.url))
    email_academic = academicish_domain(email_domain(email))
    foreign_source = bool(hints and source_academic and not source_matches)
    foreign_email = bool(hints and email_academic and not email_matches)
    if foreign_email or (foreign_source and not email_matches):
        parts = []
        if source_key:
            parts.append(f"source={source_key}")
        if email_key:
            parts.append(f"email={email_key}")
        if hints:
            parts.append(f"expected={','.join(sorted(hints))}")
        return matched, True, "institution mismatch: " + "; ".join(parts)
    return matched, False, ""


def url_name_score(url: str, tokens: list[str]) -> int:
    text = compact(urllib.parse.urlparse(url).path)
    if not text:
        return 0
    score = 0
    for token in tokens:
        if len(token) >= 4 and token in text:
            score += 2
    if tokens:
        first = tokens[0]
        last = tokens[-1]
        if first and last and compact(first[0] + last[:5]) in text:
            score += 3
    return min(score, 5)


def name_match_score(email: str, name: str) -> tuple[int, list[str]]:
    local = compact(email.split("@", 1)[0].split("+", 1)[0])
    tokens = name_tokens(name)
    reasons: list[str] = []
    if not tokens:
        return 0, reasons
    first = tokens[0]
    last = tokens[-1]
    score = 0
    if len(last) >= 4 and last in local:
        score += 7
        reasons.append("local part contains last name")
    if len(first) >= 4 and first in local:
        score += 4
        reasons.append("local part contains first name")
    if first and last and len(last) >= 3:
        initial_last = compact(first[0] + last)
        if local.startswith(initial_last) or local.startswith(compact(first[0] + last[:5])):
            score += 8
            reasons.append("local part matches first initial + last name")
        if local.startswith(compact(last + first[0])):
            score += 7
            reasons.append("local part matches last name + first initial")
        if local.startswith(compact(first + last[0])):
            score += 4
            reasons.append("local part matches first name + last initial")
    initials = "".join(token[0] for token in tokens if token)
    if len(initials) >= 2 and local == initials:
        score += 4
        reasons.append("local part matches name initials")
    for token in tokens[1:-1]:
        if len(token) >= 4 and token in local:
            score += 2
            reasons.append("local part contains middle name token")
    return score, reasons


def context_score(evidence: str, source_url: str, name: str) -> tuple[int, list[str]]:
    tokens = name_tokens(name)
    if not tokens:
        return 0, []
    text = ascii_fold(f"{evidence} {source_url}").lower()
    full_name = " ".join(tokens)
    reasons: list[str] = []
    score = 0
    if full_name and full_name in text:
        score += 5
        reasons.append("evidence contains full name")
    if tokens[0] in text and tokens[-1] in text:
        score += 3
        reasons.append("evidence contains first and last name")
    url_score = url_name_score(source_url, tokens)
    if url_score:
        score += url_score
        reasons.append("source URL matches advisor name")
    return score, reasons


def classify_email(
    email: str,
    row: server.DbRow | dict,
    raw: dict,
    source: SourceText,
    evidence: str,
    emails_on_source: int,
) -> ContactCandidate:
    email = email.lower()
    name = str(row["name"])
    local = compact(email.split("@", 1)[0])
    evidence_lower = evidence.lower()
    if source.kind == "raw_json_dump" and not source.url:
        return ContactCandidate(email, "其他", "待确认", source.url, evidence, 0, "raw_json dump has no source URL", source.kind)
    if local in GENERIC_LOCAL_PARTS or any(local.startswith(prefix) for prefix in GENERIC_LOCAL_PREFIXES):
        return ContactCandidate(email, "项目邮箱", "低", source.url, evidence, 0, "generic local part", source.kind)
    if any(term in evidence_lower for term in ["admissions", "graduate office", "department office", "program coordinator"]):
        name_score, _ = name_match_score(email, name)
        if name_score < 5:
            return ContactCandidate(email, "项目邮箱", "低", source.url, evidence, name_score, "program or office context", source.kind)

    name_score, name_reasons = name_match_score(email, name)
    ctx_score, ctx_reasons = context_score(evidence, source.url, name)
    score = name_score + ctx_score
    institution_matches, institution_mismatch, institution_reason = institution_alignment(email, row, raw, source, evidence)
    if institution_mismatch:
        return ContactCandidate(
            email,
            "其他",
            "待确认",
            source.url,
            evidence,
            max(0, score - 8),
            institution_reason,
            source.kind,
        )
    if institution_matches:
        score += 3
        ctx_reasons.append("source or email matches institution")
    if officialish_url(source.url):
        score += 1
    if emails_on_source > 5 and ctx_score < 3:
        score -= 4
    domain = email_domain(email)
    if domain.endswith((".edu", ".ca")):
        score += 1
    if domain in {"gmail.com", "outlook.com", "hotmail.com", "icloud.com"} and ctx_score < 3:
        score -= 2

    reasons = name_reasons + ctx_reasons
    name_match_enough = name_score >= 4 or (name_score >= 2 and ctx_score >= 8 and emails_on_source <= 2)
    if score >= 11:
        confidence = "高"
    elif score >= 7:
        confidence = "中"
    else:
        confidence = "待确认"

    if name_match_enough and score >= 7:
        return ContactCandidate(email, "导师邮箱", confidence, source.url, evidence, score, "; ".join(reasons), source.kind)
    if "lab" in local or "group" in local:
        return ContactCandidate(email, "Lab 邮箱", "中", source.url, evidence, score, "lab-like local part", source.kind)
    return ContactCandidate(email, "其他", "待确认", source.url, evidence, score, "; ".join(reasons), source.kind)


def snippet(text: str, email: str, radius: int = 220) -> str:
    clean = clean_text(text)
    index = clean.lower().find(email.lower())
    if index < 0:
        local = email.split("@", 1)[0].lower()
        index = clean.lower().find(local)
    if index < 0:
        return clean[: radius * 2]
    start = max(0, index - radius)
    end = min(len(clean), index + len(email) + radius)
    return clean[start:end].strip()


def decode_cfemail(value: str) -> str:
    try:
        data = bytes.fromhex(value)
    except ValueError:
        return ""
    if len(data) < 2:
        return ""
    key = data[0]
    return "".join(chr(byte ^ key) for byte in data[1:])


def obfuscated_matches(text: str) -> list[str]:
    emails: list[str] = []
    unescaped = html.unescape(text or "")
    for match in OBFUSCATED_RE.finditer(unescaped):
        local = match.group(1).strip(" .")
        domain_base = re.sub(r"\s+", "", match.group(2).strip(" ."))
        suffix = re.sub(r"(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\}|\s+dot\s+|&#46;)", ".", match.group(3), flags=re.I)
        suffix = re.sub(r"\s+", "", suffix).strip(".")
        emails.append(f"{local}@{domain_base}.{suffix}")
    return emails


def extract_email_candidates_from_source(source: SourceText) -> list[tuple[str, str]]:
    raw_limited = source.raw[:120_000]
    text_limited = source.text[:120_000]
    haystacks = [raw_limited, text_limited, html.unescape(raw_limited), html.unescape(text_limited)]
    candidates: list[tuple[str, str]] = []
    for raw in haystacks:
        if not raw:
            continue
        for encoded in CFEMAIL_RE.findall(raw):
            decoded = decode_cfemail(encoded)
            if email_is_valid(decoded):
                candidates.append((decoded.lower(), snippet(raw, decoded)))
        for match in MAILTO_RE.finditer(raw):
            value = urllib.parse.unquote(match.group(1)).split("?", 1)[0]
            if email_is_valid(value):
                candidates.append((value.lower(), snippet(raw, value)))
        for match in EMAIL_RE.finditer(html.unescape(raw)):
            value = match.group(1).strip().lower()
            if email_is_valid(value):
                candidates.append((value, snippet(raw, value)))
        for value in obfuscated_matches(raw):
            if email_is_valid(value):
                candidates.append((value.lower(), snippet(raw, value)))

    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for email_value, evidence in candidates:
        if email_value in seen:
            continue
        seen.add(email_value)
        deduped.append((email_value, evidence))
    return deduped


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    raw = raw[:120_000]
    pieces: list[str] = []
    title = re.search(r"<title[^>]*>([^<]{0,500})</title>", raw[:8_000], flags=re.I | re.S)
    if title:
        pieces.append(title.group(1))
    body = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return clean_text(" ".join(pieces + [body]))


def default_cache_dirs() -> list[Path]:
    env_value = os.environ.get("PHD_PLATFORM_ADVISOR_EMAIL_CACHE_DIRS", "")
    dirs = [Path(item).expanduser() for item in env_value.split(":") if item.strip()]
    dirs.extend(
        [
            Path("/private/tmp/applicant_advisor_evidence_cache_2026-07-01_us3000"),
            Path("/private/tmp/applicant_advisor_evidence_cache_2026-06-30_us2000"),
            Path("/private/tmp/applicant_advisor_evidence_cache_2026-06-29"),
        ]
    )
    return [path for path in dirs if path.exists()]


def cache_path(url: str, cache_dirs: list[Path]) -> Path | None:
    filename = f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.html"
    for directory in cache_dirs:
        path = directory / filename
        if path.exists() and path.stat().st_size > 80:
            return path
    return None


def read_cached_source(url: str, cache_dirs: list[Path]) -> SourceText | None:
    path = cache_path(url, cache_dirs)
    if not path:
        return None
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return SourceText(url=url, text=html_to_text(raw), raw=raw, kind="cache")


def web_ssl_context() -> ssl.SSLContext | None:
    cert_file = os.environ.get("SSL_CERT_FILE", "").strip()
    if cert_file:
        path = Path(cert_file).expanduser()
        if path.exists():
            return ssl.create_default_context(cafile=str(path))
    try:
        import certifi  # type: ignore
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def fetch_url(url: str, timeout: int, sleep_seconds: float) -> SourceText | None:
    if not url.startswith(("http://", "https://")) or low_value_url(url):
        return None
    try:
        result = subprocess.run(
            [
                "curl",
                "-L",
                "-sS",
                "--compressed",
                "--connect-timeout",
                str(max(2, min(timeout, 6))),
                "--max-time",
                str(max(3, timeout)),
                "-A",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            timeout=max(5, timeout + 3),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    if sleep_seconds:
        time.sleep(sleep_seconds)
    raw_bytes = result.stdout[:300_000]
    if raw_bytes[:4] == b"%PDF":
        return None
    raw = raw_bytes.decode("utf-8", errors="ignore")
    if len(raw) < 80:
        return None
    return SourceText(url=url, text=html_to_text(raw), raw=raw, kind="fetched")


def extract_links(raw: str, base_url: str) -> list[str]:
    links: list[str] = []
    for href, label in re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw[:240_000], flags=re.I | re.S):
        label_text = clean_text(re.sub(r"<[^>]+>", " ", label))
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        url = urllib.parse.urljoin(base_url, href).split("#", 1)[0].rstrip("/")
        if not url.startswith(("http://", "https://")):
            continue
        marker = f"{url} {label_text}".lower()
        if any(term in marker for term in ["contact", "people", "faculty", "profile", "cv", "bio", "about"]):
            links.append(url)
    seen: set[str] = set()
    deduped: list[str] = []
    for url in links:
        if url in seen or low_value_url(url):
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def source_urls_from_raw(raw: dict) -> list[str]:
    urls: list[str] = []
    for key in URL_FIELDS:
        value = str(raw.get(key, "") or "").strip()
        if value.startswith(("http://", "https://")) and not low_value_url(value):
            urls.append(value.split("#", 1)[0].rstrip("/"))
    links = raw.get("links")
    if isinstance(links, list):
        for item in links:
            if isinstance(item, str):
                value = item.strip()
            elif isinstance(item, dict):
                value = str(item.get("url") or item.get("href") or "").strip()
            else:
                value = ""
            if value.startswith(("http://", "https://")) and not low_value_url(value):
                urls.append(value.split("#", 1)[0].rstrip("/"))
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def text_sources_from_raw(raw: dict) -> list[SourceText]:
    sources: list[SourceText] = []
    for text_key, url_key in TEXT_FIELDS:
        text = str(raw.get(text_key, "") or "").strip()
        if not text:
            continue
        url = str(raw.get(url_key, "") or "").strip()
        sources.append(SourceText(url=url, text=clean_text(text), raw=text, kind="raw_json"))
    raw_dump = json.dumps(raw, ensure_ascii=False)
    sources.append(SourceText(url="", text=clean_text(raw_dump), raw=raw_dump, kind="raw_json_dump"))
    return sources


def infer_site_domain(raw: dict) -> str:
    domains = Counter()
    for url in source_urls_from_raw(raw):
        host = urllib.parse.urlparse(url).netloc.lower()
        if ".edu" in host or ".ac." in host or host.endswith(".ca"):
            domains[site_key(url)] += 1
    if domains:
        return domains.most_common(1)[0][0]
    return ""


def search_provider() -> str:
    if os.environ.get("TAVILY_API_KEY"):
        return "tavily"
    if os.environ.get("SERPAPI_API_KEY"):
        return "serpapi"
    if os.environ.get("BING_SEARCH_API_KEY"):
        return "bing"
    return ""


def record_search_error(kind: str, detail: str) -> None:
    SEARCH_ERROR_COUNTS[kind] += 1
    if len(SEARCH_ERROR_EXAMPLES) < 10:
        SEARCH_ERROR_EXAMPLES.append(clean_text(detail)[:500])


def search_api(query: str, max_results: int, timeout: int) -> list[str]:
    provider = search_provider()
    if not provider:
        return []
    try:
        if provider == "tavily":
            payload = json.dumps(
                {
                    "api_key": os.environ["TAVILY_API_KEY"],
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": False,
                    "include_raw_content": False,
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                "https://api.tavily.com/search",
                data=payload,
                headers={"content-type": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=timeout, context=web_ssl_context()) as response:
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
            return [item.get("url", "") for item in data.get("results", []) if item.get("url")]
        if provider == "serpapi":
            params = urllib.parse.urlencode(
                {"engine": "google", "q": query, "num": max_results, "api_key": os.environ["SERPAPI_API_KEY"]}
            )
            request = urllib.request.Request(f"https://serpapi.com/search.json?{params}", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout, context=web_ssl_context()) as response:
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
            return [item.get("link", "") for item in data.get("organic_results", []) if item.get("link")]
        if provider == "bing":
            params = urllib.parse.urlencode({"q": query, "count": max_results})
            request = urllib.request.Request(
                f"https://api.bing.microsoft.com/v7.0/search?{params}",
                headers={"Ocp-Apim-Subscription-Key": os.environ["BING_SEARCH_API_KEY"], "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=timeout, context=web_ssl_context()) as response:
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
            return [item.get("url", "") for item in data.get("webPages", {}).get("value", []) if item.get("url")]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")[:500]
        record_search_error(f"http_{exc.code}", body or str(exc))
        return []
    except urllib.error.URLError as exc:
        record_search_error("url_error", str(exc.reason))
        return []
    except TimeoutError:
        record_search_error("timeout", query)
        return []
    except OSError as exc:
        record_search_error("os_error", str(exc))
        return []
    except json.JSONDecodeError as exc:
        record_search_error("json_decode", str(exc))
        return []
    return []


def search_queries(row: server.DbRow, raw: dict) -> list[str]:
    name = clean_name(str(row["name"]))
    institution = str(row["institution"] or raw.get("institution", "") or "").strip()
    domain = infer_site_domain(raw)
    queries = []
    if domain:
        queries.append(f'site:{domain} "{name}" email faculty profile')
        queries.append(f'site:{domain} "{name}" contact')
    if institution:
        queries.append(f'"{name}" "{institution}" email faculty profile')
        queries.append(f'"{name}" "{institution}" lab contact')
    return queries


def collect_sources(
    row: server.DbRow,
    raw: dict,
    cache_dirs: list[Path],
    fetch_missing: bool,
    use_search: bool,
    max_urls: int,
    timeout: int,
    sleep_seconds: float,
) -> tuple[list[SourceText], dict]:
    stats = {
        "raw_sources": 0,
        "cache_sources": 0,
        "fetched_sources": 0,
        "search_urls": 0,
        "urls_considered": 0,
    }
    sources = text_sources_from_raw(raw)
    stats["raw_sources"] = len(sources)
    urls = source_urls_from_raw(raw)
    if use_search:
        for query in search_queries(row, raw):
            for url in search_api(query, max_results=5, timeout=timeout):
                url = url.split("#", 1)[0].rstrip("/")
                if url.startswith(("http://", "https://")) and not low_value_url(url):
                    urls.append(url)
                    stats["search_urls"] += 1
    seen_urls: set[str] = set()
    expanded_urls: list[str] = []
    for url in urls:
        if url in seen_urls or low_value_url(url):
            continue
        seen_urls.add(url)
        expanded_urls.append(url)
    for url in expanded_urls[:max_urls]:
        stats["urls_considered"] += 1
        cached = read_cached_source(url, cache_dirs)
        if cached:
            sources.append(cached)
            stats["cache_sources"] += 1
            for link in extract_links(cached.raw, url):
                if len(seen_urls) >= max_urls:
                    break
                if link not in seen_urls and site_key(link) == site_key(url):
                    seen_urls.add(link)
                    expanded_urls.append(link)
            continue
        if fetch_missing:
            fetched = fetch_url(url, timeout=timeout, sleep_seconds=sleep_seconds)
            if fetched:
                sources.append(fetched)
                stats["fetched_sources"] += 1
    return sources, stats


def rank_candidates(candidates: list[ContactCandidate]) -> list[ContactCandidate]:
    def key(candidate: ContactCandidate) -> tuple[int, int, int, str]:
        official = 1 if officialish_url(candidate.source_url) else 0
        domain_bonus = 1 if email_domain(candidate.email).endswith((".edu", ".ca")) else 0
        return (candidate.score, official, domain_bonus, candidate.email)

    return sorted(candidates, key=key, reverse=True)


def residual_reason(raw: dict, candidates: list[ContactCandidate], stats: dict, use_search: bool) -> tuple[str, str]:
    if any(candidate.contact_type == "项目邮箱" for candidate in candidates):
        return "只有项目/部门邮箱，未找到导师本人邮箱", "页面邮箱为项目或部门邮箱，不能作为套磁邮箱。"
    if any(candidate.contact_type in {"Lab 邮箱", "其他"} and "@" in candidate.email for candidate in candidates):
        return "页面邮箱不属于导师本人，待人工复核", "页面存在邮箱，但自动规则无法确认属于导师本人。"
    if not source_urls_from_raw(raw) and not use_search:
        return "缺官网 URL，未配置搜索 API", "当前记录没有可用官网 URL；本地未配置 Tavily/SerpAPI/Bing Search API。"
    if stats.get("cache_sources") or stats.get("fetched_sources"):
        return "已有 URL/缓存页面未发现导师本人邮箱", "已检查已有 URL 或缓存页面，未发现可确认的导师本人邮箱。"
    return "页面不可访问或缺少缓存，未找到导师本人邮箱", "已有 URL 没有可用缓存；本轮未能访问到可解析页面。"


def priority_key(row: server.DbRow, raw: dict, review_decisions: dict[str, list[str]]) -> tuple:
    category_priority = {
        "Core evaluation": 0,
        "Agent/persona": 1,
        "Trustworthy/robust": 2,
        "NLP/LLM-adjacent": 3,
        "HCI/social": 4,
        "Recommender/user": 5,
        "Education/HCI": 6,
        "AI/ML adjacent": 7,
        "CS faculty fallback": 8,
    }
    stage_priority = {"ap": 0, "faculty_unknown": 1, "associate": 2, "unknown": 3, "full": 4, "star": 5, "nonfaculty": 6}
    reliability_priority = {"高": 0, "中": 1, "低": 2, "红旗": 3}
    decisions = " ".join(review_decisions.get(str(row["id"]), []))
    reviewed_priority = 0 if any(marker in decisions for marker in ["保留", "待讨论", "高", "联系"]) else 1
    category = raw.get("primary_category") or raw.get("primaryCategory") or row.get("category") or ""
    stage = raw.get("stage_key") or raw.get("stageKey") or row.get("stage_key") or ""
    reliability = raw.get("evidence_reliability") or raw.get("evidenceReliability") or row.get("evidence_reliability") or ""
    return (
        category_priority.get(str(category), 9),
        reviewed_priority,
        stage_priority.get(str(stage), 9),
        reliability_priority.get(str(reliability), 9),
        int(row["rank"]),
    )


def load_review_decisions(conn: server.DbConnection) -> dict[str, list[str]]:
    reviews: dict[str, list[str]] = {}
    for row in conn.execute("select advisor_id, decision, interest, review_status from advisor_reviews").fetchall():
        reviews.setdefault(str(row["advisor_id"]), []).append(
            " ".join(str(row.get(key) or "") for key in ["decision", "interest", "review_status"])
        )
    return reviews


def advisor_rows(conn: server.DbConnection, missing_only: bool) -> list[server.DbRow]:
    where = ""
    if missing_only:
        where = """
        where not exists (
          select 1 from advisor_contacts c
          where c.advisor_id = advisors.id and c.contact_type = '导师邮箱'
        )
        """
    return conn.execute(
        f"""
        select id, `rank`, name, institution, category, stage_key, evidence_reliability, raw_json
        from advisors
        {where}
        order by `rank`
        """
    ).fetchall()


def existing_contact(conn: server.DbConnection, advisor_id: str, contact_value: str):
    return conn.execute(
        "select id, contact_type, created_by from advisor_contacts where advisor_id = ? and contact_value = ?",
        (advisor_id, contact_value),
    ).fetchone()


def upsert_contact(conn: server.DbConnection, advisor_id: str, candidate: ContactCandidate, is_primary: bool) -> str:
    now = server.utc_now()
    value = server.normalize_contact_value(candidate.contact_type, candidate.email)
    existing = existing_contact(conn, advisor_id, value)
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
                candidate.contact_type,
                candidate.source_url,
                candidate.evidence_text[:2000],
                candidate.confidence,
                AUTOMATION_USER,
                now,
                row_id,
                advisor_id,
            ),
        )
        action = "updated_existing"
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
                candidate.contact_type,
                value,
                candidate.source_url,
                candidate.evidence_text[:2000],
                candidate.confidence,
                AUTOMATION_USER,
                AUTOMATION_USER,
                now,
                now,
            ),
        )
        row_id = int(cursor.lastrowid)
        action = "inserted"
    if is_primary:
        conn.execute("update advisor_contacts set is_primary = 0 where advisor_id = ? and id <> ?", (advisor_id, row_id))
        conn.execute(
            "update advisor_contacts set is_primary = 1, updated_by = ?, updated_at = ? where id = ? and advisor_id = ?",
            (AUTOMATION_USER, now, row_id, advisor_id),
        )
    server.sync_advisor_contact_primary(conn, advisor_id)
    return action


def upsert_reason(conn: server.DbConnection, advisor_id: str, reason: str, evidence: str, source_url: str) -> str:
    now = server.utc_now()
    existing = conn.execute(
        """
        select id from advisor_contacts
        where advisor_id = ? and contact_type = '其他' and contact_value not like ?
        order by case when contact_value = '未找到公开联系方式' then 0 else 1 end, id
        limit 1
        """,
        (advisor_id, "%@%"),
    ).fetchone()
    if existing:
        conn.execute(
            """
            update advisor_contacts
            set contact_value = ?, source_url = ?, evidence_text = ?, confidence = '待确认',
                updated_by = ?, updated_at = ?
            where id = ? and advisor_id = ?
            """,
            (reason, source_url, evidence[:2000], AUTOMATION_USER, now, int(existing["id"]), advisor_id),
        )
        return "reason_updated"
    conn.execute(
        """
        insert into advisor_contacts (
          advisor_id, contact_type, contact_value, source_url, evidence_text,
          confidence, is_primary, created_by, updated_by, created_at, updated_at
        ) values (?, '其他', ?, ?, ?, '待确认', 0, ?, ?, ?, ?)
        """,
        (advisor_id, reason, source_url, evidence[:2000], AUTOMATION_USER, AUTOMATION_USER, now, now),
    )
    return "reason_inserted"


def process_row(
    row: server.DbRow,
    cache_dirs: list[Path],
    fetch_missing: bool,
    use_search: bool,
    max_urls: int,
    timeout: int,
    sleep_seconds: float,
) -> dict:
    raw = json.loads(row["raw_json"])
    sources, stats = collect_sources(row, raw, cache_dirs, fetch_missing, use_search, max_urls, timeout, sleep_seconds)
    candidates_by_email: dict[str, ContactCandidate] = {}
    for source in sources:
        extracted = extract_email_candidates_from_source(source)
        emails_on_source = len(extracted)
        for email_value, evidence in extracted:
            candidate = classify_email(email_value, row, raw, source, evidence, emails_on_source)
            previous = candidates_by_email.get(candidate.email)
            if not previous or candidate.score > previous.score:
                candidates_by_email[candidate.email] = candidate
    candidates = list(candidates_by_email.values())
    advisor_candidates = rank_candidates([candidate for candidate in candidates if candidate.contact_type == "导师邮箱"])
    auxiliary_candidates = rank_candidates([candidate for candidate in candidates if candidate.contact_type != "导师邮箱"])
    reason, reason_evidence = residual_reason(raw, candidates, stats, use_search)
    best_source_url = ""
    if advisor_candidates:
        best_source_url = advisor_candidates[0].source_url
    elif auxiliary_candidates:
        best_source_url = auxiliary_candidates[0].source_url
    elif source_urls_from_raw(raw):
        best_source_url = source_urls_from_raw(raw)[0]
    return {
        "advisor_id": row["id"],
        "rank": row["rank"],
        "name": row["name"],
        "institution": row["institution"],
        "primary_category": raw.get("primary_category") or raw.get("primaryCategory", ""),
        "stage_key": raw.get("stage_key") or raw.get("stageKey", row.get("stage_key", "")),
        "evidence_reliability": raw.get("evidence_reliability") or raw.get("evidenceReliability", row.get("evidence_reliability", "")),
        "stats": stats,
        "advisor_candidates": [candidate.__dict__ for candidate in advisor_candidates[:5]],
        "auxiliary_candidates": [candidate.__dict__ for candidate in auxiliary_candidates[:5]],
        "residual_reason": reason,
        "residual_evidence": reason_evidence,
        "residual_source_url": best_source_url,
    }


def run(args: argparse.Namespace) -> dict:
    SEARCH_ERROR_COUNTS.clear()
    SEARCH_ERROR_EXAMPLES.clear()
    cache_dirs = default_cache_dirs()
    provider = search_provider()
    report = {
        "mode": "apply" if args.apply else "dry-run",
        "missing_only": args.missing_only,
        "fetch_missing_pages": args.fetch,
        "search_requested": args.search,
        "search_provider": provider or "",
        "search_enabled": bool(args.search and provider),
        "record_reasons": args.record_reasons,
        "reasons_only": args.reasons_only,
        "cache_dirs": [str(path) for path in cache_dirs],
        "advisors_scanned": 0,
        "advisor_email_candidates_found": 0,
        "advisor_emails_inserted": 0,
        "advisor_emails_updated_existing": 0,
        "reasons_inserted": 0,
        "reasons_updated": 0,
        "skipped_no_advisor_email": 0,
        "search_urls_found": 0,
        "urls_considered": 0,
        "cache_sources": 0,
        "fetched_sources": 0,
        "search_error_counts": {},
        "search_error_examples": [],
        "residual_reason_counts": {},
        "selected_advisor_emails": [],
        "examples_new_advisor_emails": [],
        "examples_residual": [],
    }
    with server.connect() as conn:
        server.ensure_base_schema(conn)
        rows = advisor_rows(conn, missing_only=args.missing_only)
        reviews = load_review_decisions(conn)
        rows = sorted(rows, key=lambda row: priority_key(row, json.loads(row["raw_json"]), reviews))
        if args.limit > 0:
            rows = rows[: args.limit]
        for row in rows:
            if args.progress_every and report["advisors_scanned"] and report["advisors_scanned"] % args.progress_every == 0:
                print(
                    f"processed {report['advisors_scanned']}/{len(rows)}; "
                    f"advisor email candidates {report['advisor_email_candidates_found']}",
                    file=sys.stderr,
                    flush=True,
                )
            result = process_row(
                row,
                cache_dirs=cache_dirs,
                fetch_missing=args.fetch,
                use_search=bool(args.search and provider),
                max_urls=args.max_urls,
                timeout=args.timeout,
                sleep_seconds=args.sleep,
            )
            report["advisors_scanned"] += 1
            report["search_urls_found"] += int(result["stats"].get("search_urls", 0) or 0)
            report["urls_considered"] += int(result["stats"].get("urls_considered", 0) or 0)
            report["cache_sources"] += int(result["stats"].get("cache_sources", 0) or 0)
            report["fetched_sources"] += int(result["stats"].get("fetched_sources", 0) or 0)
            advisor_candidates = [ContactCandidate(**item) for item in result["advisor_candidates"]]
            if advisor_candidates:
                report["advisor_email_candidates_found"] += 1
                selected = advisor_candidates[: max(1, args.max_advisor_emails)]
                for candidate in selected:
                    report["selected_advisor_emails"].append(
                        {
                            "advisor_id": result["advisor_id"],
                            "name": result["name"],
                            "institution": result["institution"],
                            "email": candidate.email,
                            "confidence": candidate.confidence,
                            "score": candidate.score,
                            "source_url": candidate.source_url,
                            "source_kind": candidate.source_kind,
                        }
                    )
                if len(report["examples_new_advisor_emails"]) < 30:
                    report["examples_new_advisor_emails"].append(
                        {
                            "advisor_id": result["advisor_id"],
                            "name": result["name"],
                            "institution": result["institution"],
                            "selected": [candidate.__dict__ for candidate in selected],
                        }
                    )
                if args.reasons_only:
                    continue
                if args.apply:
                    for index, candidate in enumerate(selected):
                        action = upsert_contact(conn, str(row["id"]), candidate, is_primary=index == 0)
                        if action == "inserted":
                            report["advisor_emails_inserted"] += 1
                        elif action == "updated_existing":
                            report["advisor_emails_updated_existing"] += 1
                continue

            report["skipped_no_advisor_email"] += 1
            reason = str(result["residual_reason"])
            report["residual_reason_counts"][reason] = report["residual_reason_counts"].get(reason, 0) + 1
            if len(report["examples_residual"]) < 30:
                report["examples_residual"].append(
                    {
                        "advisor_id": result["advisor_id"],
                        "name": result["name"],
                        "institution": result["institution"],
                        "reason": reason,
                        "source_url": result["residual_source_url"],
                        "auxiliary_candidates": result["auxiliary_candidates"][:3],
                    }
                )
            if args.apply and args.record_reasons:
                action = upsert_reason(
                    conn,
                    str(row["id"]),
                    reason,
                    str(result["residual_evidence"]),
                    str(result["residual_source_url"]),
                )
                if action == "reason_inserted":
                    report["reasons_inserted"] += 1
                else:
                    report["reasons_updated"] += 1
    report["search_error_counts"] = dict(SEARCH_ERROR_COUNTS)
    report["search_error_examples"] = SEARCH_ERROR_EXAMPLES[:]
    return report


def default_report_path(apply: bool) -> Path:
    stamp = server.utc_now().replace(":", "").replace("+", "Z")
    mode = "apply" if apply else "dryrun"
    return PLATFORM_ROOT / "data" / f"advisor_email_enrichment_{mode}_{stamp}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="补齐缺导师本人邮箱的 advisor_contacts 记录。默认 dry-run。")
    parser.add_argument("--apply", action="store_true", help="写入 MySQL advisor_contacts；默认只输出报告")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 位优先级队列导师；0 表示全量")
    parser.add_argument("--missing-only", action=argparse.BooleanOptionalAction, default=True, help="只处理尚无导师邮箱的导师")
    parser.add_argument("--fetch", action="store_true", help="缓存缺失时联网抓取已有 URL")
    parser.add_argument("--search", action="store_true", help="使用 Tavily/SerpAPI/Bing Search API 定位更多候选 URL")
    parser.add_argument("--max-urls", type=int, default=10, help="每位导师最多检查的 URL 数")
    parser.add_argument("--max-advisor-emails", type=int, default=1, help="每位导师最多写入几个导师邮箱候选")
    parser.add_argument("--timeout", type=int, default=8, help="联网请求超时时间，秒")
    parser.add_argument("--sleep", type=float, default=0.08, help="联网请求间隔，秒")
    parser.add_argument("--record-reasons", action=argparse.BooleanOptionalAction, default=True, help="未找到时记录/更新缺口原因")
    parser.add_argument("--reasons-only", action="store_true", help="只更新仍无导师邮箱的缺口原因，不写入新的导师邮箱候选")
    parser.add_argument("--progress-every", type=int, default=100, help="每处理 N 位向 stderr 输出一次进度；0 表示关闭")
    parser.add_argument("--report-path", default="", help="报告 JSON 输出路径；默认写入 07_协作平台/data")
    args = parser.parse_args()
    report = run(args)
    path = Path(args.report_path).expanduser() if args.report_path else default_report_path(args.apply)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
