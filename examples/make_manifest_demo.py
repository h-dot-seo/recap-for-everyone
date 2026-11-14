"""Create a fictional contributor checkout for the manifest-generator guide."""
import argparse
import hashlib
import json
from pathlib import Path


def make_demo(output):
    root = Path(output)
    root.mkdir(parents=False, exist_ok=False)
    before = b'Synthetic original text\n'
    removed = b'Synthetic removed text\n'
    manifest = dict(project='fictional-demo', release='0.1.0', date='2026-01-01',
                    private_history_imported=False, actual_corpora_included=False,
                    synthetic_examples_only=True, license_status='NOT_SELECTED', file_count=2,
                    files=[dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                           for name, raw in [('changed.txt', before), ('removed.txt', removed)]])
    (root/'PUBLICATION_MANIFEST.json').write_bytes((json.dumps(manifest, indent=2)+'\n').encode())
    (root/'changed.txt').write_bytes(b'Synthetic changed text\n')
    (root/'added.txt').write_bytes(b'Synthetic added text\n')
    return dict(status='SYNTHETIC_DEMO_CREATED', files=3,
                boundary='Fictional files only; not an actual privacy, rights or publication review.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(make_demo(args.output)))


if __name__ == '__main__':
    main()
