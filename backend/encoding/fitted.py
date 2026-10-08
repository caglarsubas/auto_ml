"""Replay recorded encoder maps without inspecting scoring outcomes."""
import pandas as pd


def apply_fitted_encoding(frame, reports):
    result = frame.copy()
    for report in reports:
        feature = report['feature']
        if feature not in result:
            raise ValueError(f'Missing required source feature for encoding: {feature}')
        spec = report.get('mapping') or {}
        kind = spec.get('type') or report.get('strategy_applied') or report.get('strategy')
        values = result[feature]
        if kind == 'native_categorical':
            levels = spec.get('categories', report.get('categories'))
            if levels is None:
                raise ValueError(f'Native category inventory is missing: {feature}')
            result[feature] = pd.Categorical(values.where(values.notna(), None).astype('string'), categories=list(map(str, levels)))
        elif kind == 'one_hot_encoding':
            columns = spec.get('columns')
            if columns is None:
                raise ValueError(f'One-hot schema is missing: {feature}')
            strings = values.fillna(f'{feature}_NULL').astype(str)
            dummies = pd.get_dummies(strings, prefix=feature, dtype=int).reindex(columns=columns, fill_value=0)
            result = pd.concat([result.drop(columns=[feature]), dummies], axis=1)
        elif kind in ('label_encoding', 'ordinal_encoding', 'manual_grouping', 'frequency_encoding', 'target_encoding'):
            mapping = spec.get('mapping')
            if not isinstance(mapping, dict):
                raise ValueError(f'Fitted encoder map is missing: {feature}')
            default = float(spec.get('global_mean', 0)) if kind == 'target_encoding' else (0 if kind == 'frequency_encoding' else -1)
            if kind == 'ordinal_encoding':
                strings = values.astype(str)
            else:
                strings = values.fillna('__NULL__').astype(str)
            result[feature] = strings.map(lambda value: mapping.get(value, default))
            result[feature] = result[feature].astype(int if kind in ('label_encoding', 'ordinal_encoding') else float)
        else:
            raise ValueError(f'Unsupported or missing fitted encoder: {kind!r} for {feature}')
    return result
