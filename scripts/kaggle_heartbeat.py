"""Execute a harmless kernel cell every five minutes; URL stays in a private file."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import urllib.request
import uuid
import websocket


def tick(secret_file):
    base = Path(secret_file).read_text().strip().rstrip('/')
    kernels = json.load(urllib.request.urlopen(base + '/api/kernels', timeout=25))
    if not kernels:
        raise RuntimeError('No existing kernel; will not create or interrupt one')
    kernel = next((k for k in kernels if k['name'] == 'python3'), None)
    if not kernel or kernel['execution_state'] != 'idle':
        return {'kernel_exec_ok': False, 'state': 'busy_or_unavailable'}
    session = uuid.uuid4().hex
    mid = uuid.uuid4().hex
    url = base.replace('https://', 'wss://', 1) + '/api/kernels/' + kernel['id'] + '/channels?session_id=' + session
    ws = websocket.create_connection(url, timeout=35)
    try:
        ws.send(json.dumps({'header': {'msg_id': mid, 'username': 'reconcile', 'session': session, 'msg_type': 'execute_request', 'version': '5.3', 'date': datetime.now(timezone.utc).isoformat()}, 'parent_header': {}, 'metadata': {}, 'channel': 'shell', 'content': {'code': 'print("reconcile heartbeat")', 'silent': False, 'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True}, 'buffers': []}))
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            msg = json.loads(ws.recv())
            if msg.get('parent_header', {}).get('msg_id') == mid and msg.get('msg_type') == 'execute_reply':
                return {'kernel_exec_ok': msg['content']['status'] == 'ok'}
        raise TimeoutError()
    finally:
        ws.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--secret-file', required=True)
    p.add_argument('--log', required=True)
    p.add_argument('--once', action='store_true')
    args = p.parse_args()
    end = time.monotonic() + 12 * 3600
    while time.monotonic() < end:
        try:
            result = tick(args.secret_file)
        except Exception as exc:
            # Exception strings may contain the credential URL. Log type only.
            result = {'kernel_exec_ok': False, 'error_type': type(exc).__name__}
        result['ts_utc'] = datetime.now(timezone.utc).isoformat()
        with open(args.log, 'a') as f:
            f.write(json.dumps(result) + '\n')
        print(json.dumps(result), flush=True)
        if args.once:
            return
        time.sleep(300)

if __name__ == '__main__':
    main()
