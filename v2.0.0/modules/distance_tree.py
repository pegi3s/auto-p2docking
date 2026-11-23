#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version

distance_tree_autop2_version = "2.0.0"
megax_cc_docker_version = "10.0.5"
distance_tree_megaxcc_program_version = "10.0.5"
newick_utils_docker_version = "1.6"
distance_tree_newick_utils_program_version = "1.6"
megaxcc_ref = "Kumar, S., Stecher, G., Peterson, D., & Tamura, K. (2012)"
megaxcc_doi = "10.1093/bioinformatics/bts507"
newick_utils_ref = "Junier T, Zdobnov EM. (2010)"
newick_utils_doi = "10.1093/bioinformatics/btq243"


def _cut_columns(lines, spec):
    """Equivalent of `cut -d$'\\t' -f "spec"`: spec is a comma-separated
    list of 1-based column numbers and/or ranges (e.g. "1,3-5"). Columns
    are returned in ascending original order, de-duplicated.
    """
    indices = set()

    for part in spec.split(","):
        if "-" in part:
            start, end = part.split("-")
            indices.update(range(int(start), int(end) + 1))
        else:
            indices.add(int(part))

    sorted_idx = sorted(indices)
    result = []

    for line in lines:
        fields = line.split("\t")

        selected = [
            fields[i - 1]
            for i in sorted_idx
            if i - 1 < len(fields)
        ]

        result.append("\t".join(selected))

    return result


def _increment_coordinates(coordinates):
    """Equivalent of the awk range-incrementing block: turns "0-2,5-7"
    into "1-3,6-8" (each range's start/end incremented by 1).
    """
    new_ranges = []

    for part in coordinates.split(","):
        start, end = part.split("-")
        new_ranges.append(
            f"{int(start) + 1}-{int(end) + 1}"
        )

    return ",".join(new_ranges)


def main():
    global distance_tree_autop2_version, megax_cc_docker_version
    global distance_tree_megaxcc_program_version, newick_utils_docker_version
    global distance_tree_newick_utils_program_version

    if len(sys.argv) < 4:
        sys.exit(
            "Usage: distance_tree.py <input_dir> <out_dir> <prefix>"
        )

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]

    load_config()

    if os.environ.get("megax_cc_docker_c_version"):
        distance_tree_autop2_version = "?"
        megax_cc_docker_version = os.environ["megax_cc_docker_c_version"]
        distance_tree_megaxcc_program_version = "?"

    if os.environ.get("newick_utils_docker_c_version"):
        distance_tree_autop2_version = "?"
        newick_utils_docker_version = os.environ[
            "newick_utils_docker_c_version"
        ]
        distance_tree_newick_utils_program_version = "?"

    host_dir = os.environ.get("dir", "")
    project = os.environ.get("project", "")
    distance_tree_coordinates = os.environ.get(
        "distance_tree_coordinates", ""
    )
    vt_columns = os.environ.get("vt_columns", "")

    work_dir = f"/data/{prefix}distance_tree"
    out_dir_path = f"/data/{out_dir}"

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(out_dir_path, exist_ok=True)

    input_file = "tabulated.tsv"

    # Remove Windows-style line endings.
    with open(f"/data/{input_dir}/{input_file}") as f:
        raw_lines = f.read().splitlines()

    input_file_mod_lines = [
        line.replace("\r", "")
        for line in raw_lines
    ]

    with open("input_file_mod", "w") as f:
        for line in input_file_mod_lines:
            f.write(line + "\n")

    # Extract the specified columns from the input file.
    if not distance_tree_coordinates:
        input_file_mod1_lines = list(input_file_mod_lines)
    else:
        distance_tree_coordinates = _increment_coordinates(
            distance_tree_coordinates
        )

        input_file_mod1_lines = _cut_columns(
            input_file_mod_lines,
            f"1,{distance_tree_coordinates}",
        )

    with open("input_file_mod1", "w") as f:
        for line in input_file_mod1_lines:
            f.write(line + "\n")

    # Remove the amino-acid-name line.
    if len(input_file_mod1_lines) >= 2:
        del input_file_mod1_lines[1]

    with open("input_file_mod1", "w") as f:
        for line in input_file_mod1_lines:
            f.write(line + "\n")

    # Extract feature names and data matrix,
    # skipping the header line.
    lines = input_file_mod1_lines

    feature_names = []
    data = []

    for line in lines[1:]:
        row = line.split("\t")
        feature_names.append(row[0])
        data.append(row[1:])

    num_features = len(feature_names)

    num_data_columns = (
        len(lines[1].split("\t")) - 1
        if len(lines) > 1
        else 0
    )

    # Calculate the distance matrix.
    print("Calculating the distance matrix")

    distance_matrix = [
        [0] * num_features
        for _ in range(num_features)
    ]

    for i in range(num_features):
        for j in range(num_features):
            distance = 0

            for k in range(num_data_columns):
                if int(data[i][k]) != int(data[j][k]):
                    distance += 1

            distance_matrix[i][j] = distance

    # Print the distance matrix.
    results_lines = [
        "\t" + " ".join(feature_names)
    ]

    for i in range(num_features):
        row = feature_names[i] + "".join(
            f"\t{distance_matrix[i][j]}"
            for j in range(num_features)
        )

        results_lines.append(row)

    results_text = "\n".join(results_lines) + "\n"
    results_text = results_text.replace(" ", "\t")

    with open("results", "w") as f:
        f.write(results_text)

    shutil.copy2(
        "results",
        os.path.join(work_dir, "distance_matrix"),
    )

    os.remove("results")

    # Prepare the file for MEGA.
    print("Preparing the file for the UPGMA analysis")

    with open("results_mega.meg", "w", newline="") as f:
        f.write("#mega\r\n")
        f.write("title\r\n")
        f.write("\r\n")

        for name in feature_names:
            f.write(f"#{name}\r\n")

        f.write("\n")

        for i in range(num_features):
            for j in range(num_features):
                if i > j:
                    f.write(
                        f"{distance_matrix[i][j]}\t"
                    )

            f.write("\r\n")

    shutil.copy2(
        "results_mega.meg",
        os.path.join(work_dir, "mega_file.meg"),
    )

    # Make the MEGA analysis file available to
    # the nested megax_cc container.
    mao_file = "infer_UPGMA_distances.mao"
    module_dir = os.path.dirname(
        os.path.abspath(__file__)
    )
    mao_source = os.path.join(
        module_dir,
        mao_file,
    )
    mao_target = os.path.join(
        work_dir,
        mao_file,
    )

    if not os.path.isfile(mao_source):
        raise FileNotFoundError(
            f"Required MEGA analysis file not found: "
            f"{mao_source}"
        )

    shutil.copy2(
        mao_source,
        mao_target,
    )

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{host_dir}:/data",
            f"pegi3s/megax_cc:{megax_cc_docker_version}",
            "megacc",
            "-a",
            f"/data/{prefix}distance_tree/{mao_file}",
            "-d",
            f"/data/{prefix}distance_tree/mega_file.meg",
            "-o",
            f"/data/{out_dir}/distance_tree",
        ],
        check=True,
    )

    nwk_path = f"/data/{out_dir}/distance_tree.nwk"

    if not os.path.isfile(nwk_path):
        raise FileNotFoundError(
            f"MEGA did not generate the expected tree: "
            f"{nwk_path}"
        )

    # Extract the order of the samples from the tree.
    tree_order = []

    with open(nwk_path) as f:
        nwk_lines = f.read().splitlines()

    for nwk_line in nwk_lines:
        transformed = nwk_line.replace(",", "\n")
        transformed = transformed.replace("(", "")
        transformed = transformed.replace("):", ":\n")
        transformed = transformed.replace(":", ":\n")

        for part in transformed.split("\n"):
            if ":" in part:
                tree_order.append(
                    part.replace(":", "")
                )

    # Recover the original two header lines.
    with open(f"/data/{input_dir}/{input_file}") as f:
        original_head = f.read().splitlines()[:2]

    original_head = [
        line.replace("\r", "")
        for line in original_head
    ]

    if distance_tree_coordinates:
        header_lines = _cut_columns(
            original_head,
            f"1,{distance_tree_coordinates}",
        )
    else:
        header_lines = original_head

    # Write data in tree order.
    data_sorted_path = (
        f"/data/{out_dir}/data_sorted.tsv"
    )

    with open(data_sorted_path, "w") as f:
        for line in header_lines:
            f.write(line + "\n")

    with open(data_sorted_path, "a") as out:
        for order_value in tree_order:
            pattern = re.compile(
                r"^"
                + re.escape(order_value)
                + r"\b"
            )

            for line in input_file_mod1_lines:
                if pattern.match(line):
                    out.write(line + "\n")

    # Clean temporary files.
    os.remove("input_file_mod")
    os.remove("input_file_mod1")

    summary_path = (
        f"/data/{out_dir}/distance_tree_summary.txt"
    )

    if os.path.isfile(summary_path):
        os.remove(summary_path)

    os.remove("results_mega.meg")

    # Draw the Newick tree.
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{host_dir}:/data",
            f"pegi3s/newick_utils:{newick_utils_docker_version}",
            "bash",
            "-c",
            (
                f"nw_display -w {vt_columns} "
                f"-b 'visibility:hidden' "
                f"-s /data/{out_dir}/distance_tree.nwk "
                f"> /data/{out_dir}/distance_tree.svg"
            ),
        ],
        check=True,
    )

    svg_path = (
        f"/data/{out_dir}/distance_tree.svg"
    )

    if not os.path.isfile(svg_path):
        raise FileNotFoundError(
            f"newick_utils did not generate the expected SVG: "
            f"{svg_path}"
        )

    with open(svg_path) as f:
        svg_content = f.read()

    svg_content = svg_content.replace(
        "<defs><style type",
        '\n<rect width="100%" height="100%" '
        'fill="white"/>\n<defs><style type',
    )

    svg_content = svg_content.replace(
        ">substitutions/site<",
        ">distance<",
    )

    with open(svg_path, "w") as f:
        f.write(svg_content)

    record_version(
        f"distance_tree {distance_tree_autop2_version},"
        f"pegi3s/megax_cc:{megax_cc_docker_version},"
        f'MegaX_CC {distance_tree_megaxcc_program_version},'
        f'"{megaxcc_ref}","{megaxcc_doi}"'
    )

    record_version(
        f",pegi3s/newick_utils:"
        f"{newick_utils_docker_version},"
        f"Newick utils "
        f'{distance_tree_newick_utils_program_version},'
        f'"{newick_utils_ref}","{newick_utils_doi}"'
    )

    record_refs(
        f'megaxcc_ref="{megaxcc_ref}"\\'
        f'megaxcc_doi="{megaxcc_doi}"\n'
    )

    record_refs(
        f'newick_utils="{newick_utils_ref}"\\'
        f'newick_utils_doi="{newick_utils_doi}"\n'
    )


if __name__ == "__main__":
    print("Distances to trees", flush=True)
    main()
