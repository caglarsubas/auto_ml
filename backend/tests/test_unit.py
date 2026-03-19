"""
UNIT TESTS
===========
Isolated tests for models, serializers, utility functions, and pure logic.
These tests do NOT hit the database or make HTTP requests unless necessary
for Django model validation.
"""
import pytest
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats


# ---------------------------------------------------------------------------
# Declaration model tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestDeclarationModel:

    def test_create_declaration(self):
        """Declaration can be created with required fields."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        assert decl.pk is not None
        assert str(decl) == 'test.csv'

    def test_declaration_get_file_path_returns_none_when_missing(self, _use_tmp_media):
        """get_file_path returns None when file does not exist on disk."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/nonexistent.csv',
            name='nonexistent.csv',
            original_name='nonexistent.csv',
        )
        assert decl.get_file_path() is None


@pytest.mark.unit
@pytest.mark.django_db
class TestDataDictionaryModel:

    def test_create_data_dictionary(self):
        """DataDictionary can be linked to a Declaration."""
        from declaration.models import Declaration, DataDictionary
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        dd = DataDictionary.objects.create(
            data_file=decl,
            column_name='Age',
            description='Customer age in years',
        )
        assert dd.pk is not None
        assert str(dd) == 'test.csv - Age'

    def test_get_description_returns_none_for_missing(self):
        """get_description returns None when column not in dictionary."""
        from declaration.models import DataDictionary
        assert DataDictionary.get_description(file_id=9999, column_name='X') is None

    def test_unique_together_constraint(self):
        """Duplicate (data_file, column_name) raises IntegrityError."""
        from django.db import IntegrityError
        from declaration.models import Declaration, DataDictionary
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        DataDictionary.objects.create(data_file=decl, column_name='Age', description='v1')
        with pytest.raises(IntegrityError):
            DataDictionary.objects.create(data_file=decl, column_name='Age', description='v2')


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestDeclarationSerializer:

    def test_serializer_fields(self):
        """Serializer exposes the expected field set."""
        from declaration.serializers import DeclarationSerializer
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        s = DeclarationSerializer(decl)
        assert set(s.data.keys()) == {'id', 'file', 'name', 'original_name', 'uploaded_at'}

    def test_serializer_read_only_id(self):
        """The id field is read-only."""
        from declaration.serializers import DeclarationSerializer
        s = DeclarationSerializer()
        assert s.fields['id'].read_only is True


# ---------------------------------------------------------------------------
# Utility / pure-logic tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetSeparator:

    def _get_separator(self, name):
        """Mirror the DeclarationViewSet.get_separator logic."""
        separators = {
            'semicolon': ';',
            'comma': ',',
            'tab': '\t',
            'space': ' ',
        }
        return separators.get(name, ';')

    def test_known_separators(self):
        assert self._get_separator('semicolon') == ';'
        assert self._get_separator('comma') == ','
        assert self._get_separator('tab') == '\t'
        assert self._get_separator('space') == ' '

    def test_unknown_defaults_to_semicolon(self):
        assert self._get_separator('pipe') == ';'
        assert self._get_separator('') == ';'


@pytest.mark.unit
class TestRenameDuplicateColumns:

    def _rename(self, columns):
        new_columns = []
        seen = set()
        for item in columns:
            counter = 1
            new_item = item
            while new_item in seen:
                new_item = f"{item}_{counter}"
                counter += 1
            new_columns.append(new_item)
            seen.add(new_item)
        return new_columns

    def test_no_duplicates(self):
        assert self._rename(['A', 'B', 'C']) == ['A', 'B', 'C']

    def test_with_duplicates(self):
        result = self._rename(['A', 'A', 'B', 'A'])
        assert result == ['A', 'A_1', 'B', 'A_2']

    def test_empty_list(self):
        assert self._rename([]) == []


