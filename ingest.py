from config import CHUNK_OVERLAP, CHUNK_SIZE, PAPERS_DIR, VECTOR_DB_DIR, make_embeddings
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from text_utils import clean_documents


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


def split_documents(documents):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
        strip_whitespace=True,
        separators=[
            "\n\n",
            "\n",
            ". ",
            "; ",
            ", ",
            " ",
            "",
        ],
    )
    return text_splitter.split_documents(documents)


def build_vector_store():
    print(f"Loading PDFs from {PAPERS_DIR.resolve()}...")
    documents = clean_documents(load_documents())
    print(f"Loaded {len(documents)} document pages.")

    chunks = split_documents(documents)
    print(f"Created {len(chunks)} text chunks.")

    print("Creating local embeddings and FAISS index...")
    return FAISS.from_documents(chunks, make_embeddings())


def main() -> None:
    vector_store = build_vector_store()
    VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(VECTOR_DB_DIR))
    print(f"Saved vector database to {VECTOR_DB_DIR.resolve()}")


if __name__ == "__main__":
    main()
