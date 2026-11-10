"""Provision local accounts without printing or committing their passwords."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True,help='Private path outside the checkout')
    args=p.parse_args()
    checkout=Path(__file__).resolve().parents[1]
    output=args.output.resolve()
    if output.is_relative_to(checkout):
        raise SystemExit('Choose a private account-file path outside the repository')
    if output.exists():
        accounts=json.loads(output.read_text())
    else:
        accounts=[{'email':role+'@reconcile.local','display_name':name,'role':role,'password':secrets.token_urlsafe(24)}
            for role,name in [('approver','Local approver'),('clerk','Local reviewer'),('admin','Local administrator')]]
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(accounts,indent=2))
        output.chmod(0o600)
    code='from reconcile.database import session\nfrom reconcile.cli import create_user\nimport json\nwith session() as db, db.begin():\n for a in json.loads('+repr(json.dumps(accounts))+'):\n  create_user(db,a["email"],a["display_name"],a["role"],a["password"])\n'
    subprocess.run(['docker','compose','exec','-T','app','python'],input=code,text=True,cwd=checkout,check=True,capture_output=True)
    print('Local accounts provisioned. Private account file:',output)

if __name__=='__main__':main()
