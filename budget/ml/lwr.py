"""Locally Weighted Regression (from scratch).

Ordinary linear regression fits one straight line to all points. LWR fits a
new line for every query point x_q, giving nearby points more influence:

    weight  w_i = exp( -(x_i - x_q)^2 / (2 * tau^2) )
    theta       = (X^T W X)^-1  X^T W y        (weighted least squares)
    prediction  = [1, x_q] . theta

tau (the bandwidth) controls how "local" the fit is:
  small tau -> only the last few months matter (reacts fast to changes)
  large tau -> all months matter equally (close to plain linear regression)
"""

import numpy as np


def lwr_predict(x, y, x_query: float, tau: float) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones_like(x), x])
    w = np.exp(-((x - x_query) ** 2) / (2 * tau ** 2))
    XtW = X.T * w                               # same as X^T @ diag(w), without building diag(w)
    theta = np.linalg.pinv(XtW @ X) @ XtW @ y   # pinv stays stable when X^T W X is near-singular
    return float(np.array([1.0, x_query]) @ theta)


def lwr_curve(x, y, x_grid, tau: float) -> np.ndarray:
    """LWR prediction at every point of x_grid (for drawing the fitted curve)."""
    return np.array([lwr_predict(x, y, xq, tau) for xq in x_grid])
