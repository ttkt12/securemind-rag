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
from langchain_community.vectorstores import FAISS
from openai import APIStatusError, OpenAI

NO_RELEVANT_CONTEXT_ANSWER = (
    "Không tìm thấy thông tin này trong tài liệu được cung cấp. "
    "Bạn có thể hỏi lại cụ thể hơn hoặc kiểm tra xem tài liệu liên quan "
    "đã được thêm vào hệ thống chưa."
)
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
    is_follow_up: bool = False
    needs_clarification: bool = False
    clarification_question: str = ""
    expanded_query: str = ""


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


def format_context(documents) -> str:
    context_parts = []
    remaining_chars = MAX_CONTEXT_CHARS

    for index, document in enumerate(documents, start=1):
        if remaining_chars <= 0:
            break

        source = Path(document.metadata.get("source", "unknown")).name
        page = document.metadata.get("page")
        page_label = f", page {page + 1}" if isinstance(page, int) else ""
        content = document.page_content[:remaining_chars]
        remaining_chars -= len(content)
        context_parts.append(f"[{index}] Source: {source}{page_label}\n{content}")

    return "\n\n".join(context_parts)


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or "")).lower()
    return " ".join(text.split())


def fold_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or ""))
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def contains_text(haystack: str, needle: str) -> bool:
    normalized_haystack = normalize_for_match(haystack)
    normalized_needle = normalize_for_match(needle)
    if normalized_needle in normalized_haystack:
        return True

    return fold_accents(normalized_needle) in fold_accents(normalized_haystack)


def extract_document_codes(question: str) -> list[str]:
    codes = re.findall(r"\b[A-Z]{2,10}-[A-Z]{2,10}-\d{2,3}\b", question.upper())
    return list(dict.fromkeys(codes))


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
    ]
    return len(folded_question.split()) <= 6 or any(term in folded_question for term in follow_up_terms)


def has_count_terms(text: str) -> bool:
    folded_text = fold_accents(normalize_for_match(text))
    return any(term in folded_text for term in ("may", "bao nhieu", "how many", "count"))


def has_list_all_terms(text: str) -> bool:
    folded_text = fold_accents(normalize_for_match(text))
    return any(
        term in folded_text
        for term in ("tat ca", "toan bo", "liet ke", "ke", "ke ten", "danh sach", "all", "list")
    )


def has_version_terms(text: str) -> bool:
    folded_text = fold_accents(normalize_for_match(text))
    return any(term in folded_text for term in ("phien ban", "version", "ver", " v"))


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


def expand_query(question: str, analysis: QueryAnalysis | None = None) -> str:
    folded_question = fold_accents(normalize_for_match(question))
    expansions = []
    roles = analysis.requested_roles if analysis else detect_requested_roles(question)
    sections = analysis.requested_sections if analysis else detect_requested_sections(question)
    versions = analysis.requested_versions if analysis else extract_requested_versions(question)
    document_codes = analysis.document_codes if analysis else extract_document_codes(question)

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
    if not analysis.document_codes and requires_document_context:
        analysis.needs_clarification = True
        analysis.intent = "ambiguous_follow_up" if is_follow_up else analysis.intent
        analysis.clarification_question = build_clarification_question(analysis)

    analysis.expanded_query = expand_query(question, analysis)
    return analysis


def decide_retrieval_strategy(analysis: QueryAnalysis) -> dict:
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

    return {
        "use_keyword": exact_constraints,
        "use_semantic": True,
        "filter_document_code": bool(analysis.document_codes),
        "prefer_exact_constraints": exact_constraints,
        "keyword_limit": keyword_limit,
        "fetch_k": RETRIEVAL_FETCH_K,
    }


def document_source_name(document) -> str:
    return Path(document.metadata.get("source", "unknown")).name


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
    matches = []
    for document in vector_store.docstore._dict.values():
        if document_codes and not document_matches_code(document, document_codes):
            continue

        matched_keywords = [
            keyword
            for keyword in keywords_to_match
            if contains_text(document.page_content, keyword)
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
        code_priority = 0 if document_codes and document_matches_code(document, document_codes) else 1
        toc_priority = 1 if looks_like_table_of_contents(document) else 0
        page = selected_document.metadata.get("page")
        page_priority = page if isinstance(page, int) else 999999
        matches.append(
            (
                code_priority,
                keyword_rank + (2 if toc_priority else 0),
                page_priority,
                -len(matched_keywords),
                page_priority,
                selected_document,
            )
        )

    non_toc_matches = [item for item in matches if not looks_like_table_of_contents(item[5])]
    if non_toc_matches:
        matches = non_toc_matches

    matches.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
    return [item[5] for item in matches[:limit]]


def keyword_density(document, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if contains_text(document.page_content, keyword))


def rank_evidence(documents: list, analysis: QueryAnalysis) -> list:
    section_keywords = section_keywords_from_analysis(analysis)

    def sort_key(document):
        source = document_source_name(document).upper()
        page = document.metadata.get("page")
        page_priority = page if isinstance(page, int) else 999999
        exact_document = 0 if not analysis.document_codes or any(code in source for code in analysis.document_codes) else 1
        version_match = 0 if not analysis.requested_versions or any(contains_text(document.page_content, version) for version in analysis.requested_versions) else 1
        role_match = 0 if not analysis.requested_roles or document_has_any_keyword(document, section_keywords) else 1
        section_match = 0 if not analysis.requested_sections or document_has_any_keyword(document, section_keywords) else 1
        toc_penalty = 1 if looks_like_table_of_contents(document) else 0
        method_priority = 0 if document.metadata.get("retrieval_method") == "keyword" else 1
        keyword_rank = document.metadata.get("keyword_rank")
        keyword_rank = keyword_rank if isinstance(keyword_rank, int) else 4
        score = document.metadata.get("retrieval_score")
        semantic_score = score if isinstance(score, float) else 0.0
        density = -keyword_density(document, section_keywords)
        source_name = document_source_name(document) if not analysis.document_codes else ""
        return (
            exact_document,
            version_match,
            role_match,
            section_match,
            method_priority,
            keyword_rank,
            toc_penalty,
            density,
            semantic_score,
            page_priority,
            source_name,
        )

    return sorted(documents, key=sort_key)


def retrieve_documents(question: str, vector_store, analysis: QueryAnalysis | None = None) -> tuple[list, list, dict]:
    analysis = analysis or analyze_question(question)
    strategy = decide_retrieval_strategy(analysis)
    document_codes = analysis.document_codes
    section_keywords = section_keywords_from_analysis(analysis)
    expanded_query = analysis.expanded_query
    exact_question = bool(document_codes or section_keywords or analysis.requested_versions or analysis.requested_entities)
    keyword_limit = strategy["keyword_limit"]

    keyword_documents = keyword_search_documents(
        vector_store,
        document_codes,
        section_keywords,
        limit=keyword_limit,
    ) if strategy["use_keyword"] else []
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
        semantic_documents.append(selected_document)

    combined_candidates = rank_evidence(keyword_documents + semantic_documents, analysis)
    combined_documents = []
    seen_keys = set()
    result_limit = max(RETRIEVAL_K, 3) if analysis.intent == "version_author_mapping" else RETRIEVAL_K
    for document in combined_candidates:
        key = document_key(document)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        combined_documents.append(document)
        if len(combined_documents) >= result_limit:
            break

    debug_info = {
        "expanded_query": expanded_query,
        "document_codes": document_codes,
        "section_keywords": section_keywords,
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
    print(f"- threshold: {MIN_RELEVANCE_SCORE}")

    print("- selected documents:")
    for index, document in enumerate(debug_info["selected_documents"], start=1):
        source = Path(document.metadata.get("source", "unknown")).name
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
        source = Path(document.metadata.get("source", "unknown")).name
        page = document.metadata.get("page")
        page_label = f" page {page + 1}" if isinstance(page, int) else ""
        print(f"  {index}. {source}{page_label} | score: {float(score):.4f}")


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


def call_llm(client: OpenAI, question: str, context: str, concise_retry: bool = False):
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
                "Không suy luận nội bộ. Không giải thích quá trình suy luận.\n\n"
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
) -> tuple[str, list, object]:
    analysis = analyze_question(question, conversation_state=conversation_state)
    if analysis.needs_clarification:
        return analysis.clarification_question, [], None

    if conversation_state is not None and analysis.document_codes:
        conversation_state["last_document_codes"] = analysis.document_codes
        conversation_state["last_topic"] = analysis.requested_sections or analysis.requested_roles

    relevant_documents, raw_results, debug_info = retrieve_documents(question, vector_store, analysis=analysis)
    print_retrieval_debug(raw_results, debug_info)

    if not relevant_documents:
        return NO_RELEVANT_CONTEXT_ANSWER, [], None

    context = format_context(relevant_documents)
    if not has_sufficient_evidence(context, analysis):
        return NO_RELEVANT_CONTEXT_ANSWER, relevant_documents, None

    deterministic_answer = build_structured_answer(analysis, context)
    if deterministic_answer:
        if validate_answer(deterministic_answer, analysis, relevant_documents):
            return deterministic_answer, filter_supporting_documents(relevant_documents, analysis), None

    response = call_llm(client, question, context, concise_retry=False)
    answer = (response.choices[0].message.content or "").strip()
    if not answer:
        response = call_llm(client, question, context, concise_retry=True)
        answer = (response.choices[0].message.content or "").strip()

    if not answer:
        answer = EMPTY_FINAL_ANSWER

    if not validate_answer(answer, analysis, relevant_documents):
        return NO_RELEVANT_CONTEXT_ANSWER, relevant_documents, response.usage

    return answer, relevant_documents, response.usage


def build_system_prompt(concise_retry: bool = False) -> str:
    if concise_retry:
        return (
            "Bạn là trợ lý RAG. Chỉ trả lời dựa trên ngữ cảnh tài liệu. "
            "Không suy luận, không giải thích quá trình suy luận. Nếu không "
            "có thông tin, trả lời: Không tìm thấy thông tin này trong tài liệu "
            "được cung cấp. Trả lời ngắn gọn bằng tiếng Việt."
        )

    if ANSWER_LANGUAGE == "vi":
        return (
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
            "thích quá trình suy luận hoặc chain-of-thought."
        )

    return (
        "You are a helpful RAG assistant. Answer using only the provided "
        "document context. If the answer is not in the context, say you do not "
        "know. Keep the final answer concise. Start immediately with the final "
        "answer. Do not explain your reasoning."
    )


def print_sources(documents) -> None:
    seen_keys = set()
    seen_sources = []
    for document in documents:
        source = Path(document.metadata.get("source", "unknown")).name
        page = document.metadata.get("page")
        key = (source, page)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        page_label = f" page {page + 1}" if isinstance(page, int) else ""
        score = format_retrieval_score(document)
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
