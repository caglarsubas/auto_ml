"""Shared development folds and fold-fitted transforms for modeling/SFS/HPO."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, KFold, StratifiedKFold, TimeSeriesSplit

from modeling.split_contract import fit_numeric_imputer, transform_numeric_impute
from preprocessing.purifier_contract import parse_split_dates


def development_folds(context, row_index, y, n_splits):
    row_index = pd.Index(row_index)
    if type(n_splits) is not int or n_splits < 2:
        raise ValueError('Development validation requires an integer fold count of at least two.')
    if not row_index.is_unique or not row_index.isin(context['frame'].index).all():
        raise ValueError('Development rows must be unique members of the recorded development population.')
    frame = context['frame'].loc[row_index]
    config = (context.get('split_meta') or {}).get('split_config') or {}
    strategy = (context.get('split_meta') or {}).get('strategy', 'random')
    group_column = config.get('group_column')
    if strategy == 'group' and not group_column:
        raise ValueError('Declared group validation requires group_column; shuffled fallback is prohibited.')
    groups = frame[group_column] if group_column else None
    if groups is not None and groups.isna().any():
        raise ValueError('Development groups contain missing identifiers.')
    labels = pd.Series(y, index=row_index)
    if labels.isna().any() or not np.array_equal(labels.to_numpy(), context['labels'].loc[row_index].to_numpy()):
        raise ValueError('Development labels must match the recorded row membership and target semantics.')
    if strategy == 'oot':
        date_column = config.get('date_column')
        if not date_column or date_column not in frame:
            raise ValueError('Development temporal folds require an explicit date_column. Legacy chronology cannot be qualified.')
        dates = parse_split_dates(frame[date_column])
        if dates.isna().any():
            raise ValueError('Development temporal folds require valid timestamps.')
        order = dates.sort_values(kind='mergesort').index
        end_column = config.get('label_end_column')
        ends = parse_split_dates(frame[end_column]) if end_column else dates
        if ends.isna().any() or (ends < dates).any():
            raise ValueError('Development label windows are invalid.')
        splitter = TimeSeriesSplit(n_splits=n_splits)
        for train_pos, valid_pos in splitter.split(order):
            train, valid = order[train_pos], order[valid_pos]
            boundary = dates.loc[valid].min()
            train = train[(dates.loc[train] < boundary) & (ends.loc[train] < boundary)]
            if groups is not None:
                train = train[~groups.loc[train].isin(groups.loc[valid])]
            _check_fold(train, valid)
            yield train, valid
    elif strategy in ('random', 'group'):
        if groups is not None:
            splitter = GroupKFold(n_splits=n_splits)
            splits = splitter.split(frame, labels, groups)
        elif context['task'] == 'regression':
            splits = KFold(n_splits=n_splits, shuffle=True, random_state=42).split(frame)
        else:
            if labels.value_counts().min() < n_splits:
                raise ValueError('Declared classification folds require enough examples of every class; reduce fold count or revise the data population.')
            splits = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42).split(frame, labels)
        for train_pos, valid_pos in splits:
            train, valid = frame.index[train_pos], frame.index[valid_pos]
            _check_fold(train, valid)
            yield train, valid
    else:
        raise ValueError(f'Unsupported development validation strategy: {strategy}')


def _check_fold(train, valid):
    if len(train) < 2 or len(valid) < 1 or not train.intersection(valid).empty:
        raise ValueError('Declared constraints leave an invalid development fold.')


def prepare_fold(context, train, valid, features=None):
    source = context['frame']
    target = context['target_column']
    columns = [column for column in source if column != target and column not in context.get('excluded_features', [])]
    work = source.loc[train.append(valid), columns].copy()
    purifier = None
    if context.get('purifier_recipe'):
        from preprocessing.replay import fit_purifier, apply_purifier
        purifier = fit_purifier(work, context['purifier_recipe'], train)
        work = apply_purifier(work, purifier)
        if features is not None:
            dropped = set(columns) - set(work.columns)
            features = [feature for feature in features if feature not in dropped and
                (feature in work.columns or not any(feature.startswith(column + '_') for column in dropped))]
    plan = context.get('encoding_plan') or []
    if plan:
        from encoding.encoding_utils import apply_encoding
        work[target] = context['labels'].loc[work.index]
        work, report = apply_encoding(work, plan, target_col=target, use_native=context.get('use_native', True), fit_idx=train)
        work = work.drop(columns=[target])
    else:
        report = []
        for column in work:
            if not pd.api.types.is_numeric_dtype(work[column]):
                levels = pd.Index(work.loc[train, column].dropna().unique())
                work[column] = pd.Categorical(work[column], categories=levels)
    if features is not None:
        # An OHE column whose category is absent in the fit fold is all zero.
        work = work.reindex(columns=features, fill_value=0.)
    if work.shape[1] == 0:
        raise ValueError('The declared purifier and candidate leave no model features in this training fold.')
    fit = work.loc[train]
    means = fit_numeric_imputer(fit)
    provenance = {'train_rows': train.tolist(), 'valid_rows': valid.tolist(),
                  'impute_means': means, 'encoding': report,
                  'purifier': purifier,
                  'upstream_limitation': None if purifier else 'Legacy processed input; upstream purifier provenance unverified.'}
    return transform_numeric_impute(fit, means), transform_numeric_impute(work.loc[valid], means), provenance


def prepared_folds(context, X, y, n_splits, *, all_declared_features=False):
    for train, valid in development_folds(context, X.index, y, n_splits):
        X_train, X_valid, provenance = prepare_fold(context, train, valid, None if all_declared_features else list(X.columns))
        yield X_train, context['labels'].loc[train], X_valid, context['labels'].loc[valid], provenance


def iter_validation_folds(context, X, y, n_splits, task):
    if context is not None:
        if context['task'] != task:
            raise ValueError('Search task contradicts the recorded development validation task.')
        yield from prepared_folds(context, X, y, n_splits)
        return
    # Existing callers remain inspectable, explicitly lacking upstream provenance.
    splitter = KFold(n_splits=n_splits, shuffle=True, random_state=42) if task == 'regression' else StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    for tr, va in splitter.split(X, y):
        yield X.iloc[tr], y.iloc[tr], X.iloc[va], y.iloc[va], {'qualification': 'legacy; preprocessing provenance unverified'}
