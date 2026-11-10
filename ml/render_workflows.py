"""Render neutral, reproducible invoice artifacts without reading expectations."""
from pathlib import Path
import hashlib,io,json,time
from copy import deepcopy
import numpy as np
from PIL import Image,ImageFilter
import pypdfium2
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor


def render(document,layout='table'):
    out=io.BytesIO();c=canvas.Canvas(out,pagesize=(595,842),invariant=1)
    c.setTitle('Invoice');c.setAuthor('Fictional validation supplier')
    c.setFillColor(HexColor('#173e34'));c.setFont('Helvetica-Bold',18);c.drawString(430,810,'INVOICE')
    c.setFillColor(HexColor('#222222'));c.setFont('Helvetica',10);c.drawString(45,810,'FROM')
    c.setFont('Helvetica-Bold',13);c.drawString(45,790,document['vendor_name'])
    c.setFont('Helvetica',10)
    no='Invoice No:' if layout=='table' else 'Invoice Number:'
    po='PO:' if layout=='table' else 'PO Number:'
    c.drawString(45,748,no+' '+(document.get('invoice_number') or ''))
    c.drawString(350,748,'Date: '+(document.get('invoice_date') or ''))
    c.drawString(45,724,po+' '+(document.get('po_reference') or 'Not provided'))
    c.drawString(350,724,'Currency: '+document['currency'])
    c.setFont('Helvetica-Bold',9)
    headers=[(45,'DESCRIPTION'),(325,'QTY'),(400,'UNIT PRICE'),(510,'AMOUNT' if layout=='table' else 'VALUE')]
    for x,text in headers:c.drawString(x,670,text)
    c.setLineWidth(.5);c.line(42,662,560,662)
    y=641
    for row in document['lines']:
        c.setFont('Helvetica',8.5)
        if c.stringWidth(row['description'])>265:raise ValueError('Description does not fit; do not silently clip the source')
        for x,text in [(45,row['description']),(325,row['qty']),(420,row['unit_price']),(510,row['amount'])]:c.drawString(x,y,text)
        if layout=='table':c.line(42,y-9,560,y-9)
        y-=30
    x=345 if layout=='table' else 45
    y-=30;c.setFont('Helvetica',10)
    for label,key in [('Subtotal','subtotal'),('Tax','tax_total'),('Grand Total','grand_total')]:
        c.drawString(x,y,label+' INR '+document[key]);y-=25
    c.setFont('Helvetica',8);c.drawString(45,60,'Fictional invoice. No payment is executed by this demonstration.')
    c.save();return out.getvalue()


def scanned(data,degraded=False):
    doc=pypdfium2.PdfDocument(data);page=doc[0];bitmap=page.render(scale=200/72)
    image=bitmap.to_pil().convert('RGB');bitmap.close();page.close();doc.close()
    if degraded:
        image=image.rotate(.4,resample=Image.Resampling.BICUBIC,expand=False,fillcolor='white')
        array=np.asarray(image,dtype=np.int16)
        rng=np.random.default_rng(1146)
        array=np.clip(array+rng.normal(0,3,array.shape),0,255).astype(np.uint8)
        image=Image.fromarray(array).filter(ImageFilter.GaussianBlur(.3))
        jpeg=io.BytesIO();image.save(jpeg,format='JPEG',quality=70);image.close();image=Image.open(io.BytesIO(jpeg.getvalue())).convert('RGB')
    out=io.BytesIO();image.save(out,format='PDF',resolution=200,creationDate=time.gmtime(0),modDate=time.gmtime(0));image.close();return out.getvalue()


def build(dataset,out):
    out.mkdir(parents=True,exist_ok=True);manifest={'renderer':'workflow-renderer-v1','variants':['native_table','native_columnar','scan_clean','scan_degraded'],'artifacts':[]}
    for path in sorted((dataset/'inputs').glob('*.json')):
        case=json.loads(path.read_text());doc=case['document'];native=render(doc)
        variants={'native_table':native,'native_columnar':render(doc,'columnar'),'scan_clean':scanned(native),'scan_degraded':scanned(native,True)}
        neutral=hashlib.sha256(json.dumps(doc,sort_keys=True).encode()).hexdigest()[:12]
        for variant,data in variants.items():
            filename=f'document-{neutral}-{variant}.pdf';target=out/filename
            if target.exists() and target.read_bytes()!=data:raise RuntimeError('Refusing to replace non-identical existing PDF')
            target.write_bytes(data)
            manifest['artifacts'].append({'case_id':case['id'],'group_id':case['group_id'],'variant':variant,'file':filename,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
    import reportlab,PIL
    manifest['versions']={'reportlab':reportlab.Version,'pillow':PIL.__version__,'numpy':np.__version__}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');return manifest

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=Path('fixtures/workflows/v1'));p.add_argument('--out',type=Path,required=True);a=p.parse_args();m=build(a.dataset,a.out);print('Rendered',len(m['artifacts']),'case/variant assignments')
