"""Source-only split audit: no model outputs, re-labelling or test selection."""
from collections import defaultdict
import argparse
import json
from pathlib import Path
from indian_gst_dataset import DEFAULT_DATA, DEFAULT_MANIFEST, ROOT, digest


def audit(data, manifest_path):
    manifest = json.loads(manifest_path.read_text())
    raw = (data / 'publisher-metadata/synthetic.jsonl').read_bytes()
    if digest(raw) != manifest['metadata_sha256']['synthetic']:
        raise RuntimeError('Publisher metadata hash mismatch')
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    groups = {kind: defaultdict(set) for kind in ['label_bytes', 'invoice_identity', 'descriptions']}
    ids = defaultdict(list)
    for row in rows:
        split = row['split']
        gold = json.loads(row['label'])
        ids[split].append(row['id'])
        groups['label_bytes'][split].add(digest(row['label'].encode()))
        identity = tuple(str(value) for value in (
            gold['supplier'].get('gstin'), gold['supplier'].get('name'),
            gold.get('invoice_number'), gold.get('invoice_date')))
        groups['invoice_identity'][split].add(identity)
        groups['descriptions'][split].update(
            str(line.get('description', '')).strip().casefold()
            for line in gold['line_items'])
    overlaps = {}
    for left, right in [('train', 'val'), ('train', 'test'), ('val', 'test')]:
        overlaps[left + '__' + right] = {
            'record_ids': len(set(ids[left]) & set(ids[right])),
            **{kind: len(values[left] & values[right]) for kind, values in groups.items()}}
    return {
        'dataset': manifest['dataset'], 'revision': manifest['revision'],
        'metadata_sha256': digest(raw), 'split_record_counts': {k: len(v) for k, v in ids.items()},
        'unique_within_split': {kind: {k: len(v) for k, v in values.items()}
                                for kind, values in groups.items()},
        'cross_split_overlap_counts': overlaps,
        'scope': 'Source metadata only; no reader predictions, image similarity audit or independent label audit.',
        'interpretation': 'Repeated product descriptions show the intended splits are not held-out product families. '
                          'Invoice identity includes supplier GSTIN/name, invoice number and date; '
                          'a matching identity is a warning for future training, not proof of an identical image. '
                          'The current baseline performs no training. Source splits and labels stay unchanged.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--output', type=Path, default=ROOT / 'ml/data/indian-gst-v1/split-audit.json')
    args = parser.parse_args()
    result = audit(args.data, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['cross_split_overlap_counts']))
