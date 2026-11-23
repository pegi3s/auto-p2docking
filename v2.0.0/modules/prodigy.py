#!/usr/bin/env python3
import glob
import hashlib
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version

prodigy_autop2_version = "2.0.0"
prodigy_docker_version = "2.4.0"
prodigy_program_version = "2.4.0"
prodigy_ref = ""
prodigy_doi = ""


def _replace_nonstandard_codes(pdb_path):
    replacements = {
        "HID": "HIS", "HIE": "HIS", "HIP": "HIS",
        "CYX": "CYS", "ASH": "ASP", "GLH": "GLU", "LYN": "LYS",
    }
    with open(pdb_path) as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        for old, new in replacements.items():
            line = line.replace(old, new)
        new_lines.append(line)
    with open(pdb_path, "w") as f:
        f.writelines(new_lines)



def _announce_once_per_pipeline(project, prefix):
    """One header per main.py invocation, rather than one per BLOCK ligand."""
    parent_pid = os.getppid()
    try:
        with open(f"/proc/{parent_pid}/stat", encoding="utf-8") as f:
            start_time = f.read().rsplit(") ", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        start_time = "unknown"

    key = f"{project}|{prefix}|prodigy|{parent_pid}|{start_time}"
    token = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    marker = os.path.join(tempfile.gettempdir(), f"auto_p2docking_prodigy_header_{token}")
    try:
        with open(marker, "x", encoding="utf-8"):
            pass
    except FileExistsError:
        return

    print("Running: PRODIGY", flush=True)


def _pdb_files_under(folder):
    """Return protein-complex PDBs beneath a folder, in stable order."""
    return sorted(
        os.path.join(root, name)
        for root, _dirs, names in os.walk(folder)
        for name in names
        if name.lower().endswith(".pdb")
    )


def _ligand_stem(value):
    """Normalize the ligand identifier supplied by main.py (with/without .pdb)."""
    name = os.path.basename(value.strip())
    return name[:-4] if name.lower().endswith(".pdb") else name


def _select_complexes(input_path, project, pdbs_dir=None):
    """Select the current ligand's complexes in BLOCK=yes.

    One ligand: all input complexes, regardless of filename/directory.
    Multiple ligands: only input/<ligand_name>/, with explicit grouping.
    """
    pdbs_dir = pdbs_dir or f"/data/{project}/PDBs"
    ligand_list_path = os.path.join(pdbs_dir, "ligands_list.txt")
    current_ligand_path = os.path.join(pdbs_dir, "input_ligand.txt")

    if not os.path.isfile(current_ligand_path):
        sys.exit(f"Error: BLOCK ligand selection file not found: {current_ligand_path}")
    with open(current_ligand_path, encoding="utf-8") as f:
        current_ligand = _ligand_stem(f.readline())
    if not current_ligand or current_ligand in {".", ".."}:
        sys.exit(f"Error: invalid BLOCK ligand in {current_ligand_path}")

    if os.path.isfile(ligand_list_path):
        with open(ligand_list_path, encoding="utf-8") as f:
            ligand_names = [
                _ligand_stem(line) for line in f
                if line.strip() and not line.lstrip().startswith("#")
            ]
    else:
        # Keep independent runs usable if main.py has not yet created the list.
        ligand_names = [
            _ligand_stem(name) for name in os.listdir(os.path.join(pdbs_dir, "Ligands"))
            if name.lower().endswith(".pdb")
        ] if os.path.isdir(os.path.join(pdbs_dir, "Ligands")) else []

    ligand_names = [name for name in ligand_names if name]
    if not ligand_names:
        sys.exit(f"Error: no BLOCK ligands found in {pdbs_dir}")
    if current_ligand not in ligand_names:
        sys.exit(
            f"Error: BLOCK ligand {current_ligand!r} is not listed in {ligand_list_path}"
        )

    if len(set(ligand_names)) == 1:
        # With a single ligand, the complex filenames are not expected to
        # identify the ligand: arbitrary names and nested directories are OK.
        return _pdb_files_under(input_path)

    # With multiple ligands, guessing from arbitrary complex filenames is
    # unsafe. Require the established HDOCK/HADDOCK/FTDock grouping.
    ligand_folder = os.path.join(input_path, current_ligand)
    if not os.path.isdir(ligand_folder):
        sys.exit(
            f"Error: multiple BLOCK ligands detected; complexes for "
            f"{current_ligand!r} must be inside {ligand_folder}. "
            "Please organize input complexes in one subfolder per ligand."
        )
    return _pdb_files_under(ligand_folder)


def main():
    global prodigy_autop2_version, prodigy_docker_version, prodigy_ref, prodigy_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: prodigy.py <input_dir> <output_dir> <prefix>")

    input_dir, output_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("prodigy_docker_c_version"):
        prodigy_autop2_version = "?"
        prodigy_docker_version = os.environ["prodigy_docker_c_version"]
        prodigy_ref = "?"
        prodigy_doi = "?"

    selection = os.environ.get("prodigy_selection", "A B")

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    input_path = f"/data/{input_dir}"
    output_path = f"/data/{output_dir}"
    intermediate_path = f"/data/{prefix}prodigy"

    if not os.path.isdir(input_path):
        sys.exit(f"Error: input directory does not exist:\n{input_path}")

    os.makedirs(output_path, exist_ok=True)
    os.makedirs(intermediate_path, exist_ok=True)
    os.makedirs("/data/files_to_keep", exist_ok=True)

    # The dispatcher calls PRODIGY once per ligand in BLOCK=yes.
    # Scope this call to the current ligand, preserving the source's folder
    # hierarchy in both intermediate and final output directories.
    pdb_files = _select_complexes(input_path, project)

    if not pdb_files:
        sys.exit(
            f"Error: no .pdb complexes found for the current BLOCK ligand "
            f"in {input_path}"
        )

    _announce_once_per_pipeline(project, prefix)

    processed = 0
    skipped = 0
    already_processed = 0

    for source_pdb in pdb_files:
        input_name = os.path.basename(source_pdb)[:-4]
        relative_dir = os.path.relpath(os.path.dirname(source_pdb), input_path)

        if relative_dir == ".":
            module_dir = os.path.join(intermediate_path, input_name)
            work_dir = os.path.join(module_dir, "work")
            final_output_dir = os.path.join(output_path, input_name)
            host_work_dir = f"{host_dir}/{prefix}prodigy/{input_name}/work"
        else:
            module_dir = os.path.join(intermediate_path, relative_dir, input_name)
            work_dir = os.path.join(module_dir, "work")
            final_output_dir = os.path.join(output_path, relative_dir, input_name)
            host_work_dir = f"{host_dir}/{prefix}prodigy/{relative_dir}/{input_name}/work"

        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(final_output_dir, exist_ok=True)

        final_prodigy_txt = os.path.join(
            final_output_dir,
            f"{input_name}.prodigy.txt"
        )

        if os.path.isfile(final_prodigy_txt):
            # A valid existing result is a normal cache hit, not a warning.
            already_processed += 1
            continue

        # Convert non-standard codes back to HIS, CYS, ASP, GLU, LYS
        _replace_nonstandard_codes(source_pdb)

        dest_pdb = os.path.join(work_dir, f"{input_name}.pdb")
        with open(source_pdb) as src, open(dest_pdb, "w") as dst:
            dst.write(src.read())

        chains = set()
        with open(dest_pdb) as f:
            for line in f:
                if line.startswith("ATOM"):
                    chains.add(line[21:22])

        if len(chains) < 2:
            print(
                f"Skipping {input_name}: "
                "PRODIGY requires a complex with at least two chains."
            )
            skipped += 1
            continue

        prodigy_txt = os.path.join(work_dir, f"{input_name}.prodigy.txt")

        with open(prodigy_txt, "w") as out_f:
            subprocess.run(
                [
                    "docker", "run", "--rm",
                    "-v", f"{host_work_dir}:/data",
                    f"pegi3s/prodigy:{prodigy_docker_version}",
                    f"/data/{input_name}.pdb",
                    "--selection", *selection.split(),
                ],
                stdout=out_f,
            )

        if not os.path.getsize(prodigy_txt):
            sys.exit(
                f"Error: PRODIGY output was not generated or is empty:\n"
                f"{prodigy_txt}"
            )

        with open(prodigy_txt) as f:
            content = f.read()

        if "binding affinity" not in content.lower():
            sys.exit(
                "Error: PRODIGY output exists, but binding affinity was not found.\n"
                "This usually means PRODIGY failed or the selected chains are wrong.\n"
                f"Check file:\n{prodigy_txt}"
            )

        with open(prodigy_txt) as src, open(final_prodigy_txt, "w") as dst:
            dst.write(src.read())

        processed += 1

    if processed == 0 and already_processed == 0:
        sys.exit(
            "Error: no valid protein-protein complexes were processed by PRODIGY.\n"
            f"Skipped files: {skipped}\n"
            "Check if your PDB files contain at least two chains and if "
            "prodigy_selection is correct."
        )

    record_version(
        f'prodigy {prodigy_autop2_version},'
        f'pegi3s/prodigy:{prodigy_docker_version},'
        f'PRODIGY {prodigy_program_version},'
        f'"{prodigy_ref}","{prodigy_doi}"'
    )


if __name__ == "__main__":
    main()

