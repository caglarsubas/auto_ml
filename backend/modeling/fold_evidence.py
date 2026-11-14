"""Portable development fit evidence, with content-addressed shared state."""

from collections.abc import Mapping

from modeling.fit_receipts import receipt_digest


class FoldEvidence:
    def __init__(self, development_rows):
        self.development_rows = set(development_rows)
        self.partitions = {}
        self.transforms = {}
        self.fits = []
        self.gaps = []

    @staticmethod
    def _bind(store, value):
        sha = receipt_digest(value)
        store.setdefault(sha, value)
        return sha

    def record(self, stage, fit, state=None, *, train_rows=None, valid_rows=None, refit=False, candidate_feature=None):
        if not fit:
            self.gaps.append({'stage': stage, 'reason': 'native_fit_receipt_unavailable'})
            return
        receipt = {key: value for key, value in fit.items() if key != 'sha256'}
        if receipt_digest(receipt) != fit.get('sha256'):
            raise ValueError('Development fit receipt digest does not match.')
        if train_rows is None or valid_rows is None:
            self.gaps.append({'stage': stage, 'reason': 'fit_membership_unavailable'})
            return
        if not isinstance(train_rows, list) or not isinstance(valid_rows, list):
            raise ValueError('Development fit membership must contain ordered row lists.')
        if any(type(row) not in {int, str} for rows in (train_rows, valid_rows) for row in rows):
            raise ValueError('Development fit row identities must be integers or strings.')
        train, valid = set(train_rows), set(valid_rows)
        if (len(train) != len(train_rows) or len(valid) != len(valid_rows)
                or not train or (not valid and not refit) or train & valid
                or not (train | valid) <= self.development_rows
                or len(train) != fit['train']['n_rows']
                or (len(train) if refit else len(valid)) != fit['valid']['n_rows']):
            raise ValueError('Development fit membership does not match the receipt or permitted partition.')
        for name, rows in (('train', train_rows), ('valid', train_rows if refit else valid_rows)):
            declared = fit.get(name + '_rows_sha256')
            if declared is not None and declared != receipt_digest(rows):
                raise ValueError('Ordered development row identities do not match the native fit receipt.')
        if any(fit.get(name + '_rows_sha256') is None for name in ('train', 'valid')):
            self.gaps.append({'stage': stage, 'reason': 'historical_ordered_membership_unverified'})
        if refit and (valid or fit.get('validation_role') == 'early_stopping'
                      or fit['train']['sha256'] != fit['valid']['sha256']):
            raise ValueError('An all-development refit cannot consume a validation partition.')
        partition = {'train_rows': train_rows, 'validation_rows': valid_rows,
                     'validation_role': 'unused_train_mirror' if refit else fit['validation_role']}
        state = state or {}
        if not isinstance(state, Mapping):
            raise ValueError('Fitted transformation evidence must be an object.')
        purifier = state.get('purifier')
        if purifier and purifier.get('fit_rows') != train_rows:
            raise ValueError('Purifier evidence was fitted on a different partition.')
        internal = fit.get('fitted_transforms')
        if internal and (internal.get('fit_partition') != 'train'
                         or internal.get('fit_input_sha256') != fit['train']['sha256']):
            raise ValueError('Native fitted transform evidence was fitted on a different partition.')
        if state.get('upstream_limitation'):
            self.gaps.append({'stage': stage, 'reason': 'upstream_preparation_unverified'})
        if fit.get('algorithm') in {'logistic_regression', 'scorecard', 'isolation_forest'} and not internal:
            self.gaps.append({'stage': stage, 'reason': 'historical_internal_transforms_unavailable'})
        transforms = {'encoding': state.get('encoding', []), 'impute_means': state.get('impute_means', {}),
                      'purifier': purifier, 'internal': internal, 'class_weight': state.get('class_weight')}
        # The hash still binds the full fitted state; reference it once in the
        # export instead of repeating it in the receipt and transformation table.
        item = {'stage': stage, 'partition_sha256': self._bind(self.partitions, partition),
                'transforms_sha256': self._bind(self.transforms, transforms),
                'fit_receipt': {key: value for key, value in fit.items() if key != 'fitted_transforms'}}
        if candidate_feature is not None:
            item['candidate_feature'] = candidate_feature
        self.fits.append(item)

    def fold(self, stage, row, *, candidate_feature=None, parent_rows=None):
        if parent_rows is not None and not set((row.get('train_rows') or []) + (row.get('valid_rows') or [])) <= parent_rows:
            raise ValueError('Search folds exceed the frozen outer development-training partition.')
        self.record(stage, row.get('native_fit') or row.get('fit_receipt'), row,
                    train_rows=row.get('train_rows'), valid_rows=row.get('valid_rows'), candidate_feature=candidate_feature)

    def result(self):
        return {'schema_version': 1, 'partitions': self.partitions, 'transform_states': self.transforms,
                'fits': self.fits, 'unverified': self.gaps, 'evidence_scope': 'exploratory_development',
                'independent_reproduction_verified': False, 'production_use_approved': False}
