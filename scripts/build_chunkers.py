"""HW3 Part 2: build the three chunking pipelines over the domain corpus."""
from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import (
    TokenTextSplitter,
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

CORPUS_DIR = Path("data/hw03_corpus")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def load_documents():
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        docs.append(Document(text=text, metadata={"file_name": path.name}))
    return docs


def avg_len(nodes):
    if not nodes:
        return 0
    return sum(len(n.get_content()) for n in nodes) / len(nodes)


def main():
    docs = load_documents()
    print(f"Loaded {len(docs)} source documents, {sum(len(d.text) for d in docs):,} total characters\n")

    embed_model = HuggingFaceEmbedding(model_name=MODEL_NAME)

    # 1. Token-based chunking
    token_splitter = TokenTextSplitter(chunk_size=256, chunk_overlap=20)
    token_nodes = token_splitter.get_nodes_from_documents(docs)
    print(f"[Token]           {len(token_nodes)} chunks, avg length {avg_len(token_nodes):.1f} chars")

    # 2. Semantic chunking
    semantic_splitter = SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model,
    )
    semantic_nodes = semantic_splitter.get_nodes_from_documents(docs)
    print(f"[Semantic]        {len(semantic_nodes)} chunks, avg length {avg_len(semantic_nodes):.1f} chars")

    # 3. Sentence-window chunking
    window_splitter = SentenceWindowNodeParser.from_defaults(
        window_size=3,
        window_metadata_key="window",
        original_text_metadata_key="original_text",
    )
    window_nodes = window_splitter.get_nodes_from_documents(docs)
    print(f"[Sentence-window] {len(window_nodes)} chunks, avg length {avg_len(window_nodes):.1f} chars")

    print("\n--- Sample chunk from each technique (first 200 chars) ---")
    print(f"\nToken:\n{token_nodes[0].get_content()[:200]}")
    print(f"\nSemantic:\n{semantic_nodes[0].get_content()[:200]}")
    print(f"\nSentence-window:\n{window_nodes[0].get_content()[:200]}")
    print(f"Sentence-window metadata keys: {list(window_nodes[0].metadata.keys())}")


if __name__ == "__main__":
    main()