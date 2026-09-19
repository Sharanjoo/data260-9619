"""HW3 Part 2: sanity check — confirm llama-index + HF embedding model load and work."""
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

def main():
    print(f"Loading embedding model: {MODEL_NAME} ...")
    embed_model = HuggingFaceEmbedding(model_name=MODEL_NAME)

    text = "The FDA classifies food recalls into Class I, Class II, and Class III based on health risk."
    vector = embed_model.get_text_embedding(text)

    print(f"Embedding dimension: {len(vector)}")
    print(f"First 8 values: {vector[:8]}")

    # quick cosine sanity check between a related and unrelated sentence
    import numpy as np
    v1 = np.array(embed_model.get_text_embedding("Salmonella outbreak linked to shell eggs caused illnesses across several states."))
    v2 = np.array(embed_model.get_text_embedding("FDA recall classifications range from Class I to Class III."))
    v3 = np.array(embed_model.get_text_embedding("The weather in Paris is sunny today."))

    def cosine(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    print(f"\nCosine(salmonella outbreak, recall classification) = {cosine(v1, v2):.4f}  (expect: moderate, both food-safety domain)")
    print(f"Cosine(salmonella outbreak, weather in Paris)       = {cosine(v1, v3):.4f}  (expect: low, unrelated)")

if __name__ == "__main__":
    main()