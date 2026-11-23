#!/usr/bin/env python3
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version
import pattern

getpattern_autop2_version = "2.0.0"


def _to_number(token):
    """Equivalent of awk's implicit string-to-number conversion (parses a
    leading numeric prefix, defaults to 0 for non-numeric fields)."""
    match = re.match(r"[+-]?[0-9]*\.?[0-9]+", token)
    if not match:
        return 0.0
    return float(match.group())


def main():
    if len(sys.argv) < 4:
        sys.exit("Usage: get_pattern.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    work_dir = f"/data/{prefix}get_pattern"
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    with open(f"/data/{input_dir}/tabulated.tsv") as f:
        raw_lines = f.read().splitlines()

    extracted_lines = []
    for line in raw_lines:
        fields = line.split("\t")
        extracted_lines.append("\t".join(fields[1:]))
    extracted_lines = extracted_lines[2:]

    with open(os.path.join(work_dir, "extracted_lines.tsv"), "w") as f:
        for line in extracted_lines:
            f.write(line + "\n")

    total_lines = len(extracted_lines)

    # Sum each (whitespace-split) column across all lines.
    sum_array = []
    for line in extracted_lines:
        tokens = line.split()
        for i, tok in enumerate(tokens):
            value = _to_number(tok)
            if i < len(sum_array):
                sum_array[i] += value
            else:
                sum_array.append(value)

    temp_values = []
    for total in sum_array:
        avg = (total / total_lines) * 100 if total_lines else 0.0
        temp_values.append(f"{avg:.0f}")
    temp_line = "\t".join(temp_values)

    # Comparison with pattern_cutoff
    pattern_cutoff = _to_number(os.environ.get("pattern_cutoff", "0"))
    processed_values = []
    for tok in temp_values:
        value = _to_number(tok)
        processed_values.append("1" if value >= pattern_cutoff else "0")
    processed_line = "\t".join(processed_values)

    with open(os.path.join(work_dir, "processed.tsv"), "w") as f:
        f.write(processed_line + "\n")

    output_path = os.path.join(final_dir, "pattern_positions.txt")
    linha = re.sub(r"\s+", "", processed_line)

    seq_pattern = os.environ.get("pattern", "")
    results = pattern.find_all_occurrences_re(linha, seq_pattern)
    pattern.write_positions_to_file(output_path, results)

    record_version(f"get_pattern {getpattern_autop2_version}")


if __name__ == "__main__":
    print("Running get_pattern", flush=True)
    main()
