#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import check_sites_files, load_config, record_refs, record_version

pydock_autop2_version = "2.0.0"
pydock_docker_version = "latest"
pydock_program_version = "3.2.3"
pydock_ref = "Cheng et al. (2007)"
pydock_doi = "doi.org/10.1002/prot.21419"
ftdock_program_version = "2.0"
ftdock_ref = "Gabb et al. (1997)"
ftdock_doi = "10.1006/jmbi.1997.1203"


def _extract_residue_number(item):
    return int(item.split(".")[-1])


def _write_ftdock_ini(pdb1_name, pdb2_name, pdb1_path, pdb2_path,
                       active1_path, active2_path, passive1_path, passive2_path,
                       output_ini_path):
    """Port of ftdock_ini.py, inlined directly instead of sed-patching and
    re-running the shared /opt/ftdock_ini.py template file."""
    with open(pdb1_path) as pdb1, open(pdb2_path) as pdb2, \
            open(active1_path) as active1, open(active2_path) as active2, \
            open(passive1_path) as passive1, open(passive2_path) as passive2:
        linhas_pdb1 = pdb1.readlines()
        linhas_pdb2 = pdb2.readlines()
        linhas_active1 = active1.readlines()
        linhas_active2 = active2.readlines()
        linhas_passive1 = passive1.readlines()
        linhas_passive2 = passive2.readlines()

    all_sites1 = [
        site
        for site in linhas_active1[0].split(",") + linhas_passive1[0].split(",")
        if site.strip()
    ]

    all_sites2 = [
        site
        for site in linhas_active2[0].split(",") + linhas_passive2[0].split(",")
        if site.strip()
    ]

    list_pdb1 = []
    for line in linhas_pdb1:
        if line.startswith("ATOM"):
            list_pdb1.append(line.split())

    new_list_pdb1 = []
    for atom in list_pdb1:
        new_list_pdb1.append([x.strip() for x in atom])

    list_pdb2 = []
    for line in linhas_pdb2:
        if line.startswith("ATOM"):
            list_pdb2.append(line.split())

    new_list_pdb2 = []
    for atom in list_pdb2:
        new_list_pdb2.append([x.strip() for x in atom])

    restr1 = []
    for nr in all_sites1:
        for line in new_list_pdb1:
            if int(line[5]) == int(nr):
                restr1.append(line[4] + "." + line[3] + "." + line[5])

    restr1 = list(dict.fromkeys(restr1))

    restr2 = []
    for nr in all_sites2:
        for line in new_list_pdb2:
            if int(line[5]) == int(nr):
                restr2.append(line[4] + "." + line[3] + "." + line[5])

    restr2 = list(dict.fromkeys(restr2))

    sorted_restr1 = sorted(restr1, key=_extract_residue_number)
    str1 = ", ".join(sorted_restr1)

    a_b = [
        "B" + rotulo[1:] if rotulo.startswith("A.") else rotulo
        for rotulo in restr2
    ]

    sorted_restr2 = sorted(a_b, key=_extract_residue_number)
    str2 = ", ".join(sorted_restr2)

    with open(output_ini_path, "w") as ini:
        ini.write("[receptor]\n")
        ini.write("pdb\t\t= {}\n".format(pdb1_name))
        ini.write("mol\t\t= A\n")
        ini.write("newmol\t= A\n")
        ini.write("restr   = {}\n".format(str1))
        ini.write("[ligand]\n")
        ini.write("pdb\t\t= {}\n".format(pdb2_name))
        ini.write("mol\t\t= A\n")
        ini.write("newmol\t= B\n")
        ini.write("restr   = {}".format(str2))


