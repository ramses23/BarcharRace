from pathlib import Path

import pandas as pd
import streamlit as st


def load_csv_dataset(csv_path):
    path = Path(csv_path)
    stat = path.stat()
    return _load_csv_dataset(
        str(path.resolve()),
        file_size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
    )


@st.cache_data(max_entries=8, show_spinner=False)
def _load_csv_dataset(path, *, file_size, modified_ns):
    # The signature values intentionally participate in Streamlit's cache key.
    # They invalidate a reused path when an upload replaces the underlying CSV.
    del file_size, modified_ns
    return pd.read_csv(path)
