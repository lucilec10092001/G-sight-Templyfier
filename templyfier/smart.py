from __future__ import annotations

from copy import copy
from collections import Counter
from dataclasses import asdict, dataclass, replace
from io import BytesIO
import json
from pathlib import Path
import re
import unicodedata
from typing import BinaryIO, Sequence
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .core import (
    TemplyfierError,
    _count_from_header,
    _default_split_name,
    _product_names,
    _read_bytes,
    _safe_sheet_name,
    _signature,
    _source_significance_col,
    _text,
    _workbook,
    detect_data_sheet,
    detect_layout,
)


STANDARD_METRICS = (
    "Mean",
    "Top Box",
    "Top 2 Boxes",
    "Top 3 Boxes",
    "Bottom Box",
    "Bottom 2 Boxes",
    "Bottom 3 Boxes",
)


def _excel_safe_value(value):
    """Remove characters that Excel XML cannot store, preserving all normal text.

    Some G-Sight workbooks contain escaped control characters such as U+001F.
    openpyxl decodes them on read but refuses to write them into a new workbook.
    All values copied from a source workbook must pass through this boundary.
    """
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def _validate_generated_xlsx(payload: bytes) -> None:
    """Refuse a download if its ZIP/XML package cannot be reopened cleanly."""
    try:
        with ZipFile(BytesIO(payload)) as archive:
            damaged = archive.testzip()
            if damaged:
                raise ValueError(f"damaged package member: {damaged}")
            for name in archive.namelist():
                if name.endswith((".xml", ".rels")):
                    ElementTree.fromstring(archive.read(name))
        workbook = load_workbook(BytesIO(payload), read_only=True, data_only=False)
        if not workbook.sheetnames:
            raise ValueError("workbook contains no worksheets")
        workbook.close()
    except (BadZipFile, OSError, ValueError, ElementTree.ParseError) as exc:
        raise TemplyfierError(
            "The generated Excel package failed its integrity check and was not offered for download. "
            "Please keep the source files and report this project to the Templyfier owner."
        ) from exc


@dataclass(frozen=True)
class QuestionProposal:
    keep: bool
    order: int
    section: str
    question_id: str
    mapped_kpi: str
    display_label: str
    question_type: str
    confidence: str
    first_row: int
    metrics: tuple[str, ...]
    metric_label: str = ""
    availability: tuple[str, ...] = ()
    suggested_splits: tuple[str, ...] = ()
    summary_keep: bool = False
    summary_label: str = ""
    metric_availability: tuple[tuple[str, tuple[str, ...]], ...] = ()
    stages: tuple[str, ...] = ()


@dataclass(frozen=True)
class SmartPackageInfo:
    reference_filename: str
    source_sheet: str
    product_names: tuple[str, ...]
    counts: tuple[int | None, ...]
    questions: tuple[QuestionProposal, ...]
    inputs: tuple["SmartInputInfo", ...]
    study_format: str
    stages: tuple[str, ...]
    embedded_splits: tuple[str, ...]
    warnings: tuple[str, ...]
    suggested_benchmark_count: int
    suggested_test_type: str


@dataclass(frozen=True)
class SmartInputInfo:
    filename: str
    split_name: str
    counts: tuple[int | None, ...]
    product_names: tuple[str, ...]
    source_sheet: str = ""
    role: str = "R�sultats"
    stage: str = ""
    embedded_split_count: int = 1
    comparison_codes: tuple[str, ...] = ()
    split_detection: str = "High confidence"
    product_keys: tuple[str, ...] = ()


def _paired_positions(
    product_count: int,
    source_key: str,
    filename: str,
    *,
    paired_mappings: dict[str, Sequence[Sequence[int]]] | None,
    paired_swaps: dict[str, Sequence[int]] | None,
) -> list[tuple[int, int]]:
    """Return validated zero-based Benchmark/Candidate positions for one source."""
    mappings = paired_mappings or {}
    raw_mapping = mappings.get(source_key)
    if raw_mapping is None and filename in mappings:
        raw_mapping = mappings[filename]
    if raw_mapping is None:
        if product_count < 2 or product_count % 2:
            raise TemplyfierError(
                "The automatic Paired plan needs an even number of active products. "
                "Open the optional pair mapping to define the products to compare or exclude."
            )
        pairs = [(position, position + 1) for position in range(0, product_count, 2)]
    else:
        pairs = []
        for pair_number, value in enumerate(raw_mapping, 1):
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise TemplyfierError(f"Pair {pair_number} has an invalid mapping.")
            benchmark, candidate = value
            if type(benchmark) is not int or type(candidate) is not int:
                raise TemplyfierError(f"Pair {pair_number} must use product positions.")
            if not (0 <= benchmark < product_count and 0 <= candidate < product_count):
                raise TemplyfierError(f"Pair {pair_number} refers to a product that is not active.")
            if benchmark == candidate:
                raise TemplyfierError(f"Pair {pair_number} uses the same product twice.")
            pairs.append((benchmark, candidate))
        if not pairs:
            raise TemplyfierError("Keep at least one Benchmark/Candidate pair for this split.")
    swaps = {
        int(value) for value in (paired_swaps or {}).get(
            source_key, (paired_swaps or {}).get(filename, ())
        )
    }
    return [
        (candidate, benchmark) if pair_number in swaps else (benchmark, candidate)
        for pair_number, (benchmark, candidate) in enumerate(pairs, 1)
    ]


def _occurrence_position_map(
    canonical_keys: Sequence[str], source_keys: Sequence[str]
) -> dict[int, int]:
    """Map repeated product codes by occurrence instead of collapsing to the first column."""
    if Counter(source_keys) != Counter(canonical_keys):
        raise TemplyfierError("Le plan produits n'est pas identique dans tous les exports.")
    positions: dict[str, list[int]] = {}
    for position, key in enumerate(source_keys):
        positions.setdefault(key, []).append(position)
    used: dict[str, int] = {}
    mapping: dict[int, int] = {}
    for canonical_position, key in enumerate(canonical_keys):
        occurrence = used.get(key, 0)
        mapping[canonical_position] = positions[key][occurrence]
        used[key] = occurrence + 1
    return mapping


def audit_input_plan(
    info: SmartPackageInfo,
    split_names: Sequence[str],
    benchmark_positions: Sequence[int],
    *,
    test_type: str,
    automatic_exports: bool,
    paired_mappings: dict[str, Sequence[Sequence[int]]] | None = None,
) -> dict:
    """Reconcile files, splits, benchmarks and product plans before export."""
    inputs = [item for item in info.inputs if item.role == "R�sultats"] or list(info.inputs)
    names = [_text(value) for value in split_names]
    blockers: list[str] = []
    warnings: list[str] = []
    rows: list[dict] = []
    if len(names) != len(inputs):
        blockers.append("Le nombre de noms de splits ne correspond pas au nombre d'exports de r�sultats.")
        names = [item.split_name for item in inputs]
    if not inputs:
        return {"rows": rows, "blockers": ["Aucun export de r�sultats d�tect�."], "warnings": [], "ready": False}

    for item in inputs:
        known_bases = [value for value in item.counts if isinstance(value, int)]
        if any(value <= 0 for value in known_bases):
            blockers.append(f"Base nulle d�tect�e dans {item.filename}.")
        positive_bases = [value for value in known_bases if value > 0]
        if not positive_bases:
            warnings.append(
                f"Aucune base chiffr�e n'a pu �tre lue dans {item.filename}; les scores restent utilisables."
            )
        elif len(positive_bases) > 1 and max(positive_bases) / min(positive_bases) > 1.25:
            warnings.append(
                f"Bases tr�s diff�rentes entre produits dans {item.filename} "
                f"({min(positive_bases)} � {max(positive_bases)}). V�rifie le filtre G-Sight."
            )

    canonical = inputs[0].product_keys
    paired = _normal(test_type).startswith("paired")
    for item in inputs:
        same_plan = (
            len(item.product_keys) == len(canonical)
            and (Counter(item.product_keys) == Counter(canonical) if automatic_exports and not paired else item.product_keys == canonical)
        )
        if not paired and not same_plan:
            blockers.append(f"Plan produits diff�rent dans {item.filename}.")

    if paired:
        for item, split in zip(inputs, names):
            source_key = f"{item.filename}::{item.source_sheet}"
            try:
                pairs = _paired_positions(
                    len(item.product_keys), source_key, item.filename,
                    paired_mappings=paired_mappings, paired_swaps=None,
                )
                valid = True
            except TemplyfierError as exc:
                pairs = []
                valid = False
                blockers.append(f"{split}: {exc}")
            rows.append({
                "Split": split,
                "Benchmark": f"{len(pairs)} internal pair(s)" if valid else "Pair mapping required",
                "Export": item.filename,
                "Produits": len(item.product_keys),
                "Contr�le": "Pr�t" if valid else "� corriger",
            })
    elif automatic_exports:
        benchmark_keys = [canonical[position] for position in benchmark_positions if 0 <= position < len(canonical)]
        if not benchmark_keys:
            blockers.append("Aucun benchmark valide n'a �t� identifi�.")
        split_order = list(dict.fromkeys(names))
        for split in split_order:
            indexes = [index for index, value in enumerate(names) if _normal(value) == _normal(split)]
            for benchmark_key in benchmark_keys:
                matches = [index for index in indexes if benchmark_key in inputs[index].comparison_codes]
                if len(matches) == 1:
                    status = "Pr�t"
                    export_name = inputs[matches[0]].filename
                elif not matches:
                    status = "Export manquant"
                    export_name = "-"
                    blockers.append(f"Export manquant : {split} vs {benchmark_key}.")
                else:
                    status = "Doublon"
                    export_name = " � ".join(inputs[index].filename for index in matches)
                    blockers.append(f"Plusieurs exports d�tect�s pour {split} vs {benchmark_key}.")
                rows.append({
                    "Split": split,
                    "Benchmark": benchmark_key,
                    "Export": export_name,
                    "Produits": len(canonical),
                    "Contr�le": status,
                })
        unused = [
            item.filename for item in inputs
            if not any(code in {canonical[position] for position in benchmark_positions if 0 <= position < len(canonical)}
                       for code in item.comparison_codes)
        ]
        if unused:
            warnings.append("Benchmark non rapproch� dans : " + " � ".join(unused))
    else:
        duplicate_names = {
            name for name in names
            if sum(_normal(other) == _normal(name) for other in names) > 1
        }
        if duplicate_names:
            blockers.append("Noms de splits en double : " + " � ".join(sorted(duplicate_names)))
        benchmark_keys = [canonical[position] for position in benchmark_positions if 0 <= position < len(canonical)]
        for item, split in zip(inputs, names):
            missing = [key for key in benchmark_keys if key not in item.comparison_codes]
            if missing:
                warnings.append(f"{split} : significativit� lue via les lettres G-Sight pour " + ", ".join(missing))
            rows.append({
                "Split": split,
                "Benchmark": " � ".join(benchmark_keys) or "-",
                "Export": item.filename,
                "Produits": len(item.product_keys),
                "Contr�le": "Pr�t",
            })
    return {
        "rows": rows,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "ready": not blockers,
    }


