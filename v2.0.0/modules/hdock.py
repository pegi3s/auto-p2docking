#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version

hdock_autop2_version = "2.0.0"
hdock_docker_version = "latest"
hdock_program_version = "1.1"
hdock_ref = "Yan et al. (2020)"
hdock_doi = "10.1038/s41596-020-0312-x"
hdocktopisa_docker_version = "0.22.2"


def _strip_one_trailing_space(line):
    """Equivalent of `sed -i 's/ $//g'`: removes at most one trailing
    space character per line (the pattern " $" can only match once per
    line even with the g flag, since it's anchored to the end)."""
    if line.endswith(" "):
        return line[:-1]
    return line


def main():
    global hdock_autop2_version, hdock_docker_version, hdock_ref, hdock_doi
    global hdocktopisa_docker_version

    if len(sys.argv) < 4:
        sys.exit("Usage: hdock.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("hdock_docker_c_version"):
        hdock_autop2_version = "?"
        hdock_docker_version = os.environ["hdock_docker_c_version"]
        hdock_ref = "?"
        hdock_doi = "?"

    if os.environ.get("hdocktopisa_docker_c_version"):
        hdock_autop2_version = "?"
        hdocktopisa_docker_version = os.environ["hdocktopisa_docker_c_version"]

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    receptor_files = sorted(
        p for p in glob.glob(f"/data/{project}/PDBs/Receptor/*") if os.path.isfile(p)
    )
    hdock_pdb1 = os.path.basename(receptor_files[0])

    with open(f"/data/{project}/PDBs/input_ligand.txt") as f:
        hdock_pdb2 = f.readline().rstrip("\n")

    pdb1_sem_pdb = re.sub(r"\.pdb$", "", hdock_pdb1)
    pdb2_sem_pdb = re.sub(r"\.pdb$", "", hdock_pdb2)

    if pdb1_sem_pdb == pdb2_sem_pdb:
        return

    work_dir = f"/data/{prefix}HDOCK_run"
    final_dir = f"/data/{out_dir}"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    shutil.copy2(f"/data/{project}/PDBs/Ligands/{hdock_pdb2}", work_dir)
    for path in sorted(glob.glob(f"/data/{input_dir}/*")):
        if os.path.isfile(path):
            shutil.copy2(path, work_dir)
    for path in sorted(glob.glob(f"/data/{project}/PDBs/Receptor/*")):
        if os.path.isfile(path):
            shutil.copy2(path, work_dir)

    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"/{host_dir}/{prefix}HDOCK_run:/data",
            f"pegi3s/hdock:{hdock_docker_version}",
            "bash", "-c",
            f"/exe/hdock /data/{hdock_pdb1} /data/{hdock_pdb2} -out /exe/Hdock.out && "
            f"/exe/createpl /exe/Hdock.out /exe/top100.pdb -nmax 100 -complex -models && "
            f"mkdir -p /data/results/{pdb2_sem_pdb} && cp *.pdb /data/results/{pdb2_sem_pdb}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    results_dir = os.path.join(work_dir, "results", pdb2_sem_pdb)
    final_group_dir = os.path.join(final_dir, pdb2_sem_pdb)
    os.makedirs(final_group_dir, exist_ok=True)

    for x in range(1, 101):
        name = f"model_{x}"
        model_path = os.path.join(results_dir, f"{name}.pdb")
        if os.path.isfile(model_path):
            with open(model_path) as f:
                lines = f.read().splitlines()
            with open(model_path, "w") as f:
                for line in lines:
                    f.write(_strip_one_trailing_space(line) + "\n")

        name1 = f"{pdb1_sem_pdb}_{pdb2_sem_pdb}_HDOCK_{x}"

        subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"/{host_dir}/{prefix}HDOCK_run/results/{pdb2_sem_pdb}:/data",
                f"pegi3s/utilities:{hdocktopisa_docker_version}",
                "hdock_to_PDBePISA_conversion", f"/data/{name}.pdb", f"/data/{name1}.pdb",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        converted_path = os.path.join(results_dir, f"{name1}.pdb")
        if os.path.isfile(converted_path):
            shutil.copy2(converted_path, final_group_dir)

    record_version(
        f'hdock {hdock_autop2_version},pegi3s/hdock:{hdock_docker_version},'
        f'HDOCK {hdock_program_version},"{hdock_ref}","{hdock_doi}"'
    )
    record_version(f',pegi3s/utilities:{hdocktopisa_docker_version}')
    record_refs(f'hdock_ref="{hdock_ref}"\nhdock_doi="{hdock_doi}"\n')


if __name__ == "__main__":
    print("Running HDOCK", flush=True)
    main()
