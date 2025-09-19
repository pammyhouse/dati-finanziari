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
    return text

# Funzione per generare gli embedding
def generate_embeddings(texts, model):
    embeddings = model.encode(texts)
    return embeddings

# Funzione per creare n-grammi
def generate_ngrams(texts, n=2):
    vectorizer = CountVectorizer(ngram_range=(n, n))
    ngrams = vectorizer.fit_transform(texts)
    return vectorizer.get_feature_names_out(), ngrams.toarray()

# Inizializzazione del modello
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# Recupero degli articoli
articles = fetch_yahoo_finance_articles()

# Estrazione del testo degli articoli
article_texts = [extract_article_text(url) for _, url in articles]

# Generazione degli embedding per le frasi
sentence_embeddings = generate_embeddings(article_texts, model)

# Creazione di bigrammi e trigrammi
bigram_words, bigram_embeddings = generate_ngrams(article_texts, n=2)
trigram_words, trigram_embeddings = generate_ngrams(article_texts, n=3)

# Unione di tutti i dati
all_words = bigram_words.tolist() + trigram_words.tolist()
all_embeddings = np.vstack([bigram_embeddings, trigram_embeddings])

# Salvataggio dei risultati in un file .npz
np.savez('aapl_news_embeddings.npz', words=all_words, embeddings=all_embeddings)

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
