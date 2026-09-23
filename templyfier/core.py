from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import unicodedata
from typing import BinaryIO, Iterable, Sequence
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.worksheet import Worksheet


DATA_SHEET_PRIORITY = (
    "Table_1 2_TAILED",
    "Table_1_2_TAILED",
    "Table_1 1_TAILED",
    "Table_1_1_TAILED",
    "Table_1 DELTA",
    "Table_1_2_TAILED_DELTA",
)
EXCLUDED_SHEET_WORDS = ("legend", "screener")
METRIC_HEADER_ALIASES = {
    "metric", "metrics", "metrique", "metriques", "measure", "measures",
    "statistic", "statistics", "indicateur", "indicateurs",
}


class TemplyfierError(ValueError):
    """A user-correctable input or structure error."""


@dataclass(frozen=True)
class SheetLayout:
    header_row: int
    metric_col: int
    product_cols: tuple[int, ...]
    sample_row_index: int | None = None
    product_name_row_index: int | None = None
    product_header_row_index: int | None = None

    @property
    def sample_row(self) -> int:
        return self.sample_row_index or self.header_row - 1

    @property
    def product_name_row(self) -> int:
        return self.product_name_row_index or self.header_row - 2

    @property
    def product_header_row(self) -> int:
        return self.product_header_row_index or self.header_row


@dataclass(frozen=True)
class InputInfo:
    filename: str
    split_name: str
    source_sheet: str
    counts: tuple[int | None, ...]
    product_names: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceInfo:
    sheet_name: str
    product_names: tuple[str, ...]
    benchmark_positions: tuple[int, ...]
    retained_rows: int


def _read_bytes(source: str | Path | bytes | BinaryIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    source.seek(0)
    return source.read()


def _workbook(source, *, data_only: bool = False):
    raw = _read_bytes(source)
    try:
        return load_workbook(BytesIO(raw), data_only=data_only)
    except (BadZipFile, InvalidFileException) as exc:
        raise TemplyfierError(
            "Ce fichier .XLS est dans l’ancien format Excel binaire. Ouvre-le dans Excel puis enregistre-le en .XLSX. "
            "Les exports .XLS qui contiennent déjà un classeur moderne sont acceptés automatiquement."
        ) from exc


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _safe_sheet_name(value: str, used: set[str]) -> str:
    base = re.sub(r"[\\/*?:\[\]]", " ", _text(value)) or "Split"
    base = re.sub(r"\s+", " ", base).strip()[:31]
    candidate, suffix = base, 2
    while candidate.casefold() in used:
        tail = f" ({suffix})"
        candidate = f"{base[:31-len(tail)]}{tail}"
        suffix += 1
    used.add(candidate.casefold())
    return candidate


def _count_from_header(value) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    match = re.match(r"\s*(\d+)\s*(?:-|$)", _text(value))
    return int(match.group(1)) if match else None


def _fold_text(value) -> str:
    text = unicodedata.normalize("NFKD", _text(value))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).casefold().split())


def _metric_header(value) -> bool:
    token = re.sub(r"[^a-z]+", " ", _fold_text(value)).strip()
    return token in METRIC_HEADER_ALIASES


def detect_data_sheet(workbook) -> Worksheet:
    """Select the strongest valid result table, independent of exact sheet naming."""
    def title_key(value):
        return re.sub(r"[^a-z0-9]+", "", _fold_text(value))

    priority = {title_key(name): index for index, name in enumerate(DATA_SHEET_PRIORITY)}
    diagnostics = {}
    # Keep the frequent known layouts fast, but validate them before returning.
    for preferred_name in DATA_SHEET_PRIORITY:
        preferred_key = title_key(preferred_name)
        for sheet in workbook.worksheets:
            if title_key(sheet.title) != preferred_key:
                continue
            try:
                detect_layout(sheet)
                return sheet
            except TemplyfierError as exc:
                diagnostics[sheet.title] = str(exc)
                break
    candidates = []
    for position, sheet in enumerate(workbook.worksheets):
        low = _fold_text(sheet.title)
        if any(word in low for word in EXCLUDED_SHEET_WORDS):
            continue
        try:
            layout = detect_layout(sheet)
        except TemplyfierError as exc:
            diagnostics[sheet.title] = str(exc)
            continue
        numeric_rows = sum(
            any(isinstance(sheet.cell(row, col).value, (int, float)) and
                not isinstance(sheet.cell(row, col).value, bool) for col in layout.product_cols)
            for row in range(layout.header_row + 1, min(sheet.max_row, layout.header_row + 250) + 1)
        )
        preferred = priority.get(title_key(sheet.title), len(priority))
        candidates.append((preferred, -numeric_rows, -len(layout.product_cols), position, sheet))
    if candidates:
        return min(candidates, key=lambda item: item[:-1])[-1]
    detail = "; ".join(f"{name}: {reason}" for name, reason in list(diagnostics.items())[:4])
    suffix = f" Checked sheets: {detail}" if detail else ""
    raise TemplyfierError(
        "No supported G-Sight result table was found. No output was generated."
        + suffix
    )


