import re
import unicodedata


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\x00", " ").replace("\ufeff", "")

    # Join words split by PDF line wrapping, e.g. "kinh-\ndoanh".
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)

    # Join soft line breaks inside sentences while preserving paragraphs/bullets.
    text = re.sub(r"([^\n.!?:;])\n(?=[^\n\-•*\d])", r"\1 ", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_documents(documents):
    cleaned_documents = []
    for document in documents:
        document.page_content = clean_text(document.page_content)
        if document.page_content:
            cleaned_documents.append(document)

    return cleaned_documents
