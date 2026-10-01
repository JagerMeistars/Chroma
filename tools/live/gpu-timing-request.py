"""Control a separately attached GPU audit agent; never attaches or starts a game."""
import argparse
import json
from pathlib import Path
import time
from request import request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('control', type=Path)
parser.add_argument('operation', choices=['status', 'measure', 'stop', 'detach'])
parser.add_argument('--name', default='gpu-sample')
parser.add_argument('--warmup', type=float, default=2)
parser.add_argument('--seconds', type=float, default=5)
parser.add_argument('--wait', action='store_true')
args = parser.parse_args()
payload = args.operation
if args.operation == 'measure':
    payload += f'\n{args.name}\n{args.warmup}\n{args.seconds}'
result = request(args.control, payload)
if args.operation == 'measure' and args.wait and result.get('ok'):
    output = Path(result['output'])
    deadline = time.monotonic() + args.warmup + args.seconds + 40
    while not output.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError('Capture has not saved; inspect status before retrying')
        time.sleep(.2)
    result = json.loads(output.read_text(encoding='utf-8'))
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result.get('ok') else 1)
