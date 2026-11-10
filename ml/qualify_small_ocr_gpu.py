"""Label-free GPU qualification on twelve predeclared validation images.

Run in an ML environment with torch/transformers/docling-core. No label JSON is
loaded; models receive an original image and one fixed task prompt only.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import time
import urllib.request

MODELS={
    'granite':('ibm-granite/granite-docling-258M','982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe','Convert this page to docling.'),
    'paddle-vl':('PaddlePaddle/PaddleOCR-VL-1.6','132c45f52c0a26ed5a6b2f6bd8e3985794cc27dd','Spotting:'),
}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',choices=MODELS,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume-jsonl',type=Path)
    args=parser.parse_args()
    import torch
    import transformers
    from PIL import Image
    from transformers import AutoProcessor,AutoModelForImageTextToText
    manifest=json.loads(args.manifest.read_text())
    selected=[r for r in manifest['records'] if r['id'] in manifest['qualification_ids']]
    assert len(selected)==12 and all(r['source_split']=='val' for r in selected)
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'predictions.jsonl').exists():raise RuntimeError('Refusing to overwrite qualification')
    resumed=[]
    if args.resume_jsonl:
        resumed=[json.loads(line) for line in args.resume_jsonl.read_text().splitlines() if line.strip()]
        expected={r['id']:r for r in selected}
        if len({r['id'] for r in resumed})!=len(resumed):raise RuntimeError('Duplicate checkpoint identity')
        for r in resumed:
            if r['id'] not in expected or r['image_sha256']!=expected[r['id']]['image_sha256'] or r['engine']!=args.engine:
                raise RuntimeError('Checkpoint is from a different suite/engine')
    model_id,revision,prompt=MODELS[args.engine]
    torch.set_num_threads(2)
    processor=AutoProcessor.from_pretrained(model_id,revision=revision,trust_remote_code=False)
    # Granite's recommended BF16 is unavailable on T4. FP32 avoids the observed
    # FP16 numerical degeneration; do not score that invalid precision probe.
    dtype=torch.float32 if args.engine=='granite' else torch.float16
    model=AutoModelForImageTextToText.from_pretrained(model_id,revision=revision,
        trust_remote_code=False,dtype=dtype,attn_implementation='sdpa').to('cuda').eval()
    parameters=sum(p.numel() for p in model.parameters())
    assert parameters<1_000_000_000, 'Actual model exceeds requested parameter limit'
    info={'model':model_id,'revision':revision,'actual_parameters':parameters,'torch':torch.__version__,
        'transformers':transformers.__version__,'gpu':torch.cuda.get_device_name(0),
        'dtype':str(dtype),'prompt':prompt,'use_cache':True,
        'processor_image_size':str(processor.image_processor.size),
        'manifest_sha256':hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        'max_new_tokens':4096,'max_time_seconds':90,'do_sample':False,
        'resumed_records':len(resumed),'resume_sha256':hashlib.sha256(args.resume_jsonl.read_bytes()).hexdigest() if args.resume_jsonl else None,
        'protocol':'Granite is full-page conversion; Paddle native Spotting task is a qualification only, not the separate official layout pipeline. No gold input.'}
    (args.output/'model.json').write_text(json.dumps(info,indent=2))
    with (args.output/'predictions.jsonl').open('w') as stream:
        for record in resumed:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
        stream.flush()
        completed={r['id'] for r in resumed}
        for record in selected:
            if record['id'] in completed:continue
            started=time.perf_counter();result={};error=None
            try:
                url=f'https://huggingface.co/datasets/{manifest["dataset"]}/resolve/{manifest["revision"]}/{record["source_path"]}'
                with urllib.request.urlopen(url,timeout=40) as response:raw=response.read(20*1024*1024)
                assert hashlib.sha256(raw).hexdigest()==record['image_sha256']
                image=Image.open(io.BytesIO(raw)).convert('RGB')
                messages=[{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':prompt}]}]
                inputs=processor.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,
                    return_dict=True,return_tensors='pt').to(model.device,dtype=model.dtype)
                with torch.inference_mode():
                    generated=model.generate(**inputs,max_new_tokens=4096,max_time=90,do_sample=False,use_cache=True)
                tokens=generated[0,inputs['input_ids'].shape[-1]:]
                eos=model.generation_config.eos_token_id
                eos=[eos] if isinstance(eos,int) else eos or []
                result={'text':processor.decode(tokens,skip_special_tokens=False),'new_tokens':len(tokens),
                    'hit_token_limit':len(tokens)>=4096,'stopped_before_eos':not len(tokens) or tokens[-1].item() not in eos,
                    'image_size':list(image.size)}
                if args.engine=='granite':
                    from docling_core.types.doc import DoclingDocument
                    from docling_core.types.doc.document import DocTagsDocument
                    document=DoclingDocument.load_from_doctags(
                        DocTagsDocument.from_doctags_and_image_pairs([result['text']],[image]),document_name='Invoice')
                    result['document']=document.export_to_dict()
                    result['markdown']=document.export_to_markdown()
                image.close()
            except Exception as exception:
                error=type(exception).__name__
                result['error_attribute']=getattr(exception,'name',None)
            output={'id':record['id'],'engine':args.engine,'image_sha256':record['image_sha256'],
                'seconds':time.perf_counter()-started,'error':error,**result}
            stream.write(json.dumps(output,ensure_ascii=False)+'\n');stream.flush()
            print(json.dumps({'id':record['id'],'engine':args.engine,'seconds':round(output['seconds'],2),'error':error}),flush=True)
    (args.output/'complete.json').write_text(json.dumps({'documents':12,'complete':True}))


if __name__=='__main__':main()
