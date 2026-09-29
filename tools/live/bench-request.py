"""Control the separately attached benchmark agent; never launches or attaches to a process."""
from pathlib import Path
import argparse
import json
import sys
import time
from request import request

parser = argparse.ArgumentParser()
parser.add_argument('control', type=Path)
parser.add_argument('operation', choices=['status', 'configure', 'measure', 'select-packs', 'detach'])
parser.add_argument('--pack', action='append')
parser.add_argument('--name', default='sample')
parser.add_argument('--warmup', type=float, default=10)
parser.add_argument('--seconds', type=float, default=20)
parser.add_argument('--width', type=int, default=1920)
parser.add_argument('--height', type=int, default=1080)
parser.add_argument('--wait', action='store_true')
args = parser.parse_args()
payload = args.operation
if args.operation == 'configure':
    payload += f'\n{args.width}\n{args.height}'
elif args.operation == 'measure':
    payload += f'\n{args.name}\n{args.warmup}\n{args.seconds}'
elif args.operation == 'select-packs':
    payload += '\n' + '\n'.join(args.pack or ['vanilla', 'file/Chroma'])
result = request(args.control, payload)
if args.operation == 'measure' and args.wait and result.get('ok'):
    output = Path(result['output'])
    deadline = time.monotonic() + args.warmup + args.seconds + 30
    while not output.exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Measurement did not complete; inspect benchmark status before another run')
        time.sleep(.25)
    result = json.loads(output.read_text(encoding='utf-8'))
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if result.get('ok') else 1)
