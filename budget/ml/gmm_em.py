"""Gaussian Mixture Model trained with Expectation-Maximization (from scratch).

The data is assumed to come from K Gaussian "bumps". EM alternates:

  E-step: for each point, the probability it belongs to each component
          r_ik = pi_k N(x_i | mu_k, Sigma_k) / sum_j pi_j N(x_i | mu_j, Sigma_j)
  M-step: re-estimate every component from those soft assignments
          N_k = sum_i r_ik,  pi_k = N_k / n,  mu_k = sum_i r_ik x_i / N_k,
          Sigma_k = sum_i r_ik (x_i - mu_k)(x_i - mu_k)^T / N_k
until the log-likelihood stops improving. Points with a very low
likelihood under the fitted model are unusual -> anomalies.
"""

import numpy as np

from .kmeans import kmeans


def _log_gaussian(X: np.ndarray, mean: np.ndarray, cov: np.ndarray) -> np.ndarray:
    d = X.shape[1]
    diff = X - mean
    _, logdet = np.linalg.slogdet(cov)
    mahalanobis = np.einsum("ij,ij->i", diff @ np.linalg.inv(cov), diff)
    return -0.5 * (d * np.log(2 * np.pi) + logdet + mahalanobis)


def _logsumexp(a: np.ndarray, axis: int) -> np.ndarray:
    m = a.max(axis=axis, keepdims=True)
    return (m + np.log(np.exp(a - m).sum(axis=axis, keepdims=True))).squeeze(axis)


class GaussianMixtureEM:
    def __init__(self, k: int = 3, max_iter: int = 200, tol: float = 1e-5, reg: float = 1e-4, seed: int = 0):
        self.k, self.max_iter, self.tol, self.reg, self.seed = k, max_iter, tol, reg, seed

    def _weighted_log_probs(self, X):
        return np.column_stack([np.log(self.weights[j]) + _log_gaussian(X, self.means[j], self.covs[j])
                                for j in range(self.k)])

    def fit(self, X: np.ndarray) -> "GaussianMixtureEM":
        n, d = X.shape
        # Initialise means from k-means, covariances from the whole data.
        self.means = kmeans(X, self.k, n_init=3, seed=self.seed)[0]
        self.covs = np.array([np.cov(X.T) + self.reg * np.eye(d)] * self.k)
        self.weights = np.full(self.k, 1 / self.k)
        self.log_likelihood_history = []

        for _ in range(self.max_iter):
            # E-step
            log_p = self._weighted_log_probs(X)
            log_total = _logsumexp(log_p, axis=1)
            resp = np.exp(log_p - log_total[:, None])
            self.log_likelihood_history.append(float(log_total.sum()))
            # M-step
            nk = resp.sum(axis=0) + 1e-10
            self.weights = nk / n
            self.means = (resp.T @ X) / nk[:, None]
            for j in range(self.k):
                diff = X - self.means[j]
                self.covs[j] = (resp[:, j, None] * diff).T @ diff / nk[j] + self.reg * np.eye(d)
            if len(self.log_likelihood_history) > 1 and \
                    abs(self.log_likelihood_history[-1] - self.log_likelihood_history[-2]) < self.tol * n:
                break
        return self

    def score_samples(self, X: np.ndarray) -> np.ndarray:
        """Log-likelihood of each point under the mixture (low = unusual)."""
        return _logsumexp(self._weighted_log_probs(X), axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Most likely component for each point."""
        return self._weighted_log_probs(X).argmax(axis=1)
