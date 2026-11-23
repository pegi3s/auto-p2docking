#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import convert_interface_csv_to_consensus_format, load_config, record_version, update_run_summary

pesto_autop2_version = "2.0.0"
pesto_docker_version = "i_v4_1"
pesto_program_version = "unknown"
pesto_ref = ""
pesto_doi = ""


def _run_name_for(source_pdb, input_path):
    input_name = os.path.splitext(
        os.path.basename(source_pdb)
    )[0]

    relative_dir = os.path.dirname(
        os.path.relpath(
            source_pdb,
            input_path
        )
    )

    if relative_dir in ("", "."):
        return input_name

    clean_relative_dir = relative_dir.replace(
        "/",
        "__"
    )

    return f"{clean_relative_dir}__{input_name}"


def _select_current_protein_pdb(input_path, project):
    """Resolve the ligand or receptor selected by main.py for this iteration.

    Do not fall back to processing every input PDB when selection is missing.
    """
    role = os.environ.get("AUTO_P2DOCKING_PROTEIN_ROLE", "ligand")
    if role not in ("ligand", "receptor"):
        raise SystemExit(f"Error: invalid selected protein role: {role!r}")
    selection_filename = "input_receptor.txt" if role == "receptor" else "input_ligand.txt"
    protein_folder = "Receptor" if role == "receptor" else "Ligands"
    ligand_file = Path("/data") / project / "PDBs" / selection_filename
    if not ligand_file.is_file():
        raise SystemExit(
            f"Error: missing current BLOCK ligand file: {ligand_file}"
        )

    current_ligand = Path(ligand_file.read_text(
        encoding="utf-8", errors="replace"
    ).strip()).name
    if not current_ligand or not current_ligand.lower().endswith(".pdb"):
        raise SystemExit(
            f"Error: invalid PDB name in {ligand_file}: {current_ligand!r}"
        )

    input_root = Path(input_path)
    direct = input_root / current_ligand
    if direct.is_file():
        selected = direct
    else:
        matches = sorted(p for p in input_root.rglob(current_ligand) if p.is_file())
        if len(matches) > 1:
            raise SystemExit(
                f"Error: multiple PDBs named {current_ligand!r} in {input_root}:\n"
                + "\n".join(str(p) for p in matches)
            )
        if matches:
            selected = matches[0]
        else:
            fallback = Path("/data") / project / "PDBs" / protein_folder / current_ligand
            if not fallback.is_file():
                raise SystemExit(
                    f"Error: current BLOCK PDB {current_ligand!r} was not found "
                    f"in {input_root} or {fallback}"
                )
            selected = fallback

    return str(selected)


def main():
    global pesto_autop2_version, pesto_docker_version, pesto_ref, pesto_doi

    if len(sys.argv) < 4:
        sys.exit(
            "Usage: pesto.py <input_dir> <out_dir> <prefix>"
        )

    input_dir, output_dir, prefix = (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
    )

    load_config()

    if os.environ.get("pesto_docker_c_version"):
        pesto_autop2_version = "?"
        pesto_docker_version = os.environ[
            "pesto_docker_c_version"
        ]
        pesto_ref = "?"
        pesto_doi = "?"

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    input_path = f"/data/{input_dir}"
    output_path = f"/data/{output_dir}"
    intermediate_path = f"/data/{prefix}pesto"


    if not os.path.isdir(input_path):
        print("Error: input directory does not exist:")
        sys.exit(input_path)

    os.makedirs(output_path, exist_ok=True)
    os.makedirs(intermediate_path, exist_ok=True)
    archive_root = os.path.join(intermediate_path, "pesto")
    os.makedirs(archive_root, exist_ok=True)

    pdb_files = [_select_current_protein_pdb(input_path, project)]

    if not pdb_files:
        print("Error: no .pdb files found in:")
        sys.exit(input_path)

    summary_file = os.path.join(output_path, "pesto_runs.csv")

    for source_pdb in pdb_files:
        input_name = os.path.splitext(
            os.path.basename(source_pdb)
        )[0]

        run_name = _run_name_for(
            source_pdb,
            input_path
        )

        module_dir = os.path.join(
            intermediate_path,
            "pesto",
            run_name
        )

        work_input_dir = os.path.join(
            module_dir,
            "input"
        )

        work_output_dir = os.path.join(
            module_dir,
            "output"
        )

        consensus_output_dir = os.path.join(
            output_path,
            run_name
        )

        raw_output_dir = work_output_dir

        host_work_input_dir = (
            f"{host_dir}/{prefix}pesto/pesto/"
            f"{run_name}/input"
        )

        host_work_output_dir = (
            f"{host_dir}/{prefix}pesto/pesto/"
            f"{run_name}/output"
        )

        os.makedirs(
            work_input_dir,
            exist_ok=True
        )

        if os.path.isdir(work_output_dir):
            shutil.rmtree(work_output_dir)
        os.makedirs(
            work_output_dir,
            exist_ok=True
        )

        os.makedirs(
            consensus_output_dir,
            exist_ok=True
        )


        shutil.copy2(
            source_pdb,
            os.path.join(
                work_input_dir,
                f"{input_name}.pdb"
            )
        )

        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{host_work_input_dir}:/app/input",
                "-v",
                f"{host_work_output_dir}:/app/output",
                f"pegi3s/pesto:{pesto_docker_version}",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            if result.stdout.strip():
                print(
                    result.stdout,
                    file=sys.stderr
                )

            if result.stderr.strip():
                print(
                    result.stderr,
                    file=sys.stderr
                )

            sys.exit(
                f"Error: PeSTo failed with exit code "
                f"{result.returncode}"
            )

        if not os.listdir(work_output_dir):
            print(
                "Error: PeSTo produced no output for:"
            )
            print(source_pdb)
            print("Work output dir:")
            sys.exit(work_output_dir)

        interface_csv = os.path.join(
            raw_output_dir,
            "interface_residues.csv"
        )

        consensus_file = os.path.join(
            consensus_output_dir,
            f"{run_name}.pesto.csv"
        )

        if not os.path.isfile(interface_csv):
            print(
                f"Error: interface_residues.csv "
                f"not found for {run_name}"
            )
            print("Expected file:")
            sys.exit(interface_csv)

        convert_interface_csv_to_consensus_format(
            interface_csv,
            consensus_file
        )

        if (
            not os.path.isfile(consensus_file)
            or os.path.getsize(consensus_file) == 0
        ):
            print(
                "Error: consensus file was not created or is empty:"
            )
            sys.exit(consensus_file)

        shutil.copy2(consensus_file, os.path.join(module_dir, os.path.basename(consensus_file)))

        update_run_summary(
            summary_file,
            ["input_pdb", "run_name", "consensus_file", "raw_output_directory"],
            ["run_name"],
            {"input_pdb": os.path.basename(source_pdb),
             "run_name": run_name, "consensus_file": consensus_file,
             "raw_output_directory": raw_output_dir},
        )

    shutil.copy2(summary_file, os.path.join(archive_root, os.path.basename(summary_file)))

    record_version(
        f'pesto {pesto_autop2_version},'
        f'pegi3s/pesto:{pesto_docker_version},'
        f'PeSTo {pesto_program_version},'
        f'"{pesto_ref}","{pesto_doi}"'
    )


if __name__ == "__main__":
    print("Running: PeSTo", flush=True)
    main()
