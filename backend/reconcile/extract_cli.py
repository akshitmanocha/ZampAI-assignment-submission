"""Local extraction entry point. No network, PO lookup, or automatic approval."""
import argparse
import json
import os
from pathlib import Path
from reconcile.document_text import extract_document,DocumentError
from reconcile.invoice_parser import parse_invoice


def main():
    p=argparse.ArgumentParser(description='Read invoice PDF fields and source evidence')
    p.add_argument('pdf',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        with a.pdf.open('rb') as f:data=f.read(10*1024*1024+1)
        result=parse_invoice(extract_document(data))
    except DocumentError as error:
        print(json.dumps({'error':error.code}));return 1
    # Avoid blindly overwriting an existing output or following an output symlink.
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(result,f,indent=2)
    print(json.dumps({'written':True,'parser_version':result['parser_version'],'line_count':len(result['lines']),'fields':{k:v['status'] for k,v in result['header'].items()}}))
    return 0

if __name__=='__main__':raise SystemExit(main())
