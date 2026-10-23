"""TF-IDF vectorizer (from scratch).

A transaction description like "UPI/ZOMATO/Dinner 4521" becomes a vector:
  tokens = whole words  +  character 3-grams of each word (so "zomato" also
           matches "zomatoorder" or a typo like "zomto" partially)
  tf     = how often a token appears in this description
  idf    = log((1 + N) / (1 + df)) + 1   - rare tokens get more weight
  vector = tf * idf, scaled to unit length (so dot product = cosine similarity)
"""

import re
from collections import Counter

import numpy as np

STOPWORDS = {"to", "for", "the", "and", "of", "a", "an", "at", "in", "on", "by", "from", "with",
             "payment", "paid", "upi", "neft", "imps", "pos", "txn", "ref", "online"}


def tokenize(text: str, n: int = 3) -> list[str]:
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOPWORDS]
    tokens = [f"w:{w}" for w in words]
    for w in words:
        padded = f"<{w}>"
        tokens += [padded[i:i + n] for i in range(len(padded) - n + 1)]
    return tokens


class TfidfVectorizer:
    def fit(self, texts: list[str]) -> "TfidfVectorizer":
        doc_freq = Counter()
        for t in texts:
            doc_freq.update(set(tokenize(t)))
        self.vocab = {tok: i for i, tok in enumerate(sorted(doc_freq))}
        n = len(texts)
        self.idf = np.array([np.log((1 + n) / (1 + doc_freq[tok])) + 1 for tok in sorted(doc_freq)],
                            dtype=np.float32)
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        X = np.zeros((len(texts), len(self.vocab)), dtype=np.float32)
        for row, t in enumerate(texts):
            for tok, count in Counter(tokenize(t)).items():
                col = self.vocab.get(tok)
                if col is not None:  # tokens never seen in training are ignored
                    X[row, col] = count
        X *= self.idf
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        return X / np.where(norms == 0, 1, norms)

    def fit_transform(self, texts: list[str]) -> np.ndarray:
        return self.fit(texts).transform(texts)
