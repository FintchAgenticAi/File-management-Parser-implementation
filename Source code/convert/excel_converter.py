from __future__ import annotations

from pathlib import Path

import pandas as pd

from convert.base_converter import build_output_path


def convert_excel_to_csv(input_path: Path, output_dir: Path | None = None) -> Path:
    """Convert the first worksheet in an XLS or XLSX workbook to CSV."""
    output_path = build_output_path(input_path, output_dir)
    engine = "xlrd" if input_path.suffix.lower() == ".xls" else "openpyxl"
    dataframe = pd.read_excel(input_path, sheet_name=0, engine=engine)
    dataframe.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path