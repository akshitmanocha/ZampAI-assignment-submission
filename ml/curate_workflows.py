"""Author-defined validation scenarios. Never imports application decision code.

Expected outcomes are explicit specifications, not outputs of the production
engine. A separate Fraction-based audit checks authored arithmetic below.
"""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import hashlib,json

ALL_RULES=['scope','vendor_identity','vendor_status','purchase_order','product_specification','unit_conversion','unit_price','remaining_quantity','arithmetic','duplicate','required_fields']


def world():
    return {'vendors':[{'id':'v1','legal_name':'SafeHands Supplies','status':'approved'},{'id':'v2','legal_name':'Brightline Hardware','status':'approved'}],
      'purchase_orders':[{'id':'p1','number':'PO-2026-0147','vendor_id':'v1','status':'open','currency':'INR','lines':[{'id':'l1','sku':'GLV-M','description':'Nitrile gloves medium','material':'nitrile','size':'medium','uom':'EA','ordered_qty':'1000','unit_price':'5.00'}]},
                         {'id':'p2','number':'PO-2026-0200','vendor_id':'v2','status':'open','currency':'INR','lines':[{'id':'l2','sku':'BOLT10','description':'Steel bolt M10','material':'steel','size':'M10','uom':'EA','ordered_qty':'1000','unit_price':'12.50'},{'id':'l3','sku':'NUT10','description':'Steel nut M10','material':'steel','size':'M10','uom':'EA','ordered_qty':'1000','unit_price':'4.00'}]}],
      'allocations':[{'po_line_id':'l1','qty':'400','amount':'2000.00'}], 'invoice_history':[],
      'policy':{'absolute_unit_price_tolerance':'0.05','relative_unit_price_tolerance':'0.01','amount_rounding':'ROUND_HALF_UP','quantity_tolerance':'0'}}


def gloves(qty='6',pack='100',material='nitrile',price='500.00',amount='3000.00',number='SH-000123'):
    desc=f'GLV-M {material.capitalize()} gloves medium [BOX'+(f'; {pack} EA/box' if pack else '')+']'
    return {'vendor_name':'SafeHands Supplies','invoice_number':number,'invoice_date':'2026-11-06','po_reference':'PO-2026-0147','currency':'INR','subtotal':amount,'tax_total':'0.00','grand_total':amount,'lines':[{'description':desc,'qty':qty,'unit_price':price,'amount':amount}]}


def curate(out):
    if out.exists() and any(out.iterdir()):raise RuntimeError('Refusing to overwrite a frozen dataset')
    (out/'inputs').mkdir(parents=True,exist_ok=True);(out/'expected').mkdir()
    records=[]
    def add(id,group,family,doc,company,bucket,blocks=(),unknown=(),values=None,explanation='',actions=None):
        case={'id':id,'group_id':group,'family':family,'split':'validation','document':deepcopy(doc),'company':deepcopy(company),'actions':actions or []}
        answer={'id':id,'bucket':bucket,'blocking_rules':list(blocks),'required_unknown_rules':list(unknown),'values':values or {},'explanation':explanation,'ledger_unchanged_by_recommendation':True}
        records.append((case,answer))
    base=world();doc=gloves()
    add('W01','packaging','packaging_spec',doc,base,'accept',values={'normalized_qty':['600'],'remaining_qty':['600']},explanation='Six boxes x100=600; 1000-400=600; exact unit price 5.')
    d=gloves(material='latex');add('W02','packaging','packaging_spec',d,base,'reject',['product_specification'],explanation='Printed latex conflicts with nitrile even though SKU and totals agree.')
    d=gloves(pack=None);add('W03','packaging','packaging_spec',d,base,'human_review',unknown=['unit_conversion'],explanation='The box size is not printed; never copy pack size from master data.')
    d={'vendor_name':'Brightline Hardware','invoice_number':'BL-002001','invoice_date':'2026-11-07','po_reference':'PO-2026-0200','currency':'INR','subtotal':'3300.00','tax_total':'0.00','grand_total':'3300.00','lines':[{'description':'BOLT10 Steel bolt M10 [EA]','qty':'200','unit_price':'12.50','amount':'2500.00'},{'description':'NUT10 Steel nut M10 [EA]','qty':'200','unit_price':'4.00','amount':'800.00'}]}
    add('W04','offset_prices','offset_prices',d,base,'accept',explanation='2500+800=3300 and each line price is agreed.')
    d2=deepcopy(d);d2['lines'][0].update(unit_price='13.50',amount='2700.00');d2['lines'][1].update(unit_price='3.00',amount='600.00')
    add('W05','offset_prices','offset_prices',d2,base,'reject',['unit_price'],explanation='2700+600 still=3300; both line prices violate their individual tolerances.')
    add('W06','partial_billing','partial_billing',gloves(),base,'accept',values={'normalized_qty':['600'],'remaining_qty':['600']},explanation='A pending recommendation must not consume balance.')
    add('W07','partial_billing','partial_billing',gloves(qty='7',amount='3500.00'),base,'reject',['remaining_quantity'],values={'normalized_qty':['700'],'remaining_qty':['600'],'excess_qty':['100']},explanation='700 requested versus 600 remaining; 100 over.')
    d=gloves();d['po_reference']=None
    add('W08','po_ambiguity','missing_identifiers',d,base,'accept',explanation='Only one eligible vendor order has the printed product; unique inference is allowed.')
    c=deepcopy(base);decoy=deepcopy(c['purchase_orders'][0]);decoy.update(id='p3',number='PO-2026-0999');decoy['lines'][0]['id']='l4';c['purchase_orders'].append(decoy)
    add('W09','po_ambiguity','missing_identifiers',d,c,'human_review',unknown=['purchase_order'],explanation='Two eligible orders contain the same product. Never choose by amount alone.')
    d=gloves(number=None);add('W10','missing_number','missing_identifiers',d,base,'human_review',unknown=['required_fields'],explanation='An absent printed invoice number stays absent.')
    d=gloves();d['po_reference']='PO-2026-0200';add('W11','wrong_vendor','regressions',d,base,'reject',['vendor_identity'],explanation='Explicit PO belongs to another vendor; do not silently pick the glove PO.')
    c=deepcopy(base);c['invoice_history']=[{'vendor_id':'v1','invoice_number':'SH-000123','gross_total':'3000.00','document_sha256':'same_current_document','review_state':'approved'}]
    add('W12','duplicates','regressions',gloves(),c,'reject',['duplicate'],explanation='Same file/business invoice already in prior history.')
    c=deepcopy(base);c['invoice_history']=[{'vendor_id':'v1','invoice_number':'SH-000123','gross_total':'3100.00','document_sha256':'different_prior_document','review_state':'open'}]
    add('W13','duplicates','regressions',gloves(),c,'human_review',unknown=['duplicate'],explanation='Same vendor/number with changed amount may be a revision; investigate.')
    c=deepcopy(base);c['invoice_history']=[{'vendor_id':'v2','invoice_number':'SH-000123','gross_total':'3000.00','document_sha256':'different_prior_document','review_state':'approved'}]
    add('W14','duplicates','regressions',gloves(),c,'accept',explanation='A different vendor may legitimately use the same invoice number.')
    d=gloves();d.update(tax_total='540.00',grand_total='3540.00');add('W15','tax','regressions',d,base,'accept',explanation='3000+540=3540; arithmetic only, not tax-law compliance.')
    d=deepcopy(d);d['grand_total']='3550.00';add('W16','tax','regressions',d,base,'reject',['arithmetic'],explanation='Printed total is 10 above subtotal+tax; no repair allowed.')
    c=deepcopy(base);c['purchase_orders'][0]['status']='closed';add('W17','order_status','regressions',gloves(),c,'reject',['purchase_order'],explanation='A closed current order cannot authorize a new invoice.')
    c=deepcopy(base);c['vendors'][0]['status']='blocked';add('W18','vendor_status','regressions',gloves(),c,'reject',['vendor_status'],explanation='Blocked vendor is a confirmed blocker.')
    d=gloves(qty='1',pack=None,price='5.05',amount='5.05');d['lines'][0]['description']='GLV-M Nitrile gloves medium [EA]'
    add('W19','price_boundary','regressions',d,base,'accept',values={'normalized_unit_price':['5.05'],'price_tolerance':['0.05']},explanation='abs(5.05-5)=max(.05,5*.01)=.05, inclusive boundary.')
    d=deepcopy(d);d['lines'][0]['unit_price']='5.051';add('W20','price_boundary','regressions',d,base,'reject',['unit_price'],explanation='.051 exceeds .05; line amount rounds to5.05 and must not hide the price error.')
    d=gloves(qty='3',amount='1500.00');d['lines'].append(deepcopy(d['lines'][0]));d.update(subtotal='3000.00',grand_total='3000.00')
    add('W21','row_aggregation','regressions',d,base,'accept',values={'requested_by_po_line':{'l1':'600'}},explanation='Two rows consume the same PO line: 300+300=600, no double counting.')
    d=gloves();d['lines'].append(deepcopy(d['lines'][0]));d.update(subtotal='6000.00',grand_total='6000.00')
    add('W22','row_aggregation','regressions',d,base,'reject',['remaining_quantity'],values={'requested_by_po_line':{'l1':'1200'}},explanation='Two rows request 1200 against 600 remaining; aggregate before checking.')
    for id,action in [('W23','sequential_stale'),('W24','repeat_approval'),('W25','concurrent_approval')]:
        d=gloves(qty='4',amount='2000.00',number='SH-STATE-A') if action!='repeat_approval' else gloves(number='SH-STATE-A')
        add(id,id,'stateful',d,base,'accept',values={'final_remaining_qty':'200' if action!='repeat_approval' else '0','successful_new_approvals':1},actions=[action],explanation='Initial recommendation passes; real PostgreSQL approval must consume balance once and reject staleness.')
    # Independent arithmetic audit uses rational arithmetic, not runtime Decimal
    # rules. Explicitly authored erroneous totals remain intentional cases.
    audit=[]
    for case,answer in records:
        doc=case['document'];line_sum=sum(Fraction(l['amount']) for l in doc['lines'])
        consistent=line_sum==Fraction(doc['subtotal']) and Fraction(doc['subtotal'])+Fraction(doc['tax_total'])==Fraction(doc['grand_total'])
        assert consistent==(case['id']!='W16'),case['id']
        assert all(abs(Fraction(l['qty'])*Fraction(l['unit_price'])-Fraction(l['amount']))<=Fraction(1,100) for l in doc['lines'])
        audit.append({'id':case['id'],'header_arithmetic_consistent':consistent,'expected_bucket':answer['bucket']})
    files={}
    for case,answer in records:
        for folder,value in [('inputs',case),('expected',answer)]:
            raw=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode();path=out/folder/(case['id']+'.json');path.write_bytes(raw);files[str(path.relative_to(out))]=hashlib.sha256(raw).hexdigest()
    manifest={'version':'workflow-v1','purpose':'author-defined validation/acceptance cases, not model training or a blind final test','cases':len(records),'stateless_cases':22,'stateful_cases':3,'split':'validation','case_groups':len({c['group_id'] for c,_ in records}),'gold_method':'explicit authored business expectations with separate Fraction arithmetic audit; no production engine imports or LLM-generated answers','independent_human_audit':False,'files':files,'audit':audit,'limitations':['Small hand-designed challenge set; not representative invoice traffic','Author also implements pipeline, so not externally blind','Known catalog/SKUs overlap cases; not unseen-product ML evaluation','All layout/scan variants of each group belong to validation; no train/test variant leakage']}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return manifest

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();m=curate(a.out);print('Frozen cases:',m['cases'],'groups:',m['case_groups'])