@dataclass(frozen=True)
class CmrProduct:
    cmr_code: str
    formula_code: str
    fantasy_name: str
    formula_description: str
    formula_type: str = ""
    fr_land_id: str = ""
    brand: str = ""
    line_variant: str = ""


@dataclass(frozen=True)
class CmrProductMatch:
    product_key: str
    source_name: str
    cmr_code: str = ""
    formula_code: str = ""
    formula_description: str = ""
    fantasy_name: str = ""
    formula_type: str = ""
    fr_land_id: str = ""
    suggested_label: str = ""
    matched_by: str = "Aucun rapprochement fiable"
    confidence: str = "-"
    score: int = 0


def cmr_product_label(match: CmrProductMatch, mode: str = "fantasy") -> str:
    """Return the CMI-selected CMR field, with safe fallbacks for missing cells."""
    mode = _text(mode).casefold()
    if mode == "source":
        return match.source_name
    if mode == "formula":
        return _text(match.formula_code) or _text(match.formula_description) or match.suggested_label or match.source_name
    if mode == "description":
        description = re.sub(r"\s+", " ", _text(match.formula_description).replace("\n", " ")).strip()
        return description or _text(match.formula_code) or match.suggested_label or match.source_name
    return match.suggested_label or _text(match.fantasy_name) or _text(match.formula_description) or match.source_name


def _cmr_header_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _normal(_text(value))).strip()


def _clean_fantasy_name(value: str) -> str:
    """Turn a verbose CMR fantasy-name cell into a concise, editable suggestion."""
    clean = re.sub(r"\s+", " ", _text(value).replace("\n", " ")).strip(" +")
    if not clean:
        return ""
    parts = [part.strip() for part in re.split(r"\s*\+\s*", clean) if part.strip()]
    preferred = next(
        (part for part in parts if not re.search(r"caps|encaps|planetcaps|techno", part, flags=re.I)),
        parts[0],
    )
    preferred = re.sub(r"\s*@\s*\d+(?:[.,]\d+)?\s*%?.*$", "", preferred).strip()
    preferred = re.sub(r"\s+EB\s*[-_.]?\s*\d+\s*$", "", preferred, flags=re.I).strip()
    return preferred or clean


def _cmr_benchmark_label(product: CmrProduct) -> str:
    parts = [product.brand, product.line_variant]
    clean_parts = []
    for part in parts:
        clean = re.sub(r"<\s*No Line\s*>\s*-?", "", _text(part), flags=re.I)
        clean = re.sub(r"\s+-\s+", " ", clean).strip(" -")
        if clean and _normal(clean) not in {_normal(item) for item in clean_parts}:
            clean_parts.append(clean)
    if clean_parts:
        return " ".join(clean_parts)
    description = _text(product.formula_description)
    description = re.sub(r"\s+-\s+(?:Fs\s+)?(?:Liquid|Powder).*$", "", description, flags=re.I)
    return description.strip(" -")


def parse_cmr_products(source) -> tuple[CmrProduct, ...]:
    """Read the candidate catalogue from a CMR request with flexible header locations."""
    workbook = _workbook(source, data_only=True)
    products = []
    aliases = {
        "cmr code": "cmr_code",
        "cmr codes": "cmr_code",
        "formula code": "formula_code",
        "fantasy name": "fantasy_name",
        "formula description": "formula_description",
        "formula type": "formula_type",
        "fr land id": "fr_land_id",
        "brand": "brand",
        "line variant": "line_variant",
    }
    for sheet in workbook.worksheets:
        header_row = None
        header_map = {}
        for row in range(1, min(sheet.max_row, 30) + 1):
            candidate = {}
            for col in range(1, sheet.max_column + 1):
                key = aliases.get(_cmr_header_key(sheet.cell(row, col).value))
                if key:
                    candidate[key] = col
            if "cmr_code" in candidate and ({"fantasy_name", "formula_description"} & set(candidate)):
                header_row, header_map = row, candidate
                break
        if header_row is None:
            continue
        for row in range(header_row + 1, sheet.max_row + 1):
            values = {
                field: _text(sheet.cell(row, col).value)
                for field, col in header_map.items()
            }
            if not any(values.get(field) for field in ("cmr_code", "formula_code", "fantasy_name", "formula_description")):
                continue
            products.append(CmrProduct(**{
                field: values.get(field, "")
                for field in CmrProduct.__dataclass_fields__
            }))
    if not products:
        raise TemplyfierError(
            "La CMR ne contient pas de tableau avec les colonnes CMR code et Fantasy name / Formula description."
        )
    # Some CMR exports repeat the same catalogue on several worksheets. Exact
    # duplicates are harmless; conflicting uses of one stable identifier are
    # ambiguous and must never be resolved by row order.
    unique = []
    fingerprints = set()
    identifiers: dict[tuple[str, str], tuple[tuple[str, ...], int]] = {}
    for product in products:
        fingerprint = tuple(_normal(getattr(product, field)) for field in CmrProduct.__dataclass_fields__)
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        # A CMR code identifies one row and must stay unambiguous. Secondary
        # formula/Fr-Land identifiers may legitimately be shared by several
        # row-level codes when the same benchmark is reused across pairs.
        for kind, raw_value in (("CMR code", product.cmr_code),):
            value = re.sub(r"[^a-z0-9]", "", _normal(raw_value))
            if not value:
                continue
            identity = (kind, value)
            previous = identifiers.get(identity)
            if previous and previous[0] != fingerprint:
                raise TemplyfierError(
                    f"CMR ambiguity: {kind} '{raw_value}' identifies more than one different product. "
                    "Correct the duplicate in the CMR export before generating toplines."
                )
            identifiers[identity] = (fingerprint, len(unique))
        unique.append(product)
    return tuple(unique)


def _cmr_match_score(product_key: str, source_name: str, product: CmrProduct) -> tuple[int, str]:
    key = re.sub(r"[^A-Z0-9]", "", _text(product_key).upper())
    source = _normal(source_name)
    compact_source = re.sub(r"[^a-z0-9]", "", source)
    cmr_code = re.sub(r"[^A-Z0-9]", "", product.cmr_code.upper())
    formula_code = re.sub(r"[^A-Z0-9]", "", product.formula_code.upper())
    if key and cmr_code and key == cmr_code:
        return 100, "Code CMR exact"
    # Product headers often combine the CMR code and another stable identifier,
    # for example "A26 356897". Match the code as a complete token so A2 cannot
    # accidentally match A26.
    if cmr_code and re.search(
        rf"(?<![A-Z0-9]){re.escape(cmr_code)}(?![A-Z0-9])",
        _text(source_name).upper(),
    ):
        return 99, "Code CMR exact dans le nom G-Sight"
    # Some Paired exports append a position suffix to the CMR code in the
    # G-Sight header (for example K1M1 for CMR row K1M). Accept only one
    # trailing digit and only when the unsuffixed code is otherwise exact.
    if (
        cmr_code
        and len(cmr_code) >= 3
        and re.search(
            rf"(?<![A-Z0-9]){re.escape(cmr_code)}\d(?![A-Z0-9])",
            _text(source_name).upper(),
        )
    ):
        return 97, "Code CMR avec suffixe de paire"
    if formula_code and formula_code.lower() in compact_source:
        return 98, "Formula code exact"
    fr_land_value = re.sub(r"\.0+$", "", _text(product.fr_land_id).strip())
    fr_land_digits = re.sub(r"\D", "", fr_land_value)
    if len(fr_land_digits) >= 4 and fr_land_digits in re.sub(r"\D", "", source_name):
        return 95, "Fr-Land ID exact"
    description_codes = {
        re.sub(r"[^A-Z0-9]", "", token)
        for token in re.findall(r"\b[A-Z][A-Z0-9-]{5,}\b", product.formula_description.upper())
    }
    # Ordinary description words such as FRANCE, MACHINE or REGULAR are not
    # stable identifiers. Only code-like alphanumeric tokens may identify a
    # product here; explicit Formula code matching is handled above.
    if any(
        code.lower() in compact_source
        for code in description_codes
        if len(code) >= 6 and any(character.isdigit() for character in code)
    ):
        return 94, "Code dans Formula description"
    description = _normal(product.formula_description)
    if description and (description in source or source in description):
        return 92, "Formula description"
    fantasy = _normal(_clean_fantasy_name(product.fantasy_name))
    fantasy_words = {word for word in fantasy.split() if len(word) >= 4}
    if fantasy_words:
        overlap = len(fantasy_words & set(source.split())) / len(fantasy_words)
        if overlap >= 0.75:
            return 84, "Fantasy name"
    brand_words = {
        word for word in _normal(f"{product.brand} {product.line_variant}").split()
        if len(word) >= 4 and word not in {"line", "variant"}
    }
    if brand_words:
        brand_overlap = len(brand_words & set(source.split())) / len(brand_words)
        if brand_overlap == 1:
            return 96, "Marque / variante benchmark exacte"
        if brand_overlap >= 0.6:
            return 80, "Marque / variante benchmark"
    return 0, "Aucun rapprochement fiable"


def _cmr_semantic_signature(product: CmrProduct) -> tuple[str, ...]:
    """Identify the represented product while ignoring its pair-specific CMR code."""
    return tuple(
        _normal(getattr(product, field))
        for field in (
            "formula_code", "fantasy_name", "formula_description", "formula_type",
            "fr_land_id", "brand", "line_variant",
        )
    )


def _cmr_tie_signature(
    product: CmrProduct,
    score: int,
    matched_by: str,
) -> tuple[str, ...]:
    """Group repeated CMR rows at the same level used to identify them."""
    if score == 96 and matched_by == "Marque / variante benchmark exacte":
        return (
            "benchmark_brand_variant",
            _normal(product.brand),
            _normal(product.line_variant),
            _normal(product.formula_type),
        )
    if score == 92 and matched_by == "Formula description":
        return (
            "formula_description",
            _normal(product.formula_description),
            _normal(product.formula_type),
        )
    return ("product",) + _cmr_semantic_signature(product)


