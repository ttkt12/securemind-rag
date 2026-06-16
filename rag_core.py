from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import re
import unicodedata

from config import (
    AI_BASE_URL,
    AI_MODEL,
    ANSWER_LANGUAGE,
    DEBUG_RETRIEVAL,
    EXCLUDED_SOURCE_SUBSTRINGS,
    MAX_CONTEXT_CHARS,
    MAX_TOKENS,
    MIN_RELEVANCE_SCORE,
    RETRIEVAL_FETCH_K,
    RETRIEVAL_K,
    SHOW_USAGE,
    VECTOR_DB_DIR,
    get_api_key,
    make_embeddings,
)
from context_budget import build_context_budget
from document_intelligence import (
    classify_chunk_section_types,
    classify_section_type,
    find_catalog_candidates,
    load_document_catalog,
)
from langchain_community.vectorstores import FAISS
from openai import APIStatusError, OpenAI

NO_RELEVANT_CONTEXT_ANSWER = "Không tìm thấy thông tin này trong tài liệu hiện có."
EMPTY_FINAL_ANSWER = (
    "Model đã xác thực và truy xuất được tài liệu liên quan, nhưng không trả về "
    "nội dung trả lời cuối cùng. Hãy thử tăng MAX_TOKENS hoặc hỏi ngắn hơn."
)


@dataclass
class QueryAnalysis:
    raw_question: str
    normalized_question: str
    document_codes: list[str] = field(default_factory=list)
    requested_versions: list[str] = field(default_factory=list)
    requested_sections: list[str] = field(default_factory=list)
    requested_entities: list[str] = field(default_factory=list)
    requested_roles: list[str] = field(default_factory=list)
    requested_dates: list[str] = field(default_factory=list)
    requested_count: int | None = None
    intent: str = "lookup_fact"
    operational_intents: list[str] = field(default_factory=list)
    process_areas: list[str] = field(default_factory=list)
    catalog_candidates: list[dict] = field(default_factory=list)
    document_discovery_mode: bool = False
    confidence: str = "medium"
    is_follow_up: bool = False
    needs_clarification: bool = False
    clarification_question: str = ""
    expanded_query: str = ""


OPERATIONAL_INTENT_KEYWORDS = {
    "access_request": [
        "cap quyen",
        "cap account",
        "tai khoan",
        "phan quyen",
        "quyen truy cap",
        "mo quyen",
        "xin quyen",
        "request quyen",
        "user access",
        "access request",
        "access provisioning",
        "provisioning",
        "account provisioning",
        "new account",
        "admin access",
        "permission",
        "role",
        "privilege",
        "authorization",
        "authorize",
        "authorisation",
        "system access",
        "production access",
    ],
    "access_review": [
        "uar",
        "user access review",
        "access rights review",
        "periodic access review",
        "review quyen",
        "ra soat quyen",
        "kiem tra quyen",
        "dinh ky",
        "excessive access",
        "user list review",
    ],
    "access_revocation": [
        "thu hoi quyen",
        "xoa quyen",
        "remove access",
        "revoke access",
        "disable account",
        "nghi viec",
        "resign",
        "termination",
        "offboarding",
        "staff movement",
        "mover",
        "leaver",
    ],
    "change_management": [
        "change management",
        "production change",
        "system change",
        "configuration change",
        "thay doi cau hinh",
        "thay doi he thong",
        "deployment",
        "deploy",
        "emergency change",
        "change request",
        "rollback",
    ],
    "incident_management": [
        "incident",
        "security incident",
        "su co",
        "su co bao mat",
        "report incident",
        "bao cao su co",
        "escalation",
        "response",
        "containment",
        "recovery",
    ],
    "business_continuity": [
        "bcp",
        "business continuity",
        "disaster recovery",
        "drp",
        "failover",
        "continuity",
        "interruption",
        "disruption",
        "recovery scenario",
    ],
    "logging_monitoring": [
        "log",
        "logs",
        "audit log",
        "audit logs",
        "monitoring",
        "giam sat",
        "nhat ky",
        "nhật ký",
        "opensearch",
        "superset",
        "log retention",
        "transaction log",
        "giao dich",
    ],
    "data_protection": [
        "personal data",
        "pii",
        "du lieu ca nhan",
        "data disclosure",
        "data masking",
        "encryption",
        "privacy",
        "bao mat du lieu",
    ],
    "vulnerability_management": [
        "vulnerability",
        "patching",
        "pentest",
        "penetration test",
        "security testing",
        "lo hong",
        "ban va",
    ],
    "password_policy": [
        "mat khau",
        "password",
        "passcode",
        "pin",
        "credential",
        "credentials",
        "xac thuc",
        "authentication",
        "dang nhap",
        "login",
        "tai khoan",
        "account",
        "do dai mat khau",
        "password length",
        "do phuc tap mat khau",
        "password complexity",
        "password expiration",
        "password expiry",
        "het han mat khau",
        "password policy",
        "password requirement",
        "password requirements",
    ],
    "policy_lookup": [
        "tai lieu nao",
        "o tai lieu nao",
        "xem o dau",
        "quy trinh nao",
        "policy nao",
        "which document",
        "where can i find",
        "what document",
        "which policy",
        "which procedure",
    ],
    "how_to": [
        "lam sao",
        "lam the nao",
        "can lam gi",
        "request nhu the nao",
        "ai approve",
        "ai phe duyet",
        "ticket can",
        "ticket gom",
        "how to",
        "what should i do",
        "what do i need",
    ],
}

OPERATIONAL_QUERY_EXPANSIONS = {
    "access_request": [
        "cấp quyền",
        "cấp account",
        "tài khoản",
        "quản lý tài khoản",
        "quy trình quản lý tài khoản",
        "phân quyền",
        "user access",
        "access request",
        "access provisioning",
        "account management",
        "account provisioning",
        "new account",
        "quyền truy cập",
        "admin access",
        "privilege",
        "role",
        "approval",
        "approver",
        "ticket",
        "request",
        "authorization",
        "authorize",
        "access control",
        "joiner",
        "mover",
        "leaver",
    ],
    "access_revocation": [
        "thu hồi quyền",
        "thu hồi tài khoản",
        "revoke access",
        "disable account",
        "nghỉ việc",
        "resign",
        "termination",
        "offboarding",
        "staff movement",
        "leaver",
    ],
    "access_review": [
        "user access review",
        "UAR",
        "review quyền",
        "rà soát quyền",
        "đánh giá quyền",
        "phân quyền",
        "ma trận phân quyền",
        "đánh giá ma trận phân quyền",
        "periodic review",
        "access rights review",
        "permission matrix",
    ],
    "change_management": [
        "change management",
        "quản lý thay đổi",
        "thay đổi",
        "thay đổi cấu hình",
        "cấu hình production",
        "production change",
        "deployment",
        "emergency change",
        "change request",
        "approval",
        "rollback",
    ],
    "incident_management": [
        "incident",
        "sự cố",
        "xử lý sự cố",
        "xử lý sự cố bảo mật",
        "quản lý sự cố bảo mật",
        "report incident",
        "escalation",
        "response",
        "containment",
        "recovery",
    ],
    "business_continuity": [
        "BCP",
        "business continuity",
        "kinh doanh liên tục",
        "hoạt động kinh doanh liên tục",
        "disaster recovery",
        "failover",
        "interruption",
        "scenario",
    ],
    "logging_monitoring": [
        "logs",
        "log giao dịch",
        "nhật ký",
        "ghi nhật ký",
        "giám sát",
        "giám sát bảo mật",
        "audit logs",
        "monitoring",
        "OpenSearch",
        "Superset",
        "log retention",
        "nhat ky",
        "nhật ký",
        "security monitoring",
        "event monitoring",
    ],
    "data_protection": [
        "personal data",
        "PII",
        "data disclosure",
        "data masking",
        "encryption",
        "privacy",
    ],
    "vulnerability_management": [
        "vulnerability",
        "patching",
        "VA",
        "pentest",
        "security testing",
    ],
    "password_policy": [
        "mat khau",
        "password",
        "passcode",
        "PIN",
        "credential",
        "credentials",
        "xac thuc",
        "authentication",
        "dang nhap",
        "login",
        "tai khoan",
        "account",
        "do dai mat khau",
        "password length",
        "password complexity",
        "password expiration",
        "password expiry",
        "password policy",
        "password requirements",
    ],
    "policy_lookup": [
        "document",
        "policy",
        "procedure",
        "standard",
        "tài liệu",
        "chính sách",
        "quy trình",
        "tiêu chuẩn",
    ],
    "how_to": [
        "procedure",
        "process",
        "approval",
        "owner",
        "PIC",
        "steps",
        "ticket",
        "quy trình",
        "phê duyệt",
        "các bước",
    ],
}

OPERATIONAL_PRIMARY_INTENTS = [
    "access_review",
    "access_revocation",
    "access_request",
    "change_management",
    "incident_management",
    "business_continuity",
    "logging_monitoring",
    "data_protection",
    "vulnerability_management",
    "password_policy",
    "policy_lookup",
    "how_to",
]

OPERATIONAL_META_INTENTS = {"policy_lookup", "how_to"}

OPERATIONAL_SOURCE_TERMS = [
    "account",
    "access",
    "tai khoan",
    "phan quyen",
    "user",
    "change",
    "incident",
    "continuity",
    "bcp",
    "logging",
    "monitoring",
    "vulnerability",
    "data",
    "security",
    "password",
    "mat khau",
    "credential",
    "authentication",
    "login",
    "account",
]

INTENT_SECTION_PRIORITIES = {
    "access_request": ["procedure_steps", "approval", "roles_responsibilities"],
    "access_review": ["monitoring_review", "procedure_steps", "roles_responsibilities"],
    "access_revocation": ["procedure_steps", "approval", "roles_responsibilities"],
    "change_management": ["procedure_steps", "approval", "roles_responsibilities"],
    "incident_management": ["procedure_steps", "roles_responsibilities", "monitoring_review"],
    "business_continuity": ["scope", "appendix", "procedure_steps", "roles_responsibilities"],
    "logging_monitoring": ["scope", "monitoring_review", "procedure_steps"],
    "data_protection": ["scope", "procedure_steps", "roles_responsibilities"],
    "vulnerability_management": ["procedure_steps", "monitoring_review", "evidence_record"],
    "password_policy": ["scope", "policy", "procedure_steps", "monitoring_review"],
    "policy_lookup": ["scope", "purpose", "procedure_steps"],
    "how_to": ["procedure_steps", "approval", "roles_responsibilities"],
    "version_author_mapping": ["version_control"],
    "versions_count": ["version_control"],
    "versions_list": ["version_control"],
    "version_latest": ["version_control"],
    "find_responsibility": ["roles_responsibilities"],
    "explain_process": ["procedure_steps"],
}


def make_client() -> OpenAI:
    return OpenAI(
        base_url=AI_BASE_URL,
        api_key=get_api_key(),
    )


def load_vector_store():
    index_file = VECTOR_DB_DIR / "index.faiss"
    metadata_file = VECTOR_DB_DIR / "index.pkl"
    if not index_file.exists() or not metadata_file.exists():
        raise FileNotFoundError(
            f"Cannot find vector database in {VECTOR_DB_DIR.resolve()}.\n"
            "Run this first after adding PDFs:\n"
            "  python ingest.py"
        )

    # FAISS metadata is stored with pickle, so only load indexes created locally.
    return FAISS.load_local(
        str(VECTOR_DB_DIR),
        make_embeddings(),
        allow_dangerous_deserialization=True,
    )


def format_context_with_metadata(documents) -> tuple[str, dict]:
    result = build_context_budget(
        documents,
        max_chars=MAX_CONTEXT_CHARS,
        source_name_fn=document_source_name,
        document_code_fn=extract_document_code_from_source,
    )
    return result.context, result.metadata()


