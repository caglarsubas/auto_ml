"""Replay recorded encoder maps without inspecting scoring outcomes."""
import pandas as pd

from encoding.constrained import CATEGORY_KEY_ENCODING, category_keys


def apply_fitted_encoding(frame, reports, *, native_categories=None):
    result = frame.copy()
    for report in reports:
        feature = report['feature']
        if feature not in result:
            raise ValueError(f'Missing required source feature for encoding: {feature}')
        spec = report.get('mapping') or {}
        kind = spec.get('type') or report.get('strategy_applied') or report.get('strategy')
        values = result[feature]
        if kind == 'native_categorical':
            levels = (native_categories or {}).get(feature)
            if levels is None:
                levels = spec.get('categories', report.get('categories'))
                if levels is None:
                    raise ValueError(f'Native category inventory is missing: {feature}')
                levels = list(map(str, levels))
            if levels and isinstance(levels[0], str):
                values = values.astype('string')
            result[feature] = pd.Categorical(values.where(values.isin(levels)), categories=levels)
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
            if kind == 'target_encoding' and spec.get('cross_fit_strategy') is not None:
                if spec.get('category_key_encoding') != CATEGORY_KEY_ENCODING:
                    raise ValueError(f'Unsupported target encoder category format: {feature}')
                strings = category_keys(values)
            elif kind == 'ordinal_encoding':
                strings = values.astype(str)
            else:
                strings = values.fillna('__NULL__').astype(str)
            result[feature] = strings.map(lambda value: mapping.get(value, default))
            result[feature] = result[feature].astype(int if kind in ('label_encoding', 'ordinal_encoding') else float)
        else:
            raise ValueError(f'Unsupported or missing fitted encoder: {kind!r} for {feature}')
    return result



def constrained_text_columns(reports):
    return sorted({report['feature'] for report in reports
                   if (report.get('mapping') or {}).get('cross_fit_strategy') is not None})


def scoring_encoding_reports(reports, *, features=None):
    selected = set(features) if features is not None else None
    result = []
    for report in reports:
        spec = report.get('mapping') or {}
        outputs = spec.get('columns') or [report['feature']]
        if selected is not None and not selected.intersection(outputs):
            continue
        if spec.get('cross_fit_strategy') is not None:
            # Inner training applications belong in lineage, not the score package.
            spec = {key: spec[key] for key in ('type', 'mapping', 'global_mean',
                                               'cross_fit_strategy', 'category_key_encoding')}
            report = {'feature': report['feature'], 'mapping': spec}
        result.append(report)
    return result
