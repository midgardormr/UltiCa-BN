"""Compose and check a Bright Nights pack from the current branch's sources."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from prepare_bn_tileset import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', choices=('UltimateCataclysm', 'Chibi_Ultica', 'Altica'))
    parser.add_argument('output', type=Path)
    parser.add_argument('--policy', type=Path, help='Optional external BN compatibility policy')
    args = parser.parse_args()
    tools = Path(__file__).resolve().parent
    source, output = tools.parent / 'gfx' / args.pack, args.output.resolve()
    if output == source.resolve() or source.resolve() in output.parents:
        parser.error('Output must be outside the source pack')
    if output.exists() and any(output.iterdir()):
        parser.error('Output must be empty')
    subprocess.run([sys.executable, str(tools / 'compose.py'), '--use-all',
                    '--feedback', 'CONCISE', str(source), str(output)], check=True)
    for name in ('tileset.txt', 'fallback.png', 'layering.json'):
        shutil.copyfile(source / name, output / name)
    prepare(source, output)
    command = [sys.executable, str(tools / 'check_bn_compatibility.py'), args.pack, str(output)]
    if args.policy:
        command += ['--policy', str(args.policy.resolve())]
    subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