def format_context(documents) -> str:
    context, _metadata = format_context_with_metadata(documents)
    return context


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or "")).lower()
    return " ".join(text.split())


def fold_accents(text: str) -> str:
    text = str(text or "").replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", str(text or ""))
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def contains_text(haystack: str, needle: str) -> bool:
    normalized_haystack = normalize_for_match(haystack)
    normalized_needle = normalize_for_match(needle)
    if normalized_needle in normalized_haystack:
        return True

    return fold_accents(normalized_needle) in fold_accents(normalized_haystack)


def extract_document_codes(question: str) -> list[str]:
    # Legacy strict 3-part matcher (kept so full codes behave exactly as before).
    legacy = list(dict.fromkeys(re.findall(r"\b[A-Z]{2,10}-[A-Z]{2,10}-\d{2,3}\b", question.upper())))
    # Shared resolver adds canonical + shorthand/reordered codes (e.g. "QT-04",
    # "TC-ZION-13") resolved against the catalog. Both forms are kept; downstream
    # document_matches_code() matches if ANY form is found in the filename.
    try:
        from document_code_utils import extract_document_codes as resolve_codes

        shared = resolve_codes(question)
    except Exception:
        shared = []
    return list(dict.fromkeys([*legacy, *shared]))


def extract_requested_versions(question: str) -> list[str]:
    folded_question = fold_accents(normalize_for_match(question))
    patterns = [
        r"\b(?:version|ver|v|phien ban|ban)\s*([0-9]+(?:\.[0-9]+)+)\b",
        r"\b([0-9]+(?:\.[0-9]+)+)\b",
    ]
    versions = []
    for pattern in patterns:
        versions.extend(re.findall(pattern, folded_question))

    return list(dict.fromkeys(versions))


def detect_requested_roles(question: str) -> list[str]:
    folded_question = fold_accents(normalize_for_match(question))
    role_patterns = [
        ("author", ["tac gia", "nguoi soan", "nguoi tao", "nguoi cap nhat", "ai cap nhat", "do ai cap nhat", "author", "created by", "prepared by", "updated by"]),
        ("reviewer", ["reviewer", "nguoi ra soat", "ra soat", "review"]),
        ("approver", ["approver", "nguoi phe duyet", "phe duyet", "approve", "approval"]),
        ("owner", ["owner", "nguoi phu trach", "pic", "responsible", "trach nhiem"]),
    ]
    roles = []
    for role, patterns in role_patterns:
        if any(pattern in folded_question for pattern in patterns):
            roles.append(role)

    return list(dict.fromkeys(roles))


def detect_requested_dates(question: str) -> list[str]:
    date_patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    dates = []
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, question))

    return list(dict.fromkeys(dates))


def detect_requested_count(question: str) -> int | None:
    folded_question = fold_accents(normalize_for_match(question))
    if any(term in folded_question for term in ("bao nhieu", "how many", "count", "so luong")):
        return 0

    return None


def detect_requested_entities(question: str) -> list[str]:
    folded_question = fold_accents(normalize_for_match(question))
    entities = []
    entity_patterns = [
        ("scenario", r"\b(?:scenario|kich ban)\s*([0-9]+)\b"),
        ("control", r"\b(?:control|kiem soat)\s*([0-9]+(?:\.[0-9]+)*)\b"),
        ("step", r"\b(?:step|buoc)\s*([0-9]+)\b"),
    ]
    for label, pattern in entity_patterns:
        for match in re.findall(pattern, folded_question):
            entities.append(f"{label}:{match}")

    return list(dict.fromkeys(entities))


def is_follow_up_question(question: str) -> bool:
    folded_question = fold_accents(normalize_for_match(question))
    follow_up_terms = [
        "vay",
        "the con",
        "con",
        "cai nay",
        "no",
        "version",
        "ver",
        "v",
        "what about",
        "tell me more",
        "noi ro",
        "ro hon",
        "phan",
        "muc",
        "y thu",
    ]
    return len(folded_question.split()) <= 10 or any(term in folded_question for term in follow_up_terms)


def has_count_terms(text: str) -> bool:
    folded_text = fold_accents(normalize_for_match(text))
    return any(term in folded_text for term in ("bao nhieu", "how many", "so luong")) or bool(re.search(r"\bcount\b", folded_text))


def has_list_all_terms(text: str) -> bool:
    folded_text = fold_accents(normalize_for_match(text))
    return any(
        term in folded_text
        for term in ("tat ca", "toan bo", "liet ke", "ke", "ke ten", "danh sach", "all", "list")
    )


def has_version_terms(text: str) -> bool:
    folded_text = fold_accents(normalize_for_match(text))
    return any(term in folded_text for term in ("phien ban", "version", "ver")) or bool(re.search(r"\bv\s*\d", folded_text))


def has_version_author_mapping_terms(text: str) -> bool:
    folded_text = fold_accents(normalize_for_match(text))
    mapping_terms = (
        "tuong ung",
        "corresponding",
        "voi version do",
        "moi version",
        "moi phien ban",
        "theo tung version",
        "cac version",
        "versions and authors",
        "version va tac gia",
        "phien ban va tac gia",
    )
    return has_list_all_terms(text) or any(term in folded_text for term in mapping_terms)


def has_latest_terms(text: str) -> bool:
    folded_text = fold_accents(normalize_for_match(text))
    return any(term in folded_text for term in ("moi nhat", "latest", "newest", "gan nhat"))


def is_author_intent(question: str) -> bool:
    folded_question = fold_accents(normalize_for_match(question))
    author_terms = [
        "tac gia",
        "t?c gi",
        "nguoi soan",
        "nguoi tao",
        "nguoi cap nhat",
        "ai cap nhat",
        "do ai cap nhat",
        "author",
        "created by",
        "prepared by",
        "updated by",
    ]
    if any(term in folded_question for term in author_terms):
        return True

    return bool(re.search(r"t.?c\s+gi", folded_question))


def extract_document_code_from_source(source: str) -> str:
    codes = extract_document_codes(Path(str(source or "")).name.upper())
    return codes[0] if codes else ""


def detect_document_discovery_mode(question: str) -> bool:
    folded_question = fold_accents(normalize_for_match(question))
    return any(term in folded_question for term in OPERATIONAL_INTENT_KEYWORDS["policy_lookup"])


def detect_process_areas_from_intents(intents: list[str]) -> list[str]:
    intent_to_area = {
        "access_request": "access_request",
        "access_review": "access_review",
        "access_revocation": "access_revocation",
        "change_management": "change_management",
        "incident_management": "incident_management",
        "business_continuity": "business_continuity",
        "logging_monitoring": "logging_monitoring",
        "data_protection": "data_protection",
        "vulnerability_management": "vulnerability_management",
        "password_policy": "password_policy",
    }
    areas = [intent_to_area[intent] for intent in intents if intent in intent_to_area]
    return list(dict.fromkeys(areas))


def detect_operational_intents(question: str) -> list[str]:
    folded_question = fold_accents(normalize_for_match(question))
    intents = []
    for intent in OPERATIONAL_PRIMARY_INTENTS:
        keywords = OPERATIONAL_INTENT_KEYWORDS.get(intent, [])
        if any(keyword in folded_question for keyword in keywords):
            intents.append(intent)

    if "policy_lookup" in intents and len(intents) > 1:
        intents.append(intents.pop(intents.index("policy_lookup")))
    if "how_to" in intents and len(intents) > 1:
        intents.append(intents.pop(intents.index("how_to")))

    return list(dict.fromkeys(intents))


def primary_operational_intent(analysis: QueryAnalysis) -> str | None:
    for intent in OPERATIONAL_PRIMARY_INTENTS:
        if intent in analysis.operational_intents:
            return intent
    return analysis.operational_intents[0] if analysis.operational_intents else None


def operational_keywords_from_analysis(analysis: QueryAnalysis) -> list[str]:
    keywords = []
    specific_intents = [
        intent for intent in analysis.operational_intents if intent not in OPERATIONAL_META_INTENTS
    ]
    intents_to_expand = specific_intents or analysis.operational_intents
    for intent in intents_to_expand:
        keywords.extend(OPERATIONAL_QUERY_EXPANSIONS.get(intent, []))
        keywords.extend(OPERATIONAL_INTENT_KEYWORDS.get(intent, []))
    if analysis.document_discovery_mode and not specific_intents:
        keywords.extend(OPERATIONAL_QUERY_EXPANSIONS["policy_lookup"])

    return list(dict.fromkeys(keywords))


def relevant_section_types(analysis: QueryAnalysis) -> list[str]:
    section_types = []
    if "scope" in analysis.requested_sections:
        section_types.append("scope")
    if "purpose" in analysis.requested_sections:
        section_types.extend(["purpose", "objective"])
    if "responsibility" in analysis.requested_sections or "owner" in analysis.requested_sections:
        section_types.append("roles_responsibilities")
    if "approval" in analysis.requested_sections or "approver" in analysis.requested_roles:
        section_types.append("approval")
    if "process" in analysis.requested_sections:
        section_types.append("procedure_steps")
    if "update_history" in analysis.requested_sections or analysis.requested_versions:
        section_types.append("version_control")

    section_types.extend(INTENT_SECTION_PRIORITIES.get(analysis.intent, []))
    for intent in analysis.operational_intents:
        section_types.extend(INTENT_SECTION_PRIORITIES.get(intent, []))

    return list(dict.fromkeys(section_types))


