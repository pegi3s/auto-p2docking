#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

geneid2uniprotkb_autop2_version = "2.0.0"
geneid2uniprotkb_docker_version = "1.1.1"


def main():
    global geneid2uniprotkb_autop2_version, geneid2uniprotkb_docker_version

    if len(sys.argv) < 4:
        sys.exit("Usage: geneid2uniprotkb.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("geneid2uniprotkb_docker_c_version"):
        geneid2uniprotkb_autop2_version = "?"
        geneid2uniprotkb_docker_version = os.environ["geneid2uniprotkb_docker_c_version"]

    host_dir = os.environ.get("dir", "")
    work_dir = f"/data/{prefix}geneid2uniprotkb"
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    input_path = os.path.join(work_dir, "input")
    sources = sorted(
        p for p in glob.glob(f"/data/{input_dir}/*") if os.path.isfile(p)
    )
    with open(input_path, "w") as out_f:
        for src in sources:
            with open(src) as in_f:
                out_f.write(in_f.read())

    max_retries = 5
    retry_delay = 30
    output_path = os.path.join(work_dir, "output.tsv")

    for attempt in range(1, max_retries + 1):
        subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{host_dir}/{prefix}geneid2uniprotkb:/data",
                "-w", "/data",
                f"pegi3s/id-mapping:{geneid2uniprotkb_docker_version}",
                "gene-id-to-uniprotkb", "input", "output.tsv",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        not_found = False
        if os.path.isfile(output_path):
            with open(output_path) as f:
                not_found = "Not found" in f.read()

        if not not_found:
            break
        if attempt < max_retries:
            print(
                "Some GeneIDs returned 'Not found' (possibly due to internet access "
                f"issues). Retrying in {retry_delay} seconds (attempt {attempt}/{max_retries})..."
            )
            time.sleep(retry_delay)

    uniprotkb_list_path = os.path.join(work_dir, "uniprotkb_list")
    rows = []
    if os.path.isfile(output_path):
        with open(output_path) as f:
            rows = f.read().splitlines()
    col2 = [row.split("\t")[1] if len(row.split("\t")) > 1 else "" for row in rows]
    col2 = col2[1:]
    with open(uniprotkb_list_path, "w") as f:
        for value in col2:
            f.write(value + "\n")

    shutil.copy2(uniprotkb_list_path, final_dir)

    record_version(
        f"geneid2uniprotkb {geneid2uniprotkb_autop2_version},"
        f"pegi3s/id-mapping:{geneid2uniprotkb_docker_version}"
    )


if __name__ == "__main__":
    print("Converting GeneIDs to the reference UniProtKB accession number (listed in NCBI)", flush=True)
    print(
        "GeneIDs that cannot be converted are ignored. When there are more than one "
        "reference UniProtKB accession number both will be kept", flush=True
    )
    main()
