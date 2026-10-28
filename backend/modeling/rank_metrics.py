"""Exact tie-group U statistic after caller validation; no retained input state."""
import numpy as np

MAX_EXACT_RANK_ROWS = 2**26


def tie_group_auc(positive, scores):
    """Caller validates finite scores, both classes and the exact-row ceiling."""
    if np.all(scores == scores[0]):
        return .5
    order = np.argsort(scores, kind='stable')
    ordered = scores[order]
    changes = np.flatnonzero(ordered[1:] != ordered[:-1]) + 1
    starts = np.empty(len(changes) + 1, dtype=np.intp)
    starts[0], starts[1:] = 0, changes
    positives = np.add.reduceat(positive[order].astype(np.int64), starts)
    sizes = np.empty(len(starts), dtype=np.intp)
    sizes[:-1], sizes[-1] = starts[1:] - starts[:-1], len(scores) - starts[-1]
    negatives = sizes - positives
    prior_negatives = np.cumsum(negatives) - negatives
    pairs = np.sum(positives * (prior_negatives + .5 * negatives))
    support = float(np.count_nonzero(positive))
    return float(pairs / (support * (len(scores) - support)))


MAX_BATCH_RANK_CELLS = 2**18
MAX_BATCH_RANK_CLASSES = 256
MAX_BATCH_RANK_ROWS = 4096


def small_weighted_ovr_auc(y, probabilities):
    """Bounded selected-metric calculation; None selects the row-wise fallback.

    Callers already validate class mapping, probability shape/range and class
    coverage. Temporary rank matrices are capped; no inputs/results are retained.
    Complete assessment still executes independent public ROC integration.
    """
    rows, classes = probabilities.shape
    if not (8 <= classes <= MAX_BATCH_RANK_CLASSES and rows <= min(MAX_EXACT_RANK_ROWS, MAX_BATCH_RANK_ROWS)
            and rows * classes <= MAX_BATCH_RANK_CELLS):
        return None
    from scipy.stats import rankdata

    supports = np.bincount(y, minlength=classes).astype(float)
    ranks = rankdata(probabilities, axis=0, method='average')
    positives = y[:, None] == np.arange(classes)
    pairs = np.sum(ranks * positives, axis=0) - supports * (supports + 1.) / 2.
    return float(np.average(pairs / (supports * (rows - supports)), weights=supports))


def contiguous_class_membership(labels, class_count):
    """Fresh contiguous-label validation for canonical numeric selected metrics.

    None retains the general NumPy membership path for unsupported profiles.
    This checks every input value; no label or result state survives the call.
    """
    if (type(class_count) is not int or not 1 <= class_count <= 2**24
            or labels.ndim != 1 or labels.dtype.kind not in 'biuf'
            or labels.dtype.itemsize > 8 or not labels.dtype.isnative
            or (labels.dtype.kind == 'f' and labels.dtype.itemsize not in (4, 8))):
        return None
    if not np.isfinite(labels).all() or np.any(labels < 0) or np.any(labels >= class_count):
        return False
    return bool(np.equal(labels, np.floor(labels)).all()) if labels.dtype.kind == 'f' else True