def expand_query(question: str, analysis: QueryAnalysis | None = None) -> str:
    folded_question = fold_accents(normalize_for_match(question))
    expansions = []
    roles = analysis.requested_roles if analysis else detect_requested_roles(question)
    sections = analysis.requested_sections if analysis else detect_requested_sections(question)
    versions = analysis.requested_versions if analysis else extract_requested_versions(question)
    document_codes = analysis.document_codes if analysis else extract_document_codes(question)
    operational_intents = analysis.operational_intents if analysis else detect_operational_intents(question)

    section_expansions = {
        "scope": ["scope", "phạm vi áp dụng", "phạm vi"],
        "purpose": ["purpose", "mục đích"],
        "responsibility": ["responsibility", "responsible", "trách nhiệm", "người chịu trách nhiệm"],
        "definition": ["definition", "định nghĩa", "thuật ngữ"],
        "process": ["process", "procedure", "quy trình"],
        "approval": ["approval", "approve", "phê duyệt"],
        "review": ["review", "rà soát", "xem xét"],
        "risk": ["risk", "rủi ro"],
        "scenario": ["scenario", "kịch bản"],
        "control": ["control", "kiểm soát"],
        "evidence": ["evidence", "bằng chứng"],
        "frequency": ["frequency", "tần suất"],
        "owner": ["owner", "PIC", "người phụ trách"],
        "effective_date": ["effective date", "ngày hiệu lực"],
        "update_history": ["update history", "version history", "revision history", "lịch sử thay đổi", "lịch sử phiên bản"],
    }
    role_expansions = {
        "author": ["tác giả", "người soạn", "người cập nhật", "author", "prepared by", "updated by", "version history", "version control"],
        "reviewer": ["reviewer", "người rà soát"],
        "approver": ["approver", "người phê duyệt"],
        "owner": ["owner", "PIC", "người phụ trách", "trách nhiệm"],
    }

    for section in sections:
        expansions.extend(section_expansions.get(section, [section]))
    for role in roles:
        expansions.extend(role_expansions.get(role, [role]))
    for version in versions:
        expansions.extend([f"version {version}", f"phiên bản {version}", f"v{version}"])
    if analysis and analysis.intent in {
        "version_author_mapping",
        "author_latest",
        "author_specific_version",
        "authors_all",
        "versions_count",
        "versions_list",
        "version_latest",
    }:
        expansions.extend(
            [
                "lịch sử phiên bản",
                "lịch sử thay đổi",
                "version history",
                "revision history",
                "change history",
                "version",
                "phiên bản",
                "author",
                "tác giả",
                "reviewer",
                "approver",
            ]
        )
    if analysis and analysis.intent == "authors_all":
        expansions.extend(["tất cả tác giả", "danh sách tác giả", "liệt kê tác giả"])
    if analysis and analysis.intent == "version_author_mapping":
        expansions.extend(
            [
                "version và tác giả",
                "phiên bản và tác giả",
                "tác giả tương ứng",
                "corresponding authors",
                "versions and authors",
                "version history author",
                "version control author",
            ]
        )
    if analysis and analysis.intent in {"versions_count", "versions_list"}:
        expansions.extend(["các phiên bản", "danh sách phiên bản", "version history"])

    specific_operational_intents = [
        intent for intent in operational_intents if intent not in OPERATIONAL_META_INTENTS
    ]
    intents_to_expand = specific_operational_intents or operational_intents
    for intent in intents_to_expand:
        expansions.extend(OPERATIONAL_QUERY_EXPANSIONS.get(intent, []))
        expansions.extend(OPERATIONAL_INTENT_KEYWORDS.get(intent, []))
    if analysis and analysis.document_discovery_mode and not specific_operational_intents:
        expansions.extend(OPERATIONAL_QUERY_EXPANSIONS["policy_lookup"])

    if is_author_intent(question):
        expansions.extend(
            [
                "tác giả",
                "người soạn",
                "người cập nhật",
                "lịch sử phiên bản",
                "lịch sử thay đổi",
                "phiên bản",
                "version history",
                "version control",
                "revision history",
                "change history",
                "author",
                "prepared by",
                "updated by",
                "reviewer",
                "approver",
            ]
        )

    expansion_rules = [
        (r"\bscope\b", ["phạm vi áp dụng", "phạm vi"]),
        (r"\bpurpose\b", ["mục đích"]),
        (r"\bresponsibilit(?:y|ies)\b|\bresponsible\b", ["trách nhiệm", "người chịu trách nhiệm"]),
        (r"\bdefinition\b", ["định nghĩa", "thuật ngữ"]),
        (r"\bapproval\b|\bapprove\b", ["phê duyệt"]),
        (r"\breview\b", ["rà soát", "xem xét"]),
        (r"\bprocess\b|\bprocedure\b", ["quy trình"]),
    ]

    for pattern, keywords in expansion_rules:
        if re.search(pattern, folded_question):
            expansions.extend(keywords)

    if not expansions:
        return question

    expanded_terms = list(dict.fromkeys(expansions + document_codes))
    return f"{question}\n{' '.join(expanded_terms)}"


def detect_requested_sections(question: str) -> list[str]:
    folded_question = fold_accents(normalize_for_match(question))
    section_groups = [
        ("scope", [r"\bscope\b", "pham vi"]),
        ("purpose", [r"\bpurpose\b", "muc dich"]),
        ("responsibility", [r"\bresponsibilit(?:y|ies)\b", r"\bresponsible\b", "trach nhiem"]),
        ("definition", [r"\bdefinition\b", "dinh nghia", "thuat ngu"]),
        ("approval", [r"\bapproval\b", r"\bapprove\b", "phe duyet"]),
        ("review", [r"\breview\b", "ra soat", "xem xet"]),
        ("process", [r"\bprocess\b", r"\bprocedure\b", "quy trinh"]),
        ("risk", [r"\brisk\b", "rui ro"]),
        ("scenario", [r"\bscenario\b", "kich ban"]),
        ("control", [r"\bcontrol\b", "kiem soat"]),
        ("evidence", [r"\bevidence\b", "bang chung"]),
        ("frequency", [r"\bfrequency\b", "tan suat"]),
        ("owner", [r"\bowner\b", "nguoi phu trach", r"\bpic\b"]),
        ("effective_date", [r"\beffective date\b", "ngay hieu luc"]),
        ("update_history", ["lich su thay doi", "lich su phien ban", "version history", "revision history", "change history"]),
    ]

    sections = []
    for section, triggers in section_groups:
        if any(re.search(trigger, folded_question) for trigger in triggers):
            sections.append(section)

    return list(dict.fromkeys(sections))


def section_keywords_from_analysis(analysis: QueryAnalysis) -> list[str]:
    keyword_map = {
        "scope": ["phạm vi áp dụng", "phạm vi", "scope"],
        "purpose": ["mục đích", "purpose"],
        "responsibility": ["trách nhiệm", "người chịu trách nhiệm", "responsibility"],
        "definition": ["định nghĩa", "thuật ngữ", "definition"],
        "approval": ["phê duyệt", "approval", "approve"],
        "review": ["rà soát", "xem xét", "review"],
        "process": ["quy trình", "process", "procedure"],
        "risk": ["rủi ro", "risk"],
        "scenario": ["kịch bản", "scenario"],
        "control": ["kiểm soát", "control"],
        "evidence": ["bằng chứng", "evidence"],
        "frequency": ["tần suất", "frequency"],
        "owner": ["người phụ trách", "PIC", "owner"],
        "effective_date": ["ngày hiệu lực", "effective date"],
        "update_history": ["lịch sử phiên bản", "lịch sử thay đổi", "version history", "version control", "revision history", "change history"],
    }
    role_keywords = {
        "author": ["tác giả", "người soạn", "người cập nhật", "author", "author(s)", "prepared by", "updated by", "version", "version control"],
        "reviewer": ["reviewer", "người rà soát"],
        "approver": ["approver", "người phê duyệt"],
        "owner": ["owner", "PIC", "người phụ trách"],
    }

    keywords = []
    for section in analysis.requested_sections:
        keywords.extend(keyword_map.get(section, [section]))
    for role in analysis.requested_roles:
        keywords.extend(role_keywords.get(role, [role]))
    for version in analysis.requested_versions:
        keywords.extend([version, f"version {version}", f"phiên bản {version}"])
    if analysis.intent in {"version_author_mapping", "versions_count", "versions_list", "version_latest"}:
        keywords.extend(
            [
                "lịch sử phiên bản",
                "lịch sử thay đổi",
                "version history",
                "version control",
                "revision history",
                "change history",
                "version",
                "phiên bản",
            ]
        )
    if analysis.intent in {"version_author_mapping", "author_latest", "author_specific_version", "authors_all"}:
        keywords.extend(
            [
                "lịch sử phiên bản",
                "version history",
                "version control",
                "author",
                "author(s)",
                "tác giả",
                "prepared by",
                "updated by",
                "reviewer",
                "approver",
            ]
        )

    keywords.extend(operational_keywords_from_analysis(analysis))
    return list(dict.fromkeys(keywords))


def detect_section_keywords(question: str) -> list[str]:
    analysis = QueryAnalysis(
        raw_question=question,
        normalized_question=normalize_for_match(question),
        requested_sections=detect_requested_sections(question),
        requested_roles=detect_requested_roles(question),
        requested_versions=extract_requested_versions(question),
    )
    return section_keywords_from_analysis(analysis)


def classify_intent(analysis: QueryAnalysis) -> str:
    folded_question = fold_accents(analysis.normalized_question)
    author_requested = "author" in analysis.requested_roles or is_author_intent(analysis.raw_question)
    version_requested = has_version_terms(analysis.raw_question) or bool(analysis.requested_versions)
    list_all_requested = has_list_all_terms(analysis.raw_question)
    count_requested = has_count_terms(analysis.raw_question)
    mapping_requested = has_version_author_mapping_terms(analysis.raw_question)
    operational_intent = primary_operational_intent(analysis)

    if operational_intent and not analysis.requested_versions:
        return operational_intent

    if version_requested and author_requested and mapping_requested:
        return "version_author_mapping"
    if count_requested and version_requested:
        return "versions_count"
    if (list_all_requested or ("nhung" in folded_question and "nao" in folded_question)) and version_requested:
        return "versions_list"
    if author_requested and analysis.requested_versions:
        return "author_specific_version"
    if list_all_requested and author_requested:
        return "authors_all"
    if author_requested and not analysis.requested_versions:
        return "author_latest"
    if has_latest_terms(analysis.raw_question) and version_requested:
        return "version_latest"

    if operational_intent:
        return operational_intent

    if analysis.requested_roles or "update_history" in analysis.requested_sections or analysis.requested_versions:
        return "find_version_info"
    if analysis.requested_count is not None:
        return "count_items"
    if any(term in folded_question for term in ("compare", "so sanh", "khac nhau")):
        return "compare_items"
    if any(term in folded_question for term in ("list", "liet ke", "danh sach")):
        return "list_items"
    if any(term in folded_question for term in ("summary", "summarize", "tom tat")):
        return "summarize_document"
    if any(term in folded_question for term in ("co noi ve", "mentioned", "de cap", "co khong", "does")):
        return "check_existence"
    if "process" in analysis.requested_sections or "scenario" in analysis.requested_sections:
        return "explain_process"
    if "responsibility" in analysis.requested_sections or "owner" in analysis.requested_sections:
        return "find_responsibility"
    return "lookup_fact"


def build_clarification_question(analysis: QueryAnalysis) -> str:
    if analysis.requested_versions:
        version = analysis.requested_versions[0]
        return (
            f"Bạn muốn kiểm tra version {version} của tài liệu nào? "
            "Vui lòng cung cấp mã tài liệu, ví dụ: ZION-QT-08."
        )
    if "scope" in analysis.requested_sections:
        return "Bạn muốn kiểm tra phạm vi áp dụng của tài liệu nào? Vui lòng cung cấp mã tài liệu."
    if analysis.requested_roles:
        role = analysis.requested_roles[0]
        role_label = {
            "author": "tác giả",
            "reviewer": "reviewer",
            "approver": "approver",
            "owner": "người phụ trách/PIC",
        }.get(role, role)
        return f"Bạn muốn kiểm tra {role_label} của tài liệu nào? Vui lòng cung cấp mã tài liệu."

    return "Bạn muốn kiểm tra thông tin trong tài liệu nào? Vui lòng cung cấp mã tài liệu hoặc mô tả rõ hơn."


def analyze_question(question: str, conversation_state: dict | None = None) -> QueryAnalysis:
    normalized_question = normalize_for_match(question)
    document_codes = extract_document_codes(question)
    requested_versions = extract_requested_versions(question)
    requested_sections = detect_requested_sections(question)
    requested_roles = detect_requested_roles(question)
    requested_dates = detect_requested_dates(question)
    requested_count = detect_requested_count(question)
    requested_entities = detect_requested_entities(question)
    is_follow_up = is_follow_up_question(question)
    operational_intents = detect_operational_intents(question)
    process_areas = detect_process_areas_from_intents(operational_intents)
    document_discovery_mode = detect_document_discovery_mode(question)

    if not document_codes and conversation_state:
        last_codes = conversation_state.get("last_document_codes") or []
        if last_codes and (is_follow_up or requested_versions or requested_roles or requested_sections):
            document_codes = list(last_codes)
    if conversation_state and is_follow_up and not requested_roles and not requested_sections:
        last_topic = conversation_state.get("last_topic") or []
        known_roles = {"author", "reviewer", "approver", "owner"}
        requested_roles = [topic for topic in last_topic if topic in known_roles]
        requested_sections = [topic for topic in last_topic if topic not in known_roles]

    analysis = QueryAnalysis(
        raw_question=question,
        normalized_question=normalized_question,
        document_codes=document_codes,
        requested_versions=requested_versions,
        requested_sections=requested_sections,
        requested_entities=requested_entities,
        requested_roles=requested_roles,
        requested_dates=requested_dates,
        requested_count=requested_count,
        operational_intents=operational_intents,
        process_areas=process_areas,
        document_discovery_mode=document_discovery_mode,
        is_follow_up=is_follow_up,
    )
    analysis.intent = classify_intent(analysis)

    requires_document_context = bool(
        requested_versions
        or requested_roles
        or requested_sections
        or requested_entities
        or any(term in fold_accents(normalized_question) for term in ("cai nay", "quy trinh nay", "tai lieu nay", "this document", "this procedure"))
    )
    if (
        not analysis.document_codes
        and requires_document_context
        and not analysis.operational_intents
        and not analysis.document_discovery_mode
    ):
        analysis.needs_clarification = True
        analysis.intent = "ambiguous_follow_up" if is_follow_up else analysis.intent
        analysis.clarification_question = build_clarification_question(analysis)

    analysis.expanded_query = expand_query(question, analysis)
    return analysis


