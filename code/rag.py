"""HW4 Part 4: Grounded RAG Question-Answering System.

Corpus: data/hw03_corpus (25 CDC/FDA food-safety/recall documents, reused from
HW3 -- well past the 5-document minimum, same domain as this app).
Embeddings: sentence-transformers/all-MiniLM-L6-v2 (same model as HW3).
Chunking: LlamaIndex TokenTextSplitter(chunk_size=500, chunk_overlap=50).
Vector store: FAISS (IndexFlatIP over L2-normalized vectors == cosine similarity).
Generation: qwen3:8b via Ollama, through the existing src/model_client.py adapter.

Usage:
    python code/rag.py
    python code/rag.py --ollama-url http://localhost:11434
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from llama_index.core import Document  # noqa: E402
from llama_index.core.node_parser import TokenTextSplitter  # noqa: E402
from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # noqa: E402
import faiss  # noqa: E402

from model_client import ModelClientError, OllamaModelClient  # noqa: E402

CORPUS_DIR = REPO_ROOT / "data" / "hw03_corpus"
RAW_DIR = REPO_ROOT / "reports" / "hw04" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = "qwen3:8b"

TOP_K_DEFAULT = 3
POOL_K_FOR_ENGINEERING = 5  # retrieve a slightly larger pool for Config C to filter down from

REFUSAL_TEXT = "I cannot answer this question from the provided documents."

# Relevance/dedup thresholds for Config C (context-engineered). Cosine similarity
# with MiniLM: on-topic chunks for these questions typically score ~0.4-0.7;
# off-topic chunks (e.g. for Q5/Q6) typically score well under 0.25.
DEDUP_SIM_THRESHOLD = 0.93   # near-duplicate chunks above this similarity are dropped
REL_MARGIN = 0.15            # drop chunks scoring more than this far below the top hit
ABS_SCORE_FLOOR = 0.20       # drop chunks below this absolute score regardless of margin


# ---------------------------------------------------------------------------
# The six required test questions (spec: Q1 one chunk, Q2 two chunks, Q3 similar
# info across docs, Q4 ambiguous, Q5 not in docs, Q6 unrelated -- Q5/Q6 must
# refuse). Each was checked against the actual corpus content before being
# written: Q5 in particular was grepped against the whole corpus (no "ground
# beef"/"hamburger" hits anywhere) so it's a genuine gap, not an accidental hit.
# ---------------------------------------------------------------------------
QUESTIONS = [
    {
        "id": "Q1",
        "type": "single_chunk",
        "question": "What is the difference between an FDA Class I, Class II, and Class III recall?",
        "expected_sources": ["fda_recalls_background_definitions.txt"],
        "refuse_expected": False,
    },
    {
        "id": "Q2",
        "type": "two_chunks",
        "question": (
            "Compare CDC's Listeria monocytogenes investigations into deli meats (2024) "
            "and Requeson soft cheese (June 2026): what were the total illness counts, "
            "hospitalizations, and deaths reported for each outbreak?"
        ),
        "expected_sources": ["cdc_listeria_delimeats_2024.txt", "cdc_listeria_soft_cheese_june2026.txt"],
        "refuse_expected": False,
    },
    {
        "id": "Q3",
        "type": "similar_across_docs",
        "question": (
            "What law added sesame as the ninth major food allergen in the United States, "
            "and when did the labeling requirement take effect?"
        ),
        "expected_sources": ["fda_food_allergies.txt", "fda_allergen_labeling_qa_edition5.txt"],
        "refuse_expected": False,
    },
    {
        "id": "Q4",
        "type": "ambiguous",
        "question": "How serious is Salmonella food poisoning?",
        "expected_sources": [],  # deliberately ambiguous: several docs are each a reasonable match
        "refuse_expected": False,
    },
    {
        "id": "Q5",
        "type": "not_in_corpus",
        "question": (
            "What were the case counts and outcomes in CDC's investigation of an E. coli "
            "O157:H7 outbreak linked to contaminated ground beef in 2026?"
        ),
        "expected_sources": [],
        "refuse_expected": True,
    },
    {
        "id": "Q6",
        "type": "unrelated",
        "question": "What is the capital of Australia?",
        "expected_sources": [],
        "refuse_expected": True,
    },
]

K_SWEEP_QUESTION_ID = "Q2"
K_SWEEP_VALUES = [1, 3, 5]


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Chunk:
    chunk_id: str
    source: str
    text: str

# Corpus / index
def load_and_chunk_corpus() -> list[Chunk]:
    paths = sorted(CORPUS_DIR.glob("*.txt"))
    if len(paths) < 5:
        raise RuntimeError(f"Corpus and index step requires >=5 documents, found {len(paths)} in {CORPUS_DIR}")

    documents = [Document(text=p.read_text(encoding="utf-8"), metadata={"file_name": p.name}) for p in paths]
    splitter = TokenTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    nodes = splitter.get_nodes_from_documents(documents)

    chunks = [
        Chunk(chunk_id=f"chunk_{i:04d}", source=node.metadata.get("file_name", "?"), text=node.get_content())
        for i, node in enumerate(nodes)
    ]
    print(f"[rag] {ts()} loaded {len(paths)} documents -> {len(chunks)} chunks "
          f"(chunk_size={CHUNK_SIZE}, chunk_overlap={CHUNK_OVERLAP})")
    return chunks


def build_index(chunks: list[Chunk], embed_model: HuggingFaceEmbedding) -> tuple[faiss.Index, np.ndarray]:
    print(f"[rag] {ts()} embedding {len(chunks)} chunks with {EMBED_MODEL_NAME} ...")
    vectors = np.array([embed_model.get_text_embedding(c.text) for c in chunks], dtype="float32")
    faiss.normalize_L2(vectors)  # inner product on normalized vectors == cosine similarity
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    print(f"[rag] {ts()} FAISS index built: {index.ntotal} vectors, dim={vectors.shape[1]}")
    return index, vectors


def retrieve(
    query: str,
    chunks: list[Chunk],
    index: faiss.Index,
    vectors: np.ndarray,
    embed_model: HuggingFaceEmbedding,
    top_k: int,
) -> list[dict]:
    qvec = np.array([embed_model.get_text_embedding(query)], dtype="float32")
    faiss.normalize_L2(qvec)
    scores, positions = index.search(qvec, top_k)
    results = []
    for score, pos in zip(scores[0], positions[0]):
        if pos < 0:
            continue
        chunk = chunks[pos]
        results.append({
            "pos": int(pos),
            "chunk_id": chunk.chunk_id,
            "source": chunk.source,
            "score": float(score),
            "text": chunk.text,
        })
    return results


def print_retrieved(question_id: str, label: str, results: list[dict]) -> None:
    print(f"\n[rag] {ts()} retrieved for {question_id} ({label}):")
    for r in results:
        preview = r["text"][:100].replace("\n", " ").strip()
        print(f"  {r['chunk_id']:<12} source={r['source']:<45} score={r['score']:.4f}  \"{preview}...\"")


# Config C: drop irrelevant + duplicate chunks, order + label survivors
def select_context_engineered(pool: list[dict], vectors: np.ndarray, final_k: int = TOP_K_DEFAULT) -> list[dict]:
    if not pool:
        return []
    top_score = pool[0]["score"]
    kept: list[dict] = []
    for cand in pool:
        if cand["score"] < ABS_SCORE_FLOOR or cand["score"] < top_score - REL_MARGIN:
            continue  # drop irrelevant
        is_dup = any(
            float(np.dot(vectors[cand["pos"]], vectors[k["pos"]])) > DEDUP_SIM_THRESHOLD
            for k in kept
        )
        if is_dup:
            continue  # drop duplicate
        kept.append(cand)
        if len(kept) >= final_k:
            break
    return kept


# Prompt builders for the three configurations
def prompt_no_rag(question: str) -> list[dict]:
    return [
        {"role": "system", "content": "Answer the user's question directly and concisely, using your own knowledge."},
        {"role": "user", "content": question},
    ]


def prompt_basic_rag(question: str, chunks: list[dict]) -> list[dict]:
    # "top-3 raw chunks in the prompt" -- unlabeled, no grounding rules, no citation
    # requirement. This is the deliberately *un*-engineered baseline Config C is compared against.
    raw_context = "\n\n---\n\n".join(c["text"] for c in chunks)
    user = f"Context:\n{raw_context}\n\nQuestion: {question}\nAnswer using the context above if relevant."
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": user},
    ]


def prompt_context_engineered(question: str, chunks: list[dict]) -> list[dict]:
    if not chunks:
        # Nothing survived the relevance/dedup filter -- refuse without calling the LLM at all.
        return []
    labeled = "\n\n".join(f"[Source {i}: {c['source']}]\n{c['text']}" for i, c in enumerate(chunks, start=1))
    system = (
        "You are a grounded question-answering assistant. Answer ONLY using the numbered "
        "sources provided below -- do not use any outside knowledge. Cite the source "
        "number(s) you used, in parentheses, like (Source 2). If the provided sources do "
        "not contain enough information to answer the question, respond with EXACTLY this "
        f"sentence and nothing else: \"{REFUSAL_TEXT}\""
    )
    user = f"{labeled}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def call_llm(client: OllamaModelClient, messages: list[dict]) -> str:
    if not messages:
        return REFUSAL_TEXT
    response = client.complete(messages, temperature=0.0)
    return response.content.strip()


# Main experiment
def run_all_questions(chunks, index, vectors, embed_model, client) -> list[dict]:
    all_results = []
    for q in QUESTIONS:
        qid, qtext = q["id"], q["question"]
        print(f"\n{'=' * 90}\n{qid} ({q['type']}): {qtext}\n{'=' * 90}")

        pool = retrieve(qtext, chunks, index, vectors, embed_model, top_k=POOL_K_FOR_ENGINEERING)
        print_retrieved(qid, f"pool top-{POOL_K_FOR_ENGINEERING}", pool)

        basic_chunks = pool[:TOP_K_DEFAULT]
        engineered_chunks = select_context_engineered(pool, vectors, final_k=TOP_K_DEFAULT)
        print(f"[rag] {ts()} Config C kept {len(engineered_chunks)}/{len(pool)} chunks after "
              f"relevance/dedup filtering: {[c['chunk_id'] for c in engineered_chunks]}")

        t0 = time.perf_counter()
        answer_a = call_llm(client, prompt_no_rag(qtext))
        t1 = time.perf_counter()
        answer_b = call_llm(client, prompt_basic_rag(qtext, basic_chunks))
        t2 = time.perf_counter()
        answer_c = call_llm(client, prompt_context_engineered(qtext, engineered_chunks))
        t3 = time.perf_counter()

        print(f"\n[rag] {qid} (A) No-RAG        [{t1 - t0:.2f}s]: {answer_a}")
        print(f"[rag] {qid} (B) Basic-RAG      [{t2 - t1:.2f}s]: {answer_b}")
        print(f"[rag] {qid} (C) Context-eng.   [{t3 - t2:.2f}s]: {answer_c}")

        retrieved_sources = {r["source"] for r in pool}
        expected = set(q["expected_sources"])
        correct_retrieval = expected.issubset(retrieved_sources) if expected else None

        all_results.append({
            "id": qid,
            "type": q["type"],
            "question": qtext,
            "expected_sources": q["expected_sources"],
            "refuse_expected": q["refuse_expected"],
            "retrieved_pool": [{k: v for k, v in r.items() if k != "pos"} for r in pool],
            "engineered_chunk_ids": [c["chunk_id"] for c in engineered_chunks],
            "correct_retrieval": correct_retrieval,
            "answer_no_rag": answer_a,
            "answer_basic_rag": answer_b,
            "answer_context_engineered": answer_c,
            "refused_config_c": answer_c.strip() == REFUSAL_TEXT,
        })
    return all_results


def run_k_sweep(chunks, index, vectors, embed_model, client) -> list[dict]:
    q = next(item for item in QUESTIONS if item["id"] == K_SWEEP_QUESTION_ID)
    qtext = q["question"]
    expected = set(q["expected_sources"])
    print(f"\n{'=' * 90}\nK-SWEEP on {K_SWEEP_QUESTION_ID}: {qtext}\n{'=' * 90}")

    sweep_results = []
    for k in K_SWEEP_VALUES:
        pool = retrieve(qtext, chunks, index, vectors, embed_model, top_k=k)
        print_retrieved(f"{K_SWEEP_QUESTION_ID}@k={k}", "k-sweep", pool)
        engineered = select_context_engineered(pool, vectors, final_k=k)
        answer = call_llm(client, prompt_context_engineered(qtext, engineered))
        retrieved_sources = {r["source"] for r in pool}
        both_expected_present = expected.issubset(retrieved_sources)
        irrelevant_present = any(r["score"] < ABS_SCORE_FLOOR for r in pool)

        print(f"[rag] k={k}: both expected sources present={both_expected_present}, "
              f"irrelevant chunk present={irrelevant_present}")
        print(f"[rag] k={k} answer: {answer}")

        sweep_results.append({
            "k": k,
            "retrieved_sources": sorted(retrieved_sources),
            "both_expected_sources_present": both_expected_present,
            "irrelevant_chunk_present": irrelevant_present,
            "answer": answer,
        })
    return sweep_results


def write_eval_table_template(question_results: list[dict]) -> Path:
    """Programmatic signals only (retrieval correctness, refusal correctness,
    citation format compliance). 'correct_answer' and 'grounded' require reading
    the actual generated text, so they're left blank here for manual fill-in
    against the real model output."""
    path = RAW_DIR / "rag_eval_table.csv"
    fieldnames = [
        "question_id", "type", "config", "correct_retrieval", "correct_answer",
        "grounded", "refused_when_needed", "format_compliance_citation",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for q in question_results:
            for config, answer_key in [
                ("A_no_rag", "answer_no_rag"),
                ("B_basic_rag", "answer_basic_rag"),
                ("C_context_engineered", "answer_context_engineered"),
            ]:
                answer = q[answer_key]
                refused = answer.strip() == REFUSAL_TEXT
                has_citation = "(Source" in answer
                writer.writerow({
                    "question_id": q["id"],
                    "type": q["type"],
                    "config": config,
                    "correct_retrieval": q["correct_retrieval"],
                    "correct_answer": "",  # manual
                    "grounded": "",  # manual
                    "refused_when_needed": (refused == q["refuse_expected"]) if config == "C_context_engineered" else "",
                    "format_compliance_citation": has_citation if config == "C_context_engineered" else "",
                })
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    args = parser.parse_args()

    client = OllamaModelClient(model=LLM_MODEL, base_url=args.ollama_url)
    try:
        client.check_connection()
    except ModelClientError as exc:
        print(f"[rag] ERROR: {exc}")
        sys.exit(1)
    print(f"[rag] {ts()} Ollama reachable, using model={LLM_MODEL}")

    chunks = load_and_chunk_corpus()
    embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)
    index, vectors = build_index(chunks, embed_model)

    question_results = run_all_questions(chunks, index, vectors, embed_model, client)
    sweep_results = run_k_sweep(chunks, index, vectors, embed_model, client)

    answers_path = RAW_DIR / "rag_question_results.jsonl"
    with open(answers_path, "w", encoding="utf-8") as f:
        for row in question_results:
            f.write(json.dumps(row) + "\n")
    print(f"\n[rag] {ts()} wrote {answers_path}")

    sweep_path = RAW_DIR / "rag_k_sweep.json"
    sweep_path.write_text(json.dumps(sweep_results, indent=2), encoding="utf-8")
    print(f"[rag] {ts()} wrote {sweep_path}")

    eval_path = write_eval_table_template(question_results)
    print(f"[rag] {ts()} wrote {eval_path}")

    print(f"\n[rag] {ts()} usage: {client.stats()}")
    print(f"[rag] {ts()} done. {len(question_results)} questions x 3 configs, "
          f"k-sweep over {K_SWEEP_VALUES} on {K_SWEEP_QUESTION_ID}.")


if __name__ == "__main__":
    main()
