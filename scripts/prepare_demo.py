"""Build fictional demo PDFs from ordinary source specs; never imports expected labels."""
from copy import deepcopy
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ml'))
from render_workflows import render, scanned


def main():
    out = ROOT/'backend/reconcile/demo_samples'
    out.mkdir(exist_ok=True)
    base = json.loads((ROOT/'fixtures/workflows/v1/inputs/W01.json').read_text())['document']
    hardware = json.loads((ROOT/'fixtures/workflows/v1/inputs/W05.json').read_text())['document']
    manifest = []
    specs = [
        ('happy', 'Six boxes with explicit pack size', '0147', 'GLV-M Nitrile gloves medium [BOX; 100 EA/box]', '6', False),
        ('missing-pack', 'Missing pack size for human review', '0148', 'GLV-M Nitrile gloves medium [BOX]', '6', False),
        ('wrong-material', 'A material mismatch', '0149', 'GLV-M Latex gloves medium [BOX; 100 EA/box]', '6', False),
        ('partial-a', 'First competing partial invoice', '0150', 'GLV-M Nitrile gloves medium [BOX; 100 EA/box]', '4', False),
        ('partial-b', 'Second competing partial invoice', '0150', 'GLV-M Nitrile gloves medium [BOX; 100 EA/box]', '4', False),
        ('semantic', 'Different wording for MiniLM and human confirmation', '0151', 'Disposable nitrile examination gloves medium [EA]', '600', False),
        ('scan', 'A real image-only scanned invoice', '0149', 'GLV-M Nitrile gloves medium [BOX; 100 EA/box]', '6', True),
        ('ambiguous', 'Missing order reference with several possible orders', None, 'GLV-M Nitrile gloves medium [BOX; 100 EA/box]', '6', False),
    ]
    from decimal import Decimal
    for name, title, po, description, qty, use_scan in specs:
        doc = deepcopy(base)
        doc.update(invoice_number='SH-DEMO-'+name.upper(), po_reference='PO-2026-'+po if po else None)
        price = '5.00' if name == 'semantic' else '500.00'
        amount = format(Decimal(qty)*Decimal(price), '.2f')
        doc.update(subtotal=amount, grand_total=amount)
        doc['lines'] = [{'description':description, 'qty':qty, 'unit_price':price, 'amount':amount}]
        data = render(doc)
        if use_scan:
            data = scanned(data, degraded=False)
        file = name+'.pdf'
        (out/file).write_bytes(data)
        manifest.append({'name':name,'title':title,'file':file,'note':'Fictional sample. Results depend on the current company ledger.'})
    hardware['invoice_number'] = 'BL-DEMO-OFFSET'
    (out/'offset-prices.pdf').write_bytes(render(hardware))
    manifest.append({'name':'offset-prices','title':'Two price errors hidden by a matching total','file':'offset-prices.pdf','note':'Fictional hardware invoice; inspect both line prices.'})
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2))

if __name__=='__main__':main()
