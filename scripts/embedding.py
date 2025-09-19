import feedparser
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
import numpy as np

# 1️⃣ Recupera notizie da Google News RSS
def fetch_google_news_rss(query="AAPL"):
    feed_url = f"https://news.google.com/rss/search?q={query}&hl=it&gl=IT&ceid=IT:it"
    feed = feedparser.parse(feed_url)
    articles = []
    for entry in feed.entries:
        # Usa title + summary come testo dell'articolo
        text = f"{entry.title} {entry.summary}".strip()
        if text:
            articles.append(text)
    return articles

# 2️⃣ Genera embedding
def generate_embeddings(texts, model, batch_size=32):
    return model.encode(texts, batch_size=batch_size)

# 3️⃣ Crea n-grammi (unigram, bigram, trigram)
def generate_ngrams(texts, n=2):
    texts = [t for t in texts if t.strip()]
    if not texts:
        return [], np.array([])
    vectorizer = CountVectorizer(ngram_range=(n, n))
    ngrams_matrix = vectorizer.fit_transform(texts)
    return vectorizer.get_feature_names_out(), ngrams_matrix.toarray()

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    # Inizializza il modello
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    # Recupera articoli
    article_texts = fetch_google_news_rss("AAPL")
    print(f"Articoli recuperati: {len(article_texts)}")

    if not article_texts:
        print("Nessun articolo valido trovato. Esco dallo script.")
        exit(0)

    # Embedding frasi complete
    sentence_embeddings = generate_embeddings(article_texts, model)

    # Creazione di n-gram
    unigram_words, unigram_embeddings = generate_ngrams(article_texts, n=1)
    bigram_words, bigram_embeddings = generate_ngrams(article_texts, n=2)
    trigram_words, trigram_embeddings = generate_ngrams(article_texts, n=3)

    # Unione di tutti i token e embedding
    all_words = list(unigram_words) + list(bigram_words) + list(trigram_words)

    embeddings_list = []
    if unigram_embeddings.size != 0:
        embeddings_list.append(unigram_embeddings)
    if bigram_embeddings.size != 0:
        embeddings_list.append(bigram_embeddings)
    if trigram_embeddings.size != 0:
        embeddings_list.append(trigram_embeddings)

    if embeddings_list:
        all_embeddings = np.vstack(embeddings_list)
    else:
        all_embeddings = np.array([])

    # Salvataggio su file
    np.savez("aapl_news_embeddings.npz", words=all_words, embeddings=all_embeddings)
    print(f"Dataset salvato: {len(all_words)} token (unigram/bigram/trigram).")


'''from sentence_transformers import SentenceTransformer
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
'''