def match_cmr_products(
    product_keys: Sequence[str],
    product_names: Sequence[str],
    cmr_source,
) -> tuple[CmrProductMatch, ...]:
    """Create one-to-one CMR suggestions, prioritising stable technical identifiers."""
    if len(product_keys) != len(product_names):
        raise TemplyfierError(
            "The G-Sight product plan is incomplete: product codes and product names do not have the same length."
        )
    catalog = parse_cmr_products(cmr_source)
    edges = []
    for product_index, (key, name) in enumerate(zip(product_keys, product_names)):
        for cmr_index, product in enumerate(catalog):
            score, matched_by = _cmr_match_score(key, name, product)
            if score:
                edges.append((score, product_index, cmr_index, matched_by))
    for product_index, source_name in enumerate(product_names):
        candidates = [edge for edge in edges if edge[1] == product_index]
        if not candidates:
            continue
        best_score = max(edge[0] for edge in candidates)
        best_indexes = {edge[2] for edge in candidates if edge[0] == best_score}
        represented_products = {
            _cmr_tie_signature(catalog[index], score, matched_by)
            for score, _, index, matched_by in candidates
            if score == best_score
        }
        # A reused benchmark may have one row-level CMR code per pair while all
        # stable product fields remain identical. That is repetition, not an
        # ambiguity. Still block ties between materially different products.
        if best_score >= 80 and len(represented_products) > 1:
            labels = [
                catalog[index].cmr_code or catalog[index].formula_code or catalog[index].fantasy_name
                for index in sorted(best_indexes)
            ]
            raise TemplyfierError(
                f"CMR ambiguity for G-Sight product '{source_name}': several CMR rows match with the same "
                f"confidence ({', '.join(labels)}). Correct the CMR identifiers before generating toplines."
            )
    assigned_products = {}
    cmr_owner: dict[int, tuple[tuple[str, str], int]] = {}
    for score, product_index, cmr_index, matched_by in sorted(edges, reverse=True):
        if product_index in assigned_products:
            continue
        key = re.sub(r"[^a-z0-9]", "", _normal(product_keys[product_index]))
        source = _normal(product_names[product_index])
        signature = ("key", key) if key else ("name", source)
        owner = cmr_owner.get(cmr_index)
        owner_signature = owner[0] if owner else None
        owner_score = owner[1] if owner else 0
        if owner_signature is not None and owner_signature != signature:
            # One physical CMR row may legitimately represent two positions in
            # a Paired plan when the same fragrance is tested twice. Require
            # independent medium-or-better evidence for both positions.
            if min(owner_score, score) < 80:
                continue
        if owner_signature == signature:
            has_unused_equivalent = any(
                other_score == score
                and other_product_index == product_index
                and other_cmr_index not in cmr_owner
                and _cmr_tie_signature(catalog[other_cmr_index], other_score, _)
                == _cmr_tie_signature(catalog[cmr_index], score, matched_by)
                for other_score, other_product_index, other_cmr_index, _ in edges
            )
            if has_unused_equivalent:
                continue
        assigned_products[product_index] = (catalog[cmr_index], score, matched_by)
        cmr_owner[cmr_index] = (signature, max(owner_score, score))

    matches = []
    for product_index, (key, name) in enumerate(zip(product_keys, product_names)):
        assignment = assigned_products.get(product_index)
        if not assignment:
            matches.append(CmrProductMatch(product_key=key, source_name=name))
            continue
        product, score, matched_by = assignment
        suggestion = _clean_fantasy_name(product.fantasy_name) or _cmr_benchmark_label(product)
        confidence = "�lev�e" if score >= 95 else "Moyenne" if score >= 80 else "Faible"
        matches.append(CmrProductMatch(
            product_key=key,
            source_name=name,
            cmr_code=product.cmr_code,
            formula_code=product.formula_code,
            formula_description=product.formula_description,
            fantasy_name=product.fantasy_name,
            formula_type=product.formula_type,
            fr_land_id=product.fr_land_id,
            suggested_label=suggestion,
            matched_by=matched_by,
            confidence=confidence,
            score=score,
        ))
    return tuple(matches)


