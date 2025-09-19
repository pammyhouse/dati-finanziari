import feedparser
from sentence_transformers import SentenceTransformer
import numpy as np

# ---------------------------
# 1️⃣ Recupero notizie da Google News RSS
# ---------------------------
def fetch_google_news_rss(query="AAPL"):
    feed_url = f"https://news.google.com/rss/search?q={query}&hl=it&gl=IT&ceid=IT:it"
    feed = feedparser.parse(feed_url)
    articles = []
    for entry in feed.entries:
        # Usa titolo + riassunto come testo
        text = f"{entry.title} {entry.summary}".strip()
        if text:
            articles.append(text)
    return articles

# ---------------------------
# 2️⃣ Generazione n-gram con embedding
# ---------------------------
def generate_ngrams_embeddings(texts, model, n=1):
    tokens = []
    for text in texts:
        words = text.split()
        if len(words) < n:
            continue
        ngrams = [" ".join(words[i:i+n]) for i in range(len(words)-n+1)]
        tokens.extend(ngrams)

    tokens = list(set(tokens))  # rimuovi duplicati
    if not tokens:
        return [], np.array([])

    embeddings = model.encode(tokens, batch_size=32, show_progress_bar=True)
    return tokens, embeddings

# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":
    # Inizializza modello
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    # Recupera articoli
    article_texts = fetch_google_news_rss("AAPL")
    print(f"Articoli recuperati: {len(article_texts)}")

    if not article_texts:
        print("Nessun articolo trovato. Esco.")
        exit(0)

    # Unigram, bigram, trigram embeddings
    unigram_words, unigram_embeddings = generate_ngrams_embeddings(article_texts, model, n=1)
    bigram_words, bigram_embeddings = generate_ngrams_embeddings(article_texts, model, n=2)
    trigram_words, trigram_embeddings = generate_ngrams_embeddings(article_texts, model, n=3)

    # Unisci tutto
    all_words = unigram_words + bigram_words + trigram_words
    embeddings_list = []
    if unigram_embeddings.size:
        embeddings_list.append(unigram_embeddings)
    if bigram_embeddings.size:
        embeddings_list.append(bigram_embeddings)
    if trigram_embeddings.size:
        embeddings_list.append(trigram_embeddings)

    if not embeddings_list:
        print("Nessun embedding generato. Esco.")
        exit(0)

    all_embeddings = np.vstack(embeddings_list)

    # Salvataggio dataset
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
