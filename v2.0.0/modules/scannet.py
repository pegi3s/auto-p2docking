#!/usr/bin/env python3

import csv
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(
    0,
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

from pymodule_common import load_config, update_run_summary


SCANNET_AUTOP2_VERSION = "2.0.0"
SCANNET_DOCKER_VERSION = "13.07.2026"
SCANNET_PROGRAM_VERSION = "unknown"
SCANNET_REF = ""
SCANNET_DOI = ""

SCANNET_IMAGE = (
    f"pegi3s/scannet:"
    f"{SCANNET_DOCKER_VERSION}"
)

THREE_TO_ONE = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
    "MSE": "M",
}


def normalise_header(value):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        str(value).strip().lower()
    )


def parse_integer_residue(value):
    text = str(value).strip()

    if re.fullmatch(
        r"[+-]?\d+",
        text
    ):
        return int(text)

    if re.fullmatch(
        r"[+-]?\d+\.0+",
        text
    ):
        return int(
            float(text)
        )

    raise ValueError(
        f"Residue index '{text}' is not an integer. "
        "The current consensus format cannot represent "
        "insertion codes."
    )


def read_pdb_residues(
    path,
    chain_id
):
    residues = {}

    first_model_started = False
    first_model_finished = False

    with path.open(
        "r",
        encoding="utf-8",
        errors="replace"
    ) as handle:

        for line in handle:
            record = line[0:6].strip()

            if record == "MODEL":
                if not first_model_started:
                    first_model_started = True
                    continue

                first_model_finished = True

            if (
                record == "ENDMDL"
                and first_model_started
            ):
                break

            if first_model_finished:
                break

            if record not in {
                "ATOM",
                "HETATM"
            }:
                continue

            chain = line[21:22].strip()

            if chain != chain_id:
                continue

            raw_number = (
                line[22:26].strip()
            )

            insertion_code = (
                line[26:27].strip()
            )

            if not raw_number:
                continue

            if insertion_code:
                raise SystemExit(
                    f"Insertion code found in {path}: "
                    f"chain {chain_id}, residue "
                    f"{raw_number}{insertion_code}. "
                    "The current consensus format supports "
                    "integer residue numbers only."
                )

            try:
                residue_number = int(
                    raw_number
                )

            except ValueError:
                continue

            residue_three = (
                line[17:20]
                .strip()
                .upper()
            )

            residue_one = THREE_TO_ONE.get(
                residue_three,
                "X"
            )

            residues.setdefault(
                residue_number,
                residue_one
            )

    if not residues:
        raise SystemExit(
            f"No residues were found for chain "
            f"'{chain_id}' in {path}."
        )

    return residues


def locate_prediction_csv(
    output_dir
):
    candidates = []

    for path in sorted(
        output_dir.rglob("*.csv")
    ):
        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            ) as handle:

                reader = csv.reader(
                    handle
                )

                header = next(
                    reader,
                    None
                )

        except OSError:
            continue

        if not header:
            continue

        normalised = {
            normalise_header(column)
            for column in header
        }

        if {
            "chain",
            "residueindex",
            "sequence",
            "bindingsiteprobability",
        }.issubset(normalised):
            candidates.append(path)

    if not candidates:
        found = "\n".join(
            str(path)
            for path in sorted(
                output_dir.rglob("*.csv")
            )
        )

        raise SystemExit(
            "Could not find the SCANNet per-residue "
            "prediction CSV. CSV files found:\n"
            + (
                found
                if found
                else "(none)"
            )
        )

    if len(candidates) > 1:
        exact = [
            path
            for path in candidates
            if path.name.startswith(
                "predictions_"
            )
        ]

        if len(exact) == 1:
            return exact[0]

        raise SystemExit(
            "More than one SCANNet prediction "
            "CSV matched:\n"
            + "\n".join(
                str(path)
                for path in candidates
            )
        )

    return candidates[0]


