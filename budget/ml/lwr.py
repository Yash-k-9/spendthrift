"""Locally Weighted Regression (from scratch).

Ordinary linear regression fits one straight line to all points. LWR fits a
new line for every query point x_q, giving nearby points more influence:

    weight  w_i = exp( -(x_i - x_q)^2 / (2 * tau^2) )
    theta       = (X^T W X)^-1  X^T W y        (weighted least squares)
    prediction  = [1, x_q] . theta

tau (the bandwidth) controls how "local" the fit is:
  small tau -> only the last few months matter (reacts fast to changes)
  large tau -> all months matter equally (close to plain linear regression)

degree=0 fits a weighted average instead of a line (a "local constant").

Shrunken trend: with only a handful of noisy monthly points, the slope of the
local line is mostly noise, and extending it overshoots. shrunk_lwr_predict
keeps the local level and adds only part of the local trend:

    prediction = local_constant + alpha * (local_linear - local_constant)

alpha = 0 is a weighted average, alpha = 1 is plain LWR.
"""

import numpy as np


def lwr_predict(x, y, x_query: float, tau: float, degree: int = 1) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    w = np.exp(-((x - x_query) ** 2) / (2 * tau ** 2))
    if degree == 0:
        return float(w @ y / w.sum())
    X = np.column_stack([np.ones_like(x), x])
    XtW = X.T * w                               # same as X^T @ diag(w), without building diag(w)
    theta = np.linalg.pinv(XtW @ X) @ XtW @ y   # pinv stays stable when X^T W X is near-singular
    return float(np.array([1.0, x_query]) @ theta)


def shrunk_lwr_predict(x, y, x_query: float, tau: float, alpha: float) -> float:
    level = lwr_predict(x, y, x_query, tau, degree=0)
    return level + alpha * (lwr_predict(x, y, x_query, tau, degree=1) - level)


def lwr_curve(x, y, x_grid, tau: float) -> np.ndarray:
    """LWR prediction at every point of x_grid (for drawing the fitted curve)."""
    return np.array([lwr_predict(x, y, xq, tau) for xq in x_grid])
