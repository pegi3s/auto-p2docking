#!/usr/bin/env python3
import os
import sys

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
module_dir_real = os.path.realpath(MODULE_DIR)
sys.path[:] = [
    path for path in sys.path
    if os.path.realpath(path or os.getcwd()) != module_dir_real
]
import copy as _stdlib_copy  # noqa: F401  (cached in sys.modules)
import tarfile
import tempfile
import subprocess
from pathlib import Path

sys.path.insert(0, MODULE_DIR)
from pymodule_common import load_config, record_version

DATA_ROOT = Path('/data')

pdb2fasta_autop2_version = '2.0.0'
pdb2fasta_docker_version = '0.24.0'
pdb2fasta_program_version = 'unknown'
pdb2fasta_ref = ''
pdb2fasta_doi = ''


def data_path(value):
    """Resolve an auto-p2docking relative path inside /data."""
    candidate = (DATA_ROOT / value).resolve()
    base = DATA_ROOT.resolve()
    if candidate == base or not candidate.is_relative_to(base):
        raise ValueError(f'Invalid path outside /data: {value}')
    return candidate


def main():
    global pdb2fasta_autop2_version, pdb2fasta_docker_version
    global pdb2fasta_ref, pdb2fasta_doi

    if len(sys.argv) != 4:
        sys.exit('Usage: pdb2fasta.py <input_dir> <output_dir> <prefix>')

    input_dir, output_dir, _prefix = sys.argv[1:4]
    load_config()

    # Honour the module-specific Docker override used throughout auto-p2docking.
    custom_docker_version = os.environ.get('pdb2fasta_docker_c_version', '').strip()
    if custom_docker_version:
        pdb2fasta_autop2_version = '?'
        pdb2fasta_docker_version = custom_docker_version
        pdb2fasta_ref = '?'
        pdb2fasta_doi = '?'

    try:
        source = data_path(input_dir)
        destination = data_path(output_dir)
    except ValueError as exc:
        sys.exit(f'Error: {exc}')

    if source == destination:
        sys.exit('Error: input and output directories must differ')
    if not source.is_dir():
        sys.exit(f'Error: PDB input directory does not exist: {source}')

    # The original utility searches for lowercase *.pdb files.
    pdbs = sorted(f for f in source.iterdir() if f.is_file() and f.suffix == '.pdb')
    if not pdbs:
        sys.exit(f'Error: no .pdb files found in {source}')

    destination.mkdir(parents=True, exist_ok=True)
    fasta_file = destination / 'Fasta_file'
    if fasta_file.is_symlink():
        sys.exit(f'Error: output is a symlink: {fasta_file}')
    if fasta_file.exists():
        if not fasta_file.is_file():
            sys.exit(f'Error: output is not a file: {fasta_file}')
        fasta_file.unlink()  # Never accept a stale result from an earlier run.

    image = f'pegi3s/utilities:{pdb2fasta_docker_version}'

    # The Docker daemon is on the HOST. Its bind-mount paths do not necessarily
    # match /data paths inside this container. Use stdin/stdout instead of -v.
    with tempfile.TemporaryFile() as archive:
        with tarfile.open(fileobj=archive, mode='w') as tar:
            for pdb in pdbs:
                tar.add(str(pdb), arcname=pdb.name, recursive=False)
        archive.seek(0)

        # The upstream utility writes Fasta_file into its working directory.
        # Redirect its status lines to stderr; return only FASTA bytes on stdout.
        script = (
            'set -eu; '
            'mkdir -p /tmp/pdb2fasta_input /tmp/pdb2fasta_output; '
            'tar -xf - -C /tmp/pdb2fasta_input; '
            'cd /tmp/pdb2fasta_output; '
            'pdb2fasta /tmp/pdb2fasta_input >&2; '
            'test -s Fasta_file; '
            'cat Fasta_file'
        )
        try:
            result = subprocess.run(
                ['docker', 'run', '--rm', '-i', '--entrypoint', '/bin/sh',
                 image, '-c', script],
                stdin=archive, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            sys.exit(f'Error: could not run Docker: {exc}')

    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.decode('utf-8', errors='replace').rstrip(),
                  file=sys.stderr, flush=True)
        sys.exit(f'Error: {image} pdb2fasta failed (exit code {result.returncode})')

    fasta = result.stdout
    if not fasta.strip() or not fasta.lstrip().startswith(b'>'):
        sys.exit('Error: utility returned no valid FASTA output')
    fasta_file.write_bytes(fasta)
    print(f'pdb2fasta: {len(pdbs)} PDB(s) → {output_dir}/Fasta_file', flush=True)

    record_version(
        f'pdb2fasta {pdb2fasta_autop2_version},'
        f'{image},'
        f'pdb2fasta {pdb2fasta_program_version},'
        f'"{pdb2fasta_ref}","{pdb2fasta_doi}"'
    )


if __name__ == '__main__':
    print('Running: pdb2fasta', flush=True)
    main()
