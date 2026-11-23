#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

prodigy_list_autop2_version = "2.0.0"


def main():
    if len(sys.argv) < 4:
        sys.exit("Usage: prodigy_list.py <input_dir> <output_dir> <prefix>")

    input_dir, output_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    print("Running: PRODIGY_LIST", flush=True)

    input_path = f"/data/{input_dir}"
    final_output_dir = f"/data/{output_dir}"
    csv_output = f"{final_output_dir}/prodigy_results.csv"
    intermediate_dir = f"/data/{prefix}prodigy_list"

    if not os.path.isdir(input_path):
        sys.exit(f"Error: input directory does not exist:\n{input_path}")

    os.makedirs(final_output_dir, exist_ok=True)
    os.makedirs(intermediate_dir, exist_ok=True)
    os.makedirs("/data/files_to_keep", exist_ok=True)

    # Hide routine per-file parser messages. Preserve stderr and show any
    # captured stdout if the helper fails (some errors are printed to stdout).
    result = subprocess.run(
        ["python3", "/opt/make_prodigy_csv.py", input_path, csv_output],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout.rstrip(), file=sys.stderr)
        sys.exit(f"Error: make_prodigy_csv.py failed with exit code {result.returncode}")

    # Keep genuine warnings/errors from tool stdout, not progress chatter.
    for line in (result.stdout or "").splitlines():
        if line.lstrip().lower().startswith(("warning", "[warning]", "error", "[error]")):
            print(line, file=sys.stderr)

    if not os.path.isfile(csv_output) or os.path.getsize(csv_output) == 0:
        sys.exit(f"Error: CSV was not created or is empty:\n{csv_output}")

    shutil.copy2(csv_output, "/data/files_to_keep/prodigy_results.csv")

    record_version(f"prodigy_list {prodigy_list_autop2_version}")


if __name__ == "__main__":
    main()

