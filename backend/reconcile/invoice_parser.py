"""Source-grounded deterministic invoice parser, baseline x2.

No vendor, purchase-order, expected-label or model access. Unresolved values stay
missing/ambiguous; monetary strings are never repaired to match an order.
"""
from dataclasses import dataclass,asdict
from datetime import datetime
from decimal import Decimal,InvalidOperation
import re
import statistics
from typing import Literal
from reconcile.document_types import PageText,Word

PARSER_VERSION = 'x3-printed-gst-columns-1.0'

@dataclass(frozen=True)
class Evidence:
    page: int
    bbox: tuple[float,float,float,float]
    text: str
    method: str

@dataclass(frozen=True)
class Reading:
    value: str | None
    status: Literal['found','missing','ambiguous','invalid']
    evidence: tuple[Evidence,...] = ()
    alternatives: tuple[str,...] = ()

@dataclass(frozen=True)
class Row:
    page: int
    method: str
    words: tuple[Word,...]

    @property
    def text(self):return ' '.join(w.text for w in self.words)
    @property
    def bbox(self):return (min(w.bbox[0] for w in self.words),min(w.bbox[1] for w in self.words),max(w.bbox[2] for w in self.words),max(w.bbox[3] for w in self.words))
    def evidence(self):
        boxes=[w.source_bbox or w.bbox for w in self.words]
        box=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
        return Evidence(self.page,box,self.text,self.method)


def text_rows(pages):
    result=[]
    for p in pages:
        median=statistics.median([w.bbox[3]-w.bbox[1] for w in p.words]) if p.words else 10
        groups=[]
        for w in sorted(p.words,key=lambda w:((w.bbox[1]+w.bbox[3])/2,w.bbox[0])):
            center=(w.bbox[1]+w.bbox[3])/2
            group=next((g for g in reversed(groups[-4:]) if abs(g[0]-center)<=max(2,median*.7)),None)
            if group is None:groups.append([center,[w]])
            else:group[1].append(w)
        for _,words in groups:result.append(Row(p.page,p.method,tuple(sorted(words,key=lambda w:w.bbox[0]))))
    return result


def decimal_string(text):
    text=re.sub(r'^(?:INR|USD|CAD|AUD|EUR|GBP|Rs\.?|[CA]\$|[$£€₹])\s*','',text.strip(),flags=re.I)
    text=re.sub(r'/-$','',text)
    if not re.fullmatch(r'[+-]?\d[\d,]*(?:\.\d+)?',text):return None
    # Comma decimal formats remain unresolved, rather than treating 12,50 as 1250.
    if ',' in text:
        integer=text.split('.')[0].lstrip('+-')
        if not (re.fullmatch(r'\d{1,3}(?:,\d{3})+',integer) or re.fullmatch(r'\d{1,2}(?:,\d{2})*,\d{3}',integer)):return None
    try:
        value=Decimal(text.replace(',',''))
        return str(value) if value.is_finite() else None
    except InvalidOperation:return None


def resolve(candidates):
    # Preserve all corroborating/conflicting readings. Never select by amount fit.
    valid=[(str(value),e) for value,e in candidates if value is not None]
    values=tuple(dict.fromkeys(v for v,_ in valid))
    evidence=tuple(dict.fromkeys(e for _,e in valid))
    if not values:return Reading(None,'missing')
    if len(values)>1:return Reading(None,'ambiguous',evidence,values)
    return Reading(values[0],'found',evidence)


def ref_value(text):
    tokens=re.findall(r'[A-Za-z0-9][A-Za-z0-9._/\-]*',text)
    for token in tokens:
        if any(c.isdigit() for c in token) and not re.fullmatch(r'\d{1,4}[/-]\d{1,2}[/-]\d{1,4}',token):
            return token.rstrip('.')
    return None