def _layout_from_header(sheet: Worksheet, header_row: int, metric_col: int):
    last_col = min(sheet.max_column, 250)
    sample_scores = [
        (sum(_count_from_header(sheet.cell(row, col).value) is not None
             for col in range(metric_col + 1, last_col + 1)), row)
        for row in range(max(1, header_row - 12), header_row)
    ]
    sample_count, sample_row = max(sample_scores, default=(0, max(1, header_row - 1)))

    if sample_count:
        raw_product_cols = [
            col for col in range(metric_col + 1, last_col + 1)
            if _count_from_header(sheet.cell(sample_row, col).value) is not None
        ]
    else:
        # Exports without an N/base row remain usable when value columns have a
        # repeated numeric pattern. Significance-letter columns are excluded.
        data_end = min(sheet.max_row, header_row + 250)
        raw_product_cols = []
        for col in range(metric_col + 1, last_col + 1):
            numeric = sum(
                isinstance(sheet.cell(row, col).value, (int, float)) and
                not isinstance(sheet.cell(row, col).value, bool)
                for row in range(header_row + 1, data_end + 1)
            )
            if numeric >= 3:
                raw_product_cols.append(col)
        sample_row = max(1, header_row - 1)

    if len(raw_product_cols) < 2:
        raise TemplyfierError(f"Fewer than two result columns were found in '{sheet.title}'.")

    product_name_rows = (
        range(max(1, sample_row - 8), sample_row)
        if sample_count else range(max(1, header_row - 8), header_row + 1)
    )
    product_name_row = max(
        product_name_rows,
        key=lambda row: sum(bool(_text(sheet.cell(row, col).value)) for col in raw_product_cols),
    )
    product_header_rows = (
        range(min(header_row, sample_row + 1), header_row + 1)
        if sample_count else range(max(1, header_row - 1), header_row + 1)
    )
    product_header_row = max(
        product_header_rows,
        key=lambda row: sum(bool(_text(sheet.cell(row, col).value)) for col in raw_product_cols),
    )
    product_cols = [
        col for col in raw_product_cols
        if (_text(sheet.cell(product_name_row, col).value)
            or _text(sheet.cell(product_header_row, col).value)
            or any(isinstance(sheet.cell(row, col).value, (int, float)) and
                   not isinstance(sheet.cell(row, col).value, bool)
                   for row in range(header_row + 1, min(sheet.max_row, header_row + 30) + 1)))
    ]
    if len(product_cols) < 2:
        raise TemplyfierError(f"Fewer than two products were found in '{sheet.title}'.")

    metric_rows = sum(
        bool(_text(sheet.cell(row, metric_col).value))
        for row in range(header_row + 1, min(sheet.max_row, header_row + 250) + 1)
    )
    numeric_rows = sum(
        any(isinstance(sheet.cell(row, col).value, (int, float)) and
            not isinstance(sheet.cell(row, col).value, bool) for col in product_cols)
        for row in range(header_row + 1, min(sheet.max_row, header_row + 250) + 1)
    )
    if metric_rows < 2 or numeric_rows < 2:
        raise TemplyfierError(f"The result table in '{sheet.title}' is incomplete.")
    return SheetLayout(
        header_row, metric_col, tuple(product_cols),
        sample_row_index=sample_row,
        product_name_row_index=product_name_row,
        product_header_row_index=product_header_row,
    ), (numeric_rows, metric_rows, len(product_cols))


