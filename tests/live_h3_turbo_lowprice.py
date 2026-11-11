"""Opt-in three-task acceptance; keep private state outside the repository."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import time

import numpy as np
from PIL import Image, ImageDraw
import torch

from nov08_fixture import ROOT, module

nodes=module("h3_turbo_low_price_nodes")


def source_image(blue=False):
    image=Image.new("RGB",(512,512),"white")
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((130,140,350,390),40,fill=(25,80,180) if blue else (190,40,30))
    draw.ellipse((280,170,420,320),outline=(25,80,180) if blue else (190,40,30),width=20)
    return torch.from_numpy(np.asarray(image,dtype=np.float32).copy()/255).unsqueeze(0)


def main(args):
    key=os.environ.get("ZHENZHEN_H3_TURBO_KEY","").strip()
    if not args.confirm_live or not key:
        raise SystemExit("Requires --confirm-live and ZHENZHEN_H3_TURBO_KEY")
    directory=Path(args.output).resolve()
    if directory.is_relative_to(ROOT):
        raise SystemExit("Private live state must stay outside the repository")
    import av
    import folder_paths
    folder_paths.set_output_directory(str(directory))
    state_path=directory/"private_resume.json"
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    reference=json.loads((Path(args.reference)/"private_resume.json").read_text())
    config={"base_url":"https://api.seedance.nz","api_key":key}
    current,replaying="",False
    proofs=[]
    original_submit,original_poll,original_upload=nodes.submit_task,nodes.poll_task,nodes.api.upload_media

    def persist():
        state_path.write_text(json.dumps(state,indent=2),encoding="utf-8")

    def submit(body,connection,video=False):
        if replaying:
            return reference[current]["task"]
        previous=state.get(current,{})
        if previous.get("task"):
            return previous["task"]
        if previous.get("uncertain") or len(state)>=3:
            raise RuntimeError("No replay: uncertain submit or three-creation limit")
        state[current]={"uncertain":True}
        persist()
        task=original_submit(body,connection,video=video)
        state[current]={"task":task}
        persist()
        return task

    def poll(task,connection,video=False,on_progress=None):
        if replaying:
            return reference[current]["final"]
        if state[current].get("final"):
            return state[current]["final"]
        final=original_poll(task,connection,video=video,on_progress=on_progress)
        state[current]["final"]=final
        persist()
        return final

    nodes.submit_task,nodes.poll_task=submit,poll
    nodes.api.upload_media=lambda *a,**kw:"https://example.test/fixture.png" if replaying else original_upload(*a,**kw)

    def run(label,kind,**values):
        nonlocal current
        current=label
        print("START "+label+(" (completed-response replay)" if replaying else " (fresh/resumed)"),flush=True)
        start=time.monotonic()
        with contextlib.redirect_stdout(io.StringIO()):
            result=nodes.CLASSES[kind]().execute(api_config=config,**values)["result"]
        proof={"case":label,"fresh":not replaying,"success":True,"elapsed":round(time.monotonic()-start,2)}
        if kind=="video":
            path=result[0].get_stream_source() if not isinstance(result[0],str) else result[0]
            with av.open(path) as container:
                stream=container.streams.video[0]
                frames=sum(1 for _ in container.decode(video=0))
                proof.update(bytes=Path(path).stat().st_size,width=stream.width,height=stream.height,frames=frames)
            if frames<1:
                raise RuntimeError("Empty decoded video")
        else:
            tensor=result[0]
            if tensor.ndim!=4 or tensor.shape[0]!=1 or not torch.isfinite(tensor).all() or float(tensor.std())<=.001:
                raise RuntimeError("Invalid or blank decoded image")
            path=directory/(label+".png")
            Image.fromarray(np.clip(tensor[0].cpu().numpy()*255,0,255).astype(np.uint8)).save(path)
            proof.update(shape=list(tensor.shape),saved_png_bytes=path.stat().st_size)
        proofs.append(proof)
        (directory/"proof.json").write_text(json.dumps(proofs,indent=2),encoding="utf-8")
        print(json.dumps(proof),flush=True)

    try:
        red,blue=source_image(),source_image(True)
        prompt="Place the red cup from image 1 beside the blue cup from image 2 on a white studio table, preserve both colors and shapes."
        run("fresh_minimax_edit","minimax_image",prompt=prompt,resolution="1k",output_format="webp",seed=0,image1=red,image2=blue)
        run("fresh_qwen_edit","qwen",prompt=prompt,resolution="720p",seed=0,image1=red,image2=blue)
        audio={"waveform":(torch.sin(torch.arange(24000)*.04)*.02).reshape(1,1,-1),"sample_rate":8000}
        run("fresh_video_mixed","video",prompt="The red ceramic cup from the reference image rotates slowly on the table. Locked camera and quiet ambient sound.",seconds="3",resolution="480p",image1=red,audio1=audio)
        replaying=True
        for label,kind,values in (("minimax_text","minimax_image",{}),("minimax_edit","minimax_image",{"image1":red,"image2":blue,"output_format":"webp"}),
            ("qwen_text","qwen",{}),("qwen_edit","qwen",{"image1":red,"image2":blue,"resolution":"720p"}),
            ("video_text","video",{"seconds":"3"}),("video_mixed","video",{"image1":red,"audio1":audio,"seconds":"3"})):
            run(label,kind,prompt="A blue cup on a white studio table, soft light.",**values)
        return 0
    except Exception as error:
        message=re.sub(r"https?://[^\s\"']+|sk-[A-Za-z0-9]+|task_[A-Za-z0-9_-]+","[REDACTED]",str(error).replace(key,"[KEY]"))
        print(json.dumps({"case":current,"success":False,"error":type(error).__name__,"message":message[:1000]}),flush=True)
        return 1
    finally:
        nodes.submit_task,nodes.poll_task,nodes.api.upload_media=original_submit,original_poll,original_upload


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--confirm-live",action="store_true")
    parser.add_argument("--output",required=True)
    parser.add_argument("--reference",required=True)
    args=parser.parse_args()
    directory=Path(args.output).resolve()
    if directory.is_relative_to(ROOT):
        raise SystemExit("Private state must remain outside repository")
    directory.mkdir(parents=True,exist_ok=True)
    lock=directory/".live.lock"
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.close(descriptor)
    try:
        raise SystemExit(main(args))
    finally:
        lock.unlink(missing_ok=True)
