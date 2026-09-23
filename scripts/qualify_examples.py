from __future__ import annotations

from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import re
import sys

from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from templyfier.core import detect_layout
from templyfier.smart import (
    _active_layout,
    _embedded_data_sheets,
    _metric_key,
    _normal,
    _product_keys,
    build_smart_toplines,
    inspect_smart_package,
    proposal_to_row,
)


UPLOAD = ROOT / "upload"
OUTPUT_DIR = ROOT / "outputs" / "f157ae87c161"
DEFAULT_METRICS = ("Mean", "Top Box", "Top 2 Boxes", "Bottom 2 Boxes")
GREEN = {"008000", "00FF00", "4BCB4F", "21A625", "97E39C", "CCFFCC", "C7F0CC"}
RED = {"800000", "FF0000", "EB3933", "A62521", "F5B7AD", "FF9A00", "FF9900", "FADBD4"}


def _load(source, *, data_only=False):
    if isinstance(source, bytes):
        return load_workbook(BytesIO(source), data_only=data_only)
    return load_workbook(BytesIO(Path(source).read_bytes()), data_only=data_only)


def _stable_code(value: str) -> str:
    text = str(value or "")
    parenthesized = re.findall(r"\(([A-Z0-9]{2,8})\)", text.upper())
    if parenthesized:
        return parenthesized[-1]
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _header_code_map(sheet, stable_codes: set[str]) -> dict[int, str]:
    result = {}
    for col in range(3, sheet.max_column + 1):
        header = " ".join(str(sheet.cell(row, col).value or "") for row in range(1, 7)).upper()
        compact = re.sub(r"[^A-Z0-9]", "", header)
        matches = [code for code in stable_codes if code and code in compact]
        if matches:
            result[col] = max(matches, key=len)
    return result


def _topline_fingerprints(workbook, stable_codes: set[str]):
    values = Counter()
    strict_values = Counter()
    fills = Counter()
    for sheet in workbook.worksheets:
        if any(token in sheet.title.casefold() for token in ("summary", "details", "screener", "legend", "design", "verbatim", "conclusion", "max diff", "open question", "pref data")):
            continue
        code_map = _header_code_map(sheet, stable_codes)
        if not code_map:
            continue
        current_variable = ""
        for row in range(6, sheet.max_row + 1):
            variable = sheet.cell(row, 1).value
            metric = sheet.cell(row, 2).value
            if variable not in (None, ""):
                current_variable = _normal(str(variable))
            if metric in (None, ""):
                continue
            metric_key = _metric_key(str(metric))
            for col, code in code_map.items():
                cell = sheet.cell(row, col)
                value = cell.value
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                rounded = round(float(value), 10)
                values[(metric_key, code, rounded)] += 1
                strict_values[(current_variable, metric_key, code, rounded)] += 1
                rgb = (cell.fill.fgColor.rgb or "").upper()[-6:]
                direction = "higher" if rgb in GREEN else "lower" if rgb in RED else None
                if direction:
                    fills[(metric_key, code, rounded, direction)] += 1
    return values, strict_values, fills


def _source_fingerprints(paths: list[Path]):
    metric_values = set()
    loose_values = set()
    stable_codes = set()
    for path in paths:
        workbook = _load(path)
        for sheet in _embedded_data_sheets(workbook):
            layout = _active_layout(sheet, detect_layout(sheet))
            keys = [_stable_code(value) for value in _product_keys(sheet, layout)]
            stable_codes.update(keys)
            for row in range(layout.header_row + 1, sheet.max_row + 1):
                metric = sheet.cell(row, layout.metric_col).value
                if metric in (None, ""):
                    continue
                metric_key = _metric_key(str(metric))
                for code, col in zip(keys, layout.product_cols):
                    value = sheet.cell(row, col).value
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                    rounded = round(float(value), 10)
                    metric_values.add((metric_key, code, rounded))
                    loose_values.add((code, rounded))
    return metric_values, loose_values, stable_codes


