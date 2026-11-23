#!/usr/bin/env python3
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_version, update_run_summary

pipenn_autop2_version = "2.0.0"
pipenn_docker_version = "1.0.0"
pipenn_program_version = "unknown"
pipenn_ref = ""
pipenn_doi = ""


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


def _convert_pipenn_csv(
    raw_csv,
    consensus_file
):
    with open(raw_csv, newline="") as f:
        reader = csv.reader(
            f,
            delimiter=";"
        )

        rows = list(reader)

    with open(consensus_file, "w") as out:
        for row in rows[1:]:
            residue = (
                row[0].strip()
                if len(row) > 0
                else ""
            )

            status = (
                row[3].strip()
                if len(row) > 3
                else ""
            )

            if residue and status:
                out.write(
                    f"{residue} {status}\n"
                )


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
    global pipenn_autop2_version, pipenn_docker_version, pipenn_ref, pipenn_doi

    if len(sys.argv) < 4:
        sys.exit(
            "Usage: pipenn.py <input_dir> <out_dir> <prefix>"
        )

    input_dir, output_dir, prefix = (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
    )

    load_config()

    if os.environ.get("pipenn_docker_c_version"):
        pipenn_autop2_version = "?"
        pipenn_docker_version = os.environ[
            "pipenn_docker_c_version"
        ]
        pipenn_ref = "?"
        pipenn_doi = "?"

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")

    input_path = f"/data/{input_dir}"
    output_path = f"/data/{output_dir}"
    intermediate_path = f"/data/{prefix}pipenn"

    if not os.path.isdir(input_path):
        print(
            "Error: input directory does not exist:"
        )
        sys.exit(input_path)

    os.makedirs(
        output_path,
        exist_ok=True
    )

    os.makedirs(
        intermediate_path,
        exist_ok=True
    )
    archive_root = os.path.join(intermediate_path, "pipenn")
    os.makedirs(archive_root, exist_ok=True)


    pdb_files = [_select_current_protein_pdb(input_path, project)]

    if not pdb_files:
        print("Error: no .pdb files found in:")
        sys.exit(input_path)

    summary_file = os.path.join(output_path, "pipenn_runs.csv")

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
            "pipenn",
            run_name
        )

        work_dir = os.path.join(
            module_dir,
            "work"
        )

        work_output_dir = os.path.join(
            work_dir,
            "output"
        )

        final_output_dir = os.path.join(
            output_path,
            run_name
        )

        host_work_dir = (
            f"{host_dir}/{prefix}pipenn/pipenn/"
            f"{run_name}/work"
        )

        os.makedirs(
            work_dir,
            exist_ok=True
        )

        if os.path.isdir(work_output_dir):
            shutil.rmtree(work_output_dir)
        os.makedirs(work_output_dir, exist_ok=True)

        os.makedirs(
            final_output_dir,
            exist_ok=True
        )

        shutil.copy2(
            source_pdb,
            os.path.join(
                work_dir,
                f"{input_name}.pdb"
            )
        )

        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{host_work_dir}:/data",
                f"pegi3s/pipenn:{pipenn_docker_version}",
                f"/data/{input_name}.pdb",
                "/data/output",
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
                f"Error: PIPENN failed with exit code "
                f"{result.returncode}"
            )

        if not os.listdir(work_output_dir):
            print(
                "Error: PIPENN produced no output for:"
            )
            print(source_pdb)
            print("Work output dir:")
            sys.exit(work_output_dir)

        raw_csv = os.path.join(
            work_output_dir,
            "interface_residues.csv"
        )

        if not os.path.isfile(raw_csv):
            print(
                "Error: PIPENN output exists, but "
                "interface_residues.csv was not found."
            )
            print("Files found:")

            for root, _dirs, files in os.walk(
                work_output_dir
            ):
                for name in files:
                    print(
                        os.path.join(
                            root,
                            name
                        )
                    )

            sys.exit(1)

        raw_output_dir = work_output_dir

        consensus_file = os.path.join(
            final_output_dir,
            f"{run_name}.pipenn.csv"
        )

        if os.path.isfile(raw_csv):
            _convert_pipenn_csv(
                raw_csv,
                consensus_file
            )
        else:
            print(
                "Warning: could not create consensus-compatible "
                "PIPENN file because raw CSV was not found:"
            )
            print(raw_csv)

        if not os.path.isfile(consensus_file) or os.path.getsize(consensus_file) == 0:
            sys.exit(f"Error: PIPENN consensus file missing or empty: {consensus_file}")
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
        f'pipenn {pipenn_autop2_version},'
        f'pegi3s/pipenn:{pipenn_docker_version},'
        f'PIPENN {pipenn_program_version},'
        f'"{pipenn_ref}","{pipenn_doi}"'
    )


if __name__ == "__main__":
    print("Running: PIPENN", flush=True)
    main()