def cmr_benchmark_positions(matches: Sequence[CmrProductMatch]) -> tuple[int, ...]:
    """Return reliable benchmark positions declared explicitly by the CMR."""
    benchmark_words = re.compile(
        r"\b(?:benchmark|bench\s*mark|bm|control|reference|market\s+product|"
        r"current\s+product|competitor|temoin|reference\s+marche)\b"
    )
    return tuple(
        index
        for index, match in enumerate(matches)
        if match.score >= 80 and benchmark_words.search(_ncreeners: bool,
    mean_decimals: int,
    paired_swaps: dict[str, Sequence[int]] | None,
    paired_mappings: dict[str, Sequence[Sequence[int]]] | None,
    include_deltas: bool,
    include_sections: bool,
    summary_scope: str,
    summary_metric_strategy: str,
    include_summary_details: bool,
    gap_positive_points: float | None,
    gap_negative_points: float | None,
) -> tuple[bytes, dict]:
    virtual_sources = []
    for filename, source in raw_files:
        workbook = _workbook(source)
        embedded_sheets = _embedded_data_sheets(workbook)
        source_sheets = (
            embedded_sheets
            if _embedded_sheets_are_consumer_splits(filename, embedded_sheets)
            else (detect_data_sheet(workbook),)
        )
        for source_sheet in source_sheets:
            virtual_sources.append((
                filename,
                f"{filename}::{source_sheet.title}",
                workbook,
                source_sheet,
            ))
    workbooks = [item[2] for item in virtual_sources]
    data_sheets = [item[3] for item in virtual_sources]
    layouts = [_active_layout(sheet, detect_layout(sheet)) for sheet in data_sheets]
    if len(split_names) != len(virtual_sources):
        raise TemplyfierError("Le nombre de noms de splits est incorrect.")
    product_keys = [_product_keys(sheet, layout) for sheet, layout in zip(data_sheets, layouts)]
    product_counts = [len(keys) for keys in product_keys]
    pair_plans = [
        _paired_positions(
            count, source_key, filename,
            paired_mappings=paired_mappings, paired_swaps=paired_swaps,
        )
        for (filename, source_key, _, _), count in zip(virtual_sources, product_counts)
    ]
    selected_questions = _selected_question_rows(question_rows)
    output_questions = (
        _questions_in_section_blocks(selected_questions) if include_sections else selected_questions
    )
    output = Workbook()
    output.remove(output.active)
    used_names: set[str] = set()
    written_data_rows = 0
    skipped_questions = 0
    question_omissions: list[dict] = []
    mean_format = _mean_number_format(mean_decimals)
    pairs_by_split: dict[str, int] = {}
    summary_records = []

    for file_index, ((filename, source_key, _, source_sheet), layout) in enumerate(
        zip(virtual_sources, layouts)
    ):
        sheet_name = _safe_sheet_name(split_names[file_index], used_names)
        target = output.create_sheet(sheet_name)
        pairs = pair_plans[file_index]
        blocks = []
        current_col = 3
        for pair_number, (benchmark_pos, candidate_pos) in enumerate(pairs, 1):
            blocks.append({
                "benchmark_pos": benchmark_pos,
                "candidate_pos": candidate_pos,
                "benchmark": current_col,
                "candidate": current_col + 1,
                "delta": current_col + 2 if include_deltas else None,
                "spacer": current_col + (3 if include_deltas else 2),
            })
            current_col += 4 if include_deltas else 3
        # A narrow spacer separates two paired blocks, but the sheet should not
        # end with an empty technical column.
        max_col = current_col - 2
        pairs_by_split[sheet_name] = len(pairs)
        _style_sheet(target, max_col)
        for pair_number, block in enumerate(blocks, 1):
            for role, position in (("benchmark", block["benchmark_pos"]), ("candidate", block["candidate_pos"])):
                raw_col = layout.product_cols[position]
                out_col = block[role]
                target.cell(3, out_col).value = _excel_safe_value(source_sheet.cell(layout.product_name_row, raw_col).value)
                target.cell(4, out_col).value = _excel_safe_value(source_sheet.cell(layout.sample_row, raw_col).value)
                target.cell(5, out_col).value = _excel_safe_value(source_sheet.cell(layout.product_header_row, raw_col).value)
            if block["delta"] is not None:
                target.cell(3, block["delta"]).value = f"Paire {pair_number}"
                target.cell(5, block["delta"]).value = "Delta Candidat - Benchmark"
            if pair_number < len(blocks):
                target.column_dimensions[get_column_letter(block["spacer"])].width = 3

        output_row = 6
        current_section = None
        previous_variable_label = None
        summary_question_rows: dict[str, list[tuple[int, str]]] = {}
        for config in output_questions:
            if not _question_applies_to_split(config, split_names[file_index]):
                continue
            expected_in_source = _question_expected_in_source(
                config, split_names[file_index], source_sheet
            )
            question_id = _text(config.get("Question ID"))
            question_type = _text(config.get("Type"))
            question_metrics = _standard_metrics_for_question(config, standard_metrics)
            source_rows = configured_source_rows(source_sheet, layout, config, standard_metrics)
            if not source_rows:
                skipped_questions += 1
                if expected_in_source:
                    question_omissions.append({
                        "question_id": question_id,
                        "label": _text(config.get("Display label")) or question_id,
                        "sheet": sheet_name,
                    })
                continue
            missing_metrics = _missing_selected_metrics(config, source_sheet, layout, source_rows)
            if missing_metrics:
                question_omissions.append({
                    "question_id": question_id,
                    "label": _text(config.get("Display label")) or question_id,
                    "sheet": sheet_name,
                    "missing_metrics": missing_metrics,
                })
                continue
            section = _text(config.get("Section"))
            section_changed = section != current_section
            if include_sections and section_changed:
                current_section = section
                previous_variable_label = None
            if include_sections and section and section_changed:
                target.cell(output_row, 1).value = section
                target.merge_cells(start_row=output_row, start_column=1, end_row=output_row, end_column=max_col)
                cell = target.cell(output_row, 1)
                cell.fill = PatternFill("solid", fgColor="D9D3EA")
                cell.font = Font(bold=True, color="2F2952")
                output_row += 1

            for metric_index, source_row in enumerate(source_rows):
                source_metric = _text(source_sheet.cell(source_row, layout.metric_col).value)
                display_label = _text(config.get("Display label"))
                metric_label = _text(config.get("Metric label"))
                if metric_label and len(source_rows) == 1:
                    group_identity = (_text(config.get("Group ID")) or display_label, section, display_label)
                    target.cell(output_row, 1).value = display_label if group_identity != previous_variable_label else None
                    target.cell(output_row, 2).value = (
                        grouped_metric_label(config, source_metric, len(source_rows))
                    )
                    previous_variable_label = group_identity
                elif question_type in {"Attribute", "CATA"} and not metric_label:
                    target.cell(output_row, 2).value = (display_label if len(source_rows) == 1 else f"{display_label} � {clean_metric_label(config, source_metric)}")
                    previous_variable_label = None
                else:
                    variable_label = metric_label or display_label
                    target.cell(output_row, 1).value = variable_label if metric_index == 0 else None
                    target.cell(output_row, 2).value = clean_metric_label(config, source_metric)
                    previous_variable_label = None
                number_format = mean_format if _metric_key(source_metric) == "mean" else "0%"
                for block in blocks:
                    bench_raw_col = layout.product_cols[block["benchmark_pos"]]
                    cand_raw_col = layout.product_cols[block["candidate_pos"]]
                    target.cell(output_row, block["benchmark"]).value = _excel_safe_value(source_sheet.cell(source_row, bench_raw_col).value)
                    target.cell(output_row, block["candidate"]).value = _excel_safe_value(source_sheet.cell(source_row, cand_raw_col).value)
                    bench_letter = get_column_letter(block["benchmark"])
                    cand_letter = get_column_letter(block["candidate"])
                    if block["delta"] is not None:
                        target.cell(output_row, block["delta"]).value = _safe_difference_formula(
                            f"{cand_letter}{output_row}", f"{bench_letter}{output_row}",
                            scale=1 if _metric_key(source_metric) == "mean" else 100,
                        )
                    value_columns = [block["benchmark"], block["candidate"]]
                    if block["delta"] is not None:
                        value_columns.append(block["delta"])
                    for col in value_columns:
                        target.cell(output_row, col).number_format = number_format
                        target.cell(output_row, col).alignment = Alignment(horizontal="right")
                    if block["delta"] is not None:
                        _style_difference_cell(
                            target,
                            target.cell(output_row, block["delta"]),
                            is_mean=_metric_key(source_metric) == "mean",
                            mean_format=mean_format,
                            positive_points=gap_positive_points,
                            negative_points=gap_negative_points,
                            candidate_value=source_sheet.cell(source_row, cand_raw_col).value,
                            benchmark_value=source_sheet.cell(source_row, bench_raw_col).value,
                        )
                    fill = _benchmark_fill(
                        workbooks[file_index],
                        source_sheet,
                        layout,
                        source_row,
                        cand_raw_col,
                        block["benchmark_pos"],
                        product_keys[file_index],
                        (),
                        direct_value_fill=True,
                    )
                    if fill is not None:
                        target.cell(output_row, block["candidate"]).fill = fill
                _format_variable_label(target, output_row)
                summary_question_rows.setdefault(question_id.casefold(), []).append((output_row, source_metric))
                output_row += 1
                written_data_rows += 1
        target.auto_filter.ref = f"A5:{get_column_letter(max_col)}{output_row - 1}"
        fake_blocks = {
            pair_index: {
                "value": block["candidate"],
                "benchmark": block["benchmark"],
                "gaps": [],
                "spacer": None,
            }
            for pair_index, block in enumerate(blocks)
        }
        paired_product_names = {}
        for pair_index, block in enumerate(blocks):
            candidate_name = _text(target.cell(3, block["candidate"]).value)
            benchmark_name = _text(target.cell(3, block["benchmark"]).value)
            paired_product_names[pair_index] = f"{candidate_name}\nvs. {benchmark_name}"
        summary_records.append({
            "target": target,
            "split": split_names[file_index],
            "active_benchmarks": (-1,),
            "benchmark_labels": {-1: "Paired benchmarks"},
            "product_order": tuple(range(len(blocks))),
            "column_blocks": fake_blocks,
            "question_rows": summary_question_rows,
            "source_workbook": workbooks[file_index],
            "product_names": paired_product_names,
        })

    _raise_for_question_omissions(question_omissions)
    _raise_for_unwritten_selected_questions(question_rows, summary_records)
    _raise_for_empty_topline_sheets(summary_records)
    total_index = max(range(len(data_sheets)), key=lambda i: sum(count or 0 for count in _signature(data_sheets[i], layouts[i])))
    summary_sheet_names, summary_detail_sheet = _create_paired_summary(
        output,
        used_names,
        summary_records,
        question_rows,
        summary_scope,
        split_names[total_index],
        summary_metric_strategy,
        include_summary_details,
    )
    if include_screeners:
        screener = next((sheet for sheet in workbooks[total_index].worksheets if "screener" in sheet.title.casefold()), None)
        if screener is not None:
            _copy_sheet(screener, output.create_sheet("Screeners"))
    output.calculation.fullCalcOnLoad = True
    output.calculation.forceFullCalc = True
    output.calculation.calcMode = "auto"
    buffer = BytesIO()
    from .english_output import finalize
    finalize(output, include_deltas)
    output.save(buffer)
    _validate_generated_xlsx(buffer.getvalue())
    scanned = sum(_source_metric_row_count(sheet, layout) for sheet, layout in zip(data_sheets, layouts))
    return buffer.getvalue(), {
        "mode": "Nouveau projet intelligent",
        "test_type": "Paired",
        "splits": list(split_names),
        "questions": len(selected_questions),
        "questions_deleted": sum(not bool(row.get("Keep")) or row.get("Type") == "Delete" for row in question_rows),
        "data_rows_written": written_data_rows,
        "source_metric_rows_scanned": scanned,
        "metric_rows_filtered": max(0, scanned - written_data_rows),
        "technical_columns_ignored": sum(max(0, sheet.max_column - 2 - len(layout.product_cols)) for sheet, layout in zip(data_sheets, layouts)),
        "products": max(product_counts),
        "products_by_split": dict(zip(split_names, product_counts)),
        "pairs": max((len(plan) for plan in pair_plans), default=0),
        "pairs_by_split": pairs_by_split,
        "benchmarks": "mapped per pair" if paired_mappings else "first product in each adjacent pair",
        "paired_swaps": {name: list(values) for name, values in (paired_swaps or {}).items()},
        "paired_mappings": {
            name: [list(pair) for pair in values]
            for name, values in (paired_mappings or {}).items()
        },
        "include_deltas": bool(include_deltas),
        "include_sections": bool(include_sections),
        "summary_scope": _normal(summary_scope) or "none",
        "summary_sheets": summary_sheet_names,
        "summary_detail_sheet": summary_detail_sheet,
        "summary_metric_strategy": summary_metric_strategy,
        "summary_kpis": len(_selected_summary_questions(question_rows)),
        "mean_decimals": int(mean_decimals),
        "gap_positive_points": gap_positive_points,
        "gap_negative_points": gap_negative_points,
        "reference_export": virtual_sources[total_index][0],
        "skipped_stage_questions": skipped_questions,
    }


def _legend_significance_fill(source_workbook, positive: bool, confidence_row: int):
    legend = next((sheet for sheet in source_workbook.worksheets if "legend" in sheet.title.casefold()), None)
    if legend is None:
        colours = {
            (True, 4): "00FF00",
            (False, 4): "FF0000",
            (True, 5): "CCFFCC",
            (False, 5): "FF9A00",
        }
        return PatternFill("solid", fgColor=colours[(positive, confidence_row)])
    return copy(legend.cell(confidence_row, 2 if positive else 3).fill)


def _benchmark_fill(
    source_workbook,
    source_sheet,
    layout,
    source_row: int,
    candidate_raw_col: int,
    benchmark_position: int,
    product_keys: Sequence[str],
    comparison_codes: Sequence[str],
    direct_value_fill: bool = False,
):
    """Return the significance fill for one candidate-vs-benchmark comparison.

    Preserve the colours of the selected G-Sight analysis sheet (normally
    2_TAILED). Never substitute the palette from the DELTA sheet: those colours
    describe gap thresholds, not the selected statistical-significance view.
    For an additional benchmark without a dedicated colour column, interpret
    G-Sight's case-sensitive comparison letters and use the matching legend.
    """
    if direct_value_fill:
        source_fill = source_sheet.cell(source_row, candidate_raw_col).fill
        if _is_significance_fill(source_workbook, source_sheet, source_fill):
            return copy(source_fill)

    benchmark_key = product_keys[benchmark_position]
    if benchmark_key in comparison_codes:
        source_sig_col = _source_significance_col(candidate_raw_col, comparison_codes.index(benchmark_key))
        if source_sig_col <= source_sheet.max_column and source_row <= source_sheet.max_row:
            source_fill = source_sheet.cell(source_row, source_sig_col).fill
            if _is_significance_fill(source_workbook, source_sheet, source_fill):
                return copy(source_fill)
            # The selected G-Sight sheet explicitly says this comparison is not
            # significant. Do not override it with letters or DELTA thresholds.
            return None

    benchmark_raw_col = layout.product_cols[benchmark_position]
    benchmark_code = _text(source_sheet.cell(layout.product_header_row, benchmark_raw_col).value)
    candidate_code = _text(source_sheet.cell(layout.product_header_row, candidate_raw_col).value)
    candidate_letters = _text(source_sheet.cell(source_row, candidate_raw_col + 1).value)
    benchmark_letters = _text(source_sheet.cell(source_row, benchmark_raw_col + 1).value)
    exact = bool(benchmark_code and benchmark_code in candidate_letters)
    lower = bool(benchmark_code and benchmark_code.casefold() in candidate_letters.casefold())
    if not lower:
        # G-Sight stores each pair once. When the benchmark appears after the
        # candidate, the comparison letter is attached to the benchmark cell.
        exact = bool(candidate_code and candidate_code in benchmark_letters)
        lower = bool(candidate_code and candidate_code.casefold() in benchmark_letters.casefold())
    if not exact and not lower:
        return None
    candidate_value = source_sheet.cell(source_row, candidate_raw_col).value
    benchmark_value = source_sheet.cell(source_row, benchmark_raw_col).value
    if not isinstance(candidate_value, (int, float)) or not isinstance(benchmark_value, (int, float)):
        return None
    # G-Sight uses uppercase comparison letters for 95% and lowercase for 90%.
    confidence_row = 4 if exact else 5
    return _legend_significance_fill(source_workbook, candidate_value > benchmark_value, confidence_row)


def _fill_key(fill) -> tuple:
    colour = fill.fgColor
    return (
        fill.patternType,
        colour.type,
        colour.rgb,
        colour.indexed,
        colour.theme,
        colour.tint,
    )


def _is_significance_fill(source_workbook, source_sheet, fill) -> bool:
    """True only for colours belonging to the selected G-Sight analysis."""
    if fill is None or not fill.patternType:
        return False
    legend = next((sheet for sheet in source_workbook.worksheets if "legend" in sheet.title.casefold()), None)
    title = _normal(source_sheet.title)
    if "1 tailed" in title:
        legend_rows = (9,)
    elif "delta" in title:
        legend_rows = (13, 14)
    else:
        legend_rows = (3, 4, 5)
    if legend is not None:
        return any(
            legend.cell(row, col).fill.patternType
            and _fill_key(fill) == _fill_key(legend.cell(row, col).fill)
            for row in legend_rows
            for col in (2, 3)
        )
    rgb = (fill.fgColor.rgb or "").upper()[-6:]
    palettes = {
        "1_tailed": {"21A625", "A62521"},
        "delta": {"21A625", "A62521", "4BCB4F", "EB3933"},
        "2_tailed": {"008000", "800000", "00FF00", "FF0000", "CCFFCC", "FF9A00"},
    }
    palette = palettes["1_tailed" if "1 tailed" in title else "delta" if "delta" in title else "2_tailed"]
    return rgb in palette


def _summary_confidence(source_workbook, fill) -> int | None:
    """Return the significance confidence without inferring win/loss direction.

    G-Sight can use either the 2-tailed colours (legend rows 3-5) or the
    dedicated DELTA colours (rows 13-14). The colour tells us whether the
    difference is significant and at which level; the candidate and benchmark
    values themselves must decide whether the KPI is a win or a loss.
    """
    if fill is None or not fill.patternType:
        return None
    legend = next((sheet for sheet in source_workbook.worksheets if "legend" in sheet.title.casefold()), None)
    if legend is not None:
        # 99% and 95% both use the solid 95% summary arrow. DELTA exposes
        # equivalent p-value thresholds at 5% and 10% on rows 14 and 13.
        for confidence, rows in ((95, (3, 4, 14)), (90, (5, 13))):
            for row in rows:
                for col in (2, 3):
                    legend_fill = legend.cell(row, col).fill
                    if legend_fill.patternType and _fill_key(fill) == _fill_key(legend_fill):
                        return confidence
    rgb = (fill.fgColor.rgb or "").upper()[-6:]
    return {
        "008000": 95,
        "800000": 95,
        "00FF00": 95,
        "FF0000": 95,
        "4BCB4F": 95,
        "EB3933": 95,
        "97E39C": 95,
        "F5B7AD": 95,
        "CCFFCC": 90,
        "FF9A00": 90,
        "FF9900": 90,
        "21A625": 90,
        "A62521": 90,
        "C7F0CC": 90,
        "FADBD4": 90,
    }.get(rgb)


def _summary_higher_is_better(metric: str, config: dict | None = None) -> bool | None:
    """Return the favourable direction after applying the CMI scale rule."""
    key = _normal(metric)
    mode = _normal((config or {}).get("Sens favorable", "Automatique"))
    if mode in {"neutre", "neutral", "aucun"}:
        return None
    is_pole = any(value in key for value in ("too weak", "too strong", "trop faible", "trop fort"))
    is_jar = "just" in key or "ideal" in key or "parfait" in key or bool(re.match(r"^3\s", key))
    if mode in {"ideal au centre", "centre", "center", "ideal"}:
        if is_jar:
            return True
        if is_pole:
            return False
        return None
    higher = not (
        "bottom" in key
        or is_pole
    )
    if mode in {"plus bas", "lower", "low"}:
        return not higher
    return higher


def _summary_signal_from_values(
    source_workbook,
    fill,
    metric: str,
    candidate_value,
    benchmark_value,
    config: dict | None = None,
) -> str | None:
    confidence = _summary_confidence(source_workbook, fill)
    if confidence is None:
        return None
    if (
        not isinstance(candidate_value, (int, float))
        or isinstance(candidate_value, bool)
        or not isinstance(benchmark_value, (int, float))
        or isinstance(benchmark_value, bool)
        or candidate_value == benchmark_value
    ):
        return None
    higher_is_better = _summary_higher_is_better(metric, config)
    if higher_is_better is None:
        return None
    favourable = candidate_value > benchmark_value
    if not higher_is_better:
        favourable = not favourable
    if favourable:
        return "" if confidence == 95 else "?"
    return "" if confidence == 95 else "?"


def _summary_metric_rank(metric: str) -> int:
    key = _metric_key(metric)
    if key == "mean":
        return 0
    if key == "top_2":
        return 1
    if key == "top_1":
        return 2
    if "just" in key or re.match(r"^3\s", _normal(metric)):
        return 2
    if key == "bottom_2":
        return 3
    return 4


def _pick_summary_signal(signals: Sequence[tuple[str, str]]) -> str:
    if not signals:
        return "="
    ordered = sorted(signals, key=lambda item: (_summary_metric_rank(item[0]), item[1] in {"?", "?"}))
    directions = {"up" if symbol in {"", "?"} else "down" for _, symbol in ordered}
    if len(directions) > 1:
        # Conflicting metrics: use the most decision-relevant retained metric
        # (Mean, then T2B, Top Box, JAR/B2B) instead of overstating consensus.
        return ordered[0][1]
    solid = next((symbol for _, symbol in ordered if symbol in {"", ""}), None)
    return solid or ordered[0][1]


def _pick_summary_decision(entries: Sequence[dict], strategy: str) -> dict:
    """Choose one transparent summary decision from all retained metrics."""
    ordered_all = sorted(entries, key=lambda item: _summary_metric_rank(item["metric"]))
    if ordered_all and not any(item.get("direction_defined", True) for item in ordered_all):
        return {"symbol": "-", "chosen": ordered_all[0], "conflict": False,
                "reason": "Aucun sens favorable n'est d�fini pour cette question"}
    significant = [item for item in ordered_all if item.get("signal")]
    normalized_strategy = _normal(strategy).replace(" ", "_")
    if normalized_strategy in {"primary", "primary_metric", "metric_principale"}:
        chosen = ordered_all[0] if ordered_all else None
        return {
            "symbol": chosen.get("signal") if chosen and chosen.get("signal") else "=",
            "chosen": chosen,
            "conflict": False,
            "reason": "M�trique principale uniquement",
        }
    if not significant:
        return {"symbol": "=", "chosen": ordered_all[0] if ordered_all else None, "conflict": False,
                "reason": "Aucune diff�rence significative sur les m�triques retenues"}
    directions = {"win" if item["signal"] in {"", "?"} else "loss" for item in significant}
    if normalized_strategy in {"consensus", "accord"} and len(directions) > 1:
        return {"symbol": "�", "chosen": None, "conflict": True,
                "reason": "Les m�triques significatives donnent des directions oppos�es"}
    if len(directions) > 1:
        chosen = significant[0]
        return {"symbol": chosen["signal"], "chosen": chosen, "conflict": True,
                "reason": f"R�sultats partag�s - priorit� donn�e � {chosen['metric']}"}
    solid = next((item for item in significant if item["signal"] in {"", ""}), None)
    chosen = solid or significant[0]
    return {"symbol": chosen["signal"], "chosen": chosen, "conflict": False,
            "reason": f"R�sultat significatif retenu sur {chosen['metric']}"}


def _selected_summary_questions(question_rows: Sequence[dict]) -> list[dict]:
    selected = [
        row for row in question_rows
        if bool(row.get("Keep"))
        and row.get("Type") != "Delete"
        and bool(row.get("KPI Summary"))
    ]
    selected.sort(key=lambda row: (int(row.get("Order", 9999)), _text(row.get("Question ID"))))
    return selected


def _summary_product_name(record: dict, position: int) -> str:
    if position in record.get("product_names", {}):
        return record["product_names"][position]
    target = record["target"]
    value_col = record["column_blocks"][position]["value"]
    name = _text(target.cell(3, value_col).value) or f"Product {position + 1}"
    subtitle = _text(target.cell(5, value_col).value)
    return f"{name}\n{subtitle}" if subtitle else name


def _write_summary_block(
    sheet,
    start_row: int,
    record: dict,
    benchmark_position: int,
    kpis: Sequence[dict],
    summary_metric_strategy: str,
    detail_rows: list[dict],
) -> int:
    max_col = 1 + len(kpis)
    title_fill = PatternFill("solid", fgColor="4F8ED8")
    subtitle_fill = PatternFill("solid", fgColor="E7E7E7")
    header_fill = PatternFill("solid", fgColor="000000")
    neutral_fill = PatternFill("solid", fgColor="EFEFEF")
    fills = {
        "": PatternFill("solid", fgColor="97E39C"),
        "?": PatternFill("solid", fgColor="C7F0CC"),
        "": PatternFill("solid", fgColor="F5B7AD"),
        "?": PatternFill("solid", fgColor="FADBD4"),
        "�": PatternFill("solid", fgColor="FFF2CC"),
        "-": neutral_fill,
        "=": neutral_fill,
    }
    fonts = {
        "": Font(color="008A16", bold=True, size=14),
        "?": Font(color="008A16", bold=True, size=14),
        "": Font(color="C00000", bold=True, size=14),
        "?": Font(color="C00000", bold=True, size=14),
        "�": Font(color="9C6500", bold=True, size=14),
        "-": Font(color="7A7A7A", bold=True, size=12),
        "=": Font(color="7A7A7A", bold=True, size=12),
    }
    thin = Side(style="thin", color="C9C9C9")

    benchmark_label = record["benchmark_labels"].get(benchmark_position, f"Benchmark {benchmark_position + 1}")
    sheet.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=max_col)
    title = sheet.cell(start_row, 1)
    title.value = _excel_safe_value(f"{record['split'].upper()} SAMPLE VS. {benchmark_label.upper()}")
    title.fill = title_fill
    title.font = Font(color="FFFFFF", bold=True, italic=True, size=15)
    title.alignment = Alignment(vertical="center")
    sheet.row_dimensions[start_row].height = 24

    product_positions = [position for position in record["product_order"] if position not in record["active_benchmarks"]]
    counts = []
    for position in product_positions:
        value_col = record["column_blocks"][position]["value"]
        count = _count_from_header(record["target"].cell(4, value_col).value)
        if count is not None:
            counts.append(count)
    base_note = ""
    if counts:
        base_note = f" | n~{min(counts)}" + (f"-{max(counts)}" if min(counts) != max(counts) else "") + " per product"
    sheet.merge_cells(start_row=start_row + 1, start_column=1, end_row=start_row + 1, end_column=max_col)
    subtitle = sheet.cell(start_row + 1, 1)
    retained_metric_labels = []
    for metric in STANDARD_METRICS:
        if any(bool(config.get(metric)) for config in kpis):
            retained_metric_labels.append(metric)
    metric_note = " / ".join(retained_metric_labels[:4]) or "selected metrics"
    subtitle.value = _excel_safe_value(
        f"Significant result across retained metrics ({metric_note})" + base_note
    )
    subtitle.fill = subtitle_fill
    subtitle.font = Font(color="666666", italic=True, size=10)
    subtitle.alignment = Alignment(vertical="center")

    header_row = start_row + 3
    headers = ["Product"] + [
        _text(config.get("Summary label")) or _summary_label(_text(config.get("Display label")))
        for config in kpis
    ]
    for col, value in enumerate(headers, 1):
        cell = sheet.cell(header_row, col)
        cell.value = _excel_safe_value(value)
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    sheet.row_dimensions[header_row].height = 48

    question_rows = record["question_rows"]
    active_benchmarks = list(record["active_benchmarks"])
    benchmark_offset = active_benchmarks.index(benchmark_position)
    for row_offset, position in enumerate(product_positions, 1):
        row = header_row + row_offset
        product_cell = sheet.cell(row, 1)
        product_cell.value = _excel_safe_value(_summary_product_name(record, position))
        product_cell.fill = PatternFill("solid", fgColor="FFFFFF")
        product_cell.font = Font(bold=True, size=9)
        product_cell.alignment = Alignment(vertical="center", wrap_text=True)
        product_cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        sheet.row_dimensions[row].height = 34
        block = record["column_blocks"][position]
        # Significance belongs to the candidate result cell. Gap columns are a
        # presentation option and intentionally carry no colour in the clean
        # workbook, so using them here would turn every KPI into parity whenever
        # gaps are displayed.
        signal_col = block["value"]
        benchmark_value_col = (
            block.get("benchmark")
            if benchmark_position == -1
            else record["column_blocks"][benchmark_position]["value"]
        )
        for kpi_offset, config in enumerate(kpis, 2):
            question_id = _text(config.get("Question ID")).casefold()
            entries = []
            for output_row, metric in question_rows.get(question_id, ()):
                candidate_value = record["target"].cell(output_row, block["value"]).value
                benchmark_value = record["target"].cell(output_row, benchmark_value_col).value
                confidence = _summary_confidence(
                    record["source_workbook"],
                    record["target"].cell(output_row, signal_col).fill,
                )
                signal = _summary_signal_from_values(
                    record["source_workbook"],
                    record["target"].cell(output_row, signal_col).fill,
                    metric,
                    candidate_value,
                    benchmark_value,
                    config,
                )
                entries.append({
                    "metric": metric,
                    "signal": signal,
                    "confidence": confidence,
                    "candidate": candidate_value,
                    "benchmark": benchmark_value,
                    "direction_defined": _summary_higher_is_better(metric, config) is not None,
                })
            decision = _pick_summary_decision(entries, summary_metric_strategy)
            symbol = decision["symbol"]
            cell = sheet.cell(row, kpi_offset)
            cell.value = _excel_safe_value(symbol) or "="
            cell.fill = fills[symbol]
            cell.font = fonts[symbol]
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            chosen = decision.get("chosen")
            product_name = _summary_product_name(record, position).replace("\n", " � ")
            candidate_value = chosen.get("candidate") if chosen else None
            benchmark_value = chosen.get("benchmark") if chosen else None
            gap = (
                candidate_value - benchmark_value
                if isinstance(candidate_value, (int, float)) and isinstance(benchmark_value, (int, float))
                else None
            )
            significant_comparisons = " � ".join(
                f"{entry['metric']}: {entry['candidate']} vs {entry['benchmark']} ({entry['signal']})"
                for entry in entries if entry.get("signal")
            ) or "None"
            detail_rows.append({
                "Split": record["split"],
                "Benchmark": benchmark_label,
                "Produit": product_name,
                "KPI": _text(config.get("Summary label")) or _summary_label(_text(config.get("Display label"))),
                "R�gle favorable": _text(config.get("Sens favorable")) or "Automatique",
                "M�thode": summary_metric_strategy,
                "M�trique retenue": chosen.get("metric") if chosen else "Multiple metrics",
                "Comparaisons significatives": significant_comparisons,
                "Valeur produit": candidate_value,
                "Valeur benchmark": benchmark_value,
                "�cart": gap,
                "Seuil": f"{chosen.get('confidence')}%" if chosen and chosen.get("confidence") else "Non significatif",
                "R�sultat": symbol,
                "Explication": decision["reason"],
            })

    legend_row = header_row + len(product_positions) + 2
    sheet.merge_cells(start_row=legend_row, start_column=1, end_row=legend_row, end_column=max_col)
    legend = sheet.cell(legend_row, 1)
    legend.value = " win 95%   ? win 90%   = parity   � r�sultats partag�s   - non interpr�t�   ? loss 90%    loss 95%"
    legend.font = Font(color="666666", italic=True, size=9)
    legend.alignment = Alignment(horizontal="left")
    return legend_row + 3