def reference(rows,kind):
    pattern=r'\b(?:invoice|inv)\b(?:\s*(?:number|no\.?|#))?\s*[:#]?' if kind=='invoice' else r'\b(?:purchase\s+order|p\.?o\.?)(?=\s|[:#-]|$)(?:\s*(?:number|no\.?|#))?\s*[:#]?'
    candidates=[]
    for i,row in enumerate(rows):
        match=re.search(pattern,row.text,re.I)
        if not match:continue
        if kind=='invoice' and re.search(r'payment terms|from invoice|invoice date',row.text,re.I):continue
        if kind=='po' and re.search(r'\bp\.?o\.?\s+box\b',row.text,re.I):continue
        if re.match(r'\s*(?:date|total|amount|due|currency)\b',row.text[match.end():],re.I):continue
        after=row.text[match.end():].lstrip(' .:#-')
        if re.match(r'^(?:not provided|none|null|n/a|unavailable|missing)\b',after,re.I):continue
        # Bare INV-001/PO-123 is itself the reference, not a label plus suffix.
        if re.match(r'-\d',row.text[match.end():]):
            start=match.start();value=ref_value(row.text[start:])
        else:value=ref_value(after)
        if value:candidates.append((value,row.evidence()));continue
        if kind=='invoice' and re.search(r'invoice\s+(?:no\.?|number)|invoice\s*[#:]|inv\s*[#:]',row.text,re.I):
            token=re.match(r'([A-Za-z][A-Za-z-]{2,})(?=\s|$)',after)
            if token and token.group(1).lower() not in ['date','total','amount','number']:
                candidates.append((token.group(1),row.evidence()));continue
        # Look below the label only within its column; avoid stealing a date or
        # the supplier's left-column address from a two-column invoice header.
        if kind=='invoice' and not re.search(r'invoice\s+(?:no\.?|number)|invoice\s*[#:]|inv\s*[#:]|inv\s+no',row.text,re.I):continue
        label_words=[w for w in row.words if re.search(r'invoice|inv\b|purchase|p\.?o\.?\b',w.text,re.I)]
        if not label_words:continue
        anchor=label_words[0].bbox[0]
        for below in rows[i+1:i+4]:
            if below.page!=row.page or below.bbox[1]-row.bbox[3]>50:break
            if re.search(r'\b(?:po|date|tax|subtotal|total|amount)\b',below.text,re.I):break
            words=tuple(w for w in below.words if anchor-15<=w.bbox[0]<=anchor+180)
            if not words:continue
            value=ref_value(' '.join(w.text for w in words))
            if value:
                candidate=Row(below.page,below.method,words);candidates.append((value,candidate.evidence()));break
    return resolve(candidates)


def monetary_field(rows,labels,exclude=None):
    candidates=[]
    for i,row in enumerate(rows):
        if exclude and re.search(exclude,row.text,re.I):continue
        m=re.search(labels,row.text,re.I)
        if not m:continue
        # Identifier values such as TAX-REAL-PDF-1 are not tax labels.
        if re.search(r'\b(?:invoice|inv)\s*(?:number|no\.?|#)\b',row.text,re.I):continue
        if re.search(r'\b(?:invoice|inv|date|reference|number|po)\b',row.text[:m.start()],re.I):continue
        # A TOTAL column heading is not a document total.
        if re.search(r'\b(description|qty|quantity|unit price|rate|hours)\b',row.text,re.I):continue
        tail=row.text[m.end():]
        # A percentage beside an amount is a rate, not a second money reading.
        amounts=re.findall(r'(?<![\w.])(?:INR|USD|CAD|AUD|EUR|GBP|Rs\.?|[CA]\$|[$£€₹])?\s*[+-]?\d[\d,]*(?:\.\d+)?(?:/-)?(?![\d.%])',tail,re.I)
        values=[decimal_string(v.strip()) for v in amounts]
        values=[v for v in values if v is not None]
        if len(values)==1:candidates.append((values[0],row.evidence()))
        elif len(values)>1:
            candidates.extend((v,row.evidence()) for v in values)
    return resolve(candidates)


def currency(rows):
    found=[]
    for row in rows:
        for code in re.findall(r'\b(INR|USD|CAD|AUD|EUR|GBP)\b',row.text,re.I):found.append((code.upper(),row.evidence()))
        for symbol,code in [('₹','INR'),('€','EUR'),('£','GBP'),('C$','CAD'),('A$','AUD')]:
            if symbol in row.text:found.append((code,row.evidence()))
    value=resolve(found)
    if value.status=='missing' and any('$' in r.text for r in rows):
        return Reading(None,'ambiguous',tuple(r.evidence() for r in rows if '$' in r.text),('dollar_currency_unspecified',))
    return value


