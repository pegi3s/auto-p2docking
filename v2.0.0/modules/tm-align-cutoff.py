#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version

tmaligncutoff_autop2_version = "2.0.0"
tmaligncutoff_docker_version = "1.0.2"
tmaligncutoff_program_version = "2022/04/15"
tmaligncutoff_ref = "Zhang e Skolnick (2005)"
tmaligncutoff_doi = "10.1093/nar/gki524"


def main():
    global tmaligncutoff_autop2_version, tmaligncutoff_docker_version
    global tmaligncutoff_ref, tmaligncutoff_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: tm-align-cutoff.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("tmaligncutoff_docker_c_version"):
        tmaligncutoff_autop2_version = "?"
        tmaligncutoff_docker_version = os.environ["tmaligncutoff_docker_c_version"]
        tmaligncutoff_ref = "?"
        tmaligncutoff_doi = "?"

    host_dir = os.environ.get("dir", "")
    tm_cutoff_ref = os.environ.get("tm_cutoff_ref", "")
    tm_cutoff_order = os.environ.get("tm_cutoff_order", "")

    work_dir = f"/data/{prefix}TM-align-cutoff"
    input_work_dir = os.path.join(work_dir, "input")
    tmalign_dir = os.path.join(work_dir, "tm-align")
    final_dir = f"/data/{out_dir}"
    input_path = f"/data/{input_dir}"

    os.makedirs(input_work_dir, exist_ok=True)
    os.makedirs(tmalign_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    pdb_names = sorted(name for name in os.listdir(input_path) if name.endswith(".pdb"))
    unique_prefixes = sorted(set(name.split("_", 1)[0] for name in pdb_names))

    for pdb_prefix in unique_prefixes:
        group = [name for name in pdb_names if pdb_prefix in name]

        for first in group:
            for second in group:
                if first == second:
                    continue

                html1 = os.path.join(tmalign_dir, f"{first}.{second}.html")
                html2 = os.path.join(tmalign_dir, f"{second}.{first}.html")
                if os.path.isfile(html1) or os.path.isfile(html2):
                    continue

                shutil.copy2(os.path.join(input_path, first), input_work_dir)
                shutil.copy2(os.path.join(input_path, second), input_work_dir)

                subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "-v", f"{host_dir}:/data",
                        f"pegi3s/tm-align_server:{tmaligncutoff_docker_version}",
                        "bash", "-c",
                        f"/opt/run {input_work_dir} {tmalign_dir}",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                results_html = os.path.join(tmalign_dir, "results.html")
                if os.path.isfile(results_html):
                    shutil.move(results_html, html1)

    above_list = []
    under_list = []

    for html_path in sorted(glob.glob(os.path.join(tmalign_dir, "*"))):
        with open(html_path) as f:
            content = f.read()

        matches = re.findall(r"TM-score=\s*([0-9.]*)", content)[:2]
        tm_score = max(matches, key=float) if matches else ""

        just_filename = os.path.basename(html_path).split("_")[0]

        # If the server failed to return a usable TM-score for this pair,
        # treat it like a below-cutoff result (keep both files) instead of
        # risking a bash arithmetic error on an empty/non-numeric value.
        if not re.fullmatch(r"[0-9]+\.?[0-9]*", tm_score):
            under_list.append(just_filename)
            continue

        # check if TM-score is higher than the cutoff value
        if float(tm_score) > float(tm_cutoff_ref):
            above_list.append(just_filename)
        else:
            under_list.append(just_filename)

    order_tokens = tm_cutoff_order.split("-")

    # copy files by specified order
    for filename in above_list:
        for database in order_tokens:
            candidate = os.path.join(input_path, f"{filename}_{database}.pdb")
            if os.path.isfile(candidate):
                shutil.copy2(candidate, final_dir)
                break

    # keep both files if TM-score is below the one specified
    for name in under_list:
        for path in glob.glob(os.path.join(input_path, f"{name}_*.pdb")):
            shutil.copy2(path, final_dir)

    tm_scores_lines = []
    for html_path in sorted(glob.glob(os.path.join(tmalign_dir, "*.pdb.html"))):
        name = os.path.basename(html_path)
        with open(html_path) as f:
            matches_text = "".join(line for line in f if "TM-score=" in line)
        joined = " ".join(f"{name} {matches_text}".split())
        tm_scores_lines.append(joined.replace("TM-score", "\tTM-score"))

    with open(os.path.join(tmalign_dir, "tm_scores_list"), "w") as f:
        for line in tm_scores_lines:
            f.write(line + "\n")
            
    tm_scores_path = os.path.join(tmalign_dir, "tm_scores_list")

    with open(tm_scores_path, "w") as f:
        for line in tm_scores_lines:
            f.write(line + "\n")

    shutil.copy2(
        tm_scores_path,
        os.path.join(final_dir, "tm_scores_list"),
    )

    record_version(
        f'tm-align-cutoff {tmaligncutoff_autop2_version},'
        f'pegi3s/tm-align_server:{tmaligncutoff_docker_version},'
        f'TM-align server {tmaligncutoff_program_version},'
        f'"{tmaligncutoff_ref}","{tmaligncutoff_doi}"'
    )
    record_refs(
        f'tmaligncutoff_ref="{tmaligncutoff_ref}"\n'
        f'tmaligncutoff_doi="{tmaligncutoff_doi}"\n'
    )


if __name__ == "__main__":
    print("Determining TM-align scores and selecting files based on specified cutoff value and file to keep", flush=True)
    main()
