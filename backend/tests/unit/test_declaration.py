"""Unit tests - declaration (models, serializers, header/level detection).

Auto-split from the original monolithic tests/test_unit.py. Shared helpers live
in tests/unit/_shared.py; the shared engine-models fixture lives in
tests/unit/conftest.py. Test logic is unchanged.
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
# Header auto-detection tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestDetectHasHeader:
    """Test the detect_has_header heuristic from declaration/views.py."""

    def test_csv_with_text_headers(self):
        """A CSV whose first row has descriptive text headers should return True."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"AppID,Application_Datetime,Target,Var_1,Var_2\n"
            b"1,2020-01-01,0,1500,200\n"
            b"2,2020-02-01,1,3000,400\n"
            b"3,2020-03-01,0,500,100\n"
        )
        assert detect_has_header(csv_bytes, sep=',') is True

    def test_csv_without_headers(self):
        """A CSV whose first row is all data (numeric + short strings) → False."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"0,1/1/2020 0:00,0,0,L,Y,1750,1\n"
            b"1,1/1/2020 0:00,0,0,1,N,1300,12\n"
            b"2,1/1/2020 0:00,0,0,0,N,0,0\n"
            b"3,2/1/2020 0:00,1,1,0,Y,500,3\n"
        )
        assert detect_has_header(csv_bytes, sep=',') is False

    def test_csv_semicolon_with_headers(self):
        """Semicolon-delimited CSV with headers should return True."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"Name;Age;Income;City\n"
            b"Alice;30;50000;Berlin\n"
            b"Bob;25;40000;Munich\n"
        )
        assert detect_has_header(csv_bytes, sep=';') is True

    def test_csv_semicolon_without_headers(self):
        """Semicolon-delimited CSV without headers — mostly numeric + short codes."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"0;1/1/2020;Y;1750;500;A\n"
            b"1;2/1/2020;N;1300;600;R\n"
            b"2;3/1/2020;Y;0;100;A\n"
            b"3;4/1/2020;N;500;200;R\n"
        )
        result = detect_has_header(csv_bytes, sep=';')
        assert result is False

    def test_single_row_defaults_to_true(self):
        """With only one row, can't tell — default to has-header."""
        from declaration.views import detect_has_header
        csv_bytes = b"col1,col2,col3\n"
        assert detect_has_header(csv_bytes, sep=',') is True

    def test_empty_content_defaults_to_true(self):
        """Empty/unparseable content defaults to has-header."""
        from declaration.views import detect_has_header
        assert detect_has_header(b"", sep=',') is True

    def test_mixed_numeric_header(self):
        """First row has text headers, data rows are numeric → True."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"ID,Score,Amount,Balance,Limit\n"
            b"1,750,5000,2000,10000\n"
            b"2,680,3000,1500,8000\n"
            b"3,720,4500,3000,12000\n"
        )
        assert detect_has_header(csv_bytes, sep=',') is True

    def test_all_numeric_no_header(self):
        """All values including first row are numeric → False."""
        from declaration.views import detect_has_header
        csv_bytes = (
            b"100,200,300,400\n"
            b"101,201,301,401\n"
            b"102,202,302,402\n"
        )
        assert detect_has_header(csv_bytes, sep=',') is False

# ---------------------------------------------------------------------------
# Declaration model has_header field tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
class TestDeclarationHasHeader:

    def test_has_header_defaults_to_true(self):
        """New Declaration defaults to has_header=True."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
        )
        assert decl.has_header is True

    def test_has_header_can_be_set_false(self):
        """Declaration can be created with has_header=False."""
        from declaration.models import Declaration
        decl = Declaration.objects.create(
            file='data_files/test.csv',
            name='test.csv',
            original_name='test.csv',
            has_header=False,
        )
        assert decl.has_header is False

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
        assert set(s.data.keys()) == {'id', 'file', 'name', 'original_name', 'uploaded_at', 'has_header'}

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


@pytest.mark.unit
class TestDataDictionaryHeuristics:
    def test_looks_like_data_dictionary_for_feature_catalog(self):
        from declaration.views import looks_like_data_dictionary
        df = pd.DataFrame({
            'Feature_Name': ['AppID', 'Target', 'Var_1', 'Var_2', 'Var_3'],
            'Feature_Description': ['id', 'flag', 'a', 'b', 'c'],
        })
        assert looks_like_data_dictionary(df) is True

    def test_wide_modeling_frame_is_not_dictionary(self):
        from declaration.views import looks_like_data_dictionary
        df = pd.DataFrame({
            'AppID': [1, 2, 3],
            'Target': [0, 1, 0],
            'Var_1': [10, 20, 30],
            'Var_2': [1.1, 2.2, 3.3],
        })
        assert looks_like_data_dictionary(df) is False

    def test_two_column_category_target_is_not_dictionary(self):
        from declaration.views import looks_like_data_dictionary
        df = pd.DataFrame({
            'Category': list('ABC') * 10,
            'Target': [0, 1] * 15,
        })
        assert looks_like_data_dictionary(df) is False

    def test_resolve_excel_skips_dictionary_sheet(self, tmp_path):
        from declaration.views import resolve_excel_sheet
        path = tmp_path / 'combo.xlsx'
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            pd.DataFrame({
                'Feature_Name': [f'Var_{i}' for i in range(10)],
                'Feature_Description': [f'desc {i}' for i in range(10)],
            }).to_excel(writer, sheet_name='Data_Dictionary', index=False)
            pd.DataFrame({
                'AppID': list(range(8)),
                'Target': [0, 1] * 4,
                'Var_1': list(range(8)),
                'Var_2': list(range(8, 16)),
            }).to_excel(writer, sheet_name='ModelingData', index=False)
        raw = path.read_bytes()
        sheet, skipped, note = resolve_excel_sheet(raw, first_sheet_has_not_dataset=False)
        assert skipped is True
        assert sheet == 'ModelingData'
        assert note and 'Data_Dictionary' in note
