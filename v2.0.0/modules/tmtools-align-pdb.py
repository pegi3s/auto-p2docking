#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import (
    load_config,
    parse_max_tm_score,
    record_refs,
    record_version,
)

tmtoolsalignpdb_autop2_version = "2.0.0"
tmtoolsalignpdb_docker_version = "1.0.1"
tmtoolsalignpdb_program_version = "2022/04/15"
tmtoolsalignpdb_ref = "Zhang e Skolnick (2005)"
tmtoolsalignpdb_doi = "10.1093/nar/gki524"


def main():
    global tmtoolsalignpdb_autop2_version
    global tmtoolsalignpdb_docker_version
    global tmtoolsalignpdb_ref
    global tmtoolsalignpdb_doi

    if len(sys.argv) < 4:
        sys.exit(
            "Usage: tmtools-align-pdb.py "
            "<input_dir> <out_dir> <prefix>"
        )

    input_dir, out_dir, prefix = (
        sys.argv[1],
        sys.argv[2],
        sys.argv[3],
    )

    load_config()

    if os.environ.get("tmtoolsalignpdb_docker_c_version"):
        tmtoolsalignpdb_autop2_version = "?"
        tmtoolsalignpdb_docker_version = os.environ[
            "tmtoolsalignpdb_docker_c_version"
        ]
        tmtoolsalignpdb_ref = "?"
        tmtoolsalignpdb_doi = "?"

    host_dir = os.environ.get("dir", "")
    input_path = f"/data/{input_dir}"
    work_dir = f"/data/{prefix}TM-align-pdb"
    input_work_dir = os.path.join(
        work_dir,
        "input"
    )
    input_pdb_dir = os.path.join(
        work_dir,
        "input_PDB"
    )
    final_dir = f"/data/{out_dir}"

    os.makedirs(
        input_work_dir,
        exist_ok=True
    )
    os.makedirs(
        input_pdb_dir,
        exist_ok=True
    )
    os.makedirs(
        final_dir,
        exist_ok=True
    )

    # Filter PDB: for every uniprot group that has a
    # "*_PDB.pdb" reference file, copy every file
    # belonging to that group into input_PDB.
    pdb_pdb_files = sorted(
        name
        for name in os.listdir(input_path)
        if (
            name.endswith("_PDB.pdb")
            and os.path.isfile(
                os.path.join(
                    input_path,
                    name
                )
            )
        )
    )

    copied_prefixes = []

    for name in pdb_pdb_files:
        uniprot = name.split("_")[0]

        if uniprot not in copied_prefixes:
            for path in sorted(
                glob.glob(
                    os.path.join(
                        input_path,
                        f"{uniprot}_*.pdb"
                    )
                )
            ):
                shutil.copy2(
                    path,
                    input_pdb_dir
                )

            copied_prefixes.append(
                uniprot
            )

    uniprot_groups = []
    seen = set()

    for name in sorted(
        os.listdir(input_pdb_dir)
    ):
        if not name.endswith("_PDB.pdb"):
            continue

        uniprot = name.split("_")[0]

        if uniprot not in seen:
            uniprot_groups.append(
                uniprot
            )
            seen.add(
                uniprot
            )

    for uniprot in uniprot_groups:
        group_files = sorted(
            glob.glob(
                os.path.join(
                    input_pdb_dir,
                    f"{uniprot}_*"
                )
            )
        )

        refs = [
            f
            for f in group_files
            if os.path.basename(f).endswith(
                "_PDB.pdb"
            )
        ]

        candidates = [
            f
            for f in group_files
            if not os.path.basename(f).endswith(
                "_PDB.pdb"
            )
        ]

        max_score = -1.0
        best_name = None

        for ref_path in refs:
            ref_name = os.path.basename(
                ref_path
            )

            for cand_path in candidates:
                cand_name = os.path.basename(
                    cand_path
                )

                shutil.copy2(
                    ref_path,
                    input_work_dir
                )
                shutil.copy2(
                    cand_path,
                    input_work_dir
                )

                res_file = os.path.join(
                    work_dir,
                    f"{ref_name}.{cand_name}.txt"
                )

                if not os.path.isfile(res_file):
                    subprocess.run(
                        [
                            "docker",
                            "run",
                            "--rm",
                            "-v",
                            f"{host_dir}:/data",
                            f"pegi3s/tmtools:"
                            f"{tmtoolsalignpdb_docker_version}",
                            "bash",
                            "-c",
                            (
                                f"python script.py "
                                f"{input_work_dir}/{ref_name} "
                                f"{input_work_dir}/{cand_name} "
                                f"> {res_file}"
                            ),
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

                    for leftover in glob.glob(
                        os.path.join(
                            input_work_dir,
                            "*"
                        )
                    ):
                        os.remove(
                            leftover
                        )

                    current_score = parse_max_tm_score(
                        res_file
                    )

                    if (
                        current_score is not None
                        and current_score > max_score
                    ):
                        max_score = current_score
                        best_name = cand_name

        if best_name is not None:
            best_path = os.path.join(
                input_pdb_dir,
                best_name
            )

            if os.path.isfile(best_path):
                shutil.copy2(
                    best_path,
                    final_dir
                )

    # Create TM-score summary list from every comparison result.
    tm_scores_lines = []

    for txt_path in sorted(
        glob.glob(
            os.path.join(
                work_dir,
                "*.txt"
            )
        )
    ):
        name = os.path.basename(
            txt_path
        )

        with open(txt_path) as f:
            scores = [
                line.strip()
                for line in f
                if re.search(
                    r"TM-score \(chain[12]\):",
                    line
                )
            ]

        tm_scores_lines.append(
            f"{name}\t"
            + "\t".join(scores)
        )

    tm_scores_path = os.path.join(
        work_dir,
        "tm_scores_list"
    )

    with open(
        tm_scores_path,
        "w"
    ) as f:
        for line in tm_scores_lines:
            f.write(
                line + "\n"
            )

    # Also keep tm_scores_list in the normal module output.
    shutil.copy2(
        tm_scores_path,
        os.path.join(
            final_dir,
            "tm_scores_list"
        )
    )

    for name in sorted(
        os.listdir(input_path)
    ):
        path = os.path.join(
            input_path,
            name
        )

        if os.path.isfile(path):
            shutil.copy2(
                path,
                final_dir
            )

    # Final cleanup: reference-only files should not remain in the output.
    for leftover in glob.glob(
        os.path.join(
            final_dir,
            "*_PDB.pdb"
        )
    ):
        os.remove(
            leftover
        )

    record_version(
        f'tmtools {tmtoolsalignpdb_autop2_version},'
        f'pegi3s/tmtools:{tmtoolsalignpdb_docker_version},'
        f'TM-align {tmtoolsalignpdb_program_version},'
        f'"{tmtoolsalignpdb_ref}",'
        f'"{tmtoolsalignpdb_doi}"'
    )

    record_refs(
        f'tmtoolsalignpdb_ref="'
        f'{tmtoolsalignpdb_ref}"\n'
        f'tmtoolsalignpdb_doi="'
        f'{tmtoolsalignpdb_doi}"\n'
    )


if __name__ == "__main__":
    print(
        "Determining TM-align scores and selecting files",
        flush=True
    )
    main()
