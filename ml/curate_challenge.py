"""Fresh synthetic diagnostic, frozen before first scoring. No training on it."""
from pathlib import Path
from itertools import combinations
import hashlib,json,random

# New item families and explicit attribute changes; no expected value is supplied
# to the model beyond the two printed description strings.
FAMILIES=[
 ('hex nuts',['steel','brass'],['M8','M10']),
 ('flange gaskets',['rubber','PTFE'],['DN25','DN50']),
 ('woven sacks',['jute','polypropylene'],['25kg','50kg']),
 ('drill bits',['HSS','carbide'],['6mm','8mm']),
 ('ball bearings',['steel','ceramic'],['608','6201']),
 ('shipping labels',['paper','polyester'],['50x25mm','100x50mm']),
 ('power cables',['copper','aluminium'],['2.5mm2','4mm2']),
 ('compression springs',['steel','brass'],['20mm','30mm']),
 ('insulation sheets',['cork','rubber'],['3mm','5mm']),
 ('laboratory funnels',['glass','polypropylene'],['50mm','100mm']),
]

def curate(root=Path('ml/data/challenge-v1')):
    root.mkdir(parents=True,exist_ok=True);rows=[]
    for n,(family,materials,sizes) in enumerate(FAMILIES):
        products=[]
        for m in materials:
            for s in sizes:
                variants=[f'{m} {family} {s}',f'{family}, specification {s}, material {m}',f'Supply {s} {m} {family}',f'{family.upper()} | {s.upper()} | {m.upper()}',f'{m}  {family}  {s}',f'{family} ({m}), {s}; for stores']
                products.append((m,s,variants))
                for a,b in combinations(variants,2):rows.append({'left':a,'right':b,'label':1,'family':family,'reason':'same_catalog_product','split':'fresh_challenge'})
        negatives=[]
        for a,b in combinations(products,2):
            for i in range(6):negatives.append({'left':a[2][i],'right':b[2][(i+1)%6],'label':0,'family':family,'reason':'explicit_material_or_spec_conflict','split':'fresh_challenge'})
        # Repeat neither examples nor labels: six product pairs x six variants =36.
        # Balance using 36 independently selected positive description pairs.
        positives=[r for r in rows if r['family']==family]
        rows=[r for r in rows if r['family']!=family]
        rows.extend(random.Random(113+n).sample(positives,len(negatives)));rows.extend(negatives)
    raw=''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows).encode();(root/'pairs.jsonl').write_bytes(raw)
    manifest={'source':'fictional catalog-derived description pairs','rows':len(rows),'positive':sum(r['label'] for r in rows),'families':len(FAMILIES),'seed':113,'sha256':hashlib.sha256(raw).hexdigest(),'frozen_before_first_scoring':True,'limitations':['Synthetic explicit descriptions only, no independent full human audit','No OCR corruption or missing attributes','Fresh families/templates but shares material tokens and specification patterns with training','No invoice or no-candidate labels; not invoice automation']}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2));return manifest

if __name__=='__main__':print(json.dumps(curate(),indent=2))
