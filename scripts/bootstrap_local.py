"""Start the local stack, migrate, seed fictional master data and provision accounts."""
from pathlib import Path
import argparse
import secrets
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--account-file',type=Path,default=Path('/tmp/reconcile-private/local-accounts.json'))
    args=p.parse_args()
    env=ROOT/'.env'
    if not env.exists():
        env.write_text('POSTGRES_PASSWORD='+secrets.token_urlsafe(32)+'\nSESSION_COOKIE_SECURE=false\n')
        env.chmod(0o600)
    subprocess.run(['docker','compose','up','--build','-d'],cwd=ROOT,check=True)
    subprocess.run(['docker','compose','exec','-T','app','python','-m','reconcile.cli','seed'],cwd=ROOT,check=True)
    subprocess.run(['python',str(ROOT/'scripts/local_accounts.py'),'--output',str(args.account_file)],cwd=ROOT,check=True)
    print('Open http://127.0.0.1:8000 . Passwords are in the private account file, not the repository.')

if __name__=='__main__':main()
