"""Add the standalone installer and checksums to built release artifacts."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import tarfile
import tomllib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    installer = root / 'install-release.sh'
    declared = re.search(r"^VERSION = ['\"]([^'\"]+)['\"]$", installer.read_text(), re.M)
    if not declared or declared.group(1) != version:
        parser.error('The installer version must match pyproject.toml.')
    names = [f'fast_verify_lab-{version}-py3-none-any.whl', f'fast_verify_lab-{version}.tar.gz']
    for name in names:
        if not (args.directory / name).is_file():
            parser.error(f'Missing release artifact: {name}')
    with tarfile.open(args.directory / names[1]) as archive:
        member = archive.extractfile(f'fast_verify_lab-{version}/install-release.sh')
        if member is None or member.read() != installer.read_bytes():
            parser.error('The source archive must contain the current release installer.')
    shutil.copy2(installer, args.directory / installer.name)
    names.append(installer.name)
    checksums = ''.join(
        f'{hashlib.sha256((args.directory / name).read_bytes()).hexdigest()}  {name}\n'
        for name in names
    )
    (args.directory / 'SHA256SUMS').write_text(checksums, encoding='utf-8')
    print(f'Prepared {len(names)} release files and SHA256SUMS for {version}.')


if __name__ == '__main__':
    main()
