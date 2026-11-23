#!/usr/bin/env python3
import glob
import itertools
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

tabulate_autop2_version = "2.0.0"


def _line_n(path, n):
    """Equivalent of `head -n | tail -1`: return line n (1-indexed) of a
    file, or "" if the file has fewer than n lines."""
    with open(path) as f:
        for i, line in enumerate(f, start=1):
            if i == n:
                return line.rstrip("\n")
    return ""


def _awk_to_int(token):
    """Equivalent of awk's implicit string-to-number conversion followed
    by `printf "%d"` (truncates toward zero; non-numeric fields become 0),
    with the "0.00" -> 0 special case the bash awk script hard-codes."""
    if token == "0.00":
        return "0"
    match = re.match(r"[+-]?[0-9]*\.?[0-9]+", token)
    if not match:
        return "0"
    return str(int(float(match.group())))


def main():
    if len(sys.argv) < 4:
        sys.exit("Usage: tabulate.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    work_dir = f"/data/{prefix}tabulate"
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)
    os.makedirs("/data/files_to_keep", exist_ok=True)

    for path in sorted(glob.glob(f"/data/{input_dir}/*/*.tsv")):
        shutil.copy2(path, work_dir)

    project = os.environ.get("project", "")
    pdbs_marker = f"/data/{project}/PDBs"
    os.makedirs(os.path.dirname(pdbs_marker), exist_ok=True)
    if os.path.exists(pdbs_marker):
        os.utime(pdbs_marker, None)
    else:
        open(pdbs_marker, "a").close()

    tmp1_lines = []
    tmp2_lines = []
    w = 0

    for file in sorted(glob.glob(os.path.join(work_dir, "*.tsv"))):
        if w < 1:
            b1 = _line_n(file, 9).replace("Structure 1", "Structure_1").replace(" ", "\t")
            b1 = re.sub(r"[0-9:]+", "", b1)
            b2 = _line_n(file, 8).replace(" ", "\t")
            tmp2_lines = [b2, b1]
            tmp1_lines = ["", ""]
            w = 2

        tmp1_lines.append(os.path.basename(file))

        line11 = _line_n(file, 11)
        converted = [_awk_to_int(tok) for tok in line11.split()]
        tmp2_lines.append("\t".join(converted))

    tabulated_path = os.path.join(work_dir, "tabulated.tsv")
    with open(tabulated_path, "w") as f:
        for a, b in itertools.zip_longest(tmp1_lines, tmp2_lines, fillvalue=""):
            f.write(f"{a}\t{b}\n")

    shutil.copy2(tabulated_path, os.path.join(final_dir, "tabulated.tsv"))

    record_version(f"tabulate {tabulate_autop2_version}")


if __name__ == "__main__":
    print("Creating a summary table for the receptor", flush=True)
    main()
