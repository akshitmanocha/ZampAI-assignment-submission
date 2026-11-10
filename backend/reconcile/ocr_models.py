"""Pinned PP-OCRv5 ONNX weights; downloaded at setup, never during ingestion."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

ASSETS={
    'det':('ch_PP-OCRv5_det_server.onnx','0f8846b1d4bba223a2a2f9d9b44022fbc22cc019051a602b41a7fda9667e4cad'),
    'rec':('ch_PP-OCRv5_rec_server.onnx','e09385400eaaaef34ceff54aeb7c4f0f1fe014c27fa8b9905d4709b65746562a'),
}
MOBILE_ASSETS={
    'det':('ch_PP-OCRv5_det_mobile.onnx','4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae'),
    'rec':('en_PP-OCRv5_rec_mobile.onnx','c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8'),
}
BASE='https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5'


def checksum(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def assets(profile):
    if profile not in ['server','mobile']:raise ValueError('Unknown pinned OCR profile')
    return MOBILE_ASSETS if profile=='mobile' else ASSETS


def verify(directory,profile='server'):
    paths={}
    for task,(name,expected) in assets(profile).items():
        path=Path(directory)/name
        if not path.is_file() or checksum(path)!=expected:
            raise RuntimeError('Missing or invalid pinned OCR model: '+name)
        paths[task]=path
    return paths


def provision(directory,profile='server'):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for task,(name,expected) in assets(profile).items():
        path=directory/name
        if path.exists() and checksum(path)==expected:continue
        temporary=path.with_suffix('.download')
        with urllib.request.urlopen(f'{BASE}/{task}/{name}',timeout=90) as response, temporary.open('wb') as stream:
            size=0
            while chunk:=response.read(1024*1024):
                size+=len(chunk)
                if size>400*1024*1024:raise RuntimeError('OCR model exceeds download size limit')
                stream.write(chunk)
        if checksum(temporary)!=expected:
            temporary.unlink(missing_ok=True)
            raise RuntimeError('OCR weight SHA-256 mismatch')
        temporary.replace(path)
    verify(directory,profile)
    print('Verified pinned PP-OCRv5 detector and recognizer:',directory)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--profile',choices=['server','mobile'],default='server')
    args=parser.parse_args()
    provision(args.directory,args.profile)
