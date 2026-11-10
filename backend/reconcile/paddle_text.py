"""Offline PP-OCRv5 text/CTC-word boxes with bounded CPU threads."""
from functools import lru_cache
import math
import os
import statistics
from pathlib import Path
from reconcile.document_types import Word
from reconcile.ocr_models import verify


@lru_cache(maxsize=2)
def engine(directory,profile):
    from rapidocr import RapidOCR, OCRVersion, ModelType, LangDet, LangRec
    paths=verify(directory,profile)
    model_type=ModelType.MOBILE if profile=='mobile' else ModelType.SERVER
    return RapidOCR(params={
        'Global.use_cls':False,'Global.return_word_box':True,'Global.log_level':'error',
        'Global.max_side_len':2400,
        'Det.ocr_version':OCRVersion.PPOCRV5,'Det.model_type':model_type,
        'Det.lang_type':LangDet.CH,'Det.model_path':str(paths['det']),
        'Det.limit_side_len':1280 if profile=='mobile' else 960,'Det.limit_type':'max',
        'Rec.ocr_version':OCRVersion.PPOCRV5,'Rec.model_type':model_type,
        'Rec.lang_type':LangRec.EN if profile=='mobile' else LangRec.CH,'Rec.model_path':str(paths['rec']),
        'EngineConfig.onnxruntime.intra_op_num_threads':1,
        'EngineConfig.onnxruntime.inter_op_num_threads':1})


def recognize(image,width,height,directory=None,profile=None):
    directory=directory or os.getenv('OCR_MODEL_DIR','/opt/reconcile/ppocr-v5')
    profile=profile or os.getenv('OCR_PROFILE','server')
    result=engine(str(Path(directory).resolve()),profile)(image)
    sx,sy=width/image.width,height/image.height
    words=[]
    if not len(result):return ()
    angles=[]
    for polygon in result.boxes:
        dx,dy=polygon[1][0]-polygon[0][0],polygon[1][1]-polygon[0][1]
        if dx>20 and abs(dy/dx)<.27:angles.append(math.atan2(dy,dx))
    angle=statistics.median(angles) if angles else 0
    co,si=math.cos(angle),math.sin(angle)
    cx,cy=image.width/2,image.height/2
    for line in result.word_results:
        for text,confidence,polygon in line:
            if not text.strip() or polygon is None:continue
            xs=[p[0] for p in polygon];ys=[p[1] for p in polygon]
            box=(max(0,min(xs)*sx),max(0,min(ys)*sy),min(width,max(xs)*sx),min(height,max(ys)*sy))
            logical=[(co*(x-cx)+si*(y-cy)+cx,-si*(x-cx)+co*(y-cy)+cy) for x,y in polygon]
            layout=(min(p[0] for p in logical)*sx,min(p[1] for p in logical)*sy,
                max(p[0] for p in logical)*sx,max(p[1] for p in logical)*sy)
            confidence=float(confidence)*100
            if not all(math.isfinite(v) for v in (*box,confidence)):continue
            if box[0]>=box[2] or box[1]>=box[3]:continue
            words.append(Word(text.strip(),layout,confidence,box))
    return tuple(words)