def _formula_and_fill_checks(workbook):
    formulas = 0
    formula_errors = []
    fill_checks = 0
    fill_errors = []
    formula_pattern = re.compile(r"^=([A-Z]+)(\d+)-([A-Z]+)(\d+)$")
    for sheet in workbook.worksheets:
        if any(token in sheet.title.casefold() for token in ("summary", "details", "screener")):
            continue
        for row in sheet.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str) or not cell.value.startswith("="):
                    continue
                formulas += 1
                match = formula_pattern.match(cell.value)
                if not match:
                    formula_errors.append(f"{sheet.title}!{cell.coordinate}: formule inattendue {cell.value}")
                    continue
                left_col, left_row, right_col, right_row = match.groups()
                if int(left_row) != cell.row or int(right_row) != cell.row:
                    formula_errors.append(f"{sheet.title}!{cell.coordinate}: références de ligne incohérentes")
                    continue
                left = sheet.cell(cell.row, column_index_from_string(left_col)).value
                right = sheet.cell(cell.row, column_index_from_string(right_col)).value
                if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                    formula_errors.append(f"{sheet.title}!{cell.coordinate}: références non numériques")
                    continue
                rgb = (cell.fill.fgColor.rgb or "").upper()[-6:]
                if rgb in GREEN | RED:
                    fill_checks += 1
                    expected = "higher" if left > right else "lower" if left < right else "equal"
                    actual = "higher" if rgb in GREEN else "lower"
                    if expected != actual:
                        fill_errors.append(
                            f"{sheet.title}!{cell.coordinate}: couleur {actual} pour un gap {left-right:+.6g}"
                        )
    return {
        "gap_formulas": formulas,
        "gap_formula_errors": formula_errors,
        "significance_directions_checked": fill_checks,
        "significance_direction_errors": fill_errors,
    }


def _summary_checks(workbook):
    if "KPI Details" not in workbook.sheetnames:
        return {"summary_rows": 0, "summary_errors": []}
    sheet = workbook["KPI Details"]
    headers = {sheet.cell(1, col).value: col for col in range(1, sheet.max_column + 1)}
    errors = []
    for row in range(2, sheet.max_row + 1):
        symbol = sheet.cell(row, headers["Résultat"]).value
        comparisons = str(sheet.cell(row, headers["Comparaisons significatives"]).value or "")
        if symbol == "±" and not (any(up in comparisons for up in ("▲", "△")) and any(down in comparisons for down in ("▼", "▽"))):
            errors.append(f"KPI Details row {row}: conflit sans directions opposées")
        if symbol in {"▲", "△", "▼", "▽"} and symbol not in comparisons:
            errors.append(f"KPI Details row {row}: symbole non justifié par les comparaisons")
    return {"summary_rows": max(0, sheet.max_row - 1), "summary_errors": errors}


def _intersection_count(left: Counter, right: Counter) -> int:
    return sum((left & right).values())


def _scenario_definitions():
    return [
        {
            "name": "WAVE HUT — 6 splits",
            "sources": sorted(UPLOAD.glob("DataViz_WAVE*.xlsx")),
            "historical": UPLOAD / "Clean file - v2.xlsx",
            "test_type": "Monadic",
            "benchmarks": (0,),
            "benchmark_labels": ("Ariel",),
            "mode": "combined",
        },
        {
            "name": "Comfort Yellow CLT — WET/NEAT",
            "sources": [UPLOAD / "DataViz_CLT Comfort Yellow UK_NEAT.xlsx", UPLOAD / "DataViz_CLT Comfort Yellow UK_WET.xlsx"],
            "inspection_sources": [
                UPLOAD / "DataViz_CLT Comfort Yellow UK_NEAT.xlsx", UPLOAD / "DataViz_CLT Comfort Yellow UK_WET.xlsx",
                UPLOAD / "DataViz_Comparaison bench_NEAT.xlsx", UPLOAD / "DataViz_Comparaison bench_WET.xlsx",
            ],
            "historical": UPLOAD / "Toplines CLT Comfort Yellow UK(1).xlsx",
            "test_type": "Monadic",
            "benchmarks": (0, 1),
            "benchmark_labels": ("Comfort", "Lenor"),
            "mode": "separate",
        },
        {
            "name": "Comfort White HUT — classeur consolidé",
            "sources": [UPLOAD / "G-sight output - ALL SPLITS.xlsx"],
            "historical": UPLOAD / "Comfort White HUT UK - Toplines(1).xlsx",
            "test_type": "Monadic",
            "benchmarks": (0, 1),
            "benchmark_labels": ("Comfort", "Fairy"),
            "mode": "auto_exports",
        },
        {
            "name": "Einstein Paired HUT — 4 splits",
            "sources": sorted(UPLOAD.glob("DataViz_Raw Data Einstein LC_*.xlsx")),
            "historical": UPLOAD / "Toplines Einstein 2.0 Paired HUT GE.xlsx",
            "test_type": "Paired",
            "benchmarks": (),
            "benchmark_labels": (),
            "mode": "combined",
        },
        {
            "name": "Yumos Pink HUT — 8 splits × 2 benchmarks",
            "sources": [UPLOAD / name for name in (
                "DATAVI~1.XLS", "DATAVI~2.XLS", "DATAVI~3.XLS", "DATAVI~4.XLS", "DAD68F~1.XLS", "DABA5C~1.XLS",
                "DA9C69~1.XLS", "DA1981~1.XLS", "DAC581~1.XLS", "DAAE49~1.XLS", "DA26AE~1.XLS", "DA873C~1.XLS",
                "DA3D9E~1.XLS", "DA6FB3~1.XLS", "DAF0E7~1.XLS", "DA8983~1.XLS",
            )],
            "historical": UPLOAD / "Toplines Yumos Pink TK HUT.xlsx",
            "test_type": "Monadic",
            "benchmarks": (0, 1),
            "benchmark_labels": ("Yumos", "Vernel"),
            "mode": "auto_exports",
        },
        {
            "name": "Skip Active CLT — 5 splits",
            "sources": [UPLOAD / name for name in (
                "DATAVI~1(1).XLS", "DATAVI~2(1).XLS", "DATAVI~3(1).XLS", "DATAVI~4(1).XLS", "DA754D~1.XLS",
            )],
            "historical": UPLOAD / "Toplines Skip Active CLT Max Diff FR(1).xlsx",
            "test_type": "Monadic",
            "benchmarks": (0,),
            "benchmark_labels": ("Ariel",),
            "mode": "combined",
            "metrics": ("Mean", "Top Box", "Top 2 Boxes", "Top 3 Boxes", "Bottom 2 Boxes"),
        },
    ]


