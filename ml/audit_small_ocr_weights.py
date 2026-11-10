"""Independently count pinned ONNX initializers; requires optional onnx package."""
import argparse
import json
import math
from pathlib import Path
from reconcile.ocr_models import verify,checksum


def main():
    import onnx
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--profile',choices=['mobile','server'],default='mobile')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    paths=verify(args.directory,args.profile)
    files={}
    for task,path in paths.items():
        model=onnx.load(str(path))
        files[task]={'file':path.name,'sha256':checksum(path),'bytes':path.stat().st_size,
            'initializer_scalars_including_buffers':sum(math.prod(t.dims) for t in model.graph.initializer)}
    count=sum(f['initializer_scalars_including_buffers'] for f in files.values())
    if count>=1_000_000_000:raise RuntimeError('Pinned OCR profile exceeds requested stored-value budget')
    report={'profile':args.profile,'files':files,'total_initializer_scalars_including_buffers':count,
        'total_bytes':sum(f['bytes'] for f in files.values()),
        'interpretation':'Approximate network-size description; initializers include non-trainable buffers. Not an accuracy metric.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'stored_values':count,'weight_bytes':report['total_bytes']}))


if __name__=='__main__':main()
