"""Check required documents and local Markdown links. This is not an STE validator."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('README.md', 'README.ko.md', 'GUIDE.md', 'CONTRIBUTING.md', 'SECURITY.md',
            'CODE_OF_CONDUCT.md', 'CHANGELOG.md', 'LICENSE')
errors = []
for name in REQUIRED:
    if not (ROOT / name).is_file():
        errors.append(f'Missing file: {name}')
files = [ROOT / name for name in REQUIRED if name.endswith('.md')]
files += list((ROOT / 'docs').glob('*.md'))
for path in files:
    if not path.is_file():
        continue
    text = path.read_text(encoding='utf-8')
    # Code samples can contain Markdown literals that are not document links.
    prose = re.sub(r'```.*?```', '', text, flags=re.S)
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', prose):
        target = target.split(' "', 1)[0].strip('<>')
        url = urlsplit(target)
        if url.scheme or target.startswith('#') or not url.path:
            continue
        dest = (ROOT if target.startswith('/') else path.parent) / unquote(url.path).lstrip('/')
        if not dest.exists():
            errors.append(f'{path.relative_to(ROOT)}: missing link target {target}')
    if '\u2014' in prose:
        errors.append(f'{path.relative_to(ROOT)}: replace the em dash with a sentence or comma')
if errors:
    print('\n'.join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f'Checked {len(files)} documents: required files and local links pass.')
