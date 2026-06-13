from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import unicodedata

from config import VECTOR_DB_DIR, make_embeddings
from langchain_community.vectorstores import FAISS


CATALOG_PATH = Path("document_catalog.json")

PROCESS_AREAS = [
    "access_management",
    "access_request",
    "access_review",
    "access_revocation",
    "change_management",
    "incident_management",
    "business_continuity",
    "logging_monitoring",
    "data_protection",
    "vulnerability_management",
    "policy_governance",
    "risk_management",
    "compliance",
    "unknown",
]

PROCESS_AREA_KEYWORDS = {
    "access_management": [
        "account management",
        "quản lý tài khoản",
        "quan ly tai khoan",
        "truy cập",
        "truy cap",
        "định danh",
        "dinh danh",
        "phân quyền",
        "phan quyen",
        "ma trận phân quyền",
        "ma tran phan quyen",
        "access control",
        "permission matrix",
    ],
    "access_request": [
        "xin cấp account",
        "cấp tài khoản",
        "mở tài khoản",
        "tạo user",
        "cấp quyền",
        "xin quyền",
        "phân quyền",
        "access request",
        "access provisioning",
        "account provisioning",
        "user provisioning",
        "new account",
        "admin access",
        "privilege",
        "role",
        "permission",
    ],
    "access_review": [
        "rà soát quyền",
        "review quyền",
        "user access review",
        "uar",
        "periodic access review",
        "access rights review",
        "đánh giá ma trận phân quyền",
        "permission matrix review",
    ],
    "access_revocation": [
        "thu hồi quyền",
        "xóa quyền",
        "disable account",
        "resign",
        "nghỉ việc",
        "termination",
        "offboarding",
        "leaver",
        "staff movement",
        "thu hồi tài khoản",
    ],
    "change_management": [
        "change request",
        "production change",
        "deployment",
        "thay đổi hệ thống",
        "thay đổi production",
        "thay đổi cấu hình",
        "quản lý thay đổi",
        "emergency change",
        "rollback",
    ],
    "incident_management": [
        "sự cố",
        "incident",
        "security incident",
        "report incident",
        "xử lý sự cố",
        "quản lý sự cố",
        "escalation",
        "containment",
        "recovery",
    ],
    "business_continuity": [
        "bcp",
        "business continuity",
        "hoạt động kinh doanh liên tục",
        "kinh doanh liên tục",
        "disaster recovery",
        "failover",
        "interruption",
        "disruption",
        "recovery scenario",
    ],
    "logging_monitoring": [
        "log",
        "audit log",
        "monitoring",
        "giám sát",
        "ghi nhật ký",
        "nhật ký",
        "opensearch",
        "superset",
        "log retention",
    ],
    "data_protection": [
        "personal data",
        "pii",
        "dữ liệu cá nhân",
        "bảo vệ dữ liệu",
        "làm mờ dữ liệu",
        "data masking",
        "encryption",
        "privacy",
    ],
    "vulnerability_management": [
        "vulnerability",
        "lỗ hổng",
        "patching",
        "pentest",
        "penetration test",
        "security testing",
        "kiểm soát lỗ hổng",
    ],
    "policy_governance": [
        "policy",
        "chính sách",
        "governance",
        "quản trị",
        "isms",
        "information security policy",
    ],
    "risk_management": [
        "risk",
        "rủi ro",
        "quản lý rủi ro",
        "risk assessment",
        "risk treatment",
    ],
    "compliance": [
        "compliance",
        "tuân thủ",
        "audit",
        "đánh giá nội bộ",
        "iso 27001",
        "pci dss",
        "certification",
    ],
}

SECTION_TYPE_KEYWORDS = {
    "scope": ["phạm vi", "scope"],
    "objective": ["mục tiêu", "objective"],
    "purpose": ["mục đích", "purpose"],
    "definition": ["định nghĩa", "definition", "thuật ngữ"],
    "version_control": [
        "version control",
        "version history",
        "revision history",
        "lịch sử phiên bản",
        "lịch sử thay đổi",
    ],
    "roles_responsibilities": ["trách nhiệm", "responsibility", "roles", "owner", "pic"],
    "procedure_steps": ["quy trình", "procedure", "steps", "lưu đồ", "flowchart", "process"],
    "approval": ["phê duyệt", "approval", "approver", "approve"],
    "evidence_record": ["biểu mẫu", "evidence", "record", "hồ sơ", "bằng chứng"],
    "monitoring_review": ["giám sát", "monitoring", "review", "rà soát", "xem xét"],
    "appendix": ["phụ lục", "appendix"],
}