def decide_retrieval_strategy(analysis: QueryAnalysis) -> dict:
    operational_question = bool(analysis.operational_intents or analysis.document_discovery_mode)
    password_policy_question = "password_policy" in analysis.operational_intents
    exact_constraints = bool(
        analysis.document_codes
        or analysis.requested_versions
        or analysis.requested_sections
        or analysis.requested_roles
        or analysis.requested_dates
        or analysis.requested_entities
    )
    keyword_limit = min(RETRIEVAL_K, 3 if exact_constraints else RETRIEVAL_K)
    if analysis.intent == "version_author_mapping":
        keyword_limit = max(keyword_limit, 3)
    if operational_question:
        keyword_limit = max(keyword_limit, RETRIEVAL_K, 4)
    if password_policy_question:
        keyword_limit = max(keyword_limit, 8)

    return {
        "use_keyword": exact_constraints or operational_question,
        "use_semantic": True,
        "filter_document_code": bool(analysis.document_codes),
        "prefer_exact_constraints": exact_constraints,
        "keyword_limit": keyword_limit,
        "fetch_k": max(RETRIEVAL_FETCH_K, 60 if password_policy_question else 40)
        if operational_question
        else RETRIEVAL_FETCH_K,
    }


def clean_source_filename(source: str) -> str:
    name = Path(str(source or "unknown")).name
    path = Path(name)
    stem = path.stem
    suffix = path.suffix
    stem = re.sub(r"[-_\s]*(?:ThangNguyen[’']s Mac mini|copy of|copy)$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s*\(\d+\)$", "", stem)
    stem = re.sub(r"\s{2,}", " ", stem).strip(" -_")
    return f"{stem}{suffix}" if stem else name


def document_source_name(document) -> str:
    return clean_source_filename(document.metadata.get("source_filename") or document.metadata.get("source", "unknown"))


def catalog_document_key(entry: dict) -> str:
    return str(
        entry.get("file_name")
        or entry.get("filename")
        or entry.get("source")
        or entry.get("document_id")
        or entry.get("document_code")
        or entry.get("document_title")
        or ""
    ).strip()


def sanitize_catalog_document(entry: dict) -> dict:
    filename = str(entry.get("filename") or entry.get("file_name") or "").strip()
    code = str(entry.get("document_code") or "").strip()
    title = str(entry.get("document_title") or Path(filename).stem or filename).strip()
    page_count = entry.get("page_count")
    chunk_count = entry.get("chunk_count")
    if not isinstance(page_count, int):
        source_pages = entry.get("source_pages")
        page_count = len(source_pages) if isinstance(source_pages, list) else None
    return {
        "code": code,
        "title": title,
        "filename": filename,
        "page_count": page_count,
        "chunk_count": chunk_count if isinstance(chunk_count, int) else None,
    }


def document_matches_code(document, document_codes: list[str]) -> bool:
    source = document_source_name(document).upper()
    return any(code in source for code in document_codes)


def document_key(document) -> tuple[str, object, object]:
    return (
        document_source_name(document),
        document.metadata.get("page"),
        document.metadata.get("start_index"),
    )


def looks_like_table_of_contents(document) -> bool:
    content = normalize_for_match(document.page_content[:1500])
    folded_content = fold_accents(content)
    numbered_section_count = len(re.findall(r"\b\d+(?:\.\d+)+\.?\s+", folded_content))
    has_version_metadata = (
        ("version control" in folded_content or "version history" in folded_content)
        and "author" in folded_content
        and bool(re.search(r"\b\d+(?:\.\d+)+\b", folded_content))
    )
    if has_version_metadata:
        return False

    return (
        "contents" in folded_content
        or "muc luc" in folded_content
        or document.page_content[:1500].count("...") >= 3
        or numbered_section_count >= 5
    )


def has_heading_match(document, phrase: str) -> bool:
    folded_content = fold_accents(document.page_content).lower()
    folded_phrase = re.escape(fold_accents(phrase).lower())
    numbered_heading = rf"\b\d+(?:\.\d+)*\.?\s*{folded_phrase}\b"
    line_heading = rf"(?:^|[\r\n])\s*{folded_phrase}\b"
    return bool(re.search(numbered_heading, folded_content) or re.search(line_heading, folded_content))


def keyword_rank_for_document(document, keywords_to_match: list[str]) -> int:
    full_phrase_keywords = [
        keyword
        for keyword in keywords_to_match
        if len(keyword.split()) > 1 or keyword.lower() == "scope"
    ]

    if any(has_heading_match(document, keyword) for keyword in full_phrase_keywords):
        return 0
    if any(contains_text(document.page_content, keyword) for keyword in full_phrase_keywords):
        return 1
    if any(contains_text(document.page_content, keyword) for keyword in keywords_to_match):
        return 2
    return 3


def document_has_any_keyword(document, keywords: list[str]) -> bool:
    return any(contains_text(document.page_content, keyword) for keyword in keywords)


def section_keywords_indicate_author(section_keywords: list[str]) -> bool:
    folded_keywords = " ".join(fold_accents(normalize_for_match(keyword)) for keyword in section_keywords)
    return any(
        term in folded_keywords
        for term in (
            "author",
            "tac gia",
            "nguoi soan",
            "nguoi cap nhat",
            "version history",
            "version control",
            "revision history",
            "change history",
        )
    )


def author_keyword_rank_for_document(document) -> int:
    content = document.page_content
    folded_content = fold_accents(normalize_for_match(content))
    has_version_number = bool(re.search(r"\b\d+(?:\.\d+)+\b", content))
    has_version_history = any(
        term in folded_content
        for term in (
            "version control",
            "version history",
            "revision history",
            "change history",
            "lich su phien ban",
            "lich su thay doi",
        )
    )
    has_author = any(term in folded_content for term in ("author", "author(s)", "tac gia"))
    has_reviewer_or_approver = "reviewer" in folded_content or "approver" in folded_content

    if has_version_history and has_author and has_version_number:
        return 0
    if has_author and has_version_number:
        return 1
    if has_version_history or has_version_number:
        return 2
    if has_reviewer_or_approver:
        return 3
    return 4


def format_retrieval_score(document) -> str:
    method = document.metadata.get("retrieval_method")
    score = document.metadata.get("retrieval_score")
    if method == "catalog":
        section_type = document.metadata.get("section_type")
        return f"catalog/{section_type}" if section_type else "catalog"
    if method == "keyword":
        keyword_rank = document.metadata.get("keyword_rank")
        if keyword_rank == 0:
            return "keyword/exact-section"
        if keyword_rank in {1, 2}:
            return "keyword/section"
        return "keyword"
    if isinstance(score, float):
        return f"{score:.4f}"
    return str(score) if score is not None else ""


def keyword_search_documents(
    vector_store,
    document_codes: list[str],
    section_keywords: list[str],
    limit: int = 3,
) -> list:
    if not section_keywords:
        return []

    preferred_keywords = [
        keyword
        for keyword in section_keywords
        if keyword not in {"scope", "purpose", "responsibility", "definition", "approval", "review", "process", "procedure"}
    ]
    keywords_to_match = preferred_keywords or section_keywords
    author_intent = section_keywords_indicate_author(section_keywords)
    password_policy_intent = section_keywords_indicate_password_policy(section_keywords)
    matches = []
    for document in vector_store.docstore._dict.values():
        if document_codes and not document_matches_code(document, document_codes):
            continue

        source_name = document_source_name(document)
        matched_keywords = [
            keyword
            for keyword in keywords_to_match
            if contains_text(document.page_content, keyword) or contains_text(source_name, keyword)
        ]
        if not matched_keywords:
            continue

        keyword_rank = (
            author_keyword_rank_for_document(document)
            if author_intent
            else keyword_rank_for_document(document, keywords_to_match)
        )
        selected_document = deepcopy(document)
        selected_document.metadata = dict(selected_document.metadata)
        selected_document.metadata["retrieval_score"] = "keyword"
        selected_document.metadata["retrieval_method"] = "keyword"
        selected_document.metadata["keyword_rank"] = keyword_rank
        selected_document.metadata["matched_keywords"] = matched_keywords
        selected_document.metadata["document_code"] = extract_document_code_from_source(source_name)
        selected_document.metadata["section_type"] = classify_section_type(document.page_content)
        selected_document.metadata["section_types"] = classify_chunk_section_types(document.page_content)
        code_priority = 0 if document_codes and document_matches_code(document, document_codes) else 1
        password_priority = password_policy_priority(selected_document) if password_policy_intent else 0
        toc_priority = 1 if looks_like_table_of_contents(document) else 0
        page = selected_document.metadata.get("page")
        page_priority = page if isinstance(page, int) else 999999
        matches.append(
            (
                code_priority,
                password_priority,
                keyword_rank + (2 if toc_priority else 0),
                page_priority,
                -len(matched_keywords),
                page_priority,
                selected_document,
            )
        )

    non_toc_matches = [item for item in matches if not looks_like_table_of_contents(item[6])]
    if non_toc_matches:
        matches = non_toc_matches

    matches.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4], item[5]))
    return [item[6] for item in matches[:limit]]


def keyword_density(document, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if contains_text(document.page_content, keyword))


def section_keywords_indicate_password_policy(section_keywords: list[str]) -> bool:
    folded_keywords = " ".join(fold_accents(normalize_for_match(keyword)) for keyword in section_keywords)
    return any(
        term in folded_keywords
        for term in (
            "mat khau",
            "password",
            "passcode",
            "credential",
            "password length",
            "password complexity",
            "password expiration",
        )
    )


def password_policy_priority(document) -> int:
    """Prefer actual password policy evidence over generic auth/login mentions."""
    folded_content = fold_accents(normalize_for_match(document.page_content))
    folded_source = fold_accents(normalize_for_match(document_source_name(document)))
    combined = f"{folded_source} {folded_content}"

    requirement_terms = [
        "password length",
        "password complexity",
        "password expiration",
        "do dai mat khau",
        "do phuc tap mat khau",
        "het han mat khau",
        "policy password",
        "password policy",
    ]
    password_terms = [
        "mat khau",
        "password",
        "passcode",
    ]
    credential_terms = ["credential", "credentials", "thong tin xac thuc", "bi mat chung thuc"]
    weak_terms = ["authentication", "xac thuc", "login", "dang nhap", "account", "tai khoan"]
    preferred_sources = [
        "zion-tc-13",
        "dinh danh",
        "identity",
        "truy cap",
        "access",
        "quan ly tai khoan",
        "account management",
    ]

    if any(term in folded_content for term in requirement_terms):
        return 0
    if any(term in folded_content for term in password_terms):
        return 1
    if any(term in folded_content for term in credential_terms):
        return 2
    if any(term in folded_source for term in preferred_sources) and any(term in combined for term in weak_terms):
        return 3
    if any(term in combined for term in weak_terms):
        return 4
    return 5


