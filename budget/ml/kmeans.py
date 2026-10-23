"""k-Means clustering (from scratch).

  1. choose k starting centroids (k-means++: spread them out - each new
     centroid is picked with probability proportional to its squared
     distance from the nearest centroid already chosen)
  2. assignment step: put every point in the cluster of its nearest centroid
  3. update step: move each centroid to the mean of its points
  4. repeat 2-3 until the assignments stop changing
Run several times from different starts and keep the lowest SSE
(sum of squared distances from points to their centroid).
"""

import numpy as np


def _kmeans_pp_init(X: np.ndarray, k: int, rng) -> np.ndarray:
    centroids = [X[rng.integers(len(X))]]
    for _ in range(1, k):
        d2 = np.min(((X[:, None, :] - np.array(centroids)[None]) ** 2).sum(-1), axis=1)
        probs = d2 / d2.sum() if d2.sum() > 0 else np.full(len(X), 1 / len(X))
        centroids.append(X[rng.choice(len(X), p=probs)])
    return np.array(centroids, dtype=float)


def kmeans(X: np.ndarray, k: int, n_init: int = 10, max_iter: int = 100, seed: int = 0):
    """Returns (centroids, labels, sse, iterations)."""
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        centroids = _kmeans_pp_init(X, k, rng)
        labels = None
        for it in range(1, max_iter + 1):
            dist = ((X[:, None, :] - centroids[None]) ** 2).sum(-1)
            new_labels = dist.argmin(axis=1)
            if labels is not None and np.array_equal(new_labels, labels):
                break
            labels = new_labels
            for c in range(k):
                if np.any(labels == c):
                    centroids[c] = X[labels == c].mean(axis=0)
        sse = float(((X - centroids[labels]) ** 2).sum())
        if best is None or sse < best[2]:
            best = (centroids.copy(), labels.copy(), sse, it)
    return best


def elbow(X: np.ndarray, k_values) -> list[float]:
    """SSE for each k - the 'elbow' where SSE stops dropping fast suggests a good k."""
    return [kmeans(X, k, n_init=5)[2] for k in k_values]