def detect_layout(sheet: Worksheet) -> SheetLayout:
    """Detect G-Sight tables from their structure rather than fixed coordinates."""
    def find_headers(max_rows, max_cols, *, skip_fast_area=False):
        found = []
        for row in range(1, min(sheet.max_row, max_rows) + 1):
            for col in range(1, min(sheet.max_column, max_cols) + 1):
                if skip_fast_area and row <= 25 and col <= 15:
                    continue
                if _metric_header(sheet.cell(row, col).value):
                    found.append((row, col))
        return found

    headers = find_headers(25, 15)
    if not headers:
        headers = find_headers(100, 60, skip_fast_area=True)
    if not headers:
        raise TemplyfierError(f"No Metric/Measure header was found in '{sheet.title}'.")

    candidates = []
    for row, col in headers:
        try:
            layout, score = _layout_from_header(sheet, row, col)
            candidates.append((score, -row, -col, layout))
        except TemplyfierError:
            continue
    if not candidates:
        raise TemplyfierError(f"No complete result table was found in '{sheet.title}'.")
    return max(candidates, key=lambda item: item[:-1])[-1]


def _product_names(sheet: Worksheet, layout: SheetLayout) -> tuple[str, ...]:
    return tuple(_text(sheet.cell(layout.product_name_row, col).value) for col in layout.product_cols)


def _signature(sheet: Worksheet, layout: SheetLayout) -> tuple[int | None, ...]:
    return tuple(_count_from_header(sheet.cell(layout.sample_row, col).value) for col in layout.product_cols)


def _normal_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 10)
    if value in (None, ""):
        return None
    return _text(value)


def _row_vector(sheet: Worksheet, row: int, cols: Sequence[int]) -> tuple:
    return tuple(_normal_value(sheet.cell(row, col).value) for col in cols)


def _has_data(vector: Sequence) -> bool:
    return any(isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector)


def _pick_reference_sheet(reference_wb, requested: str | None = None) -> Worksheet:
    if requested:
        if requested not in reference_wb.sheetnames:
            raise TemplyfierError(f"La feuille template ‘{requested}’ est introuvable.")
        return reference_wb[requested]
    for preferred in ("TOTAL", "Total", "TOTAL SAMPLE", "Total Sample"):
        if preferred in reference_wb.sheetnames:
            return reference_wb[preferred]
    candidates = [
        ws for ws in reference_wb.worksheets
        if not any(word in ws.title.casefold() for word in EXCLUDED_SHEET_WORDS)
    ]
    if not candidates:
        raise TemplyfierError("Le fichier clean ne contient aucune feuille utilisable comme template.")
    return candidates[-1]


def _match_reference_raw(reference_sheet: Worksheet, raw_sheets: Sequence[Worksheet]) -> int:
    ref_layout = detect_layout(reference_sheet)
    ref_sig = _signature(reference_sheet, ref_layout)
    exact = []
    for index, sheet in enumerate(raw_sheets):
        layout = detect_layout(sheet)
        if _signature(sheet, layout) == ref_sig:
            exact.append(index)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return exact[0]

    # Fallback: score the first retained data rows against every raw export.
    best_index, best_score = 0, -1
    for index, raw_sheet in enumerate(raw_sheets):
        raw_layout = detect_layout(raw_sheet)
        raw_vectors = {
            _row_vector(raw_sheet, row, raw_layout.product_cols)
            for row in range(raw_layout.header_row + 1, raw_sheet.max_row + 1)
        }
        score = sum(
            1
            for row in range(ref_layout.header_row + 1, reference_sheet.max_row + 1)
            if _row_vector(reference_sheet, row, ref_layout.product_cols) in raw_vectors
        )
        if score > best_score:
            best_index, best_score = index, score
    if best_score <= 0:
        raise TemplyfierError("Impossible d’identifier l’export correspondant à la feuille template.")
    return best_index


def _learn_row_map(reference_sheet: Worksheet, raw_sheet: Worksheet) -> dict[int, int]:
    ref_layout, raw_layout = detect_layout(reference_sheet), detect_layout(raw_sheet)
    if len(ref_layout.product_cols) != len(raw_layout.product_cols):
        raise TemplyfierError(
            "Le template et les exports n’ont pas le même nombre de produits "
            f"({len(ref_layout.product_cols)} vs {len(raw_layout.product_cols)})."
        )

    by_vector: dict[tuple, list[int]] = {}
    for row in range(raw_layout.header_row + 1, raw_sheet.max_row + 1):
        vector = _row_vector(raw_sheet, row, raw_layout.product_cols)
        if _has_data(vector):
            by_vector.setdefault(vector, []).append(row)

    row_map: dict[int, int] = {}
    used: set[int] = set()
    unmatched: list[int] = []
    previous_raw_row = 0
    for ref_row in range(ref_layout.header_row + 1, reference_sheet.max_row + 1):
        vector = _row_vector(reference_sheet, ref_row, ref_layout.product_cols)
        if not _has_data(vector):
            continue
        candidates = [row for row in by_vector.get(vector, []) if row not in used]
        if not candidates:
            unmatched.append(ref_row)
            continue
        ref_metric = _text(reference_sheet.cell(ref_row, ref_layout.metric_col).value).casefold()
        metric_matches = [
            row for row in candidates
            if _text(raw_sheet.cell(row, raw_layout.metric_col).value).casefold() == ref_metric
        ]
        pool = metric_matches or candidates
        after = [row for row in pool if row > previous_raw_row]
        chosen = min(after or pool)
        row_map[ref_row] = chosen
        used.add(chosen)
        previous_raw_row = chosen

    if unmatched:
        preview = ", ".join(map(str, unmatched[:8]))
        raise TemplyfierError(
            f"{len(unmatched)} ligne(s) du template n’ont pas été retrouvées dans l’export "
            f"de référence (lignes {preview}). Vérifie que le clean et les DataViz viennent du même test."
        )
    return row_map


def _reference_split_lookup(reference_wb) -> dict[tuple[int | None, ...], list[str]]:
    lookup: dict[tuple[int | None, ...], list[str]] = {}
    for sheet in reference_wb.worksheets:
        if any(word in sheet.title.casefold() for word in EXCLUDED_SHEET_WORDS):
            continue
        try:
            layout = detect_layout(sheet)
        except TemplyfierError:
            continue
        lookup.setdefault(_signature(sheet, layout), []).append(sheet.title)
    return lookup


def _default_split_name(filename: str) -> str:
    stem = Path(filename).stem
    stamp = re.search(r"(\d{2})_(\d{2})_(\d{2})$", stem)
    return f"Split {stamp.group(1)}-{stamp.group(2)}-{stamp.group(3)}" if stamp else stem[:31]


def inspect_package(reference, raw_files: Sequence[tuple[str, object]], reference_sheet: str | None = None):
    reference_wb = _workbook(reference)
    ref_sheet = _pick_reference_sheet(reference_wb, reference_sheet)
    lookup = _reference_split_lookup(reference_wb)
    infos: list[InputInfo] = []
    used_names: set[str] = set()
    for filename, source in raw_files:
        wb = _workbook(source)
        sheet = detect_data_sheet(wb)
        layout = detect_layout(sheet)
        signature = _signature(sheet, layout)
        candidates = lookup.get(signature, [])
        proposed = candidates.pop(0) if candidates else _default_split_name(filename)
        proposed = _safe_sheet_name(proposed, used_names)
        infos.append(InputInfo(filename, proposed, sheet.title, signature, _product_names(sheet, layout)))
    return ref_sheet.title, infos


def inspect_reference(reference, reference_sheet: str | None = None) -> ReferenceInfo:
    """Return user-facing facts inferred from the clean reference workbook."""
    workbook = _workbook(reference)
    sheet = _pick_reference_sheet(workbook, reference_sheet)
    layout = detect_layout(sheet)
    product_cols = list(layout.product_cols)
    benchmark_positions: list[int] = []
    for pos, product_col in enumerate(product_cols):
        next_col = product_cols[pos + 1] if pos + 1 < len(product_cols) else sheet.max_column + 1
        gap_count = sum(
            1
            for col in range(product_col + 1, next_col)
            if "gap" in _text(sheet.cell(layout.header_row, col).value).casefold()
            or "delta" in _text(sheet.cell(layout.header_row, col).value).casefold()
        )
        if gap_count == 0:
            benchmark_positions.append(pos)
    retained_rows = sum(
        1
        for row in range(layout.header_row + 1, sheet.max_row + 1)
        if _has_data(_row_vector(sheet, row, layout.product_cols))
    )
    return ReferenceInfo(
        sheet_name=sheet.title,
        product_names=_product_names(sheet, layout),
        benchmark_positions=tuple(benchmark_positions),
        retained_rows=retained_rows,
    )


def _source_significance_col(product_col: int, benchmark_offset: int) -> int:
    # Current G-Sight monadic structure: value, letters, colour-vs-benchmark(s).
    return product_col + 2 + benchmark_offset


def _copy_fill_font(source_cell, *target_cells):
    for target in target_cells:
        target.fill = copy(source_cell.fill)


def _populate_sheet(
    output_sheet: Worksheet,
    raw_sheet: Worksheet,
    row_map: dict[int, int],
    benchmark_positions: Sequence[int],
):
    out_layout, raw_layout = detect_layout(output_sheet), detect_layout(raw_sheet)
    if len(out_layout.product_cols) != len(raw_layout.product_cols):
        raise TemplyfierError(f"Nombre de produits incohérent pour le split ‘{output_sheet.title}’.")

    # Product title, base and letter headers.
    for out_col, raw_col in zip(out_layout.product_cols, raw_layout.product_cols):
        for out_row, raw_row in (
            (out_layout.product_name_row, raw_layout.product_name_row),
            (out_layout.sample_row, raw_layout.sample_row),
            (out_layout.header_row, raw_layout.header_row),
        ):
            output_sheet.cell(out_row, out_col).value = raw_sheet.cell(raw_row, raw_col).value

    product_cols = list(out_layout.product_cols)
    benchmark_cols = [product_cols[pos] for pos in benchmark_positions]
    gap_columns_by_product: dict[int, list[int]] = {}
    for pos, out_col in enumerate(product_cols):
        next_col = product_cols[pos + 1] if pos + 1 < len(product_cols) else output_sheet.max_column + 1
        gap_columns_by_product[pos] = [
            col for col in range(out_col + 1, next_col)
            if "gap" in _text(output_sheet.cell(out_layout.header_row, col).value).casefold()
            or "delta" in _text(output_sheet.cell(out_layout.header_row, col).value).casefold()
        ]
        if pos in benchmark_positions and gap_columns_by_product[pos]:
            raise TemplyfierError(
                "Le plan de benchmarks sélectionné ne correspond pas à la structure du template : "
                f"le produit {pos + 1} possède déjà une colonne Gap."
            )
        if pos not in benchmark_positions and len(gap_columns_by_product[pos]) < len(benchmark_cols):
            raise TemplyfierError(
                "Le template ne contient pas assez de colonnes Gap pour le nombre de benchmarks choisi."
            )

    for out_row, raw_row in row_map.items():
        metric = _text(output_sheet.cell(out_row, out_layout.metric_col).value).casefold()
        is_mean = "mean" in metric or "moyenne" in metric
        number_format = "0.00" if is_mean else "0%"

        for pos, (out_col, raw_col) in enumerate(zip(product_cols, raw_layout.product_cols)):
            target = output_sheet.cell(out_row, out_col)
            source = raw_sheet.cell(raw_row, raw_col)
            target.value = source.value
            target.number_format = number_format
            if pos in benchmark_positions:
                target.fill = copy(source.fill)

        # A template identifies its gap columns by their visible header.
        for pos, out_col in enumerate(product_cols):
            if pos in benchmark_positions:
                continue
            gap_cols = gap_columns_by_product[pos]
            for bench_offset, gap_col in enumerate(gap_cols[: len(benchmark_cols)]):
                benchmark_col = benchmark_cols[bench_offset]
                candidate_letter = output_sheet.cell(1, out_col).column_letter
                benchmark_letter = output_sheet.cell(1, benchmark_col).column_letter
                gap = output_sheet.cell(out_row, gap_col)
                gap.value = f"={candidate_letter}{out_row}-{benchmark_letter}{out_row}"
                gap.number_format = number_format
                source_sig_col = _source_significance_col(raw_layout.product_cols[pos], bench_offset)
                if source_sig_col <= raw_sheet.max_column:
                    sig_cell = raw_sheet.cell(raw_row, source_sig_col)
                    _copy_fill_font(sig_cell, output_sheet.cell(out_row, out_col), gap)

    output_sheet.freeze_panes = output_sheet.freeze_panes or f"C{out_layout.header_row + 1}"
    output_sheet.sheet_view.showGridLines = False


def build_toplines(
    reference,
    raw_files: Sequence[tuple[str, object]],
    *,
    split_names: Sequence[str] | None = None,
    reference_sheet: str | None = None,
    benchmark_positions: Sequence[int] = (0,),
    product_labels: Sequence[str] | None = None,
) -> tuple[bytes, dict]:
    if not raw_files:
        raise TemplyfierError("Ajoute au moins un export G-Sight.")

    reference_bytes = _read_bytes(reference)
    output_wb = load_workbook(BytesIO(reference_bytes), data_only=False)
    analysis_wb = load_workbook(BytesIO(reference_bytes), data_only=True)
    ref_sheet_formula = _pick_reference_sheet(output_wb, reference_sheet)
    ref_sheet_values = analysis_wb[ref_sheet_formula.title]
    reference_order = [
        ws.title for ws in output_wb.worksheets
        if not any(word in ws.title.casefold() for word in EXCLUDED_SHEET_WORDS)
    ]

    raw_workbooks = [_workbook(source, data_only=False) for _, source in raw_files]
    raw_data_sheets = [detect_data_sheet(wb) for wb in raw_workbooks]
    reference_raw_index = _match_reference_raw(ref_sheet_values, raw_data_sheets)
    raw_reference_values_wb = _workbook(raw_files[reference_raw_index][1], data_only=True)
    raw_reference_values = detect_data_sheet(raw_reference_values_wb)
    row_map = _learn_row_map(ref_sheet_values, raw_reference_values)

    _, inferred = inspect_package(reference_bytes, raw_files, ref_sheet_formula.title)
    requested_names = list(split_names) if split_names is not None else [info.split_name for info in inferred]
    if len(requested_names) != len(raw_files):
        raise TemplyfierError("Le nombre de noms de splits ne correspond pas au nombre d’exports.")

    benchmark_positions = tuple(int(pos) for pos in benchmark_positions)
    product_count = len(detect_layout(raw_data_sheets[0]).product_cols)
    if not benchmark_positions or any(pos < 0 or pos >= product_count for pos in benchmark_positions):
        raise TemplyfierError("Sélection de benchmark invalide.")
    if product_labels is not None and len(product_labels) != product_count:
        raise TemplyfierError("Le nombre de noms produits ne correspond pas au plan G-Sight.")

    # Keep the chosen template and the reference screener only; remove historical split tabs.
    template_title = ref_sheet_formula.title
    for sheet in list(output_wb.worksheets):
        if sheet.title == template_title or "screener" in sheet.title.casefold():
            continue
        output_wb.remove(sheet)

    used: set[str] = {s.title.casefold() for s in output_wb.worksheets if s.title != template_title}
    output_sheets: list[Worksheet] = []
    for index, (filename, _) in enumerate(raw_files):
        target = ref_sheet_formula if index == 0 else output_wb.copy_worksheet(ref_sheet_formula)
        target.title = _safe_sheet_name(requested_names[index], used)
        _populate_sheet(target, raw_data_sheets[index], row_map, benchmark_positions)
        if product_labels is not None:
            target_layout = detect_layout(target)
            for label, col in zip(product_labels, target_layout.product_cols):
                target.cell(target_layout.product_name_row, col).value = _text(label)
        output_sheets.append(target)

    # Reproduce the reference tab order; append genuinely new split names afterwards.
    order_index = {name.casefold(): index for index, name in enumerate(reference_order)}
    toplines = sorted(
        output_sheets,
        key=lambda ws: (order_index.get(ws.title.casefold(), len(order_index)), ws.title.casefold()),
    )
    screeners = [ws for ws in output_wb.worksheets if "screener" in ws.title.casefold()]
    output_wb._sheets = toplines + screeners
    output_wb.calculation.fullCalcOnLoad = True
    output_wb.calculation.forceFullCalc = True
    output_wb.calculation.calcMode = "auto"

    buffer = BytesIO()
    output_wb.save(buffer)
    report = {
        "reference_sheet": template_title,
        "reference_export": raw_files[reference_raw_index][0],
        "mapped_rows": len(row_map),
        "splits": [ws.title for ws in output_sheets],
        "products": product_count,
        "benchmarks": [pos + 1 for pos in benchmark_positions],
        "product_labels_updated": product_labels is not None,
    }
    return buffer.getvalue(), report