def _create_summary_details(output, used_names: set[str], detail_rows: Sequence[dict]) -> str | None:
    if not detail_rows:
        return None
    sheet = output.create_sheet(_safe_sheet_name("KPI Details", used_names))
    headers = list(detail_rows[0])
    for col, header in enumerate(headers, 1):
        cell = sheet.cell(1, col, header)
        cell.fill = PatternFill("solid", fgColor="3E356B")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row_index, values in enumerate(detail_rows, 2):
        for col, header in enumerate(headers, 1):
            cell = sheet.cell(row_index, col, values.get(header))
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=header in {"Produit", "KPI", "Comparaisons significatives", "Explication"},
            )
            if header in {"Valeur produit", "Valeur benchmark", "�cart"}:
                cell.number_format = "0.00"
    widths = {
        "Split": 20, "Benchmark": 22, "Produit": 36, "KPI": 28, "R�gle favorable": 18,
        "M�thode": 18, "M�trique retenue": 22, "Valeur produit": 14, "Valeur benchmark": 16,
        "Comparaisons significatives": 48, "�cart": 12, "Seuil": 15, "R�sultat": 10, "Explication": 46,
    }
    for col, header in enumerate(headers, 1):
        sheet.column_dimensions[get_column_letter(col)].width = widths.get(header, 18)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{sheet.max_row}"
    sheet.sheet_view.showGridLines = False
    return sheet.title


