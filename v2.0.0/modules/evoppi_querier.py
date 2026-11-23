#!/usr/bin/env python3
import ast
import glob
import os
import random
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymodule_common import load_config, record_refs, record_version

evoppi_autop2_version = "2.0.0"
evoppi_docker_version = "1.0.1"
evoppi_ref = "Vázquez et al. (2019)"
evoppi_doi = "10.1007/s12539-019-00317-y"

_CONFIG_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evoppi_config.py")


def _load_species_defaults(source_path=_CONFIG_PY):
    """Each table entry is a 7-item list:
    [species_name, int_db, int_mod, int_polyq, pred_db, pred_mod, pred_polyq]
    """
    with open(source_path) as f:
        source = f.read()

    table = {}
    for name, literal in re.findall(r"^(\w+)\s*=\s*(\[.*\])\s*$", source, re.MULTILINE):
        if name.startswith("evoppi_q_"):
            continue
        try:
            values = ast.literal_eval(literal)
        except (SyntaxError, ValueError):
            continue
        if isinstance(values, list) and len(values) == 7:
            table[values[0]] = values
    return table


def _resolve_defaults(species, intdb, intmod, intpolyq, preddb, predmod, predpolyq):
    """Replace any field equal to "*" with the species' default value,
    matching evoppi_config.py's "if evoppi_q_intdb == '*': ..." blocks."""
    defaults = _load_species_defaults().get(species)
    if defaults is None:
        return intdb, intmod, intpolyq, preddb, predmod, predpolyq

    _, d_intdb, d_intmod, d_intpolyq, d_preddb, d_predmod, d_predpolyq = defaults
    return (
        d_intdb if intdb == "*" else intdb,
        d_intmod if intmod == "*" else intmod,
        d_intpolyq if intpolyq == "*" else intpolyq,
        d_preddb if preddb == "*" else preddb,
        d_predmod if predmod == "*" else predmod,
        d_predpolyq if predpolyq == "*" else predpolyq,
    )


def _write_evoppi_config(path, species, geneid, level, intdb, intmod, intpolyq, preddb, predmod, predpolyq):
    with open(path, "w") as f:
        f.write(f"Species={species}\n")
        f.write(f"GeneID={geneid}\n")
        f.write(f"Int_level={level}\n")
        f.write("Format=single\n")
        f.write(f"Interactome.Databases={intdb}\n")
        f.write(f"Interactome.Modifiers_22={intmod}\n")
        f.write(f"Interactome.polyQ_22={intpolyq}\n")
        f.write(f"Predictome.Databases={preddb}\n")
        f.write(f"Predictome.Modifiers_22={predmod}\n")
        f.write(f"Predictome.polyQ_22={predpolyq}")


def main():
    global evoppi_autop2_version, evoppi_docker_version, evoppi_ref, evoppi_doi

    if len(sys.argv) < 4:
        sys.exit("Usage: evoppi_querier.py <input_dir> <out_dir> <prefix>")

    load_config()

    input_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]

    for input_file in sorted(glob.glob(f"/data/{input_dir}/*")):
        if os.path.isfile(input_file):
            load_config(input_file)

    if os.environ.get("evoppi_docker_c_version"):
        evoppi_autop2_version = "?"
        evoppi_docker_version = os.environ["evoppi_docker_c_version"]
        evoppi_ref = "?"
        evoppi_doi = "?"

    final_dir = f"/data/{out_dir}"
    if os.path.exists(os.path.join(final_dir, "evoppi_output_1.gi")):
        print("There are already two files in the folder. Doing nothing")
        return

    work_dir = f"/data/{prefix}evoppi_querier"
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    species = os.environ.get("evoppi_q_species", "")
    geneid = os.environ.get("evoppi_q_geneid", "")
    level = os.environ.get("evoppi_q_level", "")
    intdb, intmod, intpolyq, preddb, predmod, predpolyq = _resolve_defaults(
        species,
        os.environ.get("evoppi_q_intdb", ""),
        os.environ.get("evoppi_q_intmod", ""),
        os.environ.get("evoppi_q_intpolyq", ""),
        os.environ.get("evoppi_q_preddb", ""),
        os.environ.get("evoppi_q_predmod", ""),
        os.environ.get("evoppi_q_predpolyq", ""),
    )

    config_path = os.path.join(work_dir, "config")
    _write_evoppi_config(config_path, species, geneid, level, intdb, intmod, intpolyq, preddb, predmod, predpolyq)

    host_dir = os.environ.get("dir", "")
    output_dir = os.path.join(work_dir, "evoppi_querier_output")
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{host_dir}/{prefix}evoppi_querier:/data",
            "-w", "/data",
            f"pegi3s/evoppi-querier:{evoppi_docker_version}",
            "query_single_species", "-c", "config", "-o", "evoppi_querier_output",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    col3, col1 = [], []
    for csv_path in sorted(glob.glob(os.path.join(output_dir, "*"))):
        if not os.path.isfile(csv_path):
            continue
        with open(csv_path) as f:
            rows = f.read().splitlines()[1:]
        for row in rows:
            fields = row.split(",")
            if len(fields) >= 3:
                col3.append(fields[2])
            if fields:
                col1.append(fields[0])

    combined = sorted(set(col1 + col3))
    combined = [gi for gi in combined if gi != geneid]

    pattern = re.compile(re.escape(geneid) + ".*" + re.escape(geneid)) if geneid else None
    paste_lines = [f"{a}\t{b}" for a, b in zip(col3, col1)]
    if pattern and any(pattern.search(line) for line in paste_lines):
        combined.append(geneid)

    working_output_path = os.path.join(work_dir, "evoppi_output.gi")
    with open(working_output_path, "w") as f:
        for gi in combined:
            f.write(gi + "\n")

    max_int = int(os.environ.get("evoppi_q_max_int") or 0)
    if len(combined) > max_int:
        shuffled = combined[:]
        random.shuffle(shuffled)
        selected = shuffled[:max_int]
    else:
        selected = combined

    dest_file = "evoppi_output_1.gi" if os.path.exists(os.path.join(final_dir, "evoppi_output.gi")) else "evoppi_output.gi"
    dest_path = os.path.join(final_dir, dest_file)
    with open(dest_path, "w") as f:
        for gi in selected:
            f.write(gi + "\n")

    record_version(
        f'evoppi_querier {evoppi_autop2_version},pegi3s/evoppi-querier:{evoppi_docker_version},,"{evoppi_ref}","{evoppi_doi}"'
    )
    record_refs(f'evoppi_ref="{evoppi_ref}"\nevoppi_doi="{evoppi_doi}"\n')


if __name__ == "__main__":
    print("Querying evoppi", flush=True)
    main()
