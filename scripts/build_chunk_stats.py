"""HW3 Part 2: capture full-corpus chunk stats (count, avg length) per technique.

Saved separately from retrieval_results.jsonl because that file only records the
top-k *retrieved* chunks per query, not every chunk the parser produced.
"""
import csv
from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import (
    TokenTextSplitter,
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

CORPUS_DIR = Path("data/hw03_corpus")
RAW_OUT_DIR = Path("reports/hw03/raw")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_documents():
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        docs.append(Document(text=text, metadata={"file_name": path.name}))
    return docs


def main():
    docs = load_documents()
    embed_model = HuggingFaceEmbedding(model_name=MODEL_NAME)

    parsers = {
        "token": TokenTextSplitter(chunk_size=256, chunk_overlap=20),
        "semantic": SemanticSplitterNodeParser(
            buffer_size=1, breakpoint_percentile_threshold=95, embed_model=embed_model
        ),
        "sentence_window": SentenceWindowNodeParser.from_defaults(
            window_size=3, window_metadata_key="window", original_text_metadata_key="original_text"
        ),
    }

    rows = []
    for tname, parser in parsers.items():
        nodes = parser.get_nodes_from_documents(docs)
        lengths = [len(n.get_content()) for n in nodes]
        num_chunks = len(nodes)
        avg_len = sum(lengths) / num_chunks if num_chunks else 0
        rows.append({
            "technique": tname,
            "num_chunks": num_chunks,
            "avg_chunk_length_chars": round(avg_len, 1),
            "min_chunk_length_chars": min(lengths) if lengths else 0,
            "max_chunk_length_chars": max(lengths) if lengths else 0,
        })
        print(f"[{tname}] {num_chunks} chunks, avg length {avg_len:.1f} chars "
              f"(min {min(lengths) if lengths else 0}, max {max(lengths) if lengths else 0})")

    out_path = RAW_OUT_DIR / "chunk_stats.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()