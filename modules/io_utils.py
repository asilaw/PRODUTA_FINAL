from pathlib import Path
import pandas as pd


def read_table(file_or_path):
    if file_or_path is None:
        return pd.DataFrame()
    if hasattr(file_or_path, "name"):
        name = file_or_path.name
    else:
        name = str(file_or_path)
    suffix = Path(name).suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(file_or_path)
    if suffix in [".csv", ".txt", ".tsv"]:
        sep = "\t" if suffix == ".tsv" else None
        return pd.read_csv(file_or_path, sep=sep, engine="python")
    raise ValueError("Format file harus .xlsx, .xls, .csv, .tsv, atau .txt")


def first_existing_file(folder, patterns=("*.csv", "*.xlsx", "*.xls")):
    folder = Path(folder)
    for pattern in patterns:
        files = sorted(folder.glob(pattern))
        if files:
            return files[0]
    return None
