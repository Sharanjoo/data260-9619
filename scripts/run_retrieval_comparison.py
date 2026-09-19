"""HW3 Part 2: retrieval-only comparison of Token / Semantic / Sentence-window chunking.

For each of the 5 questions in reports/hw03/questions.yaml, run retrieval against all
three chunking techniques and print + save the required per-query, per-technique table.
"""
import json
import time
from pathlib import Path

import numpy as np
import yaml
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser import (
    TokenTextSplitter,
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

CORPUS_DIR = Path("data/hw03_corpus")
QUESTIONS_PATH = Path("reports/hw03/questions.yaml")
RAW_OUT_DIR = Path("reports/hw03/raw")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5

RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_documents():
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        docs.append(Document(text=text, metadata={"file_name": path.name}))
    return docs


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def build_technique_index(name, docs, embed_model):
    if name == "token":
        parser = TokenTextSplitter(chunk_size=256, chunk_overlap=20)
    elif name == "semantic":
        parser = SemanticSplitterNodeParser(
            buffer_size=1, breakpoint_percentile_threshold=95, embed_model=embed_model
        )
    elif name == "sentence_window":
        parser = SentenceWindowNodeParser.from_defaults(
            window_size=3, window_metadata_key="window", original_text_metadata_key="original_text"
        )
    else:
        raise ValueError(name)

    nodes = parser.get_nodes_from_documents(docs)
    index = VectorStoreIndex(nodes, embed_model=embed_model)
    return nodes, index


def node_text_for_scoring(node_with_score, technique):
    # For sentence-window, score against the *window* text (the retrieval context),
    # not just the single sentence, since that's the actual context the technique carries.
    node = node_with_score.node
    if technique == "sentence_window" and "window" in node.metadata:
        return node.metadata["window"]
    return node.get_content()


def main():
    questions = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]
    docs = load_documents()
    embed_model = HuggingFaceEmbedding(model_name=MODEL_NAME)

    techniques = ["token", "semantic", "sentence_window"]
    indexes = {}
    node_counts = {}
    for tname in techniques:
        print(f"Building index for technique: {tname} ...")
        nodes, index = build_technique_index(tname, docs, embed_model)
        indexes[tname] = index
        node_counts[tname] = len(nodes)
        print(f"  {len(nodes)} nodes indexed.")

    all_rows = []

    for q in questions:
        qid = q["id"]
        query_text = q["question"].strip()
        expected_source = q["expected_source_file"]

        print(f"\n{'='*90}\nQUESTION {qid}: {query_text}\nExpected source: {expected_source}\n{'='*90}")

        query_vec = np.array(embed_model.get_text_embedding(query_text))
        print(f"Query embedding dimension: {query_vec.shape[0]}")
        print(f"First 8 values: {query_vec[:8].tolist()}")

        for tname in techniques:
            retriever = indexes[tname].as_retriever(similarity_top_k=TOP_K)

            t0 = time.perf_counter()
            results = retriever.retrieve(query_text)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            doc_vecs = []
            table_rows = []
            for rank, nws in enumerate(results, start=1):
                scoring_text = node_text_for_scoring(nws, tname)
                doc_vec = np.array(embed_model.get_text_embedding(scoring_text))
                doc_vecs.append(doc_vec)

                cos_sim = cosine(query_vec, doc_vec)
                content = nws.node.get_content()
                chunk_len = len(content)
                preview = content[:160].replace("\n", " ").strip()
                source_file = nws.node.metadata.get("file_name", "?")

                table_rows.append({
                    "rank": rank,
                    "store_score": float(nws.score) if nws.score is not None else None,
                    "cosine_sim": cos_sim,
                    "chunk_len": chunk_len,
                    "preview": preview,
                    "source_file": source_file,
                })

            doc_matrix = np.stack(doc_vecs) if doc_vecs else np.zeros((0, query_vec.shape[0]))

            print(f"\n--- Technique: {tname} ---")
            print(f"Query vector shape: {query_vec.shape}  |  Stacked doc vectors shape: {doc_matrix.shape}")
            print(f"Retrieval latency: {latency_ms:.2f} ms")
            print(f"{'rank':<5}{'store_score':<14}{'cosine_sim':<12}{'chunk_len':<11}{'source_file':<45}preview")
            for r in table_rows:
                print(f"{r['rank']:<5}{r['store_score']:<14.4f}{r['cosine_sim']:<12.4f}{r['chunk_len']:<11}{r['source_file']:<45}{r['preview'][:70]}")

            hit_at_k = any(r["source_file"] == expected_source for r in table_rows)

            for r in table_rows:
                all_rows.append({
                    "question_id": qid,
                    "question": query_text,
                    "expected_source_file": expected_source,
                    "technique": tname,
                    "rank": r["rank"],
                    "store_score": r["store_score"],
                    "cosine_sim": r["cosine_sim"],
                    "chunk_len": r["chunk_len"],
                    "preview": r["preview"],
                    "source_file": r["source_file"],
                    "retrieval_latency_ms": latency_ms,
                    "hit_expected_source_in_topk": hit_at_k,
                    "num_chunks_technique": node_counts[tname],
                })

    out_path = RAW_OUT_DIR / "retrieval_results.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")

    print(f"\n\nSaved {len(all_rows)} rows to {out_path}")


if __name__ == "__main__":
    main()