#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, parse_max_tm_score, record_refs, record_version

tmtoolsaligncutoff_autop2_version = "2.0.0"
tmtoolsaligncutoff_docker_version = "1.0.1"
tmtoolsaligncutoff_program_version = "2022/04/15"
tmtoolsaligncutoff_ref = "Zhang e Skolnick (2005)"
tmtoolsaligncutoff_doi = "10.1093/nar/gki524"


def main():
    global tmtoolsaligncutoff_autop2_version, tmtoolsaligncutoff_docker_version
    global tmtoolsaligncutoff_ref, tmtoolsaligncutoff_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: tmtools-align-cutoff.py <input_dir> <out_dir> <prefix>")

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    load_config()

    if os.environ.get("tmtoolsaligncutoff_docker_c_version"):
        tmtoolsaligncutoff_autop2_version = "?"
        tmtoolsaligncutoff_docker_version = os.environ["tmtoolsaligncutoff_docker_c_version"]
        tmtoolsaligncutoff_ref = "?"
        tmtoolsaligncutoff_doi = "?"

    host_dir = os.environ.get("dir", "")
    input_path = f"/data/{input_dir}"
    work_dir = f"/data/{prefix}TMtools-align-cutoff"
    input_work_dir = os.path.join(work_dir, "input")
    tm_align_dir = os.path.join(work_dir, "tm-align")
    final_dir = f"/data/{out_dir}"

    os.makedirs(input_work_dir, exist_ok=True)
    os.makedirs(tm_align_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    pdb_files = sorted(
        name for name in os.listdir(input_path)
        if name.endswith(".pdb") and os.path.isfile(os.path.join(input_path, name))
    )

    groups = {}

    for name in pdb_files:
        uniprot = name.split("_")[0]
        groups.setdefault(uniprot, []).append(name)

    # Compare every pair of files sharing the same UniProt prefix.
    for uniprot in sorted(groups):
        members = sorted(groups[uniprot])

        for first, second in combinations(members, 2):
            res_file = os.path.join(
                tm_align_dir,
                f"{first}.{second}.txt"
            )

            res_file_swapped = os.path.join(
                tm_align_dir,
                f"{second}.{first}.txt"
            )

            if os.path.isfile(res_file) or os.path.isfile(res_file_swapped):
                continue

            shutil.copy2(
                os.path.join(input_path, first),
                input_work_dir
            )

            shutil.copy2(
                os.path.join(input_path, second),
                input_work_dir
            )

            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{host_dir}:/data",
                    f"pegi3s/tmtools:{tmtoolsaligncutoff_docker_version}",
                    "bash",
                    "-c",
                    (
                        f"python script.py "
                        f"{input_work_dir}/{first} "
                        f"{input_work_dir}/{second} "
                        f"> {res_file}"
                    ),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            for leftover in glob.glob(
                os.path.join(input_work_dir, "*")
            ):
                os.remove(leftover)

    tm_cutoff_ref = float(
        os.environ.get("tm_cutoff_ref") or 0
    )

    tm_cutoff_order = [
        database
        for database in os.environ.get(
            "tm_cutoff_order",
            ""
        ).split("-")
        if database
    ]

    # A UniProt group must belong to only one final category.
    # If at least one comparison is at or below the cutoff,
    # the whole group is kept in "under".
    above = set()
    under = set()

    tm_scores_lines = []

    for txt_path in sorted(
        glob.glob(os.path.join(tm_align_dir, "*.txt"))
    ):
        name = os.path.basename(txt_path)

        just_filename = name.split("_")[0]

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
            f"{name}\t" + "\t".join(scores)
        )

        tm_score = parse_max_tm_score(txt_path)

        if (
            tm_score is not None
            and tm_score > tm_cutoff_ref
        ):
            # Add the group to "above" only if no previous
            # comparison from this group was below the cutoff.
            if just_filename not in under:
                above.add(just_filename)

        else:
            # One comparison below the cutoff is enough for
            # the group to remain in "under".
            under.add(just_filename)

            # Remove it from "above" if an earlier comparison
            # had placed it there.
            above.discard(just_filename)

    # Above cutoff:
    # keep only the first preferred database available.
    for filename in sorted(above):
        for database in tm_cutoff_order:
            candidate = os.path.join(
                input_path,
                f"{filename}_{database}.pdb"
            )

            if os.path.isfile(candidate):
                shutil.copy2(
                    candidate,
                    final_dir
                )
                break

    # Under cutoff:
    # keep every structure belonging to the group.
    for filename in sorted(under):
        for path in sorted(
            glob.glob(
                os.path.join(
                    input_path,
                    f"{filename}_*.pdb"
                )
            )
        ):
            shutil.copy2(
                path,
                final_dir
            )

    # Create TM-score summary list.
    with open(
        os.path.join(
            tm_align_dir,
            "tm_scores_list"
        ),
        "w"
    ) as f:
        for line in tm_scores_lines:
            f.write(line + "\n")

    record_version(
        f'tmtools {tmtoolsaligncutoff_autop2_version},'
        f'pegi3s/tmtools:{tmtoolsaligncutoff_docker_version},'
        f'TM-align {tmtoolsaligncutoff_program_version},'
        f'"{tmtoolsaligncutoff_ref}","{tmtoolsaligncutoff_doi}"'
    )

    record_refs(
        f'tmtoolsaligncutoff_ref="{tmtoolsaligncutoff_ref}"\n'
        f'tmtoolsaligncutoff_doi="{tmtoolsaligncutoff_doi}"\n'
    )


if __name__ == "__main__":
    print(
        "Determining TM-align scores and selecting files based on "
        "specified cutoff value and file to keep",
        flush=True
    )

    main()