def main():
    global pydock_autop2_version, pydock_docker_version, pydock_ref, pydock_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: pydock_ftdock.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("pydock_docker_c_version"):
        pydock_autop2_version = "?"
        pydock_docker_version = os.environ["pydock_docker_c_version"]
        pydock_ref = "?"
        pydock_doi = "?"

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    with open(f"/data/{project}/PDBs/input_ligand.txt") as f:
        ftdock_pdb2 = f.readline().rstrip("\n")

    receptor_files = sorted(
        glob.glob(f"/data/{project}/PDBs/Receptor/*")
    )

    ftdock_pdb1 = os.path.basename(receptor_files[0])

    pdb2 = os.path.basename(ftdock_pdb2)
    if pdb2.endswith(".pdb"):
        pdb2 = pdb2[:-4]

    pdb1 = os.path.basename(ftdock_pdb1)
    if pdb1.endswith(".pdb"):
        pdb1 = pdb1[:-4]

    warning_path = (
        f"/data/{project}/intermediate_files/"
        f"warning_files/do_not_run.{pdb2}"
    )

    if pdb2 == pdb1 or os.path.isfile(warning_path):
        return

    check_sites_files(input_dir, pdb1, pdb2)

    run_dir = f"/data/{prefix}pyDOCK_run/{pdb2}"

    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(f"/data/{out_dir}", exist_ok=True)

    shutil.copy2(
        f"/data/{project}/PDBs/Ligands/{ftdock_pdb2}",
        run_dir,
    )

    for path in glob.glob(f"/data/{input_dir}/{pdb2}/*.sites"):
        shutil.copy2(path, run_dir)

    for path in sorted(
        glob.glob(f"/data/{project}/PDBs/Receptor/*")
    ):
        shutil.copy2(path, run_dir)

    for path in glob.glob(f"/data/{input_dir}/{pdb1}/*.sites"):
        shutil.copy2(path, run_dir)

    ftdock_active_pdb1 = f"{pdb1}_active.sites"
    ftdock_active_pdb2 = f"{pdb2}_active.sites"
    ftdock_passive_pdb1 = f"{pdb1}_passive.sites"
    ftdock_passive_pdb2 = f"{pdb2}_passive.sites"
    ftdock_project_name = f"{pdb1}_{pdb2}_FTDOCK"

    ini_path = f"{run_dir}/{ftdock_project_name}.ini"

    _write_ftdock_ini(
        pdb1_name=ftdock_pdb1,
        pdb2_name=ftdock_pdb2,
        pdb1_path=f"{run_dir}/{ftdock_pdb1}",
        pdb2_path=f"{run_dir}/{ftdock_pdb2}",
        active1_path=f"{run_dir}/{ftdock_active_pdb1}",
        active2_path=f"{run_dir}/{ftdock_active_pdb2}",
        passive1_path=f"{run_dir}/{ftdock_passive_pdb1}",
        passive2_path=f"{run_dir}/{ftdock_passive_pdb2}",
        output_ini_path=ini_path,
    )

    number_of_solutions = os.environ.get(
        "pydock_ftdock_number_of_solutions",
        "",
    )

    best_pdb = os.environ.get(
        "pydock_ftdock_best_pdb",
        "",
    )

    pydock_cpus = os.environ.get(
        "pydock_ftdock_cpus",
        "1",
    )

    try:
        pydock_cpus = int(pydock_cpus)
    except ValueError:
        sys.exit(
            "Error: pydock_ftdock_cpus must be an integer between 1 and 99"
        )

    if not 1 <= pydock_cpus <= 99:
        sys.exit(
            "Error: pydock_ftdock_cpus must be between 1 and 99"
        )

    parallel_command = ""

    if pydock_cpus > 1:
        parallel_command = (
            f'REAL_PYDOCK3=$(command -v pyDock3); '
            f'export REAL_PYDOCK3; '
            f'export PYDOCK_CPUS={pydock_cpus}; '
            f'pyDock3() {{ '
            f'if [ "$2" = "dockser" ]; then '
            f'/opt/pyDock3/parallel/run_dockser_parallel.sh '
            f'"$1" "$PYDOCK_CPUS"; '
            f'else '
            f'"$REAL_PYDOCK3" "$@"; '
            f'fi; '
            f'}}; '
            f'export -f pyDock3; '
        )

    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{host_dir}/{prefix}pyDOCK_run/{pdb2}:/data",
            f"pegi3s/pydock3:{pydock_docker_version}",
            "bash", "-c",
            parallel_command
            + f"./run_ftdock {ftdock_project_name} "
              f"{number_of_solutions} {best_pdb} r",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    out_group_dir = f"/data/{out_dir}/{pdb2}"
    os.makedirs(out_group_dir, exist_ok=True)

    for path in glob.glob(
        f"{run_dir}/{ftdock_project_name}_[0-9]*.pdb"
    ):
        shutil.copy2(path, out_group_dir)

    record_version(
        f'pydock_ftdock {pydock_autop2_version},'
        f'pegi3s/pydock3:{pydock_docker_version},'
        f'Pydock3 {pydock_program_version},'
        f'"{pydock_ref}","{pydock_doi}"'
    )

    record_version(
        f',,Ftdock {ftdock_program_version},'
        f'"{ftdock_ref}","{ftdock_doi}"'
    )

    record_refs(
        f'pydock_ref="{pydock_ref}"\n'
        f'pydock_doi="{pydock_doi}"\n'
    )

    record_refs(
        f'ftdock_ref="{ftdock_ref}"\n'
        f'ftdock_doi="{ftdock_doi}"\n'
    )


if __name__ == "__main__":
    print("Running pyDock (FTDock)", flush=True)
    main()
