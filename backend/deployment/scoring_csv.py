"""Parse exact scoring bytes without silently truncating field values."""

import io

import pandas as pd


class InvalidScoringCSV(ValueError):
    pass


def scoring_text_columns(manifest):
    if "input_text_columns" in manifest:
        return manifest["input_text_columns"]
    from encoding.fitted import constrained_text_columns

    return constrained_text_columns(manifest.get("encoding_report") or [])


def read_scoring_csv(raw, *, string_columns=(), nrows=None):
    if b"\x00" in raw:
        raise InvalidScoringCSV("CSV scoring input contains an embedded NUL character.")
    frame = pd.read_csv(io.BytesIO(raw), nrows=nrows,
                        dtype={column: "string" for column in string_columns} or None)
    if not isinstance(frame.index, pd.RangeIndex):
        # The default pandas reader can reinterpret surplus fields as row labels.
        raise InvalidScoringCSV("CSV scoring rows contain more fields than the header.")
    return frame
