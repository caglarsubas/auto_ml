import pandas as pd
import pytest

from deployment.scoring_csv import InvalidScoringCSV, read_scoring_csv

pytestmark = pytest.mark.unit


def test_csv_preserves_frozen_text_and_rejects_ambiguous_records():
    frame = read_scoring_csv(b"x,cat\n2,001\n1\n", string_columns=["cat"])
    assert list(frame["x"]) == [2, 1]
    assert frame.at[0, "cat"] == "001" and pd.isna(frame.at[1, "cat"])
    for raw, message in (
        (b"x,cat\n1\x00invalid,001\n", "embedded NUL"),
        (b"x,cat\n1,001\x00changed\n", "embedded NUL"),
        (b"x,cat\n0,1,001\n", "more fields"),
    ):
        with pytest.raises(InvalidScoringCSV, match=message):
            read_scoring_csv(raw, string_columns=["cat"])
