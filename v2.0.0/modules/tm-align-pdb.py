#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version

tmalignpdb_autop2_version = "2.0.0"
tmalignpdb_docker_version = "1.0.2"
tmalignpdb_program_version = "2022/04/15"
tmalignpdb_ref = "Zhang e Skolnick (2005)"
tmalignpdb_doi = "10.1093/nar/gki524"


def _best_digit_score(html_path):
    """Faithful reproduction (via the exact same shell pipeline) of:

        grep 'TM-score=' html | cut -f2,10 -d' ' | sort -g | tail -1 | sed "s/\\.//g"

    Returns the resulting digit string as an int, or None if the pipeline
    doesn't yield a plain non-negative integer string. This mirrors the
    guard already hardened into the bash module against "-gt on an
    empty/non-numeric string" ("unary operator expected") errors, without
    reimplementing cut/sort's field-splitting semantics from scratch.
    """
    if not os.path.isfile(html_path):
        return None
    result = subprocess.run(
        [
            "bash", "-c",
            f"grep 'TM-score=' \"{html_path}\" | cut -f2,10 -d' ' | sort -g | tail -1 | sed 's/\\.//g'",
        ],
        capture_output=True,
        text=True,
    )
    a = result.stdout.strip()
    if re.fullmatch(r"[0-9]+", a):
        return int(a)
    return None


def main():
    global tmalignpdb_autop2_version, tmalignpdb_docker_version
    global tmalignpdb_ref, tmalignpdb_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: tm-align-pdb.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("tmalignpdb_docker_c_version"):
        tmalignpdb_autop2_version = "?"
        tmalignpdb_docker_version = os.environ["tmalignpdb_docker_c_version"]
        tmalignpdb_ref = "?"
        tmalignpdb_doi = "?"

    host_dir = os.environ.get("dir", "")
    input_path = f"/data/{input_dir}"
    work_dir = f"/data/{prefix}TM-align-pdb"
    input_work_dir = os.path.join(work_dir, "input")
    input_pdb_dir = os.path.join(work_dir, "input_PDB")
    final_dir = f"/data/{out_dir}"

    os.makedirs(input_work_dir, exist_ok=True)
    os.makedirs(input_pdb_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    # Filter PDB: for every uniprot group that has a "*_PDB.pdb" reference
    # file, copy every file belonging to that group into input_PDB.
    pdb_pdb_files = sorted(
        name for name in os.listdir(input_path)
        if name.endswith("_PDB.pdb") and os.path.isfile(os.path.join(input_path, name))
    )
    copied_prefixes = []
    for name in pdb_pdb_files:
        uniprot = name.split("_")[0]
        if uniprot not in copied_prefixes:
            for path in sorted(glob.glob(os.path.join(input_path, f"{uniprot}_*.pdb"))):
                shutil.copy2(path, input_pdb_dir)
            copied_prefixes.append(uniprot)

    uniprot_groups = []
    seen = set()
    for name in sorted(os.listdir(input_pdb_dir)):
        if not name.endswith("_PDB.pdb"):
            continue
        uniprot = name.split("_")[0]
        if uniprot not in seen:
            uniprot_groups.append(uniprot)
            seen.add(uniprot)

    for uniprot in uniprot_groups:
        group_files = sorted(glob.glob(os.path.join(input_pdb_dir, f"{uniprot}_*")))
        refs = [f for f in group_files if os.path.basename(f).endswith("_PDB.pdb")]
        candidates = [f for f in group_files if not os.path.basename(f).endswith("_PDB.pdb")]

        b = 0
        best_name = None

        for ref_path in refs:
            ref_name = os.path.basename(ref_path)
            for cand_path in candidates:
                cand_name = os.path.basename(cand_path)

                shutil.copy2(ref_path, input_work_dir)
                shutil.copy2(cand_path, input_work_dir)

                html_file = os.path.join(work_dir, f"{ref_name}.{cand_name}.html")
                if not os.path.isfile(html_file):
                    subprocess.run(
                        [
                            "docker", "run", "--rm",
                            "-v", f"{host_dir}:/data",
                            f"pegi3s/tm-align_server:{tmalignpdb_docker_version}",
                            "bash", "-c",
                            f"/opt/run {input_work_dir} {work_dir}",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    results_html = os.path.join(work_dir, "results.html")
                    if os.path.isfile(results_html):
                        shutil.move(results_html, html_file)

                    for leftover in glob.glob(os.path.join(input_work_dir, "*")):
                        os.remove(leftover)

                    a = _best_digit_score(html_file)
                    if a is not None and a > b:
                        b = a
                        best_name = cand_name

        if best_name is not None:
            best_path = os.path.join(input_pdb_dir, best_name)
            if os.path.isfile(best_path):
                shutil.copy2(best_path, final_dir)

    tm_scores_lines = []
    for html_path in sorted(glob.glob(os.path.join(work_dir, "*.pdb.html"))):
        name = os.path.basename(html_path)
        with open(html_path) as f:
            matches = "".join(line for line in f if "TM-score=" in line)
        joined = " ".join(f"{name} {matches}".split())
        tm_scores_lines.append(joined.replace("TM-score", "\tTM-score"))

    with open(os.path.join(work_dir, "tm_scores_list"), "w") as f:
        for line in tm_scores_lines:
            f.write(line + "\n")

    for name in sorted(os.listdir(input_path)):
        path = os.path.join(input_path, name)
        if os.path.isfile(path):
            shutil.copy2(path, final_dir)

    # Final cleanup: reference-only files should not remain in the output.
    for leftover in glob.glob(os.path.join(final_dir, "*_PDB.pdb")):
        os.remove(leftover)

    record_version(
        f'tm-align-pdb {tmalignpdb_autop2_version},'
        f'pegi3s/tm-align_server:{tmalignpdb_docker_version},'
        f'TM-align server {tmalignpdb_program_version},'
        f'"{tmalignpdb_ref}","{tmalignpdb_doi}"'
    )
    record_refs(
        f'tmalignpdb_ref="{tmalignpdb_ref}"\n'
        f'tmalignpdb_doi="{tmalignpdb_doi}"\n'
    )


if __name__ == "__main__":
    print("Determining TM-align scores and selecting files", flush=True)
    main()
