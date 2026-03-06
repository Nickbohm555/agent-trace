"""Load and chunk AI-related text into LangChain Document objects."""

from __future__ import annotations

import json
from typing import List

from langchain_core.documents import Document
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


DEFAULT_AI_SOURCE = "https://en.wikipedia.org/wiki/Artificial_intelligence"
DEFAULT_LOG_PATH = "loader.log"


def load_ai_wiki_chunks(
    source_url: str = DEFAULT_AI_SOURCE,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> List[Document]:
    """Load an AI Wikipedia source URL and return chunked LangChain Document objects."""
    loader = WebBaseLoader(web_paths=(source_url,))
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunked_docs = splitter.split_documents(docs)
    return chunked_docs


def log_chunk_examples(
    docs: List[Document],
    log_path: str = DEFAULT_LOG_PATH,
    max_examples: int = 3,
    preview_chars: int = 200,
) -> None:
    """Write short chunk-content and metadata examples to a log file."""
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Total chunks: {len(docs)}\n\n")
        for i, doc in enumerate(docs[:max_examples], start=1):
            preview = doc.page_content[:preview_chars].replace("\n", " ")
            f.write(f"Example {i}\n")
            f.write(f"page_content_preview: {preview}...\n")
            f.write(f"metadata: {json.dumps(doc.metadata, ensure_ascii=True)}\n\n")


if __name__ == "__main__":
    chunks = load_ai_wiki_chunks()
    log_chunk_examples(chunks)
    print(f"Loaded {len(chunks)} chunks from {DEFAULT_AI_SOURCE}")
    if chunks:
        preview = chunks[0].page_content[:300].replace("\n", " ")
        print(f"First chunk preview: {preview}...")
    print(f"Wrote chunk examples to {DEFAULT_LOG_PATH}")
