"""k-Nearest Neighbor classifier (from scratch).

To classify a new point:
  1. measure its similarity to every training point (cosine similarity:
     vectors are unit length, so similarity = dot product)
  2. take the k most similar points (the "nearest neighbours")
  3. each neighbour votes for its label, weighted by its similarity
  4. the label with the most votes wins; confidence = winning votes / all votes

k-NN is a "lazy learner": training just stores the data, so a user's
correction is learned instantly by adding it as a new training point.
"""

import numpy as np


class KNNClassifier:
    def __init__(self, k: int = 5, weighted: bool = True):
        self.k = k
        self.weighted = weighted

    def fit(self, X: np.ndarray, y) -> "KNNClassifier":
        self.X = X
        self.y = np.asarray(y)
        return self

    def kneighbors(self, x: np.ndarray, allowed_labels=None) -> tuple[np.ndarray, np.ndarray]:
        """Indices and similarities of the k nearest training points."""
        sims = self.X @ x
        if allowed_labels is not None:
            sims = np.where(np.isin(self.y, list(allowed_labels)), sims, -np.inf)
        k = min(self.k, int(np.isfinite(sims).sum()))
        idx = np.argsort(-sims)[:k]
        return idx, sims[idx]

    def predict_one(self, x: np.ndarray, allowed_labels=None) -> tuple[str | None, float, np.ndarray]:
        """Returns (label, confidence, neighbour indices)."""
        idx, sims = self.kneighbors(x, allowed_labels)
        if len(idx) == 0 or sims[0] <= 0:
            return None, 0.0, idx  # nothing similar at all
        votes = {}
        for label, sim in zip(self.y[idx], sims):
            votes[label] = votes.get(label, 0.0) + (max(sim, 0.0) if self.weighted else 1.0)
        label = max(votes, key=votes.get)
        total = sum(votes.values())
        return str(label), float(votes[label] / total) if total else 0.0, idx

    def predict(self, X: np.ndarray) -> list[str | None]:
        return [self.predict_one(x)[0] for x in X]


def accuracy(y_true, y_pred) -> float:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    return float((y_true == y_pred).mean()) if len(y_true) else 0.0
