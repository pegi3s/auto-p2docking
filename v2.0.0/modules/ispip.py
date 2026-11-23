#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

ispip_autop2_version = "2.0.0"
ispip_docker_version = "latest"
ispip_program_version = "unknown"
ispip_ref = ""
ispip_doi = ""


def main():
    global ispip_autop2_version, ispip_docker_version, ispip_ref, ispip_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: ispip.py <input_dir> <out_dir> <prefix>")

    input_dir, output_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("ispip_docker_c_version"):
        ispip_autop2_version = "?"
        ispip_docker_version = os.environ["ispip_docker_c_version"]
        ispip_ref = "?"
        ispip_doi = "?"

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")
    ispip_input_csv = os.environ.get("ispip_input_csv", "")

    input_path = f"/data/{input_dir}"
    output_path = f"/data/{output_dir}"
    intermediate_path = f"/data/{prefix}ispip"

    if not os.path.isdir(input_path):
        print("Error: input directory does not exist:")
        sys.exit(input_path)

    os.makedirs(output_path, exist_ok=True)
    os.makedirs(intermediate_path, exist_ok=True)
    os.makedirs("/data/files_to_keep", exist_ok=True)

    print("Searching for ISPIP input CSV files in:")
    print(input_path)

    if ispip_input_csv:
        csv_path = os.path.join(input_path, ispip_input_csv)
        if not os.path.isfile(csv_path):
            print("Error: ISPIP input CSV defined in config was not found:")
            sys.exit(csv_path)
        csv_files = [csv_path]
    else:
        csv_files = sorted(glob.glob(os.path.join(input_path, "*.csv")))

    if not csv_files:
        print("Error: no CSV input files found in:")
        print(input_path)
        print("Either place a .csv file there or define:")
        print("ispip_input_csv=input.csv")
        sys.exit("in /data/config")

    print("CSV files selected for ISPIP:")
    for csv_file in csv_files:
        print(f"  {csv_file}")

    summary_file = os.path.join(output_path, "ispip_runs.csv")
    with open(summary_file, "w") as f:
        f.write("input_csv;output_directory\n")

    for source_csv in csv_files:
        input_name = os.path.splitext(os.path.basename(source_csv))[0]

        module_dir = os.path.join(intermediate_path, input_name)
        work_dir = os.path.join(module_dir, "work")
        work_output_dir = os.path.join(work_dir, "output")
        final_output_dir = os.path.join(output_path, input_name)

        host_work_dir = f"{host_dir}/{prefix}ispip/{input_name}/work"

        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(work_output_dir, exist_ok=True)
        os.makedirs(final_output_dir, exist_ok=True)

        shutil.copy2(source_csv, os.path.join(work_dir, "input.csv"))

        subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{host_work_dir}:/data",
                f"pegi3s/ispip:{ispip_docker_version}",
                "-i", "/data/input.csv",
                "-of", "/data/output",
            ],
        )

        if not os.listdir(work_output_dir):
            print("Error: ISPIP produced no output for:")
            print(source_csv)
            print("Work output dir:")
            sys.exit(work_output_dir)

        for name in os.listdir(work_output_dir):
            src = os.path.join(work_output_dir, name)
            dst = os.path.join(final_output_dir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        with open(summary_file, "a") as f:
            f.write(f"{os.path.basename(source_csv)};{final_output_dir}\n")

        print("Finished ISPIP for:")
        print(input_name)

    record_version(
        f'ispip {ispip_autop2_version},pegi3s/ispip:{ispip_docker_version},'
        f'ISPIP {ispip_program_version},"{ispip_ref}","{ispip_doi}"'
    )

if __name__ == "__main__":
    print("Running: ISPIP", flush=True)
    main()