DISCOVERY_TERMS = [
    "tài liệu nào",
    "xem ở đâu",
    "quy trình nào",
    "policy nào",
    "where can i find",
    "which document",
    "what document",
    "which procedure",
    "which policy",
]

PROCESS_QUESTIONS = {
    "access_request": [
        "Muốn xin cấp account thì xem tài liệu nào?",
        "How do I request user access?",
        "Who approves access provisioning?",
    ],
    "access_review": [
        "Cần rà soát quyền định kỳ thì xem tài liệu nào?",
        "Where is the user access review procedure?",
    ],
    "access_revocation": [
        "User nghỉ việc thì thu hồi quyền theo tài liệu nào?",
        "How should leaver access be removed?",
    ],
    "change_management": [
        "Which procedure applies to production change?",
        "Muốn thay đổi cấu hình production thì theo quy trình nào?",
    ],
    "incident_management": [
        "Có sự cố bảo mật thì report theo tài liệu nào?",
        "How do I report a security incident?",
    ],
    "business_continuity": [
        "BCP áp dụng khi nào và xem tài liệu nào?",
        "Where can I find disaster recovery scenarios?",
    ],
    "logging_monitoring": [
        "Log giao dịch cần kiểm tra ở tài liệu nào?",
        "Where are audit log requirements defined?",
    ],
    "data_protection": [
        "Tài liệu nào nói về bảo vệ dữ liệu cá nhân?",
        "Where can I find data masking or privacy requirements?",
    ],
    "vulnerability_management": [
        "Tài liệu nào nói về kiểm soát lỗ hổng?",
        "Where is vulnerability management defined?",
    ],
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or "")).lower()
    return " ".join(text.split())


def fold_accents(text: str) -> str:
    text = str(text or "").replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def contains_text(haystack: str, needle: str) -> bool:
    haystack_norm = normalize_text(haystack)
    needle_norm = normalize_text(needle)
    if needle_norm in haystack_norm:
        return True
    return fold_accents(needle_norm) in fold_accents(haystack_norm)


def extract_document_codes(text: str) -> list[str]:
    patterns = [
        r"\b[A-Z]{2,10}-[A-Z]{2,10}-\d{2,3}\b",
        r"\bISMS-\d{2,3}\b",
    ]
    codes = []
    for pattern in patterns:
        codes.extend(re.findall(pattern, str(text or "").upper()))
    return list(dict.fromkeys(codes))


def extract_document_code(file_name: str) -> str:
    codes = extract_document_codes(file_name)
    return codes[0] if codes else ""


def clean_document_title(file_name: str, metadata_title: str | None = None) -> str:
    title = Path(file_name).stem
    title = re.sub(r"-?ThangNguyen.*$", "", title).strip(" -")
    title = re.sub(r"-?MacBook Pro.*$", "", title).strip(" -")
    title = re.sub(r"^[A-Z]{2,10}-[A-Z]{2,10}-\d{2,3}\s*[-_]\s*", "", title)
    title = re.sub(r"^ISMS-\d{2,3}\s*[-_]\s*", "", title)
    if len(title) < 4 and metadata_title:
        title = metadata_title.strip()
    return " ".join(title.split()) or Path(file_name).stem


def infer_document_type(file_name: str, title: str) -> str:
    text = fold_accents(normalize_text(f"{file_name} {title}"))
    code = extract_document_code(file_name)
    if "-QT-" in code or "quy trinh" in text or "procedure" in text:
        return "procedure"
    if "-CS-" in code or "chinh sach" in text or "policy" in text:
        return "policy"
    if "-TC-" in code or "tieu chuan" in text or "standard" in text:
        return "standard"
    if "-TL-" in code or "danh sach" in text or "list" in text:
        return "record"
    if "certification" in text or "coc" in text:
        return "certificate"
    return "document"


def detect_process_areas(text: str) -> list[str]:
    matched = []
    for area, keywords in PROCESS_AREA_KEYWORDS.items():
        if any(contains_text(text, keyword) for keyword in keywords):
            matched.append(area)
    return matched or ["unknown"]


def is_document_discovery_question(question: str) -> bool:
    folded_question = fold_accents(normalize_text(question))
    return any(fold_accents(term) in folded_question for term in DISCOVERY_TERMS)


def classify_section_type(text: str) -> str:
    folded_text = fold_accents(normalize_text(str(text or "")[:2500]))
    for section_type, keywords in SECTION_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if fold_accents(normalize_text(keyword)) in folded_text:
                return section_type
    return "unknown"


def classify_chunk_section_types(text: str) -> list[str]:
    folded_text = fold_accents(normalize_text(str(text or "")[:3000]))
    section_types = []
    for section_type, keywords in SECTION_TYPE_KEYWORDS.items():
        if any(fold_accents(normalize_text(keyword)) in folded_text for keyword in keywords):
            section_types.append(section_type)
    return section_types or ["unknown"]