def _create_monadic_summaries(
    output,
    used_names: set[str],
    records: Sequence[dict],
    question_rows: Sequence[dict],
    summary_scope: str,
    reference_split_name: str,
    summary_metric_strategy: str,
    include_summary_details: bool,
) -> tuple[list[str], str | None]:
    normalized_scope = _normal(summary_scope)
    if normalized_scope in {"", "none", "no", "off"}:
        return [], None
    kpis = _selected_summary_questions(question_rows)
    if not kpis:
        return [], None
    if normalized_scope not in {"total", "all"}:
        raise TemplyfierError("P�rim�tre KPI Summary inconnu.")
    selected_records = list(records)
    if normalized_scope == "total":
        reference_key = _normal(reference_split_name)
        selected_records = [record for record in records if _normal(record["split"]) == reference_key]

    benchmark_order = []
    for record in selected_records:
        for benchmark_position in record["active_benchmarks"]:
            if benchmark_position not in benchmark_order:
                benchmark_order.append(benchmark_position)
    created = []
    created_sheets = []
    detail_rows: list[dict] = []
    for benchmark_position in benchmark_order:
        matching = [record for record in selected_records if benchmark_position in record["active_benchmarks"]]
        seen_splits = set()
        unique_matching = []
        for record in matching:
            split_key = _normal(record["split"])
            if split_key in seen_splits:
                continue
            seen_splits.add(split_key)
            unique_matching.append(record)
        matching = unique_matching
        if not matching:
            continue
        label = matching[0]["benchmark_labels"].get(benchmark_position, f"B{benchmark_position + 1}")
        requested_name = "KPI Summary" if len(benchmark_order) == 1 else f"KPI Summary vs {label}"
        sheet = output.create_sheet(_safe_sheet_name(requested_name, used_names))
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "B4"
        sheet.column_dimensions["A"].width = 38
        for col in range(2, 2 + len(kpis)):
            sheet.column_dimensions[get_column_letter(col)].width = 16
        next_row = 1
        for record in matching:
            next_row = _write_summary_block(
                sheet, next_row, record, benchmark_position, kpis,
                summary_metric_strategy, detail_rows,
            )
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        created.append(sheet.title)
        created_sheets.append(sheet)
    for sheet in reversed(created_sheets):
        output.move_sheet(sheet, offset=-output.index(sheet))
    detail_name = _create_summary_details(output, used_names, detail_rows) if include_summary_details else None
    if detail_name:
        detail_sheet = output[detail_name]
        output.move_sheet(detail_sheet, offset=-output.index(detail_sheet) + len(created))
    return created, detail_name


def _create_paired_summary(
    output,
    used_names: set[str],
    records: Sequence[dict],
    question_rows: Sequence[dict],
    summary_scope: str,
    reference_split_name: str,
    summary_metric_strategy: str,
    include_summary_details: bool,
) -> tuple[list[str], str | None]:
    normalized_scope = _normal(summary_scope)
    if normalized_scope in {"", "none", "no", "off"}:
        return [], None
    if normalized_scope not in {"total", "all"}:
        raise TemplyfierError("P�rim�tre KPI Summary inconnu.")
    kpis = _selected_summary_questions(question_rows)
    if not kpis:
        return [], None
    selected_records = list(records)
    if normalized_scope == "total":
        reference_key = _normal(reference_split_name)
        selected_records = [record for record in records if _normal(record["split"]) == reference_key]
    if not selected_records:
        return [], None
    sheet = output.create_sheet(_safe_sheet_name("KPI Summary", used_names))
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "B4"
    sheet.column_dimensions["A"].width = 42
    for col in range(2, 2 + len(kpis)):
        sheet.column_dimensions[get_column_letter(col)].width = 16
    next_row = 1
    detail_rows: list[dict] = []
    for record in selected_records:
        next_row = _write_summary_block(
            sheet, next_row, record, -1, kpis,
            summary_metric_strategy, detail_rows,
        )
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    output.move_sheet(sheet, offset=-output.index(sheet))
    detail_name = _create_summary_details(output, used_names, detail_rows) if include_summary_details else None
    if detail_name:
        detail_sheet = output[detail_name]
        output.move_sheet(detail_sheet, offset=-output.index(detail_sheet) + 1)
    return [sheet.title], detail_name


