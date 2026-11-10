"""Offline VLM output adapters. All proposed geometry needs source verification."""
import math
import re
import statistics
from reconcile.document_types import PageText,Word


def proposed_page(record):
    width,height=record['image_size']
    lines=[]
    if record['engine']=='paddle-vl':
        pattern=r'([^\n]*?)((?:<\|LOC_\d+\|>){8})'
        for match in re.finditer(pattern,record.get('text','')):
            text=match.group(1).strip()
            numbers=[int(x) for x in re.findall(r'LOC_(\d+)',match.group(2))]
            polygon=[(numbers[i]*width/1000,numbers[i+1]*height/1000) for i in range(0,8,2)]
            if text:lines.append((text,polygon))
    else:
        document=record.get('document') or {}
        def rect(bbox):
            l,t,r,b=[bbox[k] for k in ['l','t','r','b']]
            if bbox.get('coord_origin')=='BOTTOMLEFT':t,b=height-t,height-b
            return [(l,min(t,b)),(r,min(t,b)),(r,max(t,b)),(l,max(t,b))]
        for item in document.get('texts',[]):
            if item.get('prov') and item.get('text'):lines.append((item['text'],rect(item['prov'][0]['bbox'])))
        for table in document.get('tables',[]):
            data=table.get('data',{});nr=data.get('num_rows',0);nc=data.get('num_cols',0)
            if not table.get('prov') or not nr or not nc:continue
            polygon=rect(table['prov'][0]['bbox']);x0,y0=polygon[0];x1,y1=polygon[2]
            for cell in data.get('table_cells',[]):
                text=cell.get('text','').strip()
                r=cell.get('start_row_offset',0);c=cell.get('start_col_offset',0)
                if text:
                    box=[(x0+(x1-x0)*c/nc,y0+(y1-y0)*r/nr),
                         (x0+(x1-x0)*(c+1)/nc,y0+(y1-y0)*r/nr),
                         (x0+(x1-x0)*(c+1)/nc,y0+(y1-y0)*(r+1)/nr),
                         (x0+(x1-x0)*c/nc,y0+(y1-y0)*(r+1)/nr)]
                    lines.append((text,box))
    angles=[math.atan2(p[1][1]-p[0][1],p[1][0]-p[0][0]) for _,p in lines if p[1][0]-p[0][0]>20 and abs(p[1][1]-p[0][1])<.27*(p[1][0]-p[0][0])]
    angle=statistics.median(angles) if angles else 0
    co,si=math.cos(angle),math.sin(angle);cx,cy=width/2,height/2
    words=[]
    for text,polygon in lines:
        for token in re.finditer(r'\S+',text):
            lo,hi=token.start()/len(text),token.end()/len(text)
            top0,top1,bottom1,bottom0=polygon
            def interp(a,b,f):return (a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f)
            points=[interp(top0,top1,lo),interp(top0,top1,hi),interp(bottom0,bottom1,hi),interp(bottom0,bottom1,lo)]
            logical=[(co*(x-cx)+si*(y-cy)+cx,-si*(x-cx)+co*(y-cy)+cy) for x,y in points]
            box=(min(p[0] for p in logical),min(p[1] for p in logical),max(p[0] for p in logical),max(p[1] for p in logical))
            source=(min(p[0] for p in polygon),min(p[1] for p in polygon),max(p[0] for p in polygon),max(p[1] for p in polygon))
            words.append(Word(token.group(),box,None,source))
    scale=72/200
    words=tuple(Word(w.text,tuple(c*scale for c in w.bbox),None,
        tuple(c*scale for c in w.source_bbox)) for w in words)
    return PageText(1,'vision-proposal',width*scale,height*scale,words,('vlm_geometry_is_unverified',),record['engine'])


def require_review(extraction):
    values=list(extraction['header'].values())
    values += [v for line in extraction['lines'] for v in line.values() if isinstance(v,dict)]
    for value in values:
        if value.get('status')=='found':value['requires_source_verification']=True
    extraction['warnings'].append('vlm_readings_require_source_verification')
    return extraction


def omit_images(value):
    if isinstance(value,dict):
        return {k:('<original image omitted; source hash retained>' if k=='uri' and isinstance(v,str) and v.startswith('data:image/') else omit_images(v)) for k,v in value.items()}
    if isinstance(value,list):return [omit_images(v) for v in value]
    return value