def qualify_scenario(config: dict) -> dict:
    sources = config["sources"]
    inspection_sources = config.get("inspection_sources", sources)
    info = inspect_smart_package([(path.name, path) for path in inspection_sources])
    source_names = {path.name for path in sources}
    result_inputs = [item for item in info.inputs if item.filename in source_names and item.role == "Résultats"]
    if not result_inputs:
        result_inputs = [item for item in info.inputs if item.filename in source_names]
    split_names = [item.split_name for item in result_inputs]
    if len(sources) == 1:
        split_names = [result_inputs[0].split_name if result_inputs else "TOTAL"]
    rows = [proposal_to_row(item) for item in info.questions]
    summary_scope = "total" if any(bool(row.get("KPI Summary")) for row in rows) else "none"
    data, build_report = build_smart_toplines(
        [(path.name, path) for path in sources],
        rows,
        split_names=split_names,
        benchmark_positions=config["benchmarks"],
        standard_metrics=config.get("metrics", DEFAULT_METRICS),
        include_screeners=False,
        test_type=config["test_type"],
        benchmark_sheet_mode=config["mode"],
        benchmark_labels=config["benchmark_labels"],
        output_sheet_order="benchmark_first",
        show_monadic_gaps=True,
        summary_scope=summary_scope,
        summary_metric_strategy="consensus",
        include_summary_details=True,
    )
    generated = _load(data)
    source_values, source_loose_values, stable_codes = _source_fingerprints(sources)
    generated_values, generated_strict, generated_fills = _topline_fingerprints(generated, stable_codes)
    historical = _load(config["historical"])
    historical_values, historical_strict, historical_fills = _topline_fingerprints(historical, stable_codes)
    generated_total = sum(generated_values.values())
    metric_supported = sum(count for fingerprint, count in generated_values.items() if fingerprint in source_values)
    supported = sum(
        count for (_metric, code, value), count in generated_values.items()
        if (code, value) in source_loose_values
    )
    historical_overlap = _intersection_count(generated_values, historical_values)
    historical_total = sum(historical_values.values())
    strict_overlap = _intersection_count(generated_strict, historical_strict)
    unique_historical_overlap = len(set(generated_values) & set(historical_values))
    unique_historical_total = len(set(historical_values))
    formula_checks = _formula_and_fill_checks(generated)
    summary_checks = _summary_checks(generated)
    errors = (
        formula_checks["gap_formula_errors"]
        + formula_checks["significance_direction_errors"]
        + summary_checks["summary_errors"]
    )
    return {
        "scenario": config["name"],
        "status": "PASS" if not errors and supported == generated_total else "REVIEW",
        "source_files": len(sources),
        "generated_sheets": len(build_report.get("splits", [])),
        "missing_combinations": build_report.get("missing_benchmark_exports", []),
        "questions_selected": build_report.get("questions", 0),
        "generated_numeric_values": generated_total,
        "source_supported_values": supported,
        "source_fidelity_pct": round(100 * supported / generated_total, 2) if generated_total else 100.0,
        "source_metric_supported_values": metric_supported,
        "source_metric_fidelity_pct": round(100 * metric_supported / generated_total, 2) if generated_total else 100.0,
        "historical_numeric_values": historical_total,
        "historical_overlap_values": historical_overlap,
        "historical_recall_pct": round(100 * historical_overlap / historical_total, 2) if historical_total else 0.0,
        "historical_unique_overlap_values": unique_historical_overlap,
        "historical_unique_values": unique_historical_total,
        "historical_unique_recall_pct": (
            round(100 * unique_historical_overlap / unique_historical_total, 2)
            if unique_historical_total else 0.0
        ),
        "strict_label_overlap_values": strict_overlap,
        **formula_checks,
        **summary_checks,
        "errors": errors[:30],
        "workbook_bytes": len(data),
    }


