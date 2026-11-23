#!/usr/bin/env python3

import csv
import re
import sys
from pathlib import Path


FIELDNAMES = [
    "complex",
    "structure",
    "intermolecular_contacts",
    "charged_charged_contacts",
    "charged_polar_contacts",
    "charged_apolar_contacts",
    "polar_polar_contacts",
    "apolar_polar_contacts",
    "apolar_apolar_contacts",
    "percentage_apolar_nis_residues",
    "percentage_charged_nis_residues",
    "predicted_binding_affinity_kcal_mol",
    "predicted_dissociation_constant_m",
]


PATTERNS = {
    "structure": r"\[\+\] Processing structure\s+(.+)",
    "intermolecular_contacts": r"\[\+\] No\. of intermolecular contacts:\s+([+-]?\d+(?:\.\d+)?)",
    "charged_charged_contacts": r"\[\+\] No\. of charged-charged contacts:\s+([+-]?\d+(?:\.\d+)?)",
    "charged_polar_contacts": r"\[\+\] No\. of charged-polar contacts:\s+([+-]?\d+(?:\.\d+)?)",
    "charged_apolar_contacts": r"\[\+\] No\. of charged-apolar contacts:\s+([+-]?\d+(?:\.\d+)?)",
    "polar_polar_contacts": r"\[\+\] No\. of polar-polar contacts:\s+([+-]?\d+(?:\.\d+)?)",
    "apolar_polar_contacts": r"\[\+\] No\. of apolar-polar contacts:\s+([+-]?\d+(?:\.\d+)?)",
    "apolar_apolar_contacts": r"\[\+\] No\. of apolar-apolar contacts:\s+([+-]?\d+(?:\.\d+)?)",
    "percentage_apolar_nis_residues": r"\[\+\] Percentage of apolar NIS residues:\s+([+-]?\d+(?:\.\d+)?)",
    "percentage_charged_nis_residues": r"\[\+\] Percentage of charged NIS residues:\s+([+-]?\d+(?:\.\d+)?)",
    "predicted_binding_affinity_kcal_mol": r"\[\+\+\] Predicted binding affinity \(kcal\.mol-1\):\s+([+-]?\d+(?:\.\d+)?)",
    "predicted_dissociation_constant_m": r"\[\+\+\] Predicted dissociation constant \(M\).*?:\s+([+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?)",
}


def extract_value(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return ""


def parse_prodigy_txt(txt_file: Path) -> dict:
    text = txt_file.read_text(encoding="utf-8", errors="replace")

    complex_name = txt_file.name.replace(".prodigy.txt", "")

    row = {
        "complex": complex_name,
    }

    for column, pattern in PATTERNS.items():
        row[column] = extract_value(pattern, text)

    return row


def main():
    if len(sys.argv) != 3:
        print("Usage: make_prodigy_csv.py <input_dir> <output_csv>")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    output_csv = Path(sys.argv[2])

    if not input_dir.exists():
        print(f"[ERROR] Input directory not found: {input_dir}")
        sys.exit(1)

    txt_files = sorted(input_dir.rglob("*.prodigy.txt"))

    if not txt_files:
        print(f"[ERROR] No .prodigy.txt files found in: {input_dir}")
        sys.exit(1)

    rows = []

    for txt_file in txt_files:
        print(f"[INFO] Parsing: {txt_file}")

        if txt_file.stat().st_size == 0:
            print(f"[WARNING] File is empty: {txt_file}")
            continue

        row = parse_prodigy_txt(txt_file)

        if not row["predicted_binding_affinity_kcal_mol"]:
            print(f"[WARNING] Binding affinity not found in: {txt_file}")

        rows.append(row)

    if not rows:
        print("[ERROR] No valid PRODIGY outputs were parsed.")
        sys.exit(1)

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=FIELDNAMES,
            delimiter=";"
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"[INFO] CSV created: {output_csv}")
    print(f"[INFO] Parsed {len(rows)} file(s).")


if __name__ == "__main__":
    main()