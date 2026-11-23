#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version

pisaccp4_autop2_version = "2.0.0"
pisaccp4_docker_version = "7.0.2"
pisaccp4_program_version = "7.0"
pisaccp4_ref = "Potterton et al. (2018)"
pisaccp4_doi = "10.1107/S2059798317016035"


def _rename_key(name):
    """Equivalent of `rev | cut -d'_' -f3- | rev` / `f2-` / `f1|cut -d'.' -f1`:
    splits a filename into everything up to (but not including) the last
    two underscore-separated segments ("prefix1"), everything up to (but
    not including) the last segment ("removed_part"), and the portion of
    the last segment before its first dot ("suffix")."""
    parts = name.split("_")
    prefix1 = "_".join(parts[:-2]) if len(parts) > 2 else ""
    removed_part = "_".join(parts[:-1]) if len(parts) > 1 else ""
    suffix = parts[-1].split(".", 1)[0]
    return prefix1, removed_part, suffix


def main():
    global pisaccp4_autop2_version, pisaccp4_docker_version, pisaccp4_ref, pisaccp4_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: pisa_ccp4_extract.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("pisaccp4_docker_c_version"):
        pisaccp4_autop2_version = "?"
        pisaccp4_docker_version = os.environ["pisaccp4_docker_c_version"]
        pisaccp4_ref = "?"
        pisaccp4_doi = "?"

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    receptor_files = sorted(
        p for p in glob.glob(f"/data/{project}/PDBs/Receptor/*") if os.path.isfile(p)
    )
    pdb1 = os.path.basename(receptor_files[0])

    with open(f"/data/{project}/PDBs/input_ligand.txt") as f:
        pdb2 = f.readline().rstrip("\n")

    pdb1_sem_pdb = re.sub(r"\.pdb$", "", os.path.basename(pdb1))
    pdb2_sem_pdb = re.sub(r"\.pdb$", "", os.path.basename(pdb2))

    warning_path = f"/data/{project}/intermediate_files/warning_files/do_not_run.{pdb2}"
    if pdb1_sem_pdb == pdb2_sem_pdb or os.path.isfile(warning_path):
        return

    final_group_dir = f"/data/{out_dir}/{pdb2_sem_pdb}"
    os.makedirs(final_group_dir, exist_ok=True)

    work_dir = f"/data/{prefix}PISA_CCP4"
    tsv_dir = os.path.join(work_dir, "tsv_files", pdb2_sem_pdb)
    input_work_dir = os.path.join(work_dir, "input", pdb2_sem_pdb)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(tsv_dir, exist_ok=True)
    os.makedirs(input_work_dir, exist_ok=True)

    for path in sorted(glob.glob(f"/data/{input_dir}/{pdb2_sem_pdb}/*")):
        shutil.copy2(path, input_work_dir)

    removed_part = ""
    for name in sorted(os.listdir(input_work_dir)):
        prefix1, removed_part, suffix = _rename_key(name)
        new_name = f"{prefix1}_{suffix}"
        os.rename(os.path.join(input_work_dir, name), os.path.join(input_work_dir, f"{new_name}.pdb"))

    docker_input = f"{prefix}PISA_CCP4/input/{pdb2_sem_pdb}"
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{host_dir}:/data",
            f"pegi3s/ccp4:{pisaccp4_docker_version}",
            "bash", "-c",
            f'/ccp4/bin/run /data/{docker_input} "/data/{prefix}PISA_CCP4/{pdb2_sem_pdb}"',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ccp4_output_dir = os.path.join(work_dir, pdb2_sem_pdb)
    names1 = sorted(os.listdir(ccp4_output_dir)) if os.path.isdir(ccp4_output_dir) else []
    names1 = [
        re.sub(r"pisa\.cfg$", "", re.sub(r"tsv_files$", "", name)).strip()
        for name in names1
    ]
    names1 = [name for name in names1 if name]

    for name1 in names1:
        parts = name1.split("_")
        suffix1 = parts[-1] if parts else name1
        final_name = f"{removed_part}_{suffix1}"

        src_tsv = os.path.join(ccp4_output_dir, name1, "interface_1_info.tsv")
        renamed_tsv = os.path.join(ccp4_output_dir, name1, f"{final_name}.tsv")
        os.rename(src_tsv, renamed_tsv)
        shutil.copy2(renamed_tsv, tsv_dir)

    resid_lines = []
    for name2 in sorted(os.listdir(tsv_dir)):
        tsv_path = os.path.join(tsv_dir, name2)
        with open(tsv_path) as f:
            tsv_lines = f.read().splitlines()

        residues_first = tsv_lines[1].split("=", 1)[1] if len(tsv_lines) > 1 and "=" in tsv_lines[1] else ""
        residues_second = tsv_lines[4].split("=", 1)[1] if len(tsv_lines) > 4 and "=" in tsv_lines[4] else ""

        resid_lines.append(f"{name2}={residues_first}/{residues_second}")

    max_first = -1
    atual_second = -1
    selected_file = ""
    for line in resid_lines:
        file_, residues = line.split("=", 1)
        residues_first1_str, residues_second1_str = residues.split("/", 1)
        residues_first1 = int(residues_first1_str)
        residues_second1 = int(residues_second1_str)

        if residues_first1 > max_first or (residues_first1 == max_first and residues_second1 > atual_second):
            max_first = residues_first1
            atual_second = residues_second1
            selected_file = file_

    pdb_name = selected_file.split(".", 1)[0]
    shutil.copy2(os.path.join(tsv_dir, f"{pdb_name}.tsv"), final_group_dir)
    shutil.copy2(f"/data/{input_dir}/{pdb2_sem_pdb}/{pdb_name}.pdb", final_group_dir)

    shutil.rmtree(os.path.join(work_dir, "input"), ignore_errors=True)
    shutil.rmtree(os.path.join(work_dir, "tsv_files"), ignore_errors=True)

    record_version(
        f'pisa_ccp4_extract {pisaccp4_autop2_version},pegi3s/ccp4:{pisaccp4_docker_version},'
        f'CCP4 {pisaccp4_program_version},"{pisaccp4_ref}","{pisaccp4_doi}"'
    )
    record_refs(f'pisaccp4_ref="{pisaccp4_ref}"\npisaccp4_doi="{pisaccp4_doi}"\n')


if __name__ == "__main__":
    print("Running PISA-CCP4-extract", flush=True)
    main()