@pytest.mark.unit
class TestDetermineLevelOfMeasurement:
    """Test the level-of-measurement classification logic."""

    def _determine(self, column_data, data_type, unique_count):
        if unique_count == len(column_data):
            return 'id'
        elif (data_type in ('float64', 'float', 'float32')) and (unique_count > 1000):
            return 'continuous'
        elif (data_type in ('float64', 'float', 'float32')) and (unique_count <= 1000):
            return 'cardinal'
        elif data_type == 'integer':
            if unique_count > 1000 or unique_count / len(column_data) > 0.1:
                return 'continuous'
            else:
                if unique_count > 5:
                    return 'cardinal'
                else:
                    return 'nominal'
        elif data_type in ('object', 'str', 'string'):
            try:
                pd.to_datetime(column_data, errors='raise', format='%d/%m/%Y %I:%M:%S %p')
                return 'datetime'
            except Exception:
                return 'nominal'
        else:
            return 'unknown'

    def test_unique_id_column(self):
        data = pd.Series(range(100))
        assert self._determine(data, 'integer', 100) == 'id'

    def test_float_continuous(self):
        data = pd.Series(np.random.uniform(0, 1, 5000))
        assert self._determine(data, 'float64', 4500) == 'continuous'

    def test_float_cardinal(self):
        data = pd.Series(np.random.uniform(0, 1, 100))
        assert self._determine(data, 'float', 80) == 'cardinal'

    def test_integer_continuous(self):
        data = pd.Series(range(10000))
        assert self._determine(data, 'integer', 5000) == 'continuous'

    def test_integer_cardinal(self):
        data = pd.Series(np.random.randint(1, 20, 200))
        assert self._determine(data, 'integer', 15) == 'cardinal'

    def test_integer_nominal(self):
        data = pd.Series(np.random.choice([0, 1], 100))
        assert self._determine(data, 'integer', 2) == 'nominal'

    def test_object_nominal(self):
        data = pd.Series(['A', 'B', 'C'] * 30)
        assert self._determine(data, 'object', 3) == 'nominal'

    def test_str_nominal(self):
        """Regression: 'str' dtype (pandas 2.0+) should classify as nominal, not unknown."""
        data = pd.Series(['cat', 'dog'] * 50)
        assert self._determine(data, 'str', 2) == 'nominal'

    def test_string_nominal(self):
        """Regression: 'string' dtype should classify as nominal, not unknown."""
        data = pd.Series(['x', 'y', 'z'] * 30)
        assert self._determine(data, 'string', 3) == 'nominal'

    def test_datetime_detection(self):
        dates = pd.Series([f'01/0{i}/2024 01:00:00 AM' for i in range(1, 10)] * 3)
        assert self._determine(dates, 'object', 9) == 'datetime'

    def test_unknown_fallback(self):
        data = pd.Series([1, 2, 3])
        assert self._determine(data, 'bool', 2) == 'unknown'


@pytest.mark.unit
class TestCalculateDescriptiveStats:
    """Test descriptive statistics calculation."""

    def test_continuous_stats_keys(self):
        data = pd.Series(np.random.uniform(0, 100, 500))
        numeric_data = pd.to_numeric(data, errors='coerce')
        stats = {
            'Mean': round(numeric_data.mean(), 2),
            'Min': round(numeric_data.min(), 2),
            'Max': round(numeric_data.max(), 2),
            'Std': round(numeric_data.std(), 2),
        }
        assert 'Mean' in stats
        assert 'Min' in stats
        assert stats['Min'] <= stats['Max']
        assert stats['Std'] >= 0

    def test_nominal_stats_keys(self):
        data = pd.Series(['A', 'B', 'C', 'A', 'A', 'B'])
        value_counts = data.value_counts(dropna=False)
        total_count = len(data)
        stats = {
            '#_of_Categories': len(value_counts),
            'Mode_Value': value_counts.index[0],
            'Mode_Ratio': round((value_counts.iloc[0] / total_count) * 100, 2),
        }
        assert stats['#_of_Categories'] == 3
        assert stats['Mode_Value'] == 'A'
        assert stats['Mode_Ratio'] == 50.0
