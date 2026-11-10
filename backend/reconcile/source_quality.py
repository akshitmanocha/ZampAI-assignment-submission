"""Conservative OCR quality gate; engine scores are not correctness probabilities."""
from copy import deepcopy

VERSION='ocr-minimum-word-score-60-v1'


def assess(extraction,pages):
    result=deepcopy(extraction)
    readings=[('header.'+name,value) for name,value in result['header'].items()]
    readings += [(f'lines[{i}].'+name,value) for i,line in enumerate(result['lines'],1) for name,value in line.items() if isinstance(value,dict)]
    for path,reading in readings:
        scores=[]
        for evidence in reading.get('evidence',[]):
            if evidence['method']!='ocr':continue
            page=pages[evidence['page']-1]
            x0,y0,x1,y1=evidence['bbox']
            scores.extend(w.confidence for w in page.words if w.confidence is not None and
                x0<=((w.source_bbox or w.bbox)[0]+(w.source_bbox or w.bbox)[2])/2<=x1 and
                y0<=((w.source_bbox or w.bbox)[1]+(w.source_bbox or w.bbox)[3])/2<=y1)
        if scores:
            reading['minimum_ocr_score']=min(scores)
            if min(scores)<60:
                reading['requires_source_verification']=True
                result['warnings'].append('low_ocr_score:'+path)
    result['quality_policy']=VERSION
    return result