def candidate_matches_document(document, candidate: dict) -> bool:
    source_name = document_source_name(document)
    candidate_file = candidate.get("file_name", "")
    candidate_code = candidate.get("document_code", "")
    if candidate_file and source_name == candidate_file:
        return True
    if candidate_code and candidate_code in source_name.upper():
        return True
    return False


def catalog_priority(document, analysis: QueryAnalysis) -> int:
    if not analysis.catalog_candidates:
        return 1
    for index, candidate in enumerate(analysis.catalog_candidates):
        if candidate_matches_document(document, candidate):
            return index
    return len(analysis.catalog_candidates) + 1


def section_type_priority(document, analysis: QueryAnalysis) -> int:
    desired_sections = relevant_section_types(analysis)
    if not desired_sections:
        return 0

    section_types = document.metadata.get("section_types")
    if not section_types:
        section_types = classify_chunk_section_types(document.page_content)
    return 0 if any(section in desired_sections for section in section_types) else 1


def catalog_search_documents(
    vector_store,
    catalog_candidates: list[dict],
    analysis: QueryAnalysis,
    limit: int = 4,
) -> list:
    if not catalog_candidates:
        return []

    keywords = operational_keywords_from_analysis(analysis) + section_keywords_from_analysis(analysis)
    desired_sections = relevant_section_types(analysis)
    matches = []
    for document in vector_store.docstore._dict.values():
        candidate_index = None
        candidate = None
        for index, item in enumerate(catalog_candidates):
            if candidate_matches_document(document, item):
                candidate_index = index
                candidate = item
                break
        if candidate is None:
            continue

        section_types = classify_chunk_section_types(document.page_content)
        section_hit = any(section in desired_sections for section in section_types) if desired_sections else False
        density = keyword_density(document, keywords)
        source_name = document_source_name(document)
        page = document.metadata.get("page")
        page_priority = page if isinstance(page, int) else 999999
        selected_document = deepcopy(document)
        selected_document.metadata = dict(selected_document.metadata)
        selected_document.metadata["retrieval_score"] = "catalog"
        selected_document.metadata["retrieval_method"] = "catalog"
        selected_document.metadata["catalog_rank"] = candidate_index
        selected_document.metadata["document_code"] = candidate.get("document_code") or extract_document_code_from_source(source_name)
        selected_document.metadata["process_area"] = candidate.get("process_area")
        selected_document.metadata["section_type"] = section_types[0] if section_types else "unknown"
        selected_document.metadata["section_types"] = section_types
        matches.append(
            (
                candidate_index,
                0 if section_hit else 1,
                -density,
                page_priority,
                selected_document,
            )
        )

    matches.sort(key=lambda item: item[:4])
    return [item[4] for item in matches[:limit]]


def document_operational_priority(document, analysis: QueryAnalysis) -> int:
    if not analysis.operational_intents and not analysis.document_discovery_mode:
        return 0

    source = fold_accents(normalize_for_match(document_source_name(document)))
    source_terms = OPERATIONAL_SOURCE_TERMS + [
        fold_accents(normalize_for_match(term))
        for term in operational_keywords_from_analysis(analysis)
        if len(term.split()) <= 3
    ]
    if any(term and term in source for term in source_terms):
        return 0
    if keyword_density(document, operational_keywords_from_analysis(analysis)) > 0:
        return 1
    return 2


def rank_evidence(documents: list, analysis: QueryAnalysis) -> list:
    section_keywords = section_keywords_from_analysis(analysis)
    operational_keywords = operational_keywords_from_analysis(analysis)

    def sort_key(document):
        source = document_source_name(document).upper()
        page = document.metadata.get("page")
        page_priority = page if isinstance(page, int) else 999999
        exact_document = 0 if not analysis.document_codes or any(code in source for code in analysis.document_codes) else 1
        version_match = 0 if not analysis.requested_versions or any(contains_text(document.page_content, version) for version in analysis.requested_versions) else 1
        role_match = 0 if not analysis.requested_roles or document_has_any_keyword(document, section_keywords) else 1
        section_match = 0 if not analysis.requested_sections or document_has_any_keyword(document, section_keywords) else 1
        toc_penalty = 1 if looks_like_table_of_contents(document) else 0
        method_priority = 0 if document.metadata.get("retrieval_method") in {"catalog", "keyword"} else 1
        keyword_rank = document.metadata.get("keyword_rank")
        keyword_rank = keyword_rank if isinstance(keyword_rank, int) else 4
        score = document.metadata.get("retrieval_score")
        semantic_score = score if isinstance(score, float) else 0.0
        density = -keyword_density(document, section_keywords)
        catalog_match_priority = catalog_priority(document, analysis)
        section_priority = section_type_priority(document, analysis)
        operational_priority = document_operational_priority(document, analysis)
        password_priority = (
            password_policy_priority(document)
            if "password_policy" in analysis.operational_intents
            else 0
        )
        operational_density = -keyword_density(document, operational_keywords)
        source_name = document_source_name(document) if not analysis.document_codes else ""
        return (
            exact_document,
            password_priority,
            catalog_match_priority,
            section_priority,
            operational_priority,
            version_match,
            role_match,
            section_match,
            method_priority,
            keyword_rank,
            toc_penalty,
            operational_density,
            density,
            semantic_score,
            page_priority,
            source_name,
        )

    return sorted(documents, key=sort_key)


def estimate_retrieval_confidence(documents: list, analysis: QueryAnalysis) -> str:
    if not documents:
        return "low"

    section_keywords = section_keywords_from_analysis(analysis)
    operational_keywords = operational_keywords_from_analysis(analysis)
    has_exact_document = bool(
        analysis.document_codes
        and any(document_matches_code(document, analysis.document_codes) for document in documents)
    )
    has_exact_section = any(
        document.metadata.get("keyword_rank") == 0
        or (section_keywords and document_has_any_keyword(document, section_keywords))
        for document in documents
    )
    has_operational_signal = any(
        document_operational_priority(document, analysis) <= 1
        or (operational_keywords and keyword_density(document, operational_keywords) > 0)
        for document in documents
    )

    if analysis.document_codes and has_exact_document and (has_exact_section or not section_keywords):
        return "high"
    if section_keywords and has_exact_section and not looks_like_table_of_contents(documents[0]):
        return "high"
    if analysis.operational_intents or analysis.document_discovery_mode:
        if has_operational_signal and not looks_like_table_of_contents(documents[0]):
            return "medium"
        return "low"
    return "medium"


def build_operational_prompt_hint(analysis: QueryAnalysis) -> str:
    if not analysis.operational_intents and not analysis.document_discovery_mode:
        return ""

    intents = ", ".join(analysis.operational_intents or [analysis.intent])
    discovery = "yes" if analysis.document_discovery_mode else "no"
    candidate_lines = []
    for index, candidate in enumerate(analysis.catalog_candidates[:5], start=1):
        code = candidate.get("document_code") or "no-code"
        title = candidate.get("document_title") or candidate.get("file_name")
        area = candidate.get("process_area") or "unknown"
        sections = ", ".join((candidate.get("key_sections") or [])[:3])
        candidate_lines.append(f"{index}. {code} - {title} | process area: {area} | sections: {sections}")
    candidates_text = "\n".join(candidate_lines) if candidate_lines else "No catalog candidates found."
    return (
        "Internal retrieval guidance:\n"
        f"- detected intent: {intents}\n"
        f"- detected process areas: {', '.join(analysis.process_areas) if analysis.process_areas else 'unknown'}\n"
        f"- document discovery mode: {discovery}\n"
        f"- confidence: {analysis.confidence}\n"
        f"- catalog candidates:\n{candidates_text}\n"
        "- Use confidence internally only; do not print the label.\n"
        "- If confidence is high, answer directly from the documents.\n"
        "- If confidence is medium, phrase the answer as: tài liệu liên quan nhiều nhất là...\n"
        "- If confidence is low, say: Mình chưa tìm thấy câu trả lời trực tiếp, nhưng có tài liệu liên quan...\n"
        "- For practical or which-document questions, start with recommended document candidates, then summarize what to check or do.\n"
    )


def is_excluded_source(document) -> bool:
    """True when a chunk's source path matches a configured exclusion substring
    (e.g. the SharePoint "Archives/" folder of superseded document versions)."""
    if not EXCLUDED_SOURCE_SUBSTRINGS:
        return False
    metadata = getattr(document, "metadata", {}) or {}
    source = str(metadata.get("source") or metadata.get("file_name") or "").lower()
    return any(marker in source for marker in EXCLUDED_SOURCE_SUBSTRINGS)


def retrieve_documents(question: str, vector_store, analysis: QueryAnalysis | None = None) -> tuple[list, list, dict]:
    analysis = analysis or analyze_question(question)
    strategy = decide_retrieval_strategy(analysis)
    catalog = load_document_catalog()
    analysis.catalog_candidates = find_catalog_candidates(question, catalog, limit=6) if catalog else []
    document_codes = analysis.document_codes
    section_keywords = section_keywords_from_analysis(analysis)
    expanded_query = analysis.expanded_query
    exact_question = bool(
        document_codes
        or analysis.requested_versions
        or analysis.requested_entities
        or (analysis.requested_sections and not analysis.operational_intents)
    )
    keyword_limit = strategy["keyword_limit"]

    keyword_documents = keyword_search_documents(
        vector_store,
        document_codes,
        section_keywords,
        limit=keyword_limit,
    ) if strategy["use_keyword"] else []
    catalog_documents = catalog_search_documents(
        vector_store,
        analysis.catalog_candidates,
        analysis,
        limit=max(RETRIEVAL_K, 4),
    )
    raw_results = vector_store.similarity_search_with_score(
        expanded_query,
        k=strategy["fetch_k"],
    )
    semantic_documents = []

    for document, score in raw_results:
        score = float(score)
        if document_codes and not document_matches_code(document, document_codes):
            continue
        if not document_codes and score > MIN_RELEVANCE_SCORE:
            continue
        if exact_question and keyword_documents:
            if score > MIN_RELEVANCE_SCORE and not document_has_any_keyword(document, section_keywords):
                continue

        selected_document = deepcopy(document)
        selected_document.metadata = dict(selected_document.metadata)
        selected_document.metadata["retrieval_score"] = score
        selected_document.metadata["retrieval_method"] = "semantic"
        selected_document.metadata["document_code"] = extract_document_code_from_source(document_source_name(document))
        selected_document.metadata["section_type"] = classify_section_type(document.page_content)
        selected_document.metadata["section_types"] = classify_chunk_section_types(document.page_content)
        semantic_documents.append(selected_document)

    combined_candidates = rank_evidence(catalog_documents + keyword_documents + semantic_documents, analysis)
    if EXCLUDED_SOURCE_SUBSTRINGS:
        kept = [document for document in combined_candidates if not is_excluded_source(document)]
        # Only apply the exclusion when relevant evidence remains, so a topic that
        # genuinely only exists in an excluded location still returns an answer.
        if kept:
            combined_candidates = kept
    combined_documents = []
    seen_keys = set()
    result_limit = max(RETRIEVAL_K, 4) if (analysis.operational_intents or analysis.document_discovery_mode) else RETRIEVAL_K
    if "password_policy" in analysis.operational_intents:
        result_limit = max(result_limit, 8)
    if analysis.intent == "version_author_mapping":
        result_limit = max(result_limit, 3)
    if analysis.catalog_candidates:
        result_limit = max(result_limit, 5)
    for document in combined_candidates:
        key = document_key(document)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        combined_documents.append(document)
        if len(combined_documents) >= result_limit:
            break

    analysis.confidence = estimate_retrieval_confidence(combined_documents, analysis)
    debug_info = {
        "expanded_query": expanded_query,
        "document_codes": document_codes,
        "section_keywords": section_keywords,
        "operational_intents": analysis.operational_intents,
        "document_discovery_mode": analysis.document_discovery_mode,
        "confidence": analysis.confidence,
        "catalog_candidates": analysis.catalog_candidates,
        "analysis": analysis,
        "strategy": strategy,
        "selected_documents": combined_documents,
    }

    return combined_documents, raw_results, debug_info