def build_smart_toplines(
    raw_files: Sequence[tuple[str, object]],
    question_rows: Sequence[dict],
    *,
    split_names: Sequence[str],
    benchmark_positions: Sequence[int],
    standard_metrics: Sequence[str],
    include_screeners: bool = True,
    test_type: str = "Monadic",
    mean_decimals: int = 2,
    paired_swaps: dict[str, Sequence[int]] | None = None,
    paired_mappings: dict[str, Sequence[Sequence[int]]] | None = None,
    include_deltas: bool = True,
    include_sections: bool = True,
    benchmark_sheet_mode: str = "combined",
    benchmark_labels: Sequence[str] | None = None,
    output_sheet_order: str = "split_first",
    show_monadic_gaps: bool = True,
    product_labels: Sequence[str] | None = None,
    product_subtitles: Sequence[str] | None = None,
    highlight_benchmarks: bool = True,
    summary_scope: str = "none",
    summary_metric_strategy: str = "priority",
    include_summary_details: bool = True,
    gap_positive_points: float | None = 5.0,
    gap_negative_points: float | None = 5.0,
) -> tuple[bytes, dict]:
    if not raw_files:
        raise TemplyfierError("Ajoute au moins un export G-Sight.")
    normalized_test_type = _normal(test_type)
    columns_mode = benchmark_sheet_mode in {'auto_columns','benchmark_columns'}
    if columns_mode:
        benchmark_sheet_mode = 'auto_exports' if benchmark_sheet_mode == 'auto_columns' else 'separate'
    if normalized_test_type.startswith("paired"):
        return _build_paired_toplines(
            raw_files,
            question_rows,
            split_names=split_names,
            standard_metrics=standard_metrics,
            include_screeners=include_screeners,
            mean_decimals=mean_decimals,
            paired_swaps=paired_swaps,
            paired_mappings=paired_mappings,
            include_deltas=include_deltas,
            include_sections=include_sections,
            summary_scope=summary_scope,
            summary_metric_strategy=summary_metric_strategy,
            include_summary_details=include_summary_details,
            gap_positive_points=gap_positive_points,
            gap_negative_points=gap_negative_points,
        )
    if not normalized_test_type.startswith("monadic"):
        raise TemplyfierError("Type de test non reconnu : choisis Paired ou Monadic.")
    workbooks = [_workbook(source) for _, source in raw_files]
    virtual_inputs = []
    for file_index, ((filename, _), workbook) in enumerate(zip(raw_files, workbooks)):
        for sheet in _embedded_data_sheets(workbook):
            virtual_inputs.append((file_index, filename, sheet))

    if len(virtual_inputs) == len(raw_files):
        if len(split_names) != len(raw_files):
            raise TemplyfierError("Le nombre de noms de splits est incorrect.")
        output_split_names = list(split_names)
    elif len(split_names) == len(virtual_inputs):
        output_split_names = list(split_names)
    elif len(split_names) == len(raw_files):
        virtual_stages = tuple(dict.fromkeys(_stage_name(sheet) for _, _, sheet in virtual_inputs))
        virtual_study_format = _study_format(
            [filename for filename, _ in raw_files],
            virtual_stages,
            max((sheet.max_row for _, _, sheet in virtual_inputs), default=0),
        )
        if virtual_study_format == "HUT / in-use":
            # In consolidated HUT exports, Stage None/USE often represents the
            # benchmark configuration, not a consumer split or touchpoint.
            output_split_names = [_detected_split_label(sheet) for _, _, sheet in virtual_inputs]
        else:
            output_split_names = [
                f"{_stage_name(sheet)} � {_detected_split_label(sheet)}"
                for _, _, sheet in virtual_inputs
            ]
    else:
        raise TemplyfierError("Le nombre de noms de splits est incorrect.")

    # Consolidated workbooks can contain several stage sheets carrying the
    # same consumer split (often TOTAL). They are distinct readings and must
    # never collide when benchmark panels are combined.
    duplicate_split_names = {
        _normal(name) for name in output_split_names
        if sum(_normal(other) == _normal(name) for other in output_split_names) > 1
    }
    if duplicate_split_names and len(virtual_inputs) > len(raw_files):
        resolved_names = []
        used_names = set()
        for position, (name, (_, _, sheet)) in enumerate(zip(output_split_names, virtual_inputs), 1):
            candidate = name
            if _normal(name) in duplicate_split_names:
                stage = _stage_name(sheet)
                suffix = stage if _normal(stage) not in {"", "none", "not specified", "non precise"} else sheet.title
                candidate = f"{name} - {suffix}"
            base = candidate
            counter = 2
            while _normal(candidate) in used_names:
                candidate = f"{base} ({counter})"
                counter += 1
            used_names.add(_normal(candidate))
            resolved_names.append(candidate)
        output_split_names = resolved_names

    data_sheets = [sheet for _, _, sheet in virtual_inputs]
    source_workbooks = [workbooks[file_index] for file_index, _, _ in virtual_inputs]
    source_filenames = [filename for _, filename, _ in virtual_inputs]
    layouts = [_active_layout(sheet, detect_layout(sheet)) for sheet in data_sheets]
    comparison_codes_by_sheet = [_comparison_codes(sheet, layout) for sheet, layout in zip(data_sheets, layouts)]
    product_names = [_product_names(sheet, layout) for sheet, layout in zip(data_sheets, layouts)]
    product_keys = [_product_keys(sheet, layout) for sheet, layout in zip(data_sheets, layouts)]
    normalized_sheet_mode = _normal(benchmark_sheet_mode).replace("_", " ")
    automatic_exports = normalized_sheet_mode in {"auto exports", "automatic exports", "auto"}
    if normalized_sheet_mode not in {"combined", "separate", "separate sheets", "auto exports", "automatic exports", "auto"}:
        raise TemplyfierError("Organisation des benchmarks inconnue.")
    canonical_keys = product_keys[0]
    same_product_sets = all(Counter(keys) == Counter(canonical_keys) for keys in product_keys)
    if not same_product_sets:
        raise TemplyfierError("Le plan produits n'est pas identique dans tous les exports.")
    if not automatic_exports and any(keys != canonical_keys for keys in product_keys[1:]):
        raise TemplyfierError(
            "L'ordre des produits diff�re entre les exports. Active la d�tection automatique par fichier benchmark."
        )

    product_count = len(canonical_keys)
    benchmarks = tuple(int(pos) for pos in benchmark_positions)
    if automatic_exports and not benchmarks:
        detected_codes = list(dict.fromkeys(code for codes in comparison_codes_by_sheet for code in codes))
        detected_code_set = set(detected_codes)
        benchmarks = tuple(
            position for position, code in enumerate(canonical_keys)
            if code in detected_code_set
        )
    if not benchmarks or any(pos < 0 or pos >= product_count for pos in benchmarks):
        raise TemplyfierError("Benchmark invalide.")
    if len(set(benchmarks)) != len(benchmarks):
        raise TemplyfierError("The same benchmark was selected more than once. Nothing was generated.")
    separate_benchmarks = automatic_exports or (len(benchmarks) > 1 and normalized_sheet_mode.startswith("separate"))
    short_benchmark_labels = [_text(label) for label in (benchmark_labels or ())]
    if short_benchmark_labels and len(short_benchmark_labels) != len(benchmarks):
        raise TemplyfierError("Le nombre de noms courts ne correspond pas au nombre de benchmarks.")
    clean_product_labels = [_text(label) for label in (product_labels or ())]
    clean_product_subtitles = [_text(label) for label in (product_subtitles or ())]
    if clean_product_labels and len(clean_product_labels) != product_count:
        raise TemplyfierError("Le nombre de noms produits ne correspond pas au plan produits.")
    if clean_product_subtitles and len(clean_product_subtitles) != product_count:
        raise TemplyfierError("Le nombre de sous-titres produits ne correspond pas au plan produits.")
    normalized_output_order = _normal(output_sheet_order).replace("_", " ")
    if normalized_output_order not in {"split first", "benchmark first"}:
        raise TemplyfierError("Ordre des onglets inconnu.")

    selected_questions = _selected_question_rows(question_rows)
    output_questions = (
        _questions_in_section_blocks(selected_questions) if include_sections else selected_questions
    )

    output = Workbook()
    output.remove(output.active)
    used_names: set[str] = set()
    total_index = max(range(len(data_sheets)), key=lambda i: sum(count or 0 for count in _signature(data_sheets[i], layouts[i])))
    written_data_rows = 0
    skipped_stage_questions = 0
    question_omissions: list[dict] = []
    mean_format = _mean_number_format(mean_decimals)

    generated_sheet_names = []
    missing_benchmark_exports = []
    summary_records = []
    benchmark_label_map = {
        position: (
            short_benchmark_labels[offset]
            if offset < len(short_benchmark_labels) and short_benchmark_labels[offset]
            else clean_product_labels[position]
            if clean_product_labels
            else product_names[0][position]
        )
        for offset, position in enumerate(benchmarks)
    }
    output_jobs = []
    if automatic_exports:
        split_groups: dict[str, list[int]] = {}
        split_display_names: dict[str, str] = {}
        for index, split_name in enumerate(output_split_names):
            split_key = _normal(split_name)
            split_groups.setdefault(split_key, []).append(index)
            split_display_names.setdefault(split_key, split_name)
        combinations = (
            (
                (split_key, indexes, label_offset, benchmark_position)
                for label_offset, benchmark_position in enumerate(benchmarks)
                for split_key, indexes in split_groups.items()
            )
            if normalized_output_order == "benchmark first"
            else (
                (split_key, indexes, label_offset, benchmark_position)
                for split_key, indexes in split_groups.items()
                for label_offset, benchmark_position in enumerate(benchmarks)
            )
        )
        for split_key, indexes, label_offset, benchmark_position in combinations:
            benchmark_key = canonical_keys[benchmark_position]
            matches = [index for index in indexes if benchmark_key in comparison_codes_by_sheet[index]]
            if len(matches) > 1:
                raise TemplyfierError(
                    f"Plusieurs exports correspondent � {split_display_names[split_key]} vs {benchmark_key}. "
                    "Garde un seul fichier pour cette combinaison."
                )
            if not matches:
                missing_benchmark_exports.append(f"{split_display_names[split_key]} vs {benchmark_key}")
                continue
            output_jobs.append((matches[0], label_offset, (benchmark_position,), split_display_names[split_key]))
    else:
        if separate_benchmarks and normalized_output_order == "benchmark first":
            for label_offset, position in enumerate(benchmarks):
                for file_index in range(len(data_sheets)):
                    output_jobs.append((file_index, label_offset, (position,), output_split_names[file_index]))
        else:
            for file_index in range(len(data_sheets)):
                variants = [(None, benchmarks)]
                if separate_benchmarks:
                    variants = [(offset, (position,)) for offset, position in enumerate(benchmarks)]
                for label_offset, active_benchmarks in variants:
                    output_jobs.append((file_index, label_offset, active_benchmarks, output_split_names[file_index]))

    if not output_jobs:
        raise TemplyfierError("Aucune combinaison split � benchmark compl�te n'a �t� d�tect�e.")

    for file_index, label_offset, active_benchmarks, split_display_name in output_jobs:
            filename = source_filenames[file_index]
            source_sheet = data_sheets[file_index]
            layout = layouts[file_index]
            source_positions = _occurrence_position_map(
                canonical_keys, product_keys[file_index]
            )
            product_order = list(active_benchmarks) + [pos for pos in range(product_count) if pos not in active_benchmarks]
            column_blocks: dict[int, dict] = {}
            current_col = 3
            for pos in product_order:
                if pos in active_benchmarks:
                    column_blocks[pos] = {"value": current_col, "gaps": [], "spacer": current_col + 1}
                    current_col += 2
                elif not show_monadic_gaps:
                    column_blocks[pos] = {"value": current_col, "gaps": [], "spacer": current_col + 1}
                    current_col += 2
                else:
                    gaps = list(range(current_col + 1, current_col + 1 + len(active_benchmarks)))
                    column_blocks[pos] = {"value": current_col, "gaps": gaps, "spacer": gaps[-1] + 1}
                    current_col = gaps[-1] + 2
            max_col = current_col - 1

            requested_name = split_display_name
            if label_offset is not None:
                default_source_position = source_positions[active_benchmarks[0]]
                default_label = product_names[file_index][default_source_position]
                label = short_benchmark_labels[label_offset] if short_benchmark_labels else default_label
                requested_name = f"{requested_name} vs {label}"
            target = output.create_sheet(_safe_sheet_name(requested_name, used_names))
            generated_sheet_names.append(target.title)
            _style_sheet(target, max_col)
            for pos in product_order:
                block = column_blocks[pos]
                source_position = source_positions[pos]
                raw_col = layout.product_cols[source_position]
                value_col = block["value"]
                target.cell(3, value_col).value = _excel_safe_value(
                    clean_product_labels[pos]
                    if clean_product_labels
                    else source_sheet.cell(layout.product_name_row, raw_col).value
                )
                target.cell(4, value_col).value = _excel_safe_value(source_sheet.cell(layout.sample_row, raw_col).value)
                target.cell(5, value_col).value = _excel_safe_value(
                    clean_product_subtitles[pos]
                    if clean_product_subtitles
                    else source_sheet.cell(layout.product_header_row, raw_col).value
                )
                if highlight_benchmarks and pos in benchmarks:
                    for header_row in (3, 4):
                        header_cell = target.cell(header_row, value_col)
                        header_cell.fill = PatternFill("solid", fgColor="D6008F")
                        header_cell.font = Font(color="FFFFFF", bold=True)
                for bench_offset, gap_col in enumerate(block["gaps"]):
                    bench_name = source_sheet.cell(
                        layout.product_header_row,
                        layout.product_cols[source_positions[active_benchmarks[bench_offset]]],
                    ).value
                    target.cell(5, gap_col).value = f"Gap vs {bench_name}"
                target.column_dimensions[get_column_letter(block["spacer"])].width = 3

            output_row = 6
            current_section = None
            previous_variable_label = None
            summary_question_rows: dict[str, list[tuple[int, str]]] = {}
            for config in output_questions:
                if not _question_applies_to_split(config, split_display_name):
                    continue
                expected_in_source = _question_expected_in_source(
                    config, split_display_name, source_sheet
                )
                section = _text(config.get("Section"))
                section_changed = section != current_section
                if include_sections and section_changed:
                    current_section = section
                    previous_variable_label = None
                if include_sections and section and section_changed:
                    target.cell(output_row, 1).value = section
                    target.merge_cells(start_row=output_row, start_column=1, end_row=output_row, end_column=max_col)
                    section_cell = target.cell(output_row, 1)
                    section_cell.fill = PatternFill("solid", fgColor="D9D3EA")
                    section_cell.font = Font(bold=True, color="2F2952")
                    section_cell.alignment = Alignment(vertical="center")
                    target.row_dimensions[output_row].height = 22
                    output_row += 1

                question_id = _text(config.get("Question ID"))
                question_type = _text(config.get("Type"))
                question_metrics = _standard_metrics_for_question(config, standard_metrics)
                source_rows = configured_source_rows(source_sheet, layout, config, standard_metrics)
                if not source_rows:
                    skipped_stage_questions += 1
                    if expected_in_source:
                        question_omissions.append({
                            "question_id": question_id,
                            "label": _text(config.get("Display label")) or question_id,
                            "sheet": target.title,
                        })
                    continue
                # Side-by-side benchmark panels intentionally align a metric
                # that exists in one reading as a documented blank in another.
                # combine_readings reports those cells separately, so this is
                # not an unexplained omission.
                missing_metrics = [] if columns_mode else _missing_selected_metrics(
                    config, source_sheet, layout, source_rows
                )
                if missing_metrics:
                    question_omissions.append({
                        "question_id": question_id,
                        "label": _text(config.get("Display label")) or question_id,
                        "sheet": target.title,
                        "missing_metrics": missing_metrics,
                    })
                    continue

                for metric_index, source_row in enumerate(source_rows):
                    source_metric = _text(source_sheet.cell(source_row, layout.metric_col).value)
                    display_label = _text(config.get("Display label"))
                    metric_label = _text(config.get("Metric label"))
                    if metric_label and len(source_rows) == 1:
                        group_identity = (_text(config.get("Group ID")) or display_label, section, display_label)
                        target.cell(output_row, 1).value = display_label if group_identity != previous_variable_label else None
                        target.cell(output_row, 2).value = grouped_metric_label(config, source_metric, len(source_rows))
                        previous_variable_label = group_identity
                    elif question_type in {"Attribute", "CATA"} and not metric_label:
                        target.cell(output_row, 1).value = None
                        target.cell(output_row, 2).value = (display_label if len(source_rows) == 1 else f"{display_label} � {clean_metric_label(config, source_metric)}")
                        previous_variable_label = None
                    else:
                        variable_label = metric_label or display_label
                        target.cell(output_row, 1).value = variable_label if metric_index == 0 else None
                        target.cell(output_row, 2).value = clean_metric_label(config, source_metric)
                        previous_variable_label = None

                    is_mean = _metric_key(source_metric) == "mean"
                    number_format = mean_format if is_mean else "0%"
                    for pos in product_order:
                        source_position = source_positions[pos]
                        raw_col = layout.product_cols[source_position]
                        block = column_blocks[pos]
                        value_cell = target.cell(output_row, block["value"])
                        value_cell.value = _excel_safe_value(source_sheet.cell(source_row, raw_col).value)
                        value_cell.number_format = number_format
                        value_cell.alignment = Alignment(horizontal="right")
                        if pos not in active_benchmarks:
                            for bench_offset, gap_col in enumerate(block["gaps"]):
                                benchmark_position = active_benchmarks[bench_offset]
                                benchmark_value_col = column_blocks[benchmark_position]["value"]
                                gap_cell = target.cell(output_row, gap_col)
                                gap_cell.value = _safe_difference_formula(
                                    f"{get_column_letter(block['value'])}{output_row}",
                                    f"{get_column_letter(benchmark_value_col)}{output_row}",
                                    scale=1 if is_mean else 100,
                                )
                                _style_difference_cell(
                                    target,
                                    gap_cell,
                                    is_mean=is_mean,
                                    mean_format=mean_format,
                                    positive_points=gap_positive_points,
                                    negative_points=gap_negative_points,
                                    candidate_value=source_sheet.cell(source_row, raw_col).value,
                                    benchmark_value=source_sheet.cell(
                                        source_row,
                                        layout.product_cols[source_positions[benchmark_position]],
                                    ).value,
                                )
                                fill = _benchmark_fill(
                                    source_workbooks[file_index], source_sheet, layout, source_row, raw_col,
                                    source_positions[benchmark_position], product_keys[file_index],
                                    comparison_codes_by_sheet[file_index],
                                )
                                if fill is not None:
                                    value_cell.fill = fill
                            if not block["gaps"] and active_benchmarks:
                                fill = _benchmark_fill(
                                    source_workbooks[file_index],
                                    source_sheet,
                                    layout,
                                    source_row,
                                    raw_col,
                                    source_positions[active_benchmarks[0]],
                                    product_keys[file_index],
                                    comparison_codes_by_sheet[file_index],
                                )
                                if fill is not None:
                                    value_cell.fill = fill

                    thin = Side(style="thin", color="B8B8C3")
                    spacer_columns = [block["spacer"] for block in column_blocks.values()]
                    for col in range(2, max_col + 1):
                        if col not in spacer_columns:
                            target.cell(output_row, col).border = Border(bottom=thin)
                    _format_variable_label(target, output_row)
                    summary_question_rows.setdefault(question_id.casefold(), []).append((output_row, source_metric))
                    output_row += 1
                    written_data_rows += 1

            target.auto_filter.ref = f"A5:{get_column_letter(max_col)}{output_row - 1}"
            summary_records.append({
                "target": target,
                "split": split_display_name,
                "file_index": file_index,
                "active_benchmarks": tuple(active_benchmarks),
                "benchmark_labels": benchmark_label_map,
                "product_order": tuple(product_order),
                "column_blocks": column_blocks,
                "question_rows": summary_question_rows,
                "source_workbook": source_workbooks[file_index],
            })

    _raise_for_question_omissions(question_omissions)
    _raise_for_unwritten_selected_questions(question_rows, summary_records)
    _raise_for_empty_topline_sheets(summary_records)
    summary_sheet_names, summary_detail_sheet = _create_monadic_summaries(
        output,
        used_names,
        summary_records,
        question_rows,
        summary_scope,
        output_split_names[total_index],
        summary_metric_strategy,
        include_summary_details,
    )

    if include_screeners:
        total_wb = source_workbooks[total_index]
        screener = next((sheet for sheet in total_wb.worksheets if "screener" in sheet.title.casefold()), None)
        if screener is not None:
            _copy_sheet(screener, output.create_sheet("Screeners"))

    panel_layouts, missing_panel_metrics = [], []
    if columns_mode:
        from .benchmark_columns import combine_readings
        generated_sheet_names, panel_layouts, missing_panel_metrics = combine_readings(output, summary_records, _metric_key)
    output.calculation.fullCalcOnLoad = True
    output.calculation.forceFullCalc = True
    output.calculation.calcMode = "auto"
    buffer = BytesIO()
    from .english_output import finalize
    finalize(output, show_monadic_gaps)
    output.save(buffer)
    _validate_generated_xlsx(buffer.getvalue())
    scanned = sum(_source_metric_row_count(sheet, layout) for sheet, layout in zip(data_sheets, layouts))
    return buffer.getvalue(), {
        "mode": "Nouveau projet intelligent",
        "test_type": "Monadic",
        "splits": generated_sheet_names,
        "source_splits": output_split_names,
        "benchmark_sheet_mode": ('auto_columns' if automatic_exports else 'benchmark_columns') if columns_mode else ("auto_exports" if automatic_exports else ("separate" if separate_benchmarks else "combined")),
        "benchmark_column_panels": panel_layouts,
        "missing_panel_metrics": missing_panel_metrics,
        "missing_benchmark_exports": missing_benchmark_exports,
        "questions": len(selected_questions),
        "questions_deleted": sum(not bool(row.get("Keep")) or row.get("Type") == "Delete" for row in question_rows),
        "data_rows_written": written_data_rows,
        "source_metric_rows_scanned": scanned,
        "metric_rows_filtered": max(0, scanned - written_data_rows),
        "technical_columns_ignored": sum(max(0, sheet.max_column - 2 - len(layout.product_cols)) for sheet, layout in zip(data_sheets, layouts)),
        "products": product_count,
        "benchmarks": [pos + 1 for pos in benchmarks],
        "benchmark_labels": short_benchmark_labels,
        "output_sheet_order": (
            "benchmark_first" if normalized_output_order == "benchmark first" else "split_first"
        ),
        "show_monadic_gaps": bool(show_monadic_gaps),
        "product_labels": clean_product_labels,
        "product_subtitles": clean_product_subtitles,
        "highlight_benchmarks": bool(highlight_benchmarks),
        "summary_scope": _normal(summary_scope) or "none",
        "summary_sheets": summary_sheet_names,
        "summary_detail_sheet": summary_detail_sheet,
        "summary_metric_strategy": summary_metric_strategy,
        "summary_kpis": len(_selected_summary_questions(question_rows)),
        "reference_export": source_filenames[total_index],
        "skipped_stage_questions": skipped_stage_questions,
        "mean_decimals": int(mean_decimals),
        "gap_positive_points": gap_positive_points,
        "gap_negative_points": gap_negative_points,
        "include_sections": bool(include_sections),
    }

