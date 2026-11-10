"""Download public pinned MiniLM artifacts once, never at invoice-processing time."""
import hashlib
import json
from pathlib import Path
import urllib.request
from reconcile.retrieval import MODEL, REVISION
from reconcile.settings import model_dir

EXPECTED = {
    'tokenizer.json': 'be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037',
    'model.onnx': '6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452',
}


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for remote, local in [('tokenizer.json', 'tokenizer.json'), ('onnx/model.onnx', 'model.onnx')]:
        path = directory / local
        if not path.exists():
            temporary = path.with_suffix('.partial')
            with urllib.request.urlopen(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{remote}', timeout=120) as response, temporary.open('wb') as f:
                while chunk := response.read(1024 * 1024):
                    f.write(chunk)
            temporary.replace(path)
        hashes[local] = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes[local] != EXPECTED[local]:
            raise RuntimeError('Pinned model artifact checksum mismatch: ' + local)
    (directory / 'manifest.json').write_text(json.dumps({
        'model': MODEL, 'revision': REVISION, 'license': 'Apache-2.0',
        'pooling': 'attention masked mean, then L2 normalization', 'sha256': hashes}, indent=2))
    print('MiniLM artifacts prepared:', str(directory))


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--directory', type=Path, default=model_dir())
    prepare(p.parse_args().directory)