def create_consensus_outputs(
    pdb_file,
    scannet_output_dir,
    selected_chain,
    interface_file,
    consensus_file,
):
    pdb_residues = read_pdb_residues(
        pdb_file,
        selected_chain
    )

    prediction_csv = locate_prediction_csv(
        scannet_output_dir
    )

    predictions = {}

    with prediction_csv.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:

        reader = csv.DictReader(
            handle
        )

        if not reader.fieldnames:
            raise SystemExit(
                f"Empty SCANNet CSV: "
                f"{prediction_csv}"
            )

        columns = {
            normalise_header(column): column
            for column in reader.fieldnames
        }

        chain_column = (
            columns["chain"]
        )

        residue_column = (
            columns["residueindex"]
        )

        sequence_column = (
            columns["sequence"]
        )

        score_column = (
            columns[
                "bindingsiteprobability"
            ]
        )

        for row in reader:
            chain = str(
                row.get(
                    chain_column,
                    ""
                )
            ).strip()

            if chain != selected_chain:
                continue

            raw_residue = str(
                row.get(
                    residue_column,
                    ""
                )
            ).strip()

            if not raw_residue:
                continue

            residue_number = (
                parse_integer_residue(
                    raw_residue
                )
            )

            if residue_number in predictions:
                raise SystemExit(
                    f"Duplicate prediction for chain "
                    f"{selected_chain}, residue "
                    f"{residue_number} in "
                    f"{prediction_csv}."
                )

            residue_name = (
                str(
                    row.get(
                        sequence_column,
                        ""
                    )
                )
                .strip()
                .upper()
                or "X"
            )

            raw_score = str(
                row.get(
                    score_column,
                    ""
                )
            ).strip()

            score = None

            if raw_score:
                try:
                    parsed_score = float(
                        raw_score
                    )

                    if math.isfinite(
                        parsed_score
                    ):
                        score = parsed_score

                except ValueError:
                    score = None

            predictions[
                residue_number
            ] = (
                residue_name,
                score
            )

    if not predictions:
        raise SystemExit(
            f"No SCANNet predictions were found "
            f"for chain '{selected_chain}' "
            f"in {prediction_csv}."
        )

    minimum_position = min(
        min(pdb_residues),
        min(predictions)
    )

    maximum_position = max(
        max(pdb_residues),
        max(predictions)
    )

    interface_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    consensus_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with interface_file.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as interface_handle, consensus_file.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as consensus_handle:

        writer = csv.writer(
            interface_handle,
            delimiter=";",
            lineterminator="\n"
        )

        writer.writerow(
            [
                "residue_number",
                "chain_id",
                "residue_name",
                "score",
                "code",
            ]
        )

        for residue_number in range(
            minimum_position,
            maximum_position + 1
        ):
            pdb_residue_name = (
                pdb_residues.get(
                    residue_number,
                    ""
                )
            )

            prediction = predictions.get(
                residue_number
            )

            if prediction is None:
                residue_name = (
                    pdb_residue_name
                )

                score = None
                code = 0

            else:
                (
                    predicted_residue_name,
                    score
                ) = prediction

                residue_name = (
                    predicted_residue_name
                    or pdb_residue_name
                )

                if score is None:
                    code = 0

                elif score >= 0.50:
                    code = 1

                elif score <= 0.35:
                    code = 2

                else:
                    code = 0

            score_text = (
                ""
                if score is None
                else f"{score:.3f}"
            )

            writer.writerow(
                [
                    residue_number,
                    selected_chain,
                    residue_name,
                    score_text,
                    code,
                ]
            )

            consensus_handle.write(
                f"{residue_number} "
                f"{code}\n"
            )


def read_current_ligand(
    project
):
    role = os.environ.get("AUTO_P2DOCKING_PROTEIN_ROLE", "ligand")
    if role not in ("ligand", "receptor"):
        raise SystemExit(f"Error: invalid selected protein role: {role!r}")
    ligand_file = (
        Path("/data")
        / project
        / "PDBs"
        / ("input_receptor.txt" if role == "receptor" else "input_ligand.txt")
    )

    if not ligand_file.is_file():
        raise SystemExit(
            "Error: SCANNet is configured as a BLOCK "
            "module, but the current ligand file does "
            "not exist:\n"
            f"{ligand_file}"
        )

    ligand = ligand_file.read_text(
        encoding="utf-8",
        errors="replace"
    ).strip()

    if not ligand:
        raise SystemExit(
            "Error: the current ligand file is empty:\n"
            f"{ligand_file}"
        )

    return Path(
        ligand
    ).name


def resolve_current_pdb(
    input_path,
    project,
    ligand_name
):
    direct_candidate = (
        input_path
        / ligand_name
    )

    if direct_candidate.is_file():
        return direct_candidate

    matches = sorted(
        path
        for path in input_path.rglob(
            ligand_name
        )
        if path.is_file()
    )

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        raise SystemExit(
            "Error: more than one PDB matching "
            "the current ligand was found in the "
            "SCANNet input directory "
            f"({ligand_name}):\n"
            + "\n".join(
                str(path)
                for path in matches
            )
        )

    role = os.environ.get("AUTO_P2DOCKING_PROTEIN_ROLE", "ligand")
    project_candidate = (
        Path("/data")
        / project
        / "PDBs"
        / ("Receptor" if role == "receptor" else "Ligands")
        / ligand_name
    )

    if project_candidate.is_file():
        return project_candidate

    raise SystemExit(
        "Error: could not find the PDB selected "
        "for the current BLOCK iteration: "
        f"{ligand_name}\n"
        f"Searched in: {input_path}\n"
        f"And in: {project_candidate.parent}"
    )


def append_version_information():
    versions_file = (
        Path(
            "/data/files_to_keep"
        )
        / "versions.csv"
    )

    versions_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    module_label = (
        f"scannet "
        f"{SCANNET_AUTOP2_VERSION}"
    )

    if versions_file.is_file():
        try:
            with versions_file.open(
                "r",
                encoding="utf-8",
                errors="replace",
                newline="",
            ) as handle:

                reader = csv.reader(
                    handle
                )

                if any(
                    row
                    and row[0]
                    == module_label
                    for row in reader
                ):
                    return

        except OSError:
            pass

    with versions_file.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.writer(
            handle,
            lineterminator="\n"
        )

        writer.writerow(
            [
                module_label,
                SCANNET_IMAGE,
                (
                    f"SCANNet "
                    f"{SCANNET_PROGRAM_VERSION}"
                ),
                SCANNET_REF,
                SCANNET_DOI,
            ]
        )


