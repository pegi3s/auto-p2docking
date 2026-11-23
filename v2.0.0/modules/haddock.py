#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import check_sites_files, load_config, record_refs, record_version

haddock_autop2_version = "2.0.0"
haddock_docker_version = "latest"
haddock_program_version = "v2.4-2023.08"
haddock_ref = ""
haddock_doi = ""


def _split_number(filename):
    """Equivalent of `rev | cut -d'_' -f1 | rev | cut -d'.' -f1`: the last
    underscore-separated segment of the filename, up to its first dot."""
    last_segment = filename.rsplit("_", 1)[-1]
    return last_segment.split(".", 1)[0]


def main():
    global haddock_autop2_version, haddock_docker_version, haddock_ref, haddock_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: haddock.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("haddock_docker_c_version"):
        haddock_autop2_version = "?"
        haddock_docker_version = os.environ["haddock_docker_c_version"]
        haddock_ref = "?"
        haddock_doi = "?"

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    receptor_files = sorted(
        p for p in glob.glob(f"/data/{project}/PDBs/Receptor/*") if os.path.isfile(p)
    )
    haddock_pdb1 = os.path.basename(receptor_files[0])

    with open(f"/data/{project}/PDBs/input_ligand.txt") as f:
        haddock_pdb2 = f.readline().rstrip("\n")

    pdb2 = re.sub(r"\.pdb$", "", os.path.basename(haddock_pdb2))
    pdb1 = re.sub(r"\.pdb$", "", os.path.basename(haddock_pdb1))

    warning_path = f"/data/{project}/intermediate_files/warning_files/do_not_run.{pdb2}"
    if pdb2 == pdb1 or os.path.isfile(warning_path):
        return

    check_sites_files(input_dir, pdb1, pdb2)

    run_dir = f"/data/{prefix}HADDOCK_run/{pdb2}"
    final_dir = f"/data/{out_dir}"
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    for path in sorted(glob.glob(f"/data/{input_dir}/{pdb2}/*.sites")):
        shutil.copy2(path, run_dir)
    for path in sorted(glob.glob(f"/data/{input_dir}/{pdb1}/*.sites")):
        shutil.copy2(path, run_dir)
    for path in sorted(glob.glob(f"/data/{project}/PDBs/Receptor/*")):
        if os.path.isfile(path):
            shutil.copy2(path, run_dir)
    shutil.copy2(f"/data/{project}/PDBs/Ligands/{haddock_pdb2}", run_dir)

    haddock_active_pdb1 = f"{pdb1}_active.sites"
    haddock_active_pdb2 = f"{pdb2}_active.sites"
    haddock_passive_pdb1 = f"{pdb1}_passive.sites"
    haddock_passive_pdb2 = f"{pdb2}_passive.sites"
    haddock_all_files = os.environ.get("haddock_all_files", "")

    with open(os.path.join(run_dir, "haddock_config"), "w") as f:
        f.write(f"ACTIVE1={haddock_active_pdb1}\n")
        f.write(f"ACTIVE2={haddock_active_pdb2}\n")
        f.write(f"PASSIVE1={haddock_passive_pdb1}\n")
        f.write(f"PASSIVE2={haddock_passive_pdb2}\n")
        f.write(f"PDB1={haddock_pdb1}\n")
        f.write(f"PDB2={haddock_pdb2}\n")
        f.write(f"ALL_FILES={haddock_all_files}\n")

    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"/{host_dir}/{prefix}HADDOCK_run/{pdb2}:/data",
            f"pegi3s/haddock24:{haddock_docker_version}",
            "bash", "-c", "python3 main",
        ],
    )

    results_dir = os.path.join(run_dir, "haddock_results")
    renamed_results_dir = os.path.join(run_dir, f"haddock_results_{pdb1}_{pdb2}")
    if os.path.isdir(results_dir):
        shutil.move(results_dir, renamed_results_dir)

    final_group_dir = os.path.join(final_dir, pdb2)
    os.makedirs(final_group_dir, exist_ok=True)

    for root, _dirs, files in os.walk(renamed_results_dir):
        for name in files:
            if name.endswith(".pdb"):
                shutil.copy2(os.path.join(root, name), final_group_dir)

    for arquivo in sorted(glob.glob(os.path.join(final_group_dir, "*.pdb"))):
        number = _split_number(os.path.basename(arquivo))
        novo_nome = os.path.join(final_group_dir, f"{pdb1}_{pdb2}_HADDOCK_{number}.pdb")
        os.replace(arquivo, novo_nome)

    record_version(
        f'haddock {haddock_autop2_version},pegi3s/haddock24:{haddock_docker_version},'
        f'HADDOCK {haddock_program_version},"{haddock_ref}","{haddock_doi}"'
    )
    record_refs(f'haddock_ref="{haddock_ref}"\nhaddock_doi="{haddock_doi}"\n')


if __name__ == "__main__":
    print("Running HADDOCK", flush=True)
    main()
