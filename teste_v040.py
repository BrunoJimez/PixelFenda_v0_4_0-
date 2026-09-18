from __future__ import annotations

from pathlib import Path
import math

import cv2
import numpy as np

from pixelfenda.engine import render_video_layers
from pixelfenda.ffmpeg_utils import encoder_works, find_ffmpeg
from pixelfenda.layering import LayerStackProcessor
from pixelfenda.masks import MaskTracker, build_mask
from pixelfenda.model import LayerSpec, ProjectDocument
from pixelfenda.presets import EFFECT_PRESETS, FILTER_PRESETS
from pixelfenda.reactive import AudioReactiveTrack, ReactiveState
from pixelfenda.rhythm import detect_beats_from_track
from pixelfenda.temporal import temporal_values

ROOT = Path(__file__).resolve().parent


def card(w=640, h=360):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), np.uint8)
    img[..., 0] = np.clip(20 + 220*x/max(1,w-1),0,255).astype(np.uint8)
    img[..., 1] = np.clip(25 + 210*y/max(1,h-1),0,255).astype(np.uint8)
    img[..., 2] = np.clip(55 + 180*(1-x/max(1,w-1)),0,255).astype(np.uint8)
    cv2.rectangle(img,(35,35),(265,165),(20,20,20),-1)
    cv2.putText(img,"PIXELFENDA",(55,102),cv2.FONT_HERSHEY_SIMPLEX,1.15,(245,245,245),2,cv2.LINE_AA)
    cv2.putText(img,"v0.4.0 TEMPORAL",(55,142),cv2.FONT_HERSHEY_SIMPLEX,.62,(225,225,225),1,cv2.LINE_AA)
    cv2.circle(img,(480,175),75,(75,205,230),-1)
    return img


def main():
    print("PixelFenda v0.4.0 — autoteste Temporal Director")
    # 1. Project roundtrip / temporal fields.
    layer = LayerSpec(
        kind="effect", key="cyber_wire", intensity=.45, opacity=.9,
        start_s=.5, end_s=3.0, fade_in_s=.25, fade_out_s=.4,
        keyframe_ease="smooth",
        keyframes=[{"time":1.0,"intensity":.8,"opacity":.7,"mod_amount":.2},{"time":2.0,"intensity":.25,"opacity":1.0,"mod_amount":.6}],
        mask_kind="ellipse", mask_x=.5, mask_y=.5, mask_w=.55, mask_h=.65,
        mask_feather=.12, mask_track=True,
    ).normalized()
    doc = ProjectDocument(name="v040-test", layers=[layer])
    project_path = ROOT / "_teste_v040.pixelfenda.json"
    doc.save(project_path); loaded = ProjectDocument.load(project_path)
    assert loaded.format_version == 4 and loaded.layers[0].mask_kind == "ellipse" and len(loaded.layers[0].keyframes) == 2
    print("[OK] projeto v4 / campos temporais + máscara")

    # 2. Keyframe evaluation + time window.
    a = temporal_values(layer, .1, 4.0); b = temporal_values(layer, 1.5, 4.0); c = temporal_values(layer, 3.2, 4.0)
    assert not a.active and b.active and not c.active and 0.2 < b.intensity < 0.85
    print(f"[OK] keyframes/fades/janela temporal — intensidade@1.5s={b.intensity:.3f}")

    # 3. Mask generation.
    m = build_mask(640, 360, layer)
    assert m.shape == (360,640) and float(m.max()) > .95 and 0.05 < float(m.mean()) < .7
    cv2.imwrite(str(ROOT / "_teste_v040_mask.png"), (m*255).astype(np.uint8))
    print(f"[OK] máscara elíptica feather — cobertura média {m.mean():.3f}")

    # 4. Lightweight tracking on translated synthetic subject.
    track_spec = LayerSpec(mask_kind="rectangle", mask_x=.30, mask_y=.50, mask_w=.24, mask_h=.35, mask_track=True).normalized()
    tracker = MaskTracker(320,180,track_spec)
    centers=[]
    rng=np.random.default_rng(4)
    texture=rng.integers(0,255,(50,60,3),dtype=np.uint8)
    for i in range(9):
        f=np.zeros((180,320,3),np.uint8); x0=65+i*7; y0=65
        f[y0:y0+50,x0:x0+60]=texture
        centers.append(tracker.update(f,track_spec))
    assert centers[-1][0] > centers[1][0] + .08
    print(f"[OK] tracking de máscara por optical flow — X {centers[1][0]:.3f} -> {centers[-1][0]:.3f}")

    # 5. Beat grid from synthetic onset track.
    fps=30.0; seconds=8; features=np.zeros((int(fps*seconds),5),np.float32)
    # 120 BPM = beat every .5 s.
    for t in np.arange(.5,seconds,.5):
        idx=int(round(t*fps)); features[idx,4]=1.0; features[idx,0]=.7
    beat = detect_beats_from_track(AudioReactiveTrack(features), fps, seconds)
    assert 105 <= beat.bpm <= 135 and len(beat.beat_times) >= 10
    print(f"[OK] Beat Grid — {len(beat.beat_times)} batidas / {beat.bpm:.1f} BPM")

    # 6. Stack CPU: temporal + mask + blend.
    frame=card()
    layers=[
        LayerSpec(kind="effect",key="cyber_wire",intensity=.72,opacity=.9,mask_kind="ellipse",mask_x=.5,mask_y=.5,mask_w=.78,mask_h=.78,mask_feather=.12),
        LayerSpec(kind="filter",key="cold_archive",intensity=.62,opacity=.65,start_s=.5,end_s=3.0,fade_in_s=.25,fade_out_s=.25,keyframes=[{"time":1.0,"opacity":1.0},{"time":2.5,"opacity":.35}]),
    ]
    stack=LayerStackProcessor(640,360,layers,seed=404,gpu_mode="cpu",fps=30,duration=4.0)
    stack.frame_index=44  # approx 1.5 s
    out,meta=stack.process(frame,ReactiveState(motion=.25,audio=.35,beat=.5)); stack.release()
    cv2.imwrite(str(ROOT / "_teste_v040_temporal_stack.jpg"),out)
    assert meta["active_layers"]==2 and meta["masked_layers"]>=1 and np.mean(np.abs(out.astype(np.int16)-frame.astype(np.int16)))>2
    print("[OK] Layer Stack CPU — temporal + máscara + filtro")

    # 7. GPU route / fallback. Same logic, renderer is asserted by user hardware later.
    gpu_layers=[
        LayerSpec(kind="effect",key="signal_grid",intensity=.7,opacity=.85,mask_kind="vignette",mask_w=.9,mask_h=.9,mask_feather=.25),
        LayerSpec(kind="effect",key="spectral_echo",intensity=.5,opacity=.35,blend="screen"),
        LayerSpec(kind="filter",key="cinematic_teal_amber",intensity=.7,opacity=.6),
    ]
    stack=LayerStackProcessor(640,360,gpu_layers,seed=405,gpu_mode="auto",fps=30,duration=4.0)
    gout=frame.copy(); gmeta={}
    for _ in range(3): gout,gmeta=stack.process(gout,ReactiveState(motion=.4,motion_dx=.15,audio=.5,bass=.6,beat=.4))
    renderer=stack.renderer; stack.release(); cv2.imwrite(str(ROOT / "_teste_v040_gpu_mask_stack.jpg"),gout)
    print(f"[OK] rota gráfica + máscara + feedback + filtro: {renderer}")

    # 8. Real short CPU render to validate engine integration.
    src=ROOT/"_teste_v040_input.mp4"; dst=ROOT/"_teste_v040_render.mp4"
    fourcc=cv2.VideoWriter_fourcc(*"mp4v"); wr=cv2.VideoWriter(str(src),fourcc,30,(320,180))
    tex=np.random.default_rng(7).integers(0,255,(44,54,3),dtype=np.uint8)
    for i in range(45):
        f=cv2.resize(card(640,360),(320,180)); x=30+i*3; f[80:124,x:min(x+54,320)]=tex[:,:max(0,min(54,320-x))]
        wr.write(f)
    wr.release()
    rlayers=[LayerSpec(kind="effect",key="gothic_halo",intensity=.65,opacity=.8,start_s=.2,end_s=1.3,fade_in_s=.15,fade_out_s=.15,mask_kind="rectangle",mask_x=.45,mask_y=.55,mask_w=.7,mask_h=.6,mask_feather=.15),LayerSpec(kind="filter",key="silver_gray",intensity=.35,opacity=.45)]
    result=render_video_layers(str(src),str(dst),320,180,rlayers,resize_mode="crop",seed=406,audio_mode="silent",encoder_mode="cpu_h264",gpu_mode="cpu")
    assert result["frames"]==45 and dst.exists() and dst.stat().st_size>1000
    print("[OK] render real 45 frames — janela temporal + máscara")

    print(f"[OK] {len(EFFECT_PRESETS)} efeitos preservados")
    print(f"[OK] {len(FILTER_PRESETS)-1} filtros preservados")
    ffmpeg=find_ffmpeg(); print(f"FFmpeg: {ffmpeg}")
    for enc in ("h264_nvenc","hevc_nvenc","av1_nvenc"):
        print(f"{enc}: {'OK' if encoder_works(enc,ffmpeg) else 'indisponível neste computador'}")
    print("\nAUTOTESTE v0.4.0 CONCLUÍDO.")
    print("Imagens geradas:")
    for name in ("_teste_v040_mask.png","_teste_v040_temporal_stack.jpg","_teste_v040_gpu_mask_stack.jpg"):
        print(" -", ROOT/name)

if __name__ == "__main__":
    main()
