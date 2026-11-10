"""Deterministic synthetic procurement-pair pilot. No external-data claims."""
from pathlib import Path
from itertools import combinations
import hashlib
import json
import random

# Two independently meaningful attributes per family. All combinations are valid.
FAMILIES = [
 ('exam gloves',['nitrile','latex'],['medium','large']),
 ('hex bolts',['steel','brass'],['M6','M8']),
 ('flat washers',['steel','nylon'],['M6','M10']),
 ('water pipes',['PVC','copper'],['15mm','22mm']),
 ('packing tape',['paper','polypropylene'],['24mm','48mm']),
 ('laboratory beakers',['glass','polypropylene'],['250ml','500ml']),
 ('cable ties',['nylon','steel'],['100mm','200mm']),
 ('office folders',['paper','plastic'],['A4','A5']),
 ('hose clamps',['steel','plastic'],['20mm','40mm']),
 ('cleaning brushes',['nylon','brass'],['25mm','50mm']),
 ('rope',['cotton','nylon'],['6mm','12mm']),
 ('safety boots',['PVC','rubber'],['size 8','size 10']),
 ('storage bins',['steel','plastic'],['10L','20L']),
 ('machine screws',['steel','brass'],['M4','M6']),
 ('mesh filters',['steel','nylon'],['100 micron','200 micron']),
 ('cutting boards',['wood','plastic'],['30cm','45cm']),
 ('tubing',['silicone','PVC'],['4mm','8mm']),
 ('rubber seals',['EPDM','silicone'],['20mm','30mm']),
 ('cleaning cloths',['cotton','microfiber'],['20cm','40cm']),
 ('paint brushes',['nylon','natural bristle'],['25mm','75mm']),
]


def curate(out=Path('ml/data/pilot')):
    out.mkdir(parents=True, exist_ok=True)
    order=list(range(len(FAMILIES)));random.Random(17).shuffle(order)
    groups={i: ('train' if n<12 else 'validation' if n<15 else 'calibration' if n<17 else 'test') for n,i in enumerate(order)}
    rows=[];catalog=[]
    for fi,(family,materials,sizes) in enumerate(FAMILIES):
        products=[]
        for mi,m in enumerate(materials):
            for si,s in enumerate(sizes):
                pid=f'F{fi:02d}-M{mi}-S{si}'
                descriptions=[f'{m} {family} {s}', f'{family}, {s}, {m}', f'{s} {family} made of {m}', f'{family.upper()} / {m.upper()} / {s.upper()}']
                products.append((pid,m,s,descriptions))
                catalog.append({'product_id':pid,'family':family,'material':m,'size':s,'descriptions':descriptions,'split':groups[fi]})
        for pid,m,s,variants in products:
            for a,b in combinations(variants,2):
                rows.append({'left':a,'right':b,'label':1,'reason':'same_product','family':family,'left_id':pid,'right_id':pid,'split':groups[fi]})
        for a,b in combinations(products,2):
            for v in range(4):
                rows.append({'left':a[3][v],'right':b[3][(v+1)%4],'label':0,'reason':'material_or_size_conflict','family':family,'left_id':a[0],'right_id':b[0],'split':groups[fi]})
    assert len(rows)==960
    manifests={}
    for split in ['train','validation','calibration','test']:
        selected=[r for r in rows if r['split']==split]
        raw=''.join(json.dumps(r,sort_keys=True)+'\n' for r in selected).encode()
        (out/f'{split}.jsonl').write_bytes(raw)
        manifests[split]={'rows':len(selected),'positive':sum(r['label'] for r in selected),'families':sorted({r['family'] for r in selected}),'sha256':hashlib.sha256(raw).hexdigest()}
    (out/'catalog.json').write_text(json.dumps(catalog,indent=2))
    manifest={'source':'locally generated fictional catalog; no Hugging Face or real-invoice data','seed':17,'generator':'ml/curate.py','label_method':'exact catalog identity; material/size conflicts label negative','audit':'structural label checks automated; no independent human audit yet','limitations':['Only 20 families and four simple description templates','No OCR noise, missing attributes, packing conversions or real invoices','Family-disjoint pilot, not production performance'],'splits':manifests}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest

if __name__=='__main__':
    print(json.dumps(curate(),indent=2))
