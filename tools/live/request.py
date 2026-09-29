"""Send one request to an already attached isolated audit agent. Does not attach or launch Minecraft."""
from pathlib import Path
import argparse,json,time,sys

def request(control: Path, text: str, timeout: float=40):
    control=control.resolve()
    if not (control/'ready.json').exists():
        raise RuntimeError(f'No ready.json in {control}; no agent confirmed')
    name=str(time.time_ns())
    staging=control/(name+'.tmp')
    path=control/(name+'.req')
    done=control/(name+'.req.done')
    staging.write_text(text,encoding='utf-8')
    staging.rename(path)
    deadline=time.monotonic()+timeout
    while not done.exists():
        if time.monotonic()>deadline:raise TimeoutError(f'No completion for {path}; do not blindly repeat a mutating request')
        time.sleep(.1)
    return json.loads(done.read_text(encoding='utf-8'))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('control',type=Path)
    parser.add_argument('operation',choices=['status','commands','dispatcher','open','capture','close-screen','configure','reload','reload-status','dump','detach','exit'])
    parser.add_argument('--file',type=Path)
    parser.add_argument('--argument',default='')
    args=parser.parse_args()
    payload=args.file.read_text(encoding='utf-8') if args.file else args.argument
    result=request(args.control,args.operation+'\n'+payload)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result.get('ok'):sys.exit(1)
