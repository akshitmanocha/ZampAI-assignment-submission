"""Run an explicitly supplied Python script in the existing idle Kaggle kernel.

Never print connection exceptions: they can contain the credential URL.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request
import uuid
import websocket


def execute(secret_file, code, timeout=600):
    base = Path(secret_file).read_text().strip().rstrip('/')
    kernels = json.load(urllib.request.urlopen(base + '/api/kernels', timeout=25))
    kernel = next((k for k in kernels if k['name'] == 'python3' and k['execution_state'] == 'idle'), None)
    if kernel is None:
        raise RuntimeError('No idle Python kernel')
    session, mid = uuid.uuid4().hex, uuid.uuid4().hex
    ws = websocket.create_connection(base.replace('https://', 'wss://', 1) + '/api/kernels/' + kernel['id'] + '/channels?session_id=' + session, timeout=30)
    try:
        ws.send(json.dumps({'header': {'msg_id': mid, 'username': 'reconcile', 'session': session, 'msg_type': 'execute_request', 'version': '5.3', 'date': datetime.now(timezone.utc).isoformat()}, 'parent_header': {}, 'metadata': {}, 'channel': 'shell', 'content': {'code': code, 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True}, 'buffers': []}))
        deadline = time.monotonic() + timeout
        ok = False
        replied = False
        idle = False
        output = []
        while time.monotonic() < deadline:
            try:
                msg = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if msg.get('parent_header', {}).get('msg_id') != mid:
                continue
            kind = msg.get('msg_type', msg.get('header', {}).get('msg_type'))
            if kind == 'stream':
                # Only stdout from our own script; redact even accidental URL output.
                value = msg['content']['text'].replace(base, '<proxy>')
                output.append(value)
                print(value, end='', flush=True)
            if kind == 'execute_reply':
                replied = True
                ok = msg['content']['status'] == 'ok'
                if not ok:
                    print('Remote execution failed:', msg['content'].get('ename', 'Error'), flush=True)
            if kind == 'status' and msg['content']['execution_state'] == 'idle':
                idle = True
            if idle and replied:
                return ok, ''.join(output)
        raise TimeoutError('Execution still running; inspect kernel before retrying')
    finally:
        ws.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--secret-file', default='/tmp/reconcile-private/kaggle_proxy')
    p.add_argument('--code-file', required=True)
    p.add_argument('--timeout', type=int, default=600)
    args = p.parse_args()
    try:
        ok, _ = execute(args.secret_file, Path(args.code_file).read_text(), args.timeout)
        raise SystemExit(0 if ok else 1)
    except Exception as exc:
        print('Connection/execution error:', type(exc).__name__)
        raise SystemExit(1)
