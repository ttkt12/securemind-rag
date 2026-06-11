# SecureMind RAG

Local RAG-powered knowledge assistant for security, compliance, policy, procedure, and standard documents.

## Overview

SecureMind RAG is a local Retrieval-Augmented Generation knowledge assistant for querying security, compliance, policy, procedure, standard, ISMS, and governance documents. It ingests local PDF files, builds a FAISS vector database, retrieves relevant document context, and answers through a CLI chatbot with source traceability.

The project is designed as a local-first foundation that can later be extended with SharePoint and Microsoft Teams integration.

## Key Capabilities

* Local PDF ingestion
* Text cleaning and chunking
* Embedding generation
* FAISS vector database
* Hybrid retrieval using semantic search, document code detection, and section keyword matching
* Vietnamese and English query support
* Source traceability with file name, page number, and retrieval score
* CLI-based local interaction
* Future-ready architecture for SharePoint and Microsoft Teams integration

## Architecture

```text
Local Document Repository
↓
Document Ingestion
↓
Text Cleaning & Chunking
↓
Embedding Generation
↓
FAISS Vector Store
↓
RAG Core
↓
CLI Interface
↓
Future: Microsoft Teams Bot
```

## Project Structure

```text
.
├── papers/
│   └── .gitkeep
├── config.py
├── text_utils.py
├── ingest.py
├── rag_core.py
├── chatbot.py
├── example.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Local Setup

1. Clone the repository

```bash
git clone https://github.com/<your-username>/securemind-rag.git
cd securemind-rag
```

2. Create virtual environment

```bash
python -m venv .venv
```

3. Activate virtual environment

Windows:

```powershell
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

4. Install dependencies

```bash
pip install -r requirements.txt
```

5. Create local environment file

Windows:

```powershell
copy .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

6. Add API key into `.env`

7. Add PDF documents into `papers/`

8. Build vector database

```bash
python ingest.py
```

9. Run chatbot

```bash
python chatbot.py
```

## Configuration

| Variable | Description |
| --- | --- |
| `AI_PLATFORM_API_KEY` | API key for the configured model provider. |
| `AI_PLATFORM_BASE_URL` | OpenAI-compatible base URL for the configured provider. |
| `AI_PLATFORM_MODEL` | Model identifier used for chat completions. |
| `PAPERS_DIR` | Local folder containing PDF documents for ingestion. |
| `VECTOR_DB_DIR` | Local folder where the FAISS vector database is saved. |
| `EMBEDDING_MODEL` | Sentence embedding model used for document chunks and queries. |
| `RETRIEVAL_K` | Number of final documents selected for answer context. |
| `RETRIEVAL_FETCH_K` | Number of semantic candidates fetched before ranking/filtering. |
| `MAX_CONTEXT_CHARS` | Maximum retrieved context characters sent to the model. |
| `SHOW_USAGE` | Enables token usage display after model calls. |
| `DEBUG_RETRIEVAL` | Enables retrieval debug output for local troubleshooting. |
| `ANSWER_LANGUAGE` | Preferred answer language, currently optimized for Vietnamese. |

## Security Notes

* `.env` must never be committed.
* Internal PDF documents must not be committed.
* `vector_db/` is excluded because it can be rebuilt locally.
* `papers/` is kept as a local-only document folder.
* Use a private repository for internal, enterprise, or competition work.
* SharePoint and Teams integration should respect document permissions in future phases.

## Roadmap

* Local evaluation framework
* Document metadata handler
* Incremental indexing
* SharePoint document connector
* Microsoft Teams bot interface
* Permission-aware retrieval
* Admin monitoring and usage logging

## License

License to be defined.
