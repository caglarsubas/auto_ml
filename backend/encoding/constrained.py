"""Fit smoothed target encoders on declared, ordered development partitions."""

import json

import numpy as np
import pandas as pd


# Bound each fitted encoder's portable evidence before it enters model or search
# artifacts. Existing aggregate limits still apply to completed job results.
MAX_FIT_EVIDENCE_BYTES = 256 * 1024


CATEGORY_KEY_ENCODING = 'tagged_string_v1'


def category_keys(values):
    strings = values.astype('string')
    return ('s:' + strings).fillna('n:').astype(str)


def fit_target_encoding(df, feature, target, fit_idx, plan, smoothing):
    if not df.index.is_unique or target not in df:
        raise ValueError('Constrained target encoding requires unique rows and the declared target.')
    metadata, folds = plan
    if fit_idx is None or fit_idx.tolist() != metadata['fit_rows']:
        raise ValueError('Constrained target encoding must use its declared training rows.')
    y = pd.to_numeric(df.loc[fit_idx, target], errors='coerce')
    if not np.isfinite(y.to_numpy(dtype=float, na_value=np.nan)).all():
        raise ValueError('Constrained target encoding requires finite numeric training outcomes.')

    keys = category_keys(df[feature])
    encoded = pd.Series(index=df.index, dtype=float)

    def smoothed(rows):
        labels = y.loc[rows]
        prior = float(labels.mean())
        stats = labels.groupby(keys.loc[rows], sort=True).agg(['sum', 'count'])
        # Use the same smoothing semantics as the existing fitted encoder.
        values = (stats['sum'] + smoothing * prior) / (stats['count'] + smoothing)
        if not np.isfinite(prior) or not np.isfinite(values.to_numpy()).all():
            raise ValueError('Constrained target encoding produced nonfinite values. Check the target scale.')
        return prior, {str(key): float(value) for key, value in values.items()}

    oof_fits = []
    for train, validation in folds:
        prior, mapping = smoothed(train)
        encoded.loc[validation] = keys.loc[validation].map(lambda key: mapping.get(key, prior))
        oof_fits.append({'train_rows': train.tolist(), 'validation_rows': validation.tolist(),
                         'mapping': mapping, 'global_mean': prior})
    encoded.loc[metadata['warmup_rows']] = metadata['warmup_prior']
    prior, mapping = smoothed(fit_idx)
    application = df.index[~df.index.isin(fit_idx)]
    encoded.loc[application] = keys.loc[application].map(lambda key: mapping.get(key, prior))
    if not np.isfinite(encoded.to_numpy()).all():
        raise ValueError('Constrained target encoding did not cover every row with a finite value.')
    spec = {'type': 'target_encoding', 'mapping': mapping, 'global_mean': prior,
            'smoothing': smoothing, 'oof': True, 'fit_on_train_only': True,
            'oof_fits': oof_fits, 'category_key_encoding': CATEGORY_KEY_ENCODING, **metadata}
    if len(json.dumps(spec, allow_nan=False)) > MAX_FIT_EVIDENCE_BYTES:
        raise ValueError('Constrained target encoding evidence exceeds 256 KiB per feature and fit. Use lower-cardinality features or a smaller development population.')
    df[feature] = encoded
    return df, spec
