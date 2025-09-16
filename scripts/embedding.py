from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# Modello multilingua
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# Frasi di test
sentences = [
    "Come ti chiami?",
    "Qual è il tuo nome?",
    "Oggi piove forte."
]

# Embedding
embeddings = model.encode(sentences)

# Similarità
sim1 = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
sim2 = cosine_similarity([embeddings[0]], [embeddings[2]])[0][0]

print("Similarità (frasi equivalenti):", sim1)
print("Similarità (frasi diverse):", sim2)
