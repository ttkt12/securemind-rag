import re
from pathlib import Path
from uuid import uuid4

import numpy as np
from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    PAPERS_DIR,
    SEMANTIC_CHUNKING_ENABLED,
    SEMANTIC_CHUNK_MAX_CHARS,
    SEMANTIC_CHUNK_MIN_CHARS,
    SEMANTIC_CHUNK_SIMILARITY_THRESHOLD,
    VECTOR_DB_DIR,
    make_embeddings,
)
from langchain_core.documents import Document
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from text_utils import clean_documents


STRUCTURAL_SEPARATORS = [
    r"\n(?=\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:Mục đích|Muc dich|Phạm vi(?: áp dụng)?|Pham vi(?: ap dung)?|Định nghĩa|Dinh nghia|Tài liệu liên quan|Tai lieu lien quan|Trách nhiệm|Trach nhiem|Nội dung|Noi dung|Quy trình|Quy trinh|Biểu mẫu|Bieu mau|Scope|Purpose|Definition|Responsibility|Responsibilities|Procedure|Process|Policy)\b)",
    r"\n(?=\s*\d+(?:\.\d+)+\.?\s+)",
    r"\n(?=\s*(?:[-*•]|\([a-zA-Z0-9]+\))\s+)",
    r"\n\n",
    r"\n",
    r"\.\s+",
    r";\s+",
    r",\s+",
    r"\s+",
    "",
]

SECTION_HEADING_RE = re.compile(
    r"^\s*(?:(?:\d+(?:\.\d+)*|[IVX]+)\.?\s+)?"
    r"(?P<title>"
    r"Mục đích|Muc dich|Phạm vi(?: áp dụng)?|Pham vi(?: ap dung)?|Định nghĩa|Dinh nghia|"
    r"Tài liệu liên quan|Tai lieu lien quan|Trách nhiệm|Trach nhiem|Nội dung|Noi dung|"
    r"Quy trình|Quy trinh|Biểu mẫu|Bieu mau|Scope|Purpose|Definition|"
    r"Responsibility|Responsibilities|Procedure|Process|Policy"
    r")\b.*$",
    re.IGNORECASE,
)
NUMBERED_HEADING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+[^\n]{3,120}$")
SENTENCE_OR_PARAGRAPH_RE = re.compile(r"(?<=[.!?。！？])\s+|\n{2,}")


def clean_source_filename(source: str) -> str:
    source_name = Path(str(source or "unknown")).name
    stem = Path(source_name).stem
    suffix = Path(source_name).suffix
    stem = re.sub(
        r"[-_\s]*(?:ThangNguyen[’']s Mac mini|copy of|copy)$",
        "",
        stem,
        flags=re.IGNORECASE,
    )
    stem = re.sub(r"\s*\(\d+\)$", "", stem)
    stem = re.sub(r"\s{2,}", " ", stem).strip(" -_")
    return f"{stem}{suffix}" if stem else source_name


def load_documents():
    if not PAPERS_DIR.exists():
        raise FileNotFoundError(f"Cannot find papers folder: {PAPERS_DIR.resolve()}")

    loader = DirectoryLoader(
        path=str(PAPERS_DIR),
        glob="**/*.pdf",
        loader_cls=PyPDFLoader,
        show_progress=True,
        use_multithreading=True,
    )
    documents = loader.load()

    if not documents:
        raise RuntimeError(f"No PDF documents found in {PAPERS_DIR.resolve()}")

    return documents


def extract_document_code(source_name: str) -> str:
    match = re.search(r"\b[A-Z]{2,10}-[A-Z]{2,10}-\d{2,3}\b|\bISMS-\d{2,3}\b", source_name.upper())
    return match.group(0) if match else ""


def normalize_section_title(line: str) -> str:
    title = " ".join(str(line or "").strip().split())
    return title[:140]


def is_section_heading(line: str) -> bool:
    clean_line = normalize_section_title(line)
    if not clean_line:
        return False
    if SECTION_HEADING_RE.match(clean_line):
        return True
    return bool(NUMBERED_HEADING_RE.match(clean_line) and len(clean_line.split()) <= 18)


def split_page_into_sections(document: Document) -> list[Document]:
    source_name = clean_source_filename(document.metadata.get("source", "unknown"))
    default_title = Path(source_name).stem
    sections: list[tuple[str, list[str]]] = []
    current_title = default_title
    current_lines: list[str] = []

    for raw_line in document.page_content.splitlines():
        line = raw_line.rstrip()
        if is_section_heading(line) and current_lines:
            sections.append((current_title, current_lines))
            current_title = normalize_section_title(line)
            current_lines = [line]
            continue
        if is_section_heading(line) and not current_lines:
            current_title = normalize_section_title(line)
        current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    section_documents = []
    for section_index, (section_title, lines) in enumerate(sections):
        content = "\n".join(lines).strip()
        if not content:
            continue
        metadata = dict(document.metadata)
        metadata["source_filename"] = source_name
        metadata["document_code"] = extract_document_code(source_name)
        metadata["section_title"] = section_title
        metadata["section_index"] = section_index
        page = metadata.get("page")
        if isinstance(page, int):
            metadata["page_number"] = page + 1
        section_documents.append(Document(page_content=content, metadata=metadata))

    return section_documents


def make_structural_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
        strip_whitespace=True,
        is_separator_regex=True,
        separators=STRUCTURAL_SEPARATORS,
    )


def split_structural_documents(documents: list[Document]) -> list[Document]:
    splitter = make_structural_splitter()
    chunks: list[Document] = []
    for document in documents:
        for section_document in split_page_into_sections(document):
            if len(section_document.page_content) <= CHUNK_SIZE:
                chunks.append(section_document)
            else:
                chunks.extend(splitter.split_documents([section_document]))
    return chunks


def sentence_units(text: str) -> list[str]:
    units = [unit.strip() for unit in SENTENCE_OR_PARAGRAPH_RE.split(text or "") if unit.strip()]
    if len(units) <= 1:
        units = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return units


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0:
        return 0.0
    return float(np.dot(left, right) / denominator)


def semantic_split_document(document: Document, embeddings) -> list[Document]:
    units = sentence_units(document.page_content)
    if len(units) <= 2 or len(document.page_content) <= SEMANTIC_CHUNK_MAX_CHARS:
        return [document]

    vectors = np.array(embeddings.embed_documents(units), dtype=np.float32)
    chunks: list[str] = []
    current_units = [units[0]]
    current_length = len(units[0])

    for index in range(1, len(units)):
        similarity = cosine_similarity(vectors[index - 1], vectors[index])
        next_unit = units[index]
        next_length = len(next_unit)
        should_split = (
            current_length >= SEMANTIC_CHUNK_MIN_CHARS
            and similarity < SEMANTIC_CHUNK_SIMILARITY_THRESHOLD
        ) or current_length + next_length > SEMANTIC_CHUNK_MAX_CHARS

        if should_split:
            chunks.append(" ".join(current_units).strip())
            current_units = [next_unit]
            current_length = next_length
        else:
            current_units.append(next_unit)
            current_length += next_length + 1

    if current_units:
        chunks.append(" ".join(current_units).strip())

    merged_chunks: list[str] = []
    for chunk in chunks:
        if merged_chunks and len(chunk) < SEMANTIC_CHUNK_MIN_CHARS:
            merged_chunks[-1] = f"{merged_chunks[-1]}\n{chunk}".strip()
        else:
            merged_chunks.append(chunk)

    documents = []
    for semantic_index, chunk in enumerate(merged_chunks):
        metadata = dict(document.metadata)
        metadata["semantic_chunk_index"] = semantic_index
        documents.append(Document(page_content=chunk, metadata=metadata))
    return documents or [document]


def split_semantic_documents(documents: list[Document], embeddings) -> list[Document]:
    semantic_chunks: list[Document] = []
    for document in documents:
        semantic_chunks.extend(semantic_split_document(document, embeddings))
    return semantic_chunks


def split_documents(documents: list[Document], embeddings=None) -> list[Document]:
    structural_chunks = split_structural_documents(documents)
    if not SEMANTIC_CHUNKING_ENABLED:
        return structural_chunks
    if embeddings is None:
        embeddings = make_embeddings()
    return split_semantic_documents(structural_chunks, embeddings)


def clean_chunk_metadata(chunks):
    for index, chunk in enumerate(chunks):
        metadata = dict(chunk.metadata)
        source = metadata.get("source", "unknown")
        source_name = metadata.get("source_filename") or clean_source_filename(source)
        metadata["source_filename"] = source_name
        metadata["document_code"] = metadata.get("document_code") or extract_document_code(source_name)
        metadata["section_title"] = metadata.get("section_title") or Path(source_name).stem
        page = metadata.get("page")
        if isinstance(page, int):
            metadata["page_number"] = page + 1
        if "start_index" in metadata:
            metadata["chunk_start"] = metadata["start_index"]
        metadata["chunk_id"] = (
            f"{metadata.get('document_code') or Path(source_name).stem}:"
            f"p{metadata.get('page_number', 'unknown')}:"
            f"{metadata.get('section_index', 0)}:{index}"
        )
        metadata["ingest_chunk_uuid"] = str(uuid4())
        metadata["chunking_strategy"] = (
            "semantic-document-aware" if SEMANTIC_CHUNKING_ENABLED else "document-aware"
        )
        chunk.metadata = metadata
    return chunks


def build_vector_store():
    print(f"Loading PDFs from {PAPERS_DIR.resolve()}...")
    documents = clean_documents(load_documents())
    print(f"Loaded {len(documents)} document pages.")

    embeddings = make_embeddings()
    chunks = clean_chunk_metadata(split_documents(documents, embeddings=embeddings))
    strategy = "semantic document-aware" if SEMANTIC_CHUNKING_ENABLED else "document-aware"
    print(f"Created {len(chunks)} text chunks using {strategy} chunking.")

    print("Creating local embeddings and FAISS index...")
    return FAISS.from_documents(chunks, embeddings)


def main() -> None:
    vector_store = build_vector_store()
    VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(VECTOR_DB_DIR))
    print(f"Saved vector database to {VECTOR_DB_DIR.resolve()}")


if __name__ == "__main__":
    main()