def extract_version_values(text: str) -> list[str]:
    values = re.findall(r"\b\d+(?:\.\d+){1,2}\b", text or "")
    return list(dict.fromkeys(values))


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def latest_version(versions: list[str]) -> str:
    if not versions:
        return ""
    return max(versions, key=version_key)


def extract_person_after_label(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]\s*([^\n\r|]+)"
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            value = " ".join(match.group(1).strip().split())
            return value[:120]
    return ""


def extract_effective_date(text: str) -> str:
    patterns = [
        r"(?:effective date|ngày hiệu lực|ngay hieu luc)\s*[:：]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
        r"(?:effective date|ngày hiệu lực|ngay hieu luc)\s*[:：]?\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(1).split())
    return ""


def extract_heading_lines(text: str) -> list[str]:
    headings = []
    for line in (text or "").splitlines():
        clean = " ".join(line.strip().split())
        if not clean or len(clean) > 140:
            continue
        folded = fold_accents(normalize_text(clean))
        if re.match(r"^\d+(?:\.\d+)*\.?\s+\S+", folded) or any(
            fold_accents(normalize_text(keyword)) in folded
            for keywords in SECTION_TYPE_KEYWORDS.values()
            for keyword in keywords
        ):
            headings.append(clean)
    return list(dict.fromkeys(headings))[:30]


def extract_section_summary(chunks: list[dict], section_type: str, max_chars: int = 450) -> str:
    for chunk in chunks:
        if section_type not in chunk["section_types"]:
            continue
        text = " ".join((chunk["content"] or "").split())
        if not text:
            continue
        return text[:max_chars].strip()
    return ""


def source_pages_for_chunks(chunks: list[dict]) -> list[int]:
    pages = []
    for chunk in chunks:
        page = chunk.get("page")
        if isinstance(page, int):
            pages.append(page + 1)
    return sorted(set(pages))


def keyword_matches_for_document(file_name: str, title: str, full_text: str) -> tuple[list[str], list[str]]:
    title_text = f"{file_name}\n{title}"
    body_text = full_text[:12000]
    area_scores = []
    matched_keywords = []
    for area, keywords in PROCESS_AREA_KEYWORDS.items():
        area_terms = []
        score = 0
        for keyword in keywords:
            if contains_text(title_text, keyword):
                score += 20
                area_terms.append(keyword)
            elif contains_text(body_text, keyword):
                score += 1
                area_terms.append(keyword)
        if area_terms:
            area_scores.append((area, score))
            matched_keywords.extend(area_terms)
    area_scores.sort(key=lambda item: (-item[1], PROCESS_AREAS.index(item[0]) if item[0] in PROCESS_AREAS else 999))
    matched_areas = [area for area, _score in area_scores]
    return matched_areas or ["unknown"], sorted(set(matched_keywords))


def likely_questions_for_areas(process_areas: list[str]) -> list[str]:
    questions = []
    for area in process_areas:
        questions.extend(PROCESS_QUESTIONS.get(area, []))
    return list(dict.fromkeys(questions))[:8]


def catalog_entry_from_chunks(file_name: str, chunks: list[dict], metadata: dict) -> dict:
    full_text = "\n".join(chunk["content"] for chunk in chunks)
    document_code = extract_document_code(file_name)
    document_title = clean_document_title(file_name, metadata.get("title"))
    document_type = infer_document_type(file_name, document_title)
    process_areas, keywords = keyword_matches_for_document(file_name, document_title, full_text)
    versions = extract_version_values(full_text[:12000])
    section_counter = Counter(section for chunk in chunks for section in chunk["section_types"])
    key_sections = extract_heading_lines(full_text[:18000])

    return {
        "document_code": document_code,
        "document_title": document_title,
        "file_name": file_name,
        "document_type": document_type,
        "version": latest_version(versions),
        "latest_version": latest_version(versions),
        "author": extract_person_after_label(full_text[:12000], ["Author", "Author(s)", "Tác giả", "Tac gia"]),
        "reviewer": extract_person_after_label(full_text[:12000], ["Reviewer", "Người rà soát", "Nguoi ra soat"]),
        "approver": extract_person_after_label(full_text[:12000], ["Approver", "Người phê duyệt", "Nguoi phe duyet"]),
        "effective_date": extract_effective_date(full_text[:12000]),
        "scope_summary": extract_section_summary(chunks, "scope"),
        "purpose_summary": extract_section_summary(chunks, "purpose") or extract_section_summary(chunks, "objective"),
        "key_sections": key_sections,
        "keywords": keywords[:40],
        "process_area": process_areas[0],
        "process_areas": process_areas,
        "section_types": dict(section_counter),
        "likely_user_questions": likely_questions_for_areas(process_areas),
        "source_pages": source_pages_for_chunks(chunks),
    }


def load_vector_store_from_disk():
    return FAISS.load_local(
        str(VECTOR_DB_DIR),
        make_embeddings(),
        allow_dangerous_deserialization=True,
    )


def build_document_catalog(vector_store=None) -> list[dict]:
    vector_store = vector_store or load_vector_store_from_disk()
    grouped_chunks: dict[str, list[dict]] = defaultdict(list)
    grouped_metadata: dict[str, dict] = {}

    for document in vector_store.docstore._dict.values():
        file_name = Path(document.metadata.get("source", "unknown")).name
        grouped_metadata.setdefault(file_name, dict(document.metadata))
        grouped_chunks[file_name].append(
            {
                "content": document.page_content or "",
                "page": document.metadata.get("page"),
                "section_type": classify_section_type(document.page_content),
                "section_types": classify_chunk_section_types(document.page_content),
            }
        )

    catalog = []
    for file_name in sorted(grouped_chunks):
        chunks = sorted(
            grouped_chunks[file_name],
            key=lambda chunk: chunk["page"] if isinstance(chunk.get("page"), int) else 999999,
        )
        catalog.append(catalog_entry_from_chunks(file_name, chunks, grouped_metadata[file_name]))

    return catalog


def save_document_catalog(catalog: list[dict], path: Path = CATALOG_PATH) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vector_db_dir": str(VECTOR_DB_DIR),
        "document_count": len(catalog),
        "documents": catalog,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_document_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return payload.get("documents", [])


def catalog_document_label(entry: dict) -> str:
    code = entry.get("document_code")
    title = entry.get("document_title") or entry.get("file_name")
    return f"{code} - {title}" if code else str(title)


def score_catalog_entry(question: str, entry: dict) -> tuple[int, list[str]]:
    title_text = "\n".join(
        [
            entry.get("document_code", ""),
            entry.get("document_title", ""),
            entry.get("file_name", ""),
        ]
    )
    search_text = "\n".join(
        [
            title_text,
            " ".join(entry.get("process_areas", [])),
            " ".join(entry.get("keywords", [])),
            " ".join(entry.get("key_sections", [])),
            " ".join(entry.get("likely_user_questions", [])),
        ]
    )
    question_areas = detect_process_areas(question)
    matched_terms = []
    score = 0

    def title_matches_area(area: str) -> bool:
        keywords = list(PROCESS_AREA_KEYWORDS.get(area, []))
        if area.startswith("access_"):
            keywords.extend(PROCESS_AREA_KEYWORDS.get("access_management", []))
        return any(contains_text(title_text, keyword) for keyword in keywords)

    for code in extract_document_codes(question):
        if code and code == entry.get("document_code"):
            score += 100
            matched_terms.append(code)

    for area in question_areas:
        if area == "unknown":
            continue
        entry_primary_area = entry.get("process_area")
        entry_areas = entry.get("process_areas", [])
        if area == entry_primary_area:
            score += 50 if title_matches_area(area) else 15
            matched_terms.append(area)
        elif area.startswith("access_") and entry_primary_area == "access_management":
            score += 45 if title_matches_area(area) else 20
            matched_terms.append("access_management")
        elif area in entry_areas:
            score += 12
            matched_terms.append(area)

    for area in question_areas:
        for keyword in PROCESS_AREA_KEYWORDS.get(area, []):
            if not contains_text(question, keyword):
                continue
            if contains_text(title_text, keyword):
                score += 30
                matched_terms.append(keyword)
            elif contains_text(search_text, keyword):
                score += 2
                matched_terms.append(keyword)

    for token in fold_accents(normalize_text(question)).split():
        if len(token) >= 5 and token in fold_accents(normalize_text(search_text)):
            score += 1

    return score, list(dict.fromkeys(matched_terms))


def find_catalog_candidates(question: str, catalog: list[dict], limit: int = 5) -> list[dict]:
    scored = []
    for entry in catalog:
        score, matched_terms = score_catalog_entry(question, entry)
        if score <= 0:
            continue
        candidate = dict(entry)
        candidate["catalog_score"] = score
        candidate["matched_terms"] = matched_terms
        scored.append(candidate)

    scored.sort(
        key=lambda item: (
            -int(item.get("catalog_score", 0)),
            item.get("document_code") or item.get("document_title") or item.get("file_name"),
        )
    )
    deduped = []
    seen = set()
    for item in scored:
        key = item.get("document_code") or item.get("document_title") or item.get("file_name")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break

    return deduped
