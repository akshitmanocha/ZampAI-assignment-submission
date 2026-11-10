"""Printed GST headers and column geometry; no label/catalog/model access.

Net taxable values remain distinct from gross totals and tax components. Unit
labels are read literally: BOX never invents an items-per-box conversion.
"""
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import re
import statistics


def enrich(extraction,pages):
    from reconcile.invoice_parser import Reading,Row,text_rows,monetary_field,decimal_string,resolve
    rows=text_rows(pages)
    if not any(re.search(r'\bGSTIN\b|\bHSN\s*[/]?\s*SAC\b',r.text,re.I) for r in rows):return extraction
    header=extraction['header']
    for field,pattern in {
        'subtotal':r'\b(?:taxable\s+value|total\s+taxable(?:\s+value)?|net\s+taxable)\b',
        'grand_total':r'\b(?:grand\s+total|net\s+payable|total\s+amount)\b',
        'cgst_total':r'\bCGST\b','sgst_total':r'\bSGST\b','igst_total':r'\bIGST\b',
        'round_off':r'\bround\s*off\b',
    }.items():
        reading=monetary_field(rows,pattern)
        if reading.status!='missing':header[field]=asdict(reading)

    # A legal-name line at the top is stronger evidence than stitching an
    # invoice title or address onto it. Clip out right-hand invoice metadata.
    names=[]
    seller_limit=min([r.bbox[1] for r in rows if r.page==pages[0].page and
        re.search(r'\bGST[Il1]N\b|\bBill\s+To\b|^To\s*:',r.text,re.I)] or [pages[0].height*.23])
    for row in rows:
        if row.page!=pages[0].page or row.bbox[1]>=min(seller_limit,pages[0].height*.23):continue
        title_start=min([w.bbox[0] for w in row.words if w.text.upper() in ['TAX','INVOICE']] or [pages[0].width])
        words=tuple(w for w in row.words if w.bbox[0]<title_start)
        if not words:continue
        candidate=Row(row.page,row.method,words)
        if len(candidate.text.split())>=2 and not re.search(r'\b(?:invoice|gstin|state|code|bill|buyer|customer|recipient|original|duplicate)\b|@|\d',candidate.text,re.I):
            names.append((candidate.text,candidate.evidence()))
    if names:
        # Source order, not matching against expected vendor names.
        header['vendor_name']=asdict(resolve(names[:1]))
    else:
        # A buyer name is not a safe fallback for an unreadable seller block.
        header['vendor_name']=asdict(Reading(None,'missing'))

    columns=None;lines=[]
    patterns={
        'description':r'^(?:description|desoription|item|product|particulars|service)$',
        'hsn_sac':r'^HSN(?:/?SAC)?$', 'qty':r'^(?:qty|quantity)$',
        'unit':r'^(?:unit|uom)$','unit_price':r'^(?:rate|price)$',
        'amount':r'^(?:taxable|value)$','gst_rate':r'^GST%?$',
        'cgst_amount':r'^CGST$','sgst_amount':r'^SGST$','igst_amount':r'^IGST$',
    }
    for row in rows:
        anchors={}
        for name,pattern in patterns.items():
            found=[w for w in row.words if re.fullmatch(pattern,w.text.strip(':()'),re.I)]
            if len(found)==1:anchors[name]=found[0]
        if all(k in anchors for k in ['description','qty','unit_price','amount']) and ('hsn_sac' in anchors or 'unit' in anchors or 'gst_rate' in anchors):
            ordered=sorted(anchors,key=lambda k:sum(anchors[k].bbox[::2])/2)
            if not (ordered.index('description')<ordered.index('qty')<ordered.index('unit_price')<ordered.index('amount')):continue
            positions={k:(anchors[k].bbox[0]+anchors[k].bbox[2])/2 for k in ordered}
            # Relative to glyph height: pixel and PDF-point coordinates must
            # identify the same column. A fixed 12-point gutter could capture
            # the printed serial number when OCR pixels were scaled to points.
            glyph_height=statistics.median(w.bbox[3]-w.bbox[1] for w in anchors.values())
            limits={}
            for i,name in enumerate(ordered):
                left=(positions[ordered[i-1]]+positions[name])/2 if i else anchors[name].bbox[0]-.5*glyph_height
                right=(positions[name]+positions[ordered[i+1]])/2 if i+1<len(ordered) else pages[row.page-1].width
                if name=='description' and i+1<len(ordered):right=anchors[ordered[i+1]].bbox[0]-.35*glyph_height
                limits[name]=(left,right)
            columns=(row.page,limits);continue
        if columns is None or columns[0]!=row.page:continue
        if re.search(r'\b(?:taxable\s+value|grand\s+total|round\s*off|amount\s+in\s+words|declaration|sub[ -]?total|total\s+taxable)\b',row.text,re.I):
            columns=None;continue
        buckets={name:tuple(w for w in row.words if left<=(w.bbox[0]+w.bbox[2])/2<right) for name,(left,right) in columns[1].items()}
        desc=' '.join(w.text for w in buckets['description']).strip()
        if not desc or not any(c.isalpha() for c in desc):continue
        line={'line_no':len(lines)+1}
        for name,words in buckets.items():
            value=' '.join(w.text for w in words).strip()
            if name not in ['description','unit','hsn_sac']:
                value=decimal_string(re.sub(r'\s+','',value).rstrip('%'))
            elif not value:value=None
            reading=Reading(value,'found' if value is not None else 'missing',
                (Row(row.page,row.method,words).evidence(),) if words else ())
            line[name]=asdict(reading)
        numeric_count=sum(line.get(k,{}).get('status')=='found' for k in ['qty','unit_price','amount'])
        if numeric_count<2:
            # A short continuation occupies only the description column and
            # has no new serial number. Never infer a missing numerical value.
            before=[w for w in row.words if w.bbox[2]<columns[1]['description'][0]]
            previous=lines[-1]['description'] if lines else None
            if numeric_count==0 and previous and not before and len(desc.split())<=6 and all(not words for name,words in buckets.items() if name!='description'):
                previous['value']+=' '+desc
                previous['evidence']=(*previous['evidence'],asdict(Row(row.page,row.method,buckets['description']).evidence()))
            continue
        lines.append(line)
        if all(line.get(k,{}).get('status')=='found' for k in ['qty','unit_price','amount']):
            if abs(Decimal(line['qty']['value'])*Decimal(line['unit_price']['value'])-Decimal(line['amount']['value']))>Decimal('.01'):
                extraction['warnings'].append(f'line_{len(lines)}_arithmetic_mismatch')
    if lines:
        extraction['lines']=lines
        extraction['warnings']=[w for w in extraction['warnings'] if w!='line_items_not_reconstructed']
    else:
        # Receipt-style GST invoices print each item over three physical lines.
        # Recognition is anchored to an explicit multiplication sign and HSN;
        # the amount must be printed, never computed from qty/rate.
        receipt=[]
        number=r'[+-]?\d[\d,]*(?:\.\d+)?'
        for i,row in enumerate(rows):
            match=re.fullmatch(rf'\s*({number})\s+([A-Za-z]+)\s*[xX×]\s*({number})\s+({number})\s*',row.text)
            if not match or i==0:continue
            previous=rows[i-1]
            if previous.page!=row.page or row.bbox[1]-previous.bbox[3]>2*max(row.bbox[3]-row.bbox[1],previous.bbox[3]-previous.bbox[1]):continue
            if re.search(r'\b(?:HSN|GST|taxable|total|Bill|POS)\b',previous.text,re.I):continue
            following=rows[i+1] if i+1<len(rows) else None
            if following is None or following.page!=row.page or not re.search(r'\bHSN\b',following.text,re.I):continue
            line={'line_no':len(receipt)+1,'description':asdict(Reading(previous.text,'found',(previous.evidence(),)))}
            for name,value in zip(['qty','unit','unit_price','amount'],match.groups()):
                value=value if name=='unit' else decimal_string(value)
                line[name]=asdict(Reading(value,'found' if value is not None else 'missing',(row.evidence(),)))
            hsn=re.search(r'\bHSN\s*:?\s*(\d{4,8})\b',following.text,re.I)
            gst=re.search(r'\bGST\s*:?\s*(\d{1,2}(?:\.\d+)?)\s*%',following.text,re.I)
            for name,match_value in [('hsn_sac',hsn),('gst_rate',gst)]:
                if match_value:line[name]=asdict(Reading(match_value.group(1),'found',(following.evidence(),)))
            receipt.append(line)
        if receipt:
            extraction['lines']=receipt
            extraction['warnings']=[w for w in extraction['warnings'] if w!='line_items_not_reconstructed']
    for row in rows:
        bill=re.search(r'^Bill\s*:\s*([^\s]+)',row.text,re.I)
        if not bill:continue
        if header['invoice_number']['status']=='missing':
            header['invoice_number']=asdict(Reading(bill.group(1),'found',(row.evidence(),)))
        dates=re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b',row.text)
        if header['invoice_date']['status']=='missing' and len(dates)==1:
            token=dates[0];a,b,_=re.split(r'[/-]',token)
            if int(a)<=12 and int(b)<=12 and int(a)!=int(b):
                header['invoice_date']=asdict(Reading(None,'ambiguous',(row.evidence(),),(token,)))
            else:
                fmt='%d/%m/%Y' if int(a)>12 or int(a)==int(b) else '%m/%d/%Y'
                try:value=datetime.strptime(token,fmt.replace('/','-' if '-' in token else '/')).date().isoformat()
                except ValueError:continue
                header['invoice_date']=asdict(Reading(value,'found',(row.evidence(),)))
    extraction['gst_parser_version']='printed-gst-columns-v1'
    return extraction