def print_retrieval_debug(raw_results, debug_info) -> None:
    if not DEBUG_RETRIEVAL:
        return

    print("\nRetrieval debug:")
    print(f"- expanded query: {debug_info['expanded_query']}")
    print(f"- document codes: {debug_info['document_codes']}")
    print(f"- section keywords: {debug_info['section_keywords']}")
    print(f"- operational intents: {debug_info.get('operational_intents', [])}")
    print(f"- document discovery mode: {debug_info.get('document_discovery_mode', False)}")
    print(f"- confidence: {debug_info.get('confidence', 'medium')}")
    print(f"- threshold: {MIN_RELEVANCE_SCORE}")
    catalog_candidates = debug_info.get("catalog_candidates", [])
    if catalog_candidates:
        print("- catalog candidates:")
        for candidate in catalog_candidates[:5]:
            label = candidate.get("document_code") or candidate.get("file_name")
            title = candidate.get("document_title")
            score = candidate.get("catalog_score")
            print(f"  - {label} | {title} | catalog score: {score}")

    print("- selected documents:")
    for index, document in enumerate(debug_info["selected_documents"], start=1):
        source = document_source_name(document)
        page = document.metadata.get("page")
        page_label = f" page {page + 1}" if isinstance(page, int) else ""
        score_label = format_retrieval_score(document)
        preview = " ".join(document.page_content[:300].split())
        print(f"  {index}. {source}{page_label} | score: {score_label}")
        print(f"     preview: {preview}")

    analysis = debug_info.get("analysis")
    if analysis and analysis.intent in {
        "version_author_mapping",
        "versions_count",
        "versions_list",
        "version_latest",
        "author_latest",
        "author_specific_version",
        "authors_all",
    }:
        debug_context = format_context(debug_info["selected_documents"])
        entries = extract_version_history_entries(debug_context)
        pages = []
        for document in debug_info["selected_documents"]:
            page = document.metadata.get("page")
            if isinstance(page, int):
                pages.append(str(page + 1))
        if entries:
            preview_entries = [
                f"{entry['version']} -> {entry.get('author') or 'no author found'}"
                for entry in entries[:8]
            ]
            print("- version history extraction debug:")
            print(f"  intent: {analysis.intent}")
            print(f"  pages: {', '.join(pages) if pages else 'unknown'}")
            print(f"  parsed entries: {len(entries)}")
            print(f"  preview: {'; '.join(preview_entries)}")

    print("- raw semantic candidates:")
    for index, (document, score) in enumerate(raw_results[:RETRIEVAL_FETCH_K], start=1):
        source = document_source_name(document)
        page = document.metadata.get("page")
        page_label = f" page {page + 1}" if isinstance(page, int) else ""
        print(f"  {index}. {source}{page_label} | score: {float(score):.4f}")


def safe_debug_retrieval_payload(debug_info: dict) -> dict:
    selected_documents = debug_info.get("selected_documents") or []
    source_records = []
    seen = set()
    for document in selected_documents:
        source = document_source_name(document)
        page = document.metadata.get("page")
        page_number = page + 1 if isinstance(page, int) else None
        key = (source, page_number, document.metadata.get("retrieval_method"))
        if key in seen:
            continue
        seen.add(key)
        page_label = f" page {page_number}" if page_number is not None else ""
        source_records.append(
            {
                "label": f"{source}{page_label}",
                "filename": source,
                "page": page_number,
                "retrieval_method": document.metadata.get("retrieval_method"),
                "score": format_retrieval_score(document),
                "keyword_rank": document.metadata.get("keyword_rank"),
                "section_type": document.metadata.get("section_type"),
            }
        )

    strategy = debug_info.get("strategy") or {}
    return {
        "expanded_queries": [debug_info.get("expanded_query", "")],
        "document_codes": debug_info.get("document_codes", []),
        "section_keywords": debug_info.get("section_keywords", []),
        "operational_intents": debug_info.get("operational_intents", []),
        "document_discovery_mode": debug_info.get("document_discovery_mode", False),
        "retrieval_confidence": debug_info.get("confidence", ""),
        "retrieval_strategy": {
            "keyword_limit": strategy.get("keyword_limit"),
            "fetch_k": strategy.get("fetch_k"),
            "use_keyword": strategy.get("use_keyword"),
            "use_semantic": strategy.get("use_semantic"),
        },
        "retrieved_sources": source_records,
    }


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def version_part_count(version: str) -> int:
    return len(version.split("."))


def has_clear_version_label(text_before: str) -> bool:
    folded_before = fold_accents(normalize_for_match(text_before[-60:]))
    return bool(re.search(r"(?:^|\b)(?:version|phien ban|ver|v)\s*[:#\-]?\s*$", folded_before))


def is_false_version_candidate(text_before: str, candidate: str) -> bool:
    if has_clear_version_label(text_before):
        return False

    folded_before = fold_accents(normalize_for_match(text_before[-90:]))
    negative_terms = (
        "section",
        "step",
        "clause",
        "control",
        "muc",
        "dieu",
        "khoan",
        "diem",
        "phan",
    )
    if re.search(rf"(?:{'|'.join(negative_terms)})\s*(?:so|number|no\.?)?\s*$", folded_before):
        return True

    return version_part_count(candidate) > 2


def is_likely_version_row_start(context: str, match: re.Match) -> bool:
    candidate = match.group(0)
    text_before = context[:match.start()]
    if is_false_version_candidate(text_before, candidate):
        return False

    if has_clear_version_label(text_before):
        return True

    if version_part_count(candidate) > 2:
        return False

    line_start = context.rfind("\n", 0, match.start()) + 1
    line_prefix = context[line_start:match.start()]
    if re.match(r"^\s*(?:[\|\-•*]\s*)?$", line_prefix):
        return True

    next_text = context[match.end():match.end() + 280]
    has_date = bool(
        re.search(
            r"\b(?:\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4})\b",
            next_text,
        )
    )
    has_author_like_tail = bool(
        re.search(
            r"\b(?:[A-ZÀ-ỴĐ][A-Za-zÀ-ỹĐđ]*|[A-Z]{2,})(?:\s+(?:[A-ZÀ-ỴĐ][A-Za-zÀ-ỹĐđ]*|[A-Z]{2,})){0,5}\b",
            next_text,
        )
    )
    return has_date and has_author_like_tail


def clean_person_name(name: str) -> str:
    name = " ".join(str(name or "").strip(" .,:;|-").split())
    stop_terms = {
        "reviewer",
        "approver",
        "author",
        "authors",
        "effective",
        "date",
        "version",
        "changes",
        "made",
        "description",
        "status",
    }
    kept_tokens = []
    for token in name.split():
        folded_token = fold_accents(normalize_for_match(token.strip("():;,.|-")))
        if folded_token in stop_terms:
            break
        kept_tokens.append(token)

    name = " ".join(kept_tokens)
    return name


def extract_person_after_label(context: str, label: str) -> str | None:
    pattern = rf"\b{re.escape(label)}\s+([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){{1,5}})"
    match = re.search(pattern, context)
    if not match:
        return None

    return clean_person_name(match.group(1))


def extract_author_from_version_segment(segment: str) -> str | None:
    person_token = r"(?:[A-ZÀ-ỴĐ][A-Za-zÀ-ỹĐđ]*|[A-Z]{2,})"
    label_patterns = [
        rf"\b(?:Author(?:\(s\))?|Authors?|Prepared by|Updated by|Created by)\s*[:\-]?\s+({person_token}(?:\s+{person_token}){{0,5}})(?:\s|$)",
        rf"\b(?:Tác giả|Người soạn|Người cập nhật)\s*[:\-]?\s+({person_token}(?:\s+{person_token}){{0,5}})(?:\s|$)",
    ]
    for pattern in label_patterns:
        match = re.search(pattern, segment)
        if match:
            author = clean_person_name(match.group(1))
            if author:
                return author

    date_patterns = [
        rf"\b\d{{1,2}}\s+[A-Za-z]{{3,9}}\s+\d{{4}}\s+({person_token}(?:\s+{person_token}){{0,5}})(?:\s|$)",
        rf"\b\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}\s+({person_token}(?:\s+{person_token}){{0,5}})(?:\s|$)",
        rf"\b\d{{4}}\s+({person_token}(?:\s+{person_token}){{0,5}})(?:\s|$)",
    ]

    for pattern in date_patterns:
        match = re.search(pattern, segment)
        if match:
            author = clean_person_name(match.group(1))
            if author:
                return author

    return None


