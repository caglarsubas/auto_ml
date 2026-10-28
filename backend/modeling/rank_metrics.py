"""Exact tie-group U statistic after caller validation; no retained input state."""
import numpy as np

MAX_EXACT_RANK_ROWS = 2**26


def tie_group_auc(positive, scores):
    """Caller validates finite scores, both classes and the exact-row ceiling."""
    if np.all(scores == scores[0]):
        return .5
    order = np.argsort(scores, kind='stable')
    ordered = scores[order]
    starts = np.r_[0, np.flatnonzero(ordered[1:] != ordered[:-1]) + 1]
    positives = np.add.reduceat(positive[order].astype(np.int64), starts)
    negatives = np.diff(np.r_[starts, len(scores)]) - positives
    prior_negatives = np.cumsum(negatives) - negatives
    pairs = np.sum(positives * (prior_negatives + .5 * negatives))
    support = float(np.count_nonzero(positive))
    return float(pairs / (support * (len(scores) - support)))
