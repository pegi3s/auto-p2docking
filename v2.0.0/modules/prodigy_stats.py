#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

prodigy_stats_autop2_version = "2.0.0"
prodigy_stats_ref = ""
prodigy_stats_doi = ""


def main():
    if len(sys.argv) < 4:
        sys.exit(
            "Usage: prodigy_stats.py "
            "<input_dir> <output_dir> <prefix>"
        )

    input_dir, output_dir, prefix = (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
    )

    load_config()

    host_dir = os.environ.get("dir", "")
    print("Running: PRODIGY_STATS", flush=True)

    input_path = f"/data/{input_dir}"
    output_path = f"/data/{output_dir}"
    input_csv = (
        f"{input_path}/prodigy_results.csv"
    )

    mounted_input_path = (
        f"{host_dir}/{input_dir}"
    )

    mounted_output_path = (
        f"{host_dir}/{output_dir}"
    )

    if not os.path.isfile(input_csv):
        sys.exit(
            f"Error: Input file {input_csv} not found"
        )

    os.makedirs(
        output_path,
        exist_ok=True,
    )

    work_path = (
        f"/data/{prefix}prodigy_stats"
    )

    mounted_work_path = (
        f"{host_dir}/{prefix}prodigy_stats"
    )

    os.makedirs(
        work_path,
        exist_ok=True,
    )

    if not os.path.isfile(
        "/opt/prodigy_stats.R"
    ):
        sys.exit(
            "Error: /opt/prodigy_stats.R not found"
        )

    shutil.copy2(
        "/opt/prodigy_stats.R",
        f"{work_path}/prodigy_stats.R",
    )

    # Hide routine R stdout (e.g. "null device 1") while preserving stderr.
    # If Docker/R fails, show the captured output before exiting.
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{mounted_input_path}:/input",
            "-v",
            f"{mounted_output_path}:/output",
            "-v",
            f"{mounted_work_path}:/scripts",
            "pegi3s/r_project",
            "Rscript",
            "/scripts/prodigy_stats.R",
            "/input/prodigy_results.csv",
            "/output",
        ],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout.rstrip(), file=sys.stderr)
        sys.exit(f"Error: PRODIGY_STATS failed with exit code {result.returncode}")

    # Keep genuine warnings/errors from tool stdout, not progress chatter.
    for line in (result.stdout or "").splitlines():
        if line.lstrip().lower().startswith(("warning", "[warning]", "error", "[error]")):
            print(line, file=sys.stderr)

    summary_file = os.path.join(
        output_path,
        "prodigy_summary_stats.csv",
    )

    if not os.path.isfile(summary_file):
        sys.exit(
            "Error: prodigy_stats did not create "
            "prodigy_summary_stats.csv"
        )

    record_version(
        f"prodigy_stats "
        f"{prodigy_stats_autop2_version}"
    )


if __name__ == "__main__":
    main()