def main():
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: scannet.py "
            "<input_dir> <output_dir> <prefix>"
        )

    load_config()

    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    prefix = sys.argv[3]

    project = os.environ.get(
        "project",
        ""
    )

    host_data_dir = os.environ.get(
        "dir",
        ""
    )

    scannet_chain = (
        os.environ.get(
            "scannet_chain",
            "A"
        )
        or "A"
    )

    if not project:
        raise SystemExit(
            "Error: 'project' is not defined "
            "in /data/config."
        )

    if not host_data_dir:
        raise SystemExit(
            "Error: 'dir' is not defined in "
            "/data/config. SCANNet needs it "
            "to mount its intermediate working "
            "directory into the nested "
            "pegi3s/scannet Docker container."
        )

    input_path = (
        Path("/data")
        / input_dir
    )

    output_path = (
        Path("/data")
        / output_dir
    )

    work_root = (
        Path("/data")
        / f"{prefix}scannet"
    )

    block_id = (
        Path(prefix)
        .parent
        .name
    )


    if not input_path.is_dir():
        raise SystemExit(
            f"Error: input directory does "
            f"not exist:\n"
            f"{input_path}"
        )

    output_path.mkdir(
        parents=True,
        exist_ok=True
    )

    work_root.mkdir(
        parents=True,
        exist_ok=True
    )
    archive_root = work_root / "scannet"
    archive_root.mkdir(parents=True, exist_ok=True)



    current_ligand = read_current_ligand(
        project
    )

    source_pdb = resolve_current_pdb(
        input_path=input_path,
        project=project,
        ligand_name=current_ligand
    )

    input_name = source_pdb.stem
    run_name = input_name

    module_dir = (
        work_root
        / "scannet"
        / run_name
    )

    work_input_dir = (
        module_dir
        / "input"
    )

    work_output_dir = (
        module_dir
        / "output"
    )

    consensus_output_dir = (
        output_path
        / run_name
    )

    raw_output_dir = work_output_dir

    host_module_dir = (
        Path(host_data_dir)
        / f"{prefix}scannet"
        / "scannet"
        / run_name
    )

    for path in (
        work_input_dir,
        work_output_dir
    ):
        if path.exists():
            shutil.rmtree(path)

    work_input_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    work_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    consensus_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    shutil.copy2(
        source_pdb,
        work_input_dir
        / f"{input_name}.pdb"
    )

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{host_module_dir}:/data",
            SCANNET_IMAGE,
            "conda",
            "run",
            "--no-capture-output",
            "-n",
            "scannet",
            "python3",
            "/usr/local/bin/main.py",
            (
                f"/data/input/"
                f"{input_name}.pdb_"
                f"{scannet_chain}"
            ),
            "--mode",
            "interface",
            "--noMSA",
            "--name",
            run_name,
            "--predictions_folder",
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
            f"Error: SCANNet failed with "
            f"exit code {result.returncode}"
        )

    if not any(
        path.is_file()
        for path in work_output_dir.rglob(
            "*"
        )
    ):
        raise SystemExit(
            "Error: SCANNet produced no output for:\n"
            f"{source_pdb}\n"
            "Work output dir:\n"
            f"{work_output_dir}"
        )

    interface_csv = (
        raw_output_dir / f"{run_name}.scannet.interface_residues.csv"
    )

    consensus_file = (
        consensus_output_dir
        / f"{run_name}.scannet.csv"
    )

    create_consensus_outputs(
        pdb_file=source_pdb,
        scannet_output_dir=work_output_dir,
        selected_chain=scannet_chain,
        interface_file=interface_csv,
        consensus_file=consensus_file
    )

    if (
        not interface_csv.is_file()
        or interface_csv.stat().st_size == 0
    ):
        raise SystemExit(
            "Error: interface_residues.csv "
            "was not created or is empty:\n"
            f"{interface_csv}"
        )

    if (
        not consensus_file.is_file()
        or consensus_file.stat().st_size == 0
    ):
        raise SystemExit(
            "Error: consensus file was not "
            "created or is empty:\n"
            f"{consensus_file}"
        )

    summary_file = output_path / "scannet_runs.csv"
    shutil.copy2(consensus_file, module_dir / consensus_file.name)

    update_run_summary(
        summary_file,
        ["input_pdb", "run_name", "chain", "raw_output_directory",
         "interface_residues_csv", "consensus_file"],
        ["run_name"],
        {"input_pdb": source_pdb.name, "run_name": run_name,
         "chain": scannet_chain, "raw_output_directory": str(raw_output_dir),
         "interface_residues_csv": str(interface_csv),
         "consensus_file": str(consensus_file)},
    )

    shutil.copy2(summary_file, archive_root / summary_file.name)

    append_version_information()


if __name__ == "__main__":
    print(
        "Running: SCANNet",
        flush=True
    )

    main()