def date_reading(rows):
    candidates=[];ambiguous=[]
    date_pattern=r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{1,2} [A-Za-z]{3,9} \d{4}\b|\b[A-Za-z]{3,9} \d{1,2},? \d{4}\b'
    def consume(text,source):
        for token in re.findall(date_pattern,text):
            formats=[]
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',token):formats=['%Y-%m-%d']
            elif re.fullmatch(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}',token):
                a,b,_=re.split(r'[/-]',token)
                if int(a)<=12 and int(b)<=12 and int(a)!=int(b):
                    ambiguous.append((token,source));continue
                formats=[('%d/%m/%Y' if int(a)>12 or int(a)==int(b) else '%m/%d/%Y').replace('/','-' if '-' in token else '/')]
            else:formats=['%d %B %Y','%d %b %Y','%B %d, %Y','%b %d, %Y','%B %d %Y','%b %d %Y']
            parsed=None
            for fmt in formats:
                try:parsed=datetime.strptime(token,fmt).date().isoformat();break
                except ValueError:pass
            if parsed:candidates.append((parsed,source))
            else:ambiguous.append((token,source))
    for i,row in enumerate(rows):
        for j,word in enumerate(row.words):
            if not re.fullmatch(r'date:?',word.text,re.I):continue
            before=' '.join(w.text.lower().rstrip(':') for w in row.words[max(0,j-2):j])
            after=' '.join(w.text.lower().rstrip(':') for w in row.words[j+1:j+3])
            if re.search(r'\b(due|payment|delivery|order)\b',before) or re.match(r'(payment due|description)',after):continue
            start=row.words[j-1].bbox[0] if j and row.words[j-1].text.lower() in ['issue','invoice','document'] else word.bbox[0]
            inline=tuple(w for w in row.words[j+1:] if start-15<=w.bbox[0]<=start+180)
            inline_text=' '.join(w.text for w in inline)
            if re.search(date_pattern,inline_text):consume(inline_text,Row(row.page,row.method,inline).evidence());continue
            for below in rows[i+1:i+4]:
                if below.page!=row.page or below.bbox[1]-row.bbox[3]>45:break
                words=tuple(w for w in below.words if start-15<=w.bbox[0]<=start+150)
                if not words:continue
                text=' '.join(w.text for w in words)
                if re.search(date_pattern,text):consume(text,Row(below.page,below.method,words).evidence());break
    if ambiguous:return Reading(None,'ambiguous',tuple(e for _,e in ambiguous),tuple(v for v,_ in ambiguous))
    return resolve(candidates)


def supplier(rows,pages):
    candidates=[];anchored=[]
    first=pages[0] if pages else None
    if first is None:return Reading(None,'missing')
    for i,row in enumerate(rows):
        if row.page!=first.page:continue
        # Explicit seller/from anchors outrank visual guesses; client columns
        # are clipped out, even when the labels share a horizontal row.
        anchor=next((w for w in row.words if w.text.upper().rstrip(':') in ['FROM','SUPPLIER','SELLER']),None)
        if anchor and row.bbox[1]<first.height*.5:
            client=next((w.bbox[0] for w in row.words if w.text.upper() in ['BILL','CUSTOMER','BUYER'] and w.bbox[0]>anchor.bbox[0]),first.width*.6)
            for below in rows[i+1:i+3]:
                if below.page!=row.page or below.bbox[1]-row.bbox[3]>50:break
                words=tuple(w for w in below.words if anchor.bbox[0]-10<=w.bbox[0]<client-10)
                if words and not any(c.isdigit() for c in ' '.join(w.text for w in words)):
                    name=Row(row.page,row.method,words)
                    if name.text.lower() not in ['none','null']:anchored.append((name.text,name.evidence()))
                    break
        if row.bbox[1]>.35*first.height:continue
        words=tuple(w for w in row.words if w.bbox[0]<first.width*.58)
        if not words:continue
        name=Row(row.page,row.method,words)
        if not re.search(r'\b(supplies|solutions|systems|enterprises|limited|ltd\.?|llc|inc\.?|corporation|company|consulting)\b',name.text,re.I):continue
        if re.search(r'@|bill to|customer|make checks|invoice|\d{4}',name.text,re.I):continue
        # Legal names can be stacked in a large-font title block.
        parts=[name]
        for previous in reversed(rows[max(0,i-3):i]):
            current=parts[0]
            height=current.bbox[3]-current.bbox[1]
            ph=previous.bbox[3]-previous.bbox[1]
            if previous.page!=row.page or abs(previous.bbox[0]-current.bbox[0])>12 or current.bbox[1]-previous.bbox[3]>max(8,height*1.5) or not .6<=ph/max(height,1)<=1.6:break
            if len(previous.text)<3 or not re.fullmatch(r"[A-Za-z &'.,-]+",previous.text) or re.search(r'invoice|date|bill|amount|total|hotel',previous.text,re.I):break
            parts.insert(0,previous)
        text=' '.join(p.text for p in parts)
        if len(text.split())>=2:
            candidates.append((text,Row(row.page,row.method,tuple(w for p in parts for w in p.words)).evidence()))
    return resolve(anchored if anchored else candidates)


