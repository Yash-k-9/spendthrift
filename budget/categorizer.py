"""Automatic transaction categorization with k-Nearest Neighbor.

Training set = built-in labelled phrases (training_data.py)
             + every category the family has corrected by hand (learned instantly).
Each description is turned into a TF-IDF vector; k-NN finds the k most similar
known descriptions and lets them vote.
"""

import numpy as np

from .ml.knn import KNNClassifier, accuracy
from .ml.text import TfidfVectorizer
from .training_data import INCOME_CATEGORIES, knn_training_examples

# Each expense category belongs to one bucket of the 50/30/20 rule.
EXPENSE_CATEGORIES = {
    "Housing": "need",
    "Utilities": "need",
    "Groceries": "need",
    "Transport": "need",
    "Healthcare": "need",
    "Education": "need",
    "Insurance": "need",
    "Loan EMI": "need",
    "Dining Out": "want",
    "Shopping": "want",
    "Entertainment": "want",
    "Subscriptions": "want",
    "Travel": "want",
    "Personal Care": "want",
    "Gifts & Donations": "want",
    "Savings & Investments": "saving",
    "Other": "want",
}
ALL_CATEGORIES = list(EXPENSE_CATEGORIES) + INCOME_CATEGORIES
MIN_CONFIDENCE = 0.4    # vote share below this -> "needs review"
MIN_SIMILARITY = 0.3    # nearest neighbour less similar than this -> nothing known is close: "Other"
REVIEW_SIMILARITY = 0.45  # a weak match (e.g. "dentist" ~ "dental") is kept as a guess but flagged for review


class KNNCategorizer:
    def __init__(self, corrections: list[tuple[str, str, str]] = (), k: int = 5):
        """corrections: [(description, type, category)] the family labelled themselves."""
        seed = knn_training_examples()
        self.n_seed, self.n_corrections = len(seed), len(corrections)
        self.texts = [d for d, _, _ in seed] + [d for d, _, _ in corrections]
        self.types = np.array([t for _, t, _ in seed] + [t for _, t, _ in corrections])
        labels = [c for _, _, c in seed] + [c for _, _, c in corrections]
        self.vectorizer = TfidfVectorizer()
        self.model = KNNClassifier(k=k).fit(self.vectorizer.fit_transform(self.texts), labels)

    def predict(self, description: str, type_: str = "expense") -> dict:
        allowed = INCOME_CATEGORIES if type_ == "income" else list(EXPENSE_CATEGORIES)
        x = self.vectorizer.transform([description])[0]
        label, confidence, idx = self.model.predict_one(x, allowed_labels=allowed)
        neighbours = [(self.texts[i], str(self.model.y[i]), float(self.model.X[i] @ x)) for i in idx]
        if label is None or neighbours[0][2] < MIN_SIMILARITY:
            label, confidence = ("Other Income" if type_ == "income" else "Other"), 0.0
        return {
            "category": label,
            "confidence": round(confidence, 2),
            "needs_review": confidence < MIN_CONFIDENCE or neighbours[0][2] < REVIEW_SIMILARITY,
            "neighbours": neighbours,
        }

    def categorize(self, description: str, type_: str = "expense") -> str:
        return self.predict(description, type_)["category"]


def evaluate(k_values=(1, 3, 5, 7, 9), seed: int = 0) -> dict:
    """Hold-out evaluation on the built-in data.

    - unseen_phrasing: test rows are new phrasings of merchants seen in training
    - unseen_merchant: whole merchants are held out (harder - tests generalisation
      from character n-grams, e.g. "pharmacy" -> "medplus pharmacy")
    """
    rng = np.random.default_rng(seed)
    data = knn_training_examples(with_phrase=True)
    texts = np.array([d for d, _, _, _ in data])
    labels = np.array([c for _, _, c, _ in data])
    merchants = np.array([p for _, _, _, p in data])

    def run(test_mask):
        vec = TfidfVectorizer()
        X_train = vec.fit_transform(list(texts[~test_mask]))
        X_test = vec.transform(list(texts[test_mask]))
        out = {}
        for k in k_values:
            model = KNNClassifier(k=k).fit(X_train, labels[~test_mask])
            out[k] = accuracy(labels[test_mask], model.predict(X_test))
        return out

    phrasing_mask = rng.random(len(texts)) < 0.2
    unique_merchants = np.unique(merchants)
    held_out = set(rng.choice(unique_merchants, size=len(unique_merchants) // 5, replace=False))
    merchant_mask = np.array([m in held_out for m in merchants])
    return {"unseen_phrasing": run(phrasing_mask), "unseen_merchant": run(merchant_mask),
            "n_train": int(len(texts))}
