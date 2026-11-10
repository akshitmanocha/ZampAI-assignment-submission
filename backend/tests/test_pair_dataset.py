"""Dataset integrity checks; these do not measure model quality."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]/'ml/data/pilot'


def test_splits_have_no_product_or_family_leakage():
    seen_products=set();seen_families=set()
    for split in ['train','validation','calibration','test']:
        rows=[json.loads(x) for x in (ROOT/f'{split}.jsonl').read_text().splitlines()]
        products={r[k] for r in rows for k in ['left_id','right_id']}
        families={r['family'] for r in rows}
        assert not products&seen_products
        assert not families&seen_families
        assert sum(r['label'] for r in rows)==len(rows)//2
        seen_products.update(products);seen_families.update(families)


def test_labels_follow_catalog_identity_and_preserve_test_hashes():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for split,info in manifest['splits'].items():
        raw=(ROOT/f'{split}.jsonl').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==info['sha256']
        rows=[json.loads(x) for x in raw.decode().splitlines()]
        assert len(rows)==info['rows']
        for r in rows:
            assert r['label']==int(r['left_id']==r['right_id'])