def line_items(rows):
    result=[];warnings=[]
    header=None
    for row in rows:
        lower=row.text.lower()
        if re.search(r'\b(description|item|product|service)\b',lower) and re.search(r'\b(qty|quantity|hours)\b',lower) and re.search(r'\b(price|rate)\b',lower):
            def position(pattern,last=False):
                matches=[w for w in row.words if re.search(pattern,w.text,re.I)]
                w=matches[-1] if last and matches else matches[0] if matches else None
                return (w.bbox[0]+w.bbox[2])/2 if w else None
            q=position(r'^(qty|quantity|hours)$');p=position(r'^(price|rate)$');a=position(r'^(amount|total|value)$',True)
            desc_words=[w for w in row.words if re.search(r'^(description|item|product|service)$',w.text,re.I)]
            desc_start=desc_words[0].bbox[0]-10 if desc_words else 0
            if q is not None and p is not None and a is not None and q<p<a:
                tax=position(r'^(tax|vat)$')
                header=(row.page,desc_start,q,p,a,tax if tax is not None and p<tax<a else None)
            continue
        if header is None or row.page!=header[0]:continue
        if re.search(r'\b(subtotal|sub-total|grand total|tax|amount due|total due)\b',lower):header=None;continue
        _,desc_start,q,p,a,tax=header
        edges=(q-(p-q)/2,(q+p)/2,(p+a)/2)
        desc=[w for w in row.words if desc_start<=w.bbox[0]<edges[0]]
        qty=[w for w in row.words if edges[0]<=(w.bbox[0]+w.bbox[2])/2<edges[1]]
        price_end=(p+tax)/2 if tax is not None else edges[2]
        amount_start=(tax+a)/2 if tax is not None else edges[2]
        price=[w for w in row.words if edges[1]<=(w.bbox[0]+w.bbox[2])/2<price_end]
        amount=[w for w in row.words if (w.bbox[0]+w.bbox[2])/2>=amount_start]
        def read(words):
            # Currency and numeric parts may be separate OCR tokens.
            raw=' '.join(w.text for w in words)
            raw=re.sub(r'\s+','',raw)
            value=decimal_string(raw)
            return Reading(value,'found' if value is not None else 'missing',(Row(row.page,row.method,tuple(words)).evidence(),) if words else ())
        d=' '.join(w.text for w in desc).strip()
        if not d or not any(c.isalpha() for c in d):continue
        qr,pr,ar=read(qty),read(price),read(amount)
        if sum(r.status=='found' for r in [qr,pr,ar])<2:continue
        result.append({'line_no':len(result)+1,'description':Reading(d,'found',(Row(row.page,row.method,tuple(desc)).evidence(),)),'qty':qr,'unit_price':pr,'amount':ar})
        if qr.status=='found' and pr.status=='found' and ar.status=='found':
            if abs(Decimal(qr.value)*Decimal(pr.value)-Decimal(ar.value))>Decimal('.01'):warnings.append(f'line_{len(result)}_arithmetic_mismatch')
    if not result:warnings.append('line_items_not_reconstructed')
    return result,warnings


def parse_invoice(pages):
    rows=text_rows(pages)
    lines,warnings=line_items(rows)
    header={'vendor_name':supplier(rows,pages),'invoice_number':reference(rows,'invoice'),'po_reference':reference(rows,'po'),'invoice_date':date_reading(rows),'currency':currency(rows),'subtotal':monetary_field(rows,r'\b(?:subtotal|sub-total|net total)\b'),'tax_total':monetary_field(rows,r'\b(?:tax total|total tax|tax|gst|vat)\b',r'\b(?:analysis|rate|base)\b'),'grand_total':monetary_field(rows,r'\b(?:grand total|invoice total|amount due|balance due|total due|total)\b',r'\b(?:subtotal|sub-total|tax total|vat total|net total|total tax|total vat|total net)\b')}
    extraction={'parser_version':PARSER_VERSION,'header':{k:asdict(v) for k,v in header.items()},'lines':[{k:asdict(v) if isinstance(v,Reading) else v for k,v in line.items()} for line in lines],'warnings':sorted(set(warnings+[w for p in pages for w in p.warnings]))}
    from reconcile.gst_parser import enrich
    return enrich(extraction,pages)