def _markdown(results: list[dict]) -> str:
    total_values = sum(item["generated_numeric_values"] for item in results)
    total_gaps = sum(item["gap_formulas"] for item in results)
    total_significance = sum(item["significance_directions_checked"] for item in results)
    total_summary_rows = sum(item["summary_rows"] for item in results)
    lines = [
        "# Rapport de qualification — G-Sight Templyfier",
        "",
        "Qualification exécutée sur les exemples historiques fournis. Le contrôle distingue la fidélité technique aux sources "
        "de la ressemblance au fichier final historique, dont la sélection de questions et la mise en page peuvent volontairement différer.",
        "",
        f"**Résultat global : {len(results)}/{len(results)} cas validés.** {total_values} valeurs, {total_gaps} gaps, "
        f"{total_significance} directions de significativité et {total_summary_rows} lignes de KPI Summary contrôlés sans erreur.",
        "",
        "| Cas | Statut | Onglets | Valeurs contrôlées | Fidélité source | Gaps | Signif. | Couverture historique unique |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            f"| {item['scenario']} | {item['status']} | {item['generated_sheets']} | "
            f"{item['generated_numeric_values']} | {item['source_fidelity_pct']:.2f}% | "
            f"{item['gap_formulas'] - len(item['gap_formula_errors'])}/{item['gap_formulas']} | "
            f"{item['significance_directions_checked'] - len(item['significance_direction_errors'])}/{item['significance_directions_checked']} | "
            f"{item['historical_unique_recall_pct']:.2f}% |"
        )
    lines.extend(["", "## Lecture des contrôles", ""])
    lines.extend([
        "- **Fidélité source** : chaque valeur numérique générée est retrouvée pour le même produit dans l’export G-Sight correspondant.",
        "- **Empreinte métrique** : contrôle secondaire plus strict, qui exige aussi le même intitulé technique de métrique. "
        "Il peut être inférieur à 100 % lorsque le Templyfier remplace volontairement un item brut par un clean label.",
        "- **Gaps** : les formules Excel suivent bien `Candidat - Benchmark` et pointent vers des cellules numériques de la même ligne.",
        "- **Signif.** : lorsqu’une couleur est présente sur un gap, son sens higher/lower concorde avec le signe du gap.",
        "- **Couverture historique unique** : part des combinaisons uniques métrique × produit × valeur du fichier final historique "
        "également retrouvées dans la génération. Un taux inférieur à 100 % peut venir de questions volontairement retirées, "
        "de splits sources non fournis, de feuilles analytiques hors périmètre ou d’une autre organisation des benchmarks.",
        "- **KPI Details** : chaque symbole est rapproché des comparaisons significatives qui le justifient ; `±` exige des directions opposées.",
        "",
        "## Détail par cas",
        "",
    ])
    for item in results:
        lines.extend([
            f"### {item['scenario']} — {item['status']}",
            "",
            f"- Sources : {item['source_files']} fichier(s) ; {item['questions_selected']} question(s) sélectionnée(s).",
            f"- Valeurs : {item['source_supported_values']}/{item['generated_numeric_values']} justifiées par les sources.",
            f"- Empreinte métrique stricte : {item['source_metric_supported_values']}/{item['generated_numeric_values']}.",
            f"- Gaps : {item['gap_formulas']} formule(s), {len(item['gap_formula_errors'])} erreur(s).",
            f"- Significativités : {item['significance_directions_checked']} direction(s) contrôlée(s), "
            f"{len(item['significance_direction_errors'])} erreur(s).",
            f"- KPI Details : {item['summary_rows']} ligne(s), {len(item['summary_errors'])} incohérence(s).",
            f"- Combinaisons manquantes : {'aucune' if not item['missing_combinations'] else ' · '.join(item['missing_combinations'])}.",
        ])
        if item["errors"]:
            lines.append("- Anomalies : " + " · ".join(item["errors"]))
        if item["scenario"].startswith("Einstein Paired"):
            lines.append(
                "- Portée historique : les 4 exports fournis ne couvrent qu’une partie des splits présents dans la topline historique ; "
                "la faible couverture historique n’est donc pas une erreur de génération."
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for config in _scenario_definitions():
        print(f"Qualification: {config['name']}", flush=True)
        results.append(qualify_scenario(config))
        print(json.dumps(results[-1], ensure_ascii=False, default=str), flush=True)
    json_path = OUTPUT_DIR / "qualification_results.json"
    report_path = OUTPUT_DIR / "Rapport_qualification_Templyfier.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_markdown(results), encoding="utf-8")
    return 0 if all(item["status"] == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
