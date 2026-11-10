"""Check immutable fixture hashes and exact curator reproducibility."""
from pathlib import Path
import tempfile
from curate_workflows import curate
from evaluate_workflows import check_hashes


def check(dataset):
    expected=check_hashes(dataset)
    with tempfile.TemporaryDirectory(prefix='reconcile-data-check-') as temp:
        target=Path(temp)/'dataset';actual=curate(target)
        if actual!=expected:raise RuntimeError('Curator no longer reproduces frozen labels; review a dataset version change')
    print('PASS: all input/oracle hashes and independent curator reproduction match')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('fixtures/workflows/v1'));a=p.parse_args();check(a.dataset)
