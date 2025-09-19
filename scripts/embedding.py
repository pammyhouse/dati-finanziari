import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
import numpy as np

# Funzione per recuperare gli articoli da Yahoo Finance
def fetch_yahoo_finance_articles():
    url = "https://finance.yahoo.com/quote/AAPL/news/"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    articles = []
    for item in soup.find_all('li', class_='js-stream-content'):
        link = item.find('a', href=True)
        if link:
            article_url = "https://finance.yahoo.com" + link['href']
            article_title = link.get_text()
            articles.append((article_title, article_url))
    return articles

# Funzione per estrarre il testo principale di un articolo
def extract_article_text(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    paragraphs = soup.find_all('p')
    text = ' '.join([para.get_text() for para in paragraphs])
    return text.strip()

# Funzione per generare gli embedding
def generate_embeddings(texts, model):
    return model.encode(texts)

# Funzione per creare n-grammi in modo robusto
def generate_ngrams(texts, n=2):
    # Filtra testi vuoti
    texts = [t for t in texts if t.strip()]
    if not texts:
        return [], np.array([])  # ritorna vuoto se non ci sono testi validi
    vectorizer = CountVectorizer(ngram_range=(n, n))
    ngrams_matrix = vectorizer.fit_transform(texts)
    return vectorizer.get_feature_names_out(), ngrams_matrix.toarray()

# Inizializzazione del modello
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# Recupero degli articoli
articles = fetch_yahoo_finance_articles()
print(f"Articoli trovati: {len(articles)}")

# Estrazione del testo degli articoli
article_texts = [extract_article_text(url) for _, url in articles]
# Filtra articoli vuoti
article_texts = [t for t in article_texts if t]

if not article_texts:
    print("Nessun testo valido trovato. Esco dallo script.")
    exit(0)

# Generazione degli embedding per le frasi
sentence_embeddings = generate_embeddings(article_texts, model)

# Creazione di bigrammi e trigrammi
bigram_words, bigram_embeddings = generate_ngrams(article_texts, n=2)
trigram_words, trigram_embeddings = generate_ngrams(article_texts, n=3)

# Verifica se ci sono n-gram
all_words = list(bigram_words) + list(trigram_words)
if bigram_embeddings.size == 0 and trigram_embeddings.size == 0:
    all_embeddings = np.array([])
else:
    # Se uno dei due è vuoto, usa solo quello valido
    embeddings_list = []
    if bigram_embeddings.size != 0:
        embeddings_list.append(bigram_embeddings)
    if trigram_embeddings.size != 0:
        embeddings_list.append(trigram_embeddings)
    all_embeddings = np.vstack(embeddings_list)

# Salvataggio dei risultati
np.savez('aapl_news_embeddings.npz', words=all_words, embeddings=all_embeddings)
print(f"Dataset salvato: {len(all_words)} n-gram salvati.")
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
