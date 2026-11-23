#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version

pisaserver_autop2_version = "2.0.0"
pisaserver_docker_version = "1.0.0"
pisaserver_program_version = "1.52"
pisaserver_ref = "Krissinel and Henrick (2007)"
pisaserver_doi = "10.1016/j.jmb.2007.05.022"
pisaxmlextract_docker_version = "0.22.2"


def _cut_dash_f7_plus(name):
    """Equivalent of `cut -d'-' -f7-`: keep field 7 onward (rejoined with
    '-'); if the name has no '-' at all, cut echoes it back unchanged; if
    it has some but fewer than 7 fields, cut produces an empty line."""
    parts = name.split("-")
    if len(parts) == 1:
        return name
    if len(parts) < 7:
        return ""
    return "-".join(parts[6:])


def main():
    global pisaserver_autop2_version, pisaserver_docker_version
    global pisaserver_ref, pisaserver_doi, pisaxmlextract_docker_version

    if len(sys.argv) < 4:
        sys.exit("Usage: pisa_server_extract.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("pisaserver_docker_c_version"):
        pisaserver_autop2_version = "?"
        pisaserver_docker_version = os.environ["pisaserver_docker_c_version"]
        pisaserver_ref = "?"
        pisaserver_doi = "?"

    if os.environ.get("pisaxmlextract_docker_c_version"):
        pisaserver_autop2_version = "?"
        pisaxmlextract_docker_version = os.environ["pisaxmlextract_docker_c_version"]

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    receptor_files = sorted(
        p
        for p in glob.glob(f"/data/{project}/PDBs/Receptor/*")
        if os.path.isfile(p)
    )

    pdb1 = os.path.basename(receptor_files[0])

    with open(f"/data/{project}/PDBs/input_ligand.txt") as f:
        pdb2 = f.readline().rstrip("\n")

    pdb1_sem_pdb = re.sub(r"\.pdb$", "", pdb1)
    pdb2_sem_pdb = re.sub(r"\.pdb$", "", pdb2)

    do_not_run_flag = (
        f"/data/{project}/intermediate_files/warning_files/do_not_run.{pdb2}"
    )

    if pdb1_sem_pdb == pdb2_sem_pdb or os.path.isfile(do_not_run_flag):
        return

    work_dir = f"/data/{prefix}PISA_extract_run"
    xml_work_dir = f"/data/{prefix}XML_extract_run"
    final_dir = f"/data/{out_dir}"
    final_group_dir = os.path.join(final_dir, pdb2_sem_pdb)

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_group_dir, exist_ok=True)
    os.makedirs(xml_work_dir, exist_ok=True)

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"/{host_dir}:/data",
            f"pegi3s/pisa_server:{pisaserver_docker_version}",
            "bash",
            "-c",
            f"/opt/run /data/{input_dir}/{pdb2_sem_pdb} "
            f"{work_dir}/results/{pdb2_sem_pdb}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    results_dir = os.path.join(work_dir, "results", pdb2_sem_pdb)

    if os.path.isdir(results_dir):
        for name in sorted(os.listdir(results_dir)):
            cut_name = _cut_dash_f7_plus(name)

            if not cut_name:
                continue

            os.replace(
                os.path.join(results_dir, name),
                os.path.join(results_dir, cut_name),
            )

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{host_dir}:/data",
            f"pegi3s/utilities:{pisaxmlextract_docker_version}",
            "pisa_xml_extract",
            f"{work_dir}/results",
            f"{xml_work_dir}/{pdb2_sem_pdb}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    xml_matches = sorted(
        glob.glob(
            f"{xml_work_dir}/{pdb2_sem_pdb}/selection/"
            f"{pdb2_sem_pdb}/*.xml"
        )
    )

    if xml_matches:
        path = xml_matches[0]
        folder_name = os.path.basename(path)
        folder_name_without_extension = re.sub(r"\.xml$", "", folder_name)

        summary_path = os.path.join(path, "summary")
        if os.path.isfile(summary_path):
            shutil.copy2(summary_path, final_group_dir)

        pdb_matches = []

        for pdb_path in glob.glob(
            f"/data/{input_dir}/**/*.pdb",
            recursive=True,
        ):
            pdb_basename = os.path.basename(pdb_path)
            pdb_without_extension = re.sub(r"\.pdb$", "", pdb_basename)

            if folder_name_without_extension.endswith(pdb_without_extension):
                pdb_matches.append(pdb_path)

        if pdb_matches:
            pdb_source = pdb_matches[0]

            print("XML selected:", folder_name)
            print("Matched PDB:", os.path.basename(pdb_source))
            print("PDB source:", pdb_source)
            print("Destination:", final_group_dir)

            shutil.copy2(pdb_source, final_group_dir)
        else:
            print(
                f"PDB not found for XML: {folder_name}",
                file=sys.stderr,
            )

        summary_dest = os.path.join(final_group_dir, "summary")

        if os.path.isfile(summary_dest):
            os.replace(
                summary_dest,
                os.path.join(
                    final_group_dir,
                    f"{folder_name_without_extension}.tsv",
                ),
            )

    record_version(
        f"pisa_server_extract {pisaserver_autop2_version},"
        f"pegi3s/pisa_server:{pisaserver_docker_version},"
        f"PISA server {pisaserver_program_version},"
        f'"{pisaserver_ref}","{pisaserver_doi}"'
    )

    record_version(
        f",pegi3s/utilities:{pisaxmlextract_docker_version}"
    )

    record_refs(
        f'pisaserver_ref="{pisaserver_ref}"\n'
        f'pisaserver_doi="{pisaserver_doi}"\n'
    )


if __name__ == "__main__":
    print("Running PISA server", flush=True)
    main()