def extract_date_from_version_segment(segment: str) -> str | None:
    date_patterns = [
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{4}\b",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, segment)
        if match:
            return match.group(0)

    return None


def extract_description_from_version_segment(segment: str) -> str:
    without_version = re.sub(r"^\s*\d+(?:\.\d+)+\s*", "", segment).strip()
    date = extract_date_from_version_segment(segment)
    if date and date in without_version:
        without_version = without_version.split(date, 1)[0]

    return " ".join(without_version.strip(" .,:;|-").split())


def version_history_context(context: str) -> str:
    blocks = re.split(r"(?=\[\d+\]\s+Source:)", context)
    history_blocks = []
    for block in blocks:
        folded_block = fold_accents(normalize_for_match(block))
        has_history_heading = any(
            term in folded_block
            for term in (
                "version control",
                "version history",
                "revision history",
                "change history",
                "lich su phien ban",
                "lich su thay doi",
            )
        )
        has_author_column = any(term in folded_block for term in ("author", "author(s)", "tac gia"))
        if has_history_heading and has_author_column:
            history_blocks.append(block)

    return "\n\n".join(history_blocks) if history_blocks else context


def extract_version_history_entries(context: str) -> list[dict]:
    context = version_history_context(context)
    version_matches = [
        match
        for match in re.finditer(r"\b\d+(?:\.\d+){1,2}\b", context)
        if is_likely_version_row_start(context, match)
    ]
    entries = []
    reviewer = extract_person_after_label(context, "Reviewer")
    approver = extract_person_after_label(context, "Approver")

    for index, match in enumerate(version_matches):
        version = match.group(0)
        end = version_matches[index + 1].start() if index + 1 < len(version_matches) else len(context)
        segment = context[match.start():end]
        entry = {
            "version": version,
            "author": extract_author_from_version_segment(segment),
            "reviewer": reviewer,
            "approver": approver,
            "date": extract_date_from_version_segment(segment),
            "description": extract_description_from_version_segment(segment),
        }
        if entry["author"] or entry["date"] or entry["description"]:
            entries.append(entry)

    unique_entries = []
    seen_versions = set()
    for entry in entries:
        if entry["version"] in seen_versions:
            continue

        seen_versions.add(entry["version"])
        unique_entries.append(entry)

    return unique_entries


def extract_version_author_from_context(context: str, requested_version: str | None = None) -> dict | None:
    entries = [
        entry
        for entry in extract_version_history_entries(context)
        if entry.get("author") and (not requested_version or entry["version"] == requested_version)
    ]
    if not entries:
        return None

    entry = max(entries, key=lambda item: version_key(item["version"]))
    result = {
        "version": entry["version"],
        "author": entry["author"],
    }
    reviewer = entry.get("reviewer")
    approver = entry.get("approver")
    if reviewer:
        result["reviewer"] = reviewer
    if approver:
        result["approver"] = approver

    return result


def extract_latest_version_author_from_context(context: str) -> dict | None:
    return extract_version_author_from_context(context)


def build_author_answer(analysis: QueryAnalysis, context: str) -> str | None:
    requested_version = analysis.requested_versions[0] if analysis.requested_versions else None
    details = extract_version_author_from_context(context, requested_version=requested_version)
    if not details:
        return None

    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    if requested_version:
        answer = f"Theo {document_label}, tác giả của version {details['version']} là {details['author']}."
    else:
        answer = (
            f"Theo {document_label}, phiên bản mới nhất được ghi nhận là version "
            f"{details['version']}, với tác giả là {details['author']}."
        )
    reviewer = details.get("reviewer")
    approver = details.get("approver")
    if reviewer and approver:
        answer += (
            f" Ngoài ra, tài liệu cũng ghi nhận Reviewer là {reviewer} "
            f"và Approver là {approver}."
        )
    elif reviewer:
        answer += f" Ngoài ra, tài liệu cũng ghi nhận Reviewer là {reviewer}."
    elif approver:
        answer += f" Ngoài ra, tài liệu cũng ghi nhận Approver là {approver}."

    return answer


def answer_author_latest(analysis: QueryAnalysis, context: str) -> str | None:
    details = extract_version_author_from_context(context)
    if not details:
        return None

    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    return (
        f"Theo {document_label}, phiên bản mới nhất được ghi nhận là version "
        f"{details['version']}, với tác giả là {details['author']}."
    )


def answer_author_specific_version(analysis: QueryAnalysis, context: str) -> str | None:
    if not analysis.requested_versions:
        return None

    version = analysis.requested_versions[0]
    details = extract_version_author_from_context(context, requested_version=version)
    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    if not details:
        return (
            f"Không tìm thấy thông tin tác giả của version {version} trong "
            f"{document_label} theo tài liệu được cung cấp."
        )

    return f"Theo {document_label}, tác giả của version {version} là {details['author']}."


def sorted_version_entries(context: str) -> list[dict]:
    entries = extract_version_history_entries(context)
    return sorted(entries, key=lambda entry: version_key(entry["version"]))


def answer_authors_all(analysis: QueryAnalysis, context: str) -> str | None:
    entries = [entry for entry in sorted_version_entries(context) if entry.get("author")]
    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    if not entries:
        return f"Không tìm thấy thông tin tác giả trong {document_label} theo tài liệu được cung cấp."

    lines = [
        f"* Version {entry['version']}: {entry['author']}"
        for entry in entries
    ]
    if len({entry["author"] for entry in entries}) == 1:
        return (
            f"Theo {document_label}, chỉ tìm thấy một tác giả được ghi nhận trong "
            "ngữ cảnh truy xuất:\n\n" + "\n".join(lines)
        )

    return (
        f"Theo {document_label}, các tác giả được ghi nhận trong lịch sử phiên bản gồm:\n\n"
        + "\n".join(lines)
    )


def answer_version_author_mapping(analysis: QueryAnalysis, context: str) -> str | None:
    entries = sorted_version_entries(context)
    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    if not entries:
        return (
            f"Không tìm thấy thông tin phiên bản và tác giả tương ứng trong "
            f"{document_label} theo tài liệu được cung cấp."
        )

    lines = []
    for entry in entries:
        author = (
            entry.get("author")
            or "chưa ghi nhận tác giả trong phần lịch sử phiên bản được truy xuất"
        )
        lines.append(f"* Version {entry['version']}: {author}")

    return (
        f"Theo {document_label}, các version và tác giả tương ứng là:\n\n"
        + "\n".join(lines)
    )


def answer_versions_count(analysis: QueryAnalysis, context: str) -> str | None:
    entries = sorted_version_entries(context)
    versions = [entry["version"] for entry in entries]
    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    if not versions:
        return f"Không tìm thấy thông tin phiên bản trong {document_label} theo tài liệu được cung cấp."

    return f"Theo {document_label}, tài liệu ghi nhận {len(versions)} phiên bản: {', '.join(versions)}."


def answer_versions_list(analysis: QueryAnalysis, context: str) -> str | None:
    entries = sorted_version_entries(context)
    versions = [entry["version"] for entry in entries]
    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    if not versions:
        return f"Không tìm thấy danh sách phiên bản trong {document_label} theo tài liệu được cung cấp."

    return f"Theo {document_label}, các phiên bản được ghi nhận gồm: {', '.join(versions)}."


def answer_version_latest(analysis: QueryAnalysis, context: str) -> str | None:
    entries = sorted_version_entries(context)
    if not entries:
        return None

    latest = max(entries, key=lambda entry: version_key(entry["version"]))
    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    answer = f"Theo {document_label}, phiên bản mới nhất được ghi nhận là version {latest['version']}."
    if latest.get("author"):
        answer += f" Tác giả của phiên bản này là {latest['author']}."

    return answer


def build_role_answer(analysis: QueryAnalysis, context: str) -> str | None:
    roles = [role for role in analysis.requested_roles if role in {"reviewer", "approver"}]
    if not roles:
        return None

    details = []
    reviewer = extract_person_after_label(context, "Reviewer")
    approver = extract_person_after_label(context, "Approver")
    if "reviewer" in roles and reviewer:
        details.append(f"Reviewer là {reviewer}")
    if "approver" in roles and approver:
        details.append(f"Approver là {approver}")
    if not details:
        return None

    document_label = analysis.document_codes[0] if analysis.document_codes else "tài liệu"
    return f"Theo {document_label}, " + " và ".join(details) + "."


def build_structured_answer(analysis: QueryAnalysis, context: str) -> str | None:
    structured_routes = {
        "version_author_mapping": answer_version_author_mapping,
        "versions_count": answer_versions_count,
        "versions_list": answer_versions_list,
        "author_specific_version": answer_author_specific_version,
        "authors_all": answer_authors_all,
        "author_latest": answer_author_latest,
        "version_latest": answer_version_latest,
    }
    if analysis.intent in structured_routes:
        return structured_routes[analysis.intent](analysis, context)

    return build_role_answer(analysis, context)


def has_sufficient_evidence(context: str, analysis: QueryAnalysis) -> bool:
    if analysis.document_codes and not any(contains_text(context, code) for code in analysis.document_codes):
        return False
    if analysis.operational_intents or analysis.document_discovery_mode:
        return bool(context.strip())
    if analysis.requested_versions and not any(contains_text(context, version) for version in analysis.requested_versions):
        return False

    section_keywords = section_keywords_from_analysis(analysis)
    if analysis.requested_sections and not any(contains_text(context, keyword) for keyword in section_keywords):
        return False

    role_requirements = {
        "author": ["author", "author(s)", "tác giả", "version control", "version history"],
        "reviewer": ["reviewer", "người rà soát"],
        "approver": ["approver", "người phê duyệt"],
        "owner": ["owner", "PIC", "người phụ trách", "trách nhiệm"],
    }
    for role in analysis.requested_roles:
        required_terms = role_requirements.get(role, [role])
        if not any(contains_text(context, term) for term in required_terms):
            return False

    for entity in analysis.requested_entities:
        _label, _, value = entity.partition(":")
        if value and not contains_text(context, value):
            return False

    return True


def validate_answer(answer: str, analysis: QueryAnalysis, documents: list) -> bool:
    if not documents:
        return False

    if analysis.document_codes:
        source_text = " ".join(document_source_name(document).upper() for document in documents)
        if not any(code in source_text for code in analysis.document_codes):
            return False
    if analysis.operational_intents or analysis.document_discovery_mode:
        return bool(answer.strip())

    folded_answer = fold_accents(normalize_for_match(answer))
    if analysis.requested_versions:
        requested_version = analysis.requested_versions[0]
        if requested_version not in answer:
            return False
        other_versions = re.findall(r"\b\d+(?:\.\d+)+\b", answer)
        if other_versions and requested_version not in other_versions:
            return False

    if "reviewer" in analysis.requested_roles and "approver" in folded_answer and "reviewer" not in folded_answer:
        return False
    if "approver" in analysis.requested_roles and "reviewer" in folded_answer and "approver" not in folded_answer:
        return False
    if analysis.intent in {"versions_count", "versions_list", "version_latest"}:
        if not re.search(r"\b\d+(?:\.\d+)+\b", answer):
            return False
        if analysis.intent in {"versions_count", "versions_list"} and "tac gia" in folded_answer and "phien ban" not in folded_answer:
            return False
    if analysis.intent == "authors_all":
        if "version" not in folded_answer and "tac gia" not in folded_answer:
            return False
        if "moi nhat" in folded_answer and folded_answer.count("version") <= 1:
            return False
    if analysis.intent == "version_author_mapping":
        versions = re.findall(r"\b\d+(?:\.\d+)+\b", answer)
        if not versions:
            return False
        if "version" not in folded_answer and "phien ban" not in folded_answer:
            return False
        if "tac gia" not in folded_answer and "author" not in folded_answer:
            return False
        if ("moi nhat" in folded_answer or "latest" in folded_answer) and len(set(versions)) <= 1:
            return False
    if analysis.intent == "author_specific_version":
        requested_version = analysis.requested_versions[0] if analysis.requested_versions else ""
        if requested_version and requested_version not in answer:
            return False

    return True


def filter_supporting_documents(documents: list, analysis: QueryAnalysis) -> list:
    filters = list(analysis.requested_versions)
    if not filters and "author" in analysis.requested_roles:
        version_author_docs = [
            document
            for document in documents
            if (
                (contains_text(document.page_content, "version control") or contains_text(document.page_content, "version history"))
                and contains_text(document.page_content, "author")
            )
        ]
        if version_author_docs:
            return version_author_docs

    if not filters:
        filters.extend(section_keywords_from_analysis(analysis))

    supporting_documents = []
    for document in documents:
        if filters and any(contains_text(document.page_content, item) for item in filters):
            supporting_documents.append(document)

    return supporting_documents or documents


SOURCE_SECTION_HEADING = re.compile(
    r"^\s*(?:#+\s*)?(?:\*\*)?\s*"
    r"(?:sources?|nguồn|nguon|references?|tài liệu tham khảo|tai lieu tham khao)"
    r"\s*(?:\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)


def strip_answer_source_section(answer: str) -> str:
    """Remove model-generated source sections; API/UI return sources separately."""
    lines = (answer or "").strip().splitlines()
    for index, line in enumerate(lines):
        if SOURCE_SECTION_HEADING.match(line):
            return "\n".join(lines[:index]).strip()

    inline_source_match = re.search(
        r"\n\s*(?:\*\*)?\s*(?:sources?|nguồn|nguon|references?|tài liệu tham khảo|tai lieu tham khao)"
        r"\s*(?:\*\*)?\s*:.*\Z",
        answer or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if inline_source_match:
        return (answer or "")[: inline_source_match.start()].strip()

    return (answer or "").strip()


def normalize_conversation_history(history: list | None, max_messages: int = 10) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []

    normalized = []
    for item in history[-max_messages:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content[:1200]})
    return normalized


def conversation_state_from_history(history: list[dict[str, str]]) -> dict:
    state: dict[str, list[str]] = {}
    for item in reversed(history):
        codes = extract_document_codes(item["content"])
        if codes:
            state["last_document_codes"] = codes
            break

    for item in reversed(history):
        if item["role"] != "user":
            continue
        sections = detect_requested_sections(item["content"])
        roles = detect_requested_roles(item["content"])
        topic = sections or roles
        if topic:
            state["last_topic"] = topic
            break

    return state


def format_conversation_history(history: list[dict[str, str]], max_chars: int = 2600) -> str:
    if not history:
        return ""

    lines = []
    remaining = max_chars
    for item in history:
        role = "User" if item["role"] == "user" else "Assistant"
        content = " ".join(item["content"].split())
        line = f"{role}: {content}"
        if len(line) > remaining:
            break
        lines.append(line)
        remaining -= len(line) + 1
    return "\n".join(lines)


def build_history_search_context(history: list[dict[str, str]], question: str) -> str:
    if not history:
        return question

    recent_lines = []
    for item in history[-6:]:
        content = " ".join(item["content"].split())
        recent_lines.append(f"{item['role']}: {content[:500]}")
    return "Recent conversation:\n" + "\n".join(recent_lines) + f"\nCurrent question: {question}"


def call_llm(
    client: OpenAI,
    question: str,
    context: str,
    concise_retry: bool = False,
    analysis: QueryAnalysis | None = None,
    memory_context: str = "",
    conversation_history: list[dict[str, str]] | None = None,
):
    operational_hint = build_operational_prompt_hint(analysis) if analysis else ""
    if operational_hint:
        context = f"{operational_hint}\n{context}"
    memory_section = ""
    if memory_context.strip():
        memory_section = (
            "Ngữ cảnh bộ nhớ hội thoại:\n"
            f"{memory_context.strip()}\n\n"
            "Chỉ dùng ngữ cảnh bộ nhớ để hiểu sở thích người dùng hoặc bối cảnh hội thoại. "
            "Không dùng bộ nhớ để thay thế bằng chứng trong tài liệu.\n\n"
        )
    history_context = format_conversation_history(conversation_history or [])
    history_section = ""
    if history_context:
        history_section = (
            "Recent conversation history:\n"
            f"{history_context}\n\n"
            "Use this history only to resolve follow-up references such as this document, that part, "
            "ý thứ 2, phần đó, or what about scope. The retrieved document context below remains the "
            "source of truth.\n\n"
        )
    messages = [
        {
            "role": "system",
            "content": build_system_prompt(concise_retry=concise_retry),
        },
        {
            "role": "user",
            "content": (
                "/no_think\n"
                "Trả lời trực tiếp bằng nội dung cuối cùng. "
                "Không suy luận nội bộ. Không giải thích quá trình suy luận. "
                "Không tự thêm phần Sources, Nguồn, References hoặc trích dẫn nguồn ở cuối câu trả lời.\n\n"
                f"{memory_section}"
                f"{history_section}"
                f"Ngữ cảnh tài liệu:\n{context}\n\n"
                f"Câu hỏi: {question}"
            ),
        },
    ]
    request_kwargs = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": MAX_TOKENS,
    }

    try:
        return client.chat.completions.create(
            **request_kwargs,
            extra_body={
                "enable_thinking": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
    except APIStatusError as exc:
        if exc.status_code not in {400, 422}:
            raise

        return client.chat.completions.create(
            **request_kwargs,
            extra_body={"enable_thinking": False},
        )


def answer_question(
    question: str,
    vector_store,
    client: OpenAI,
    conversation_state: dict | None = None,
    memory_context: str = "",
    conversation_history: list | None = None,
    debug_info_out: dict | None = None,
    metadata_out: dict | None = None,
) -> tuple[str, list, object]:
    normalized_history = normalize_conversation_history(conversation_history)
    history_state = conversation_state_from_history(normalized_history)
    if conversation_state:
        history_state.update(conversation_state)
    conversation_state = history_state or conversation_state

    if metadata_out is not None:
        metadata_out.clear()
        metadata_out["answer_type"] = "rag"

    analysis = analyze_question(question, conversation_state=conversation_state)
    if analysis.needs_clarification:
        return analysis.clarification_question, [], None

    if conversation_state is not None and analysis.document_codes:
        conversation_state["last_document_codes"] = analysis.document_codes
        conversation_state["last_topic"] = analysis.requested_sections or analysis.requested_roles

    retrieval_question = (
        build_history_search_context(normalized_history, question)
        if analysis.is_follow_up and normalized_history
        else question
    )
    if retrieval_question != question:
        analysis.expanded_query = build_history_search_context(normalized_history, analysis.expanded_query)

    relevant_documents, raw_results, debug_info = retrieve_documents(retrieval_question, vector_store, analysis=analysis)
    if debug_info_out is not None:
        debug_info_out.clear()
        debug_info_out.update(safe_debug_retrieval_payload(debug_info))
    print_retrieval_debug(raw_results, debug_info)

    if not relevant_documents:
        return NO_RELEVANT_CONTEXT_ANSWER, [], None

    context, context_budget = format_context_with_metadata(relevant_documents)
    if debug_info_out is not None:
        debug_info_out["context_budget"] = context_budget
    if not has_sufficient_evidence(context, analysis):
        return NO_RELEVANT_CONTEXT_ANSWER, relevant_documents, None

    deterministic_answer = None
    if not analysis.operational_intents and not analysis.document_discovery_mode:
        deterministic_answer = build_structured_answer(analysis, context)
    if deterministic_answer:
        deterministic_answer = strip_answer_source_section(deterministic_answer)
        if validate_answer(deterministic_answer, analysis, relevant_documents):
            return deterministic_answer, filter_supporting_documents(relevant_documents, analysis), None

    response = call_llm(
        client,
        question,
        context,
        concise_retry=False,
        analysis=analysis,
        memory_context=memory_context,
        conversation_history=normalized_history,
    )
    answer = (response.choices[0].message.content or "").strip()
    if not answer:
        response = call_llm(
            client,
            question,
            context,
            concise_retry=True,
            analysis=analysis,
            memory_context=memory_context,
            conversation_history=normalized_history,
        )
        answer = (response.choices[0].message.content or "").strip()

    if not answer:
        answer = EMPTY_FINAL_ANSWER

    answer = strip_answer_source_section(answer)

    if not validate_answer(answer, analysis, relevant_documents):
        return NO_RELEVANT_CONTEXT_ANSWER, relevant_documents, response.usage

    return answer, relevant_documents, response.usage


def build_system_prompt(concise_retry: bool = False) -> str:
    if concise_retry:
        return (
            "Bạn là trợ lý RAG. Chỉ trả lời dựa trên ngữ cảnh tài liệu. "
            "Không suy luận, không giải thích quá trình suy luận. Nếu không "
            "có thông tin, trả lời: Không tìm thấy thông tin này trong tài liệu hiện có. "
            "Nếu người dùng hỏi số lượng hoặc danh sách tài liệu trong knowledge base, "
            "không suy luận từ các chunks truy xuất; chỉ dùng catalog metadata nếu có. "
            "Không thêm Sources, Nguồn hoặc References trong nội dung trả lời. "
            "Có thể dùng lịch sử hội thoại gần đây để hiểu câu hỏi nối tiếp, nhưng "
            "không dùng lịch sử thay thế bằng chứng trong tài liệu. "
            "Trả lời ngắn gọn bằng tiếng Việt."
        )

    grc_navigation_prompt = (
        "You are an internal GRC/ISMS procedure navigator. Users may ask practical "
        "questions without knowing exact document codes. Your job is to map the "
        "question to the most relevant indexed document, explain what the user "
        "should check or do. Never invent approval flows, ticket "
        "fields, owners, SLAs, or document codes. If the documents only partially "
        "support the answer, state the limitation clearly. For operational how-to "
        "or which-document questions, recommend document candidates first, then "
        "summarize the relevant procedure. Do not include a Sources, Nguồn, "
        "References, citation, or bibliography section inside the answer text; "
        "If the user asks about the number/list of documents in the knowledge base, "
        "do not answer based on retrieved document chunks. Use catalog metadata if "
        "available; otherwise say the catalog is unavailable. "
        "the application returns sources separately. Use recent conversation "
        "history only to resolve follow-up references, not as document evidence. "
    )

    if ANSWER_LANGUAGE == "vi":
        return grc_navigation_prompt + (
            "Bạn là trợ lý RAG cho các tài liệu bảo mật, tuân thủ, chính sách, "
            "quy trình và tiêu chuẩn. Chỉ trả lời từ ngữ cảnh tài liệu được "
            "cung cấp. Không suy đoán và không bổ sung kiến thức bên ngoài. "
            "Luôn tuân thủ đúng ràng buộc trong câu hỏi: nếu người dùng hỏi "
            "một version, section, vai trò, ngày, số thứ tự, scenario hoặc "
            "control cụ thể, chỉ trả lời đúng mục đó và không thay bằng giá trị "
            "mặc định hoặc mới nhất. Chỉ dùng latest/default khi người dùng "
            "không nêu mục tiêu cụ thể. Không trả lời tác giả của latest version "
            "trừ khi người dùng hỏi tác giả của tài liệu mà không nêu version và "
            "không hỏi tất cả tác giả. Nếu người dùng hỏi tất cả tác giả, hãy liệt "
            "kê tất cả tác giả tìm thấy. Nếu người dùng hỏi có bao nhiêu phiên bản, "
            "hãy đếm phiên bản. Nếu người dùng hỏi version cụ thể, chỉ trả lời "
            "version đó. Phân biệt rõ Author/Tác giả, Reviewer, "
            "Approver, Owner, PIC và nhóm chịu trách nhiệm. Nếu chỉ có một phần "
            "thông tin, hãy nói phần có trong tài liệu và phần chưa tìm thấy. "
            "Nếu không đủ bằng chứng, hãy nói rõ không tìm thấy trong tài liệu "
            "được cung cấp hoặc hỏi lại để làm rõ. Giữ nguyên tên hệ thống, "
            "công ty, tài liệu, tiêu chuẩn, chính sách, quy trình và mã tài "
            "liệu. Trả lời ngắn gọn bằng tiếng Việt, dùng gạch đầu dòng cho "
            "danh sách. Bắt đầu ngay bằng câu trả lời cuối cùng. Không giải "
            "thích quá trình suy luận hoặc chain-of-thought. Không thêm phần "
            "Sources, Nguồn, References, Tài liệu tham khảo hoặc danh sách nguồn "
            "trong nội dung trả lời; nguồn sẽ được hiển thị riêng bởi ứng dụng. "
            "Nếu người dùng hỏi số lượng hoặc danh sách tài liệu trong knowledge base, "
            "không được suy luận từ các chunks truy xuất; phải dùng catalog metadata "
            "nếu có, nếu không thì nói catalog không khả dụng. "
            "Khi câu hỏi là câu hỏi nối tiếp, dùng lịch sử hội thoại gần đây để hiểu "
            "đối tượng được nhắc tới, nhưng chỉ kết luận bằng bằng chứng trong ngữ cảnh tài liệu."
        )

    return grc_navigation_prompt + (
        "You are a helpful RAG assistant. Answer using only the provided "
        "document context. If the answer is not in the context, say you do not "
        "know. Keep the final answer concise. Start immediately with the final "
        "answer. Do not explain your reasoning. Do not include Sources, "
        "References, or citation sections in the answer text. If the user asks "
        "about the number/list of documents in the knowledge base, do not infer "
        "that from retrieved chunks; use catalog metadata if available."
    )


def print_sources(documents) -> None:
    seen_keys = set()
    seen_sources = []
    for document in documents:
        if isinstance(document, dict):
            # Catalog/metadata source record (no langchain Document).
            source = document.get("filename") or document.get("label") or "source"
            page = document.get("page")
            score = ""
        else:
            source = document_source_name(document)
            page = document.metadata.get("page")
            score = format_retrieval_score(document)
        key = (source, page)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        page_label = f" page {page + 1}" if isinstance(page, int) else ""
        score_label = f" | score: {score}" if score else ""
        label = f"{source}{page_label}{score_label}"
        if label not in seen_sources:
            seen_sources.append(label)

    if seen_sources:
        print("\nSources:")
        for source in seen_sources:
            print(f"* {source}")


def print_usage(usage) -> None:
    if not SHOW_USAGE or usage is None:
        return

    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    print("\nToken usage:")
    print(f"- prompt: {prompt_tokens}")
    print(f"- completion: {completion_tokens}")
    print(f"- total: {total_tokens}")
