from __future__ import annotations

from pathlib import Path
import tempfile
import cv2
import numpy as np

from pixelfenda.engine import preview_layers
from pixelfenda.ffmpeg_utils import encoder_works, find_ffmpeg
from pixelfenda.layering import LayerStackProcessor, blend_images
from pixelfenda.lut import CubeLUT
from pixelfenda.model import LayerSpec, ProjectDocument
from pixelfenda.presets import EFFECT_PRESETS, FILTER_PRESETS
from pixelfenda.reactive import ReactiveState
from pixelfenda.scene import SceneCutDetector

ROOT = Path(__file__).resolve().parent


def make_card(w=640, h=360):
    img=np.zeros((h,w,3),np.uint8)
    yy,xx=np.indices((h,w))
    img[...,0]=(xx*255/max(1,w-1)).astype(np.uint8)
    img[...,1]=(yy*255/max(1,h-1)).astype(np.uint8)
    img[...,2]=((xx+yy)*255/max(1,w+h-2)).astype(np.uint8)
    cv2.rectangle(img,(35,35),(265,165),(18,20,24),-1)
    cv2.putText(img,'PIXELFENDA',(55,100),cv2.FONT_HERSHEY_SIMPLEX,1.1,(240,240,240),2,cv2.LINE_AA)
    cv2.putText(img,'v0.3.0 LAYER TEST',(55,145),cv2.FONT_HERSHEY_SIMPLEX,.55,(180,205,220),1,cv2.LINE_AA)
    cv2.circle(img,(480,180),85,(40,180,240),-1)
    return img


def main():
    print('PixelFenda v0.3.0 — autoteste')
    card=make_card()
    layers=[
        LayerSpec(kind='effect',key='cyber_wire',intensity=.62,opacity=.72,blend='screen',mod_source='beat',mod_amount=.55),
        LayerSpec(kind='effect',key='psx_dither',intensity=.35,opacity=.42,blend='normal'),
        LayerSpec(kind='filter',key='cold_archive',intensity=.58,opacity=.76),
        LayerSpec(kind='lut',key='custom_lut',lut_path=str(ROOT/'luts'/'PixelFenda_CobaltNoir.cube'),intensity=.42,opacity=.48),
    ]

    # Project JSON roundtrip.
    tmp=ROOT/'_teste_v030.pixelfenda.json'
    ProjectDocument(layers=layers,scene_mode='mutate').save(tmp)
    loaded=ProjectDocument.load(tmp)
    assert len(loaded.layers)==4
    print('[OK] projeto JSON / 4 camadas')

    # LUT parser.
    lut=CubeLUT.load(ROOT/'luts'/'PixelFenda_ChromeIce.cube')
    lut_img=lut.apply(card,.7)
    assert lut_img.shape==card.shape
    cv2.imwrite(str(ROOT/'_teste_v030_lut.jpg'),lut_img)
    print(f'[OK] LUT .cube 3D — {lut.title} {lut.size}³')

    # Scene detector with an explicit synthetic cut.
    det=SceneCutDetector(threshold=.12,min_gap_frames=2)
    cuts=0
    a=np.zeros_like(card); b=np.full_like(card,255)
    for fr in [a,a,a,b,b]:
        cut,score,pulse=det.update(fr); cuts+=int(cut)
    assert cuts>=1
    print('[OK] detector de corte de cena')

    # CPU stack, including modulation/blends.
    stack=LayerStackProcessor(card.shape[1],card.shape[0],layers,gpu_mode='cpu',fps=30,scene_mode='mutate',scene_threshold=.12)
    out=card
    for i in range(5):
        out,meta=stack.process(card,ReactiveState(audio=.42,bass=.68,mids=.35,treble=.30,beat=.9 if i==2 else .15,motion=.38,motion_dx=.12))
    stack.release()
    cv2.imwrite(str(ROOT/'_teste_v030_cpu_stack.jpg'),out)
    assert meta['active_layers']==4
    print('[OK] Layer Stack CPU — efeito + efeito + filtro + LUT + blends/modulação')

    # GPU path. Auto is allowed to fall back on machines without a graphics context.
    gpu_layers=[
        LayerSpec(kind='effect',key='cyber_wire',intensity=.42,opacity=.55,blend='screen'),
        LayerSpec(kind='effect',key='liquid_chrome',intensity=.28,opacity=.28),
        LayerSpec(kind='effect',key='psx_dither',intensity=.32,opacity=.35),
        LayerSpec(kind='effect',key='gothic_halo',intensity=.36,opacity=.25,blend='screen'),
        LayerSpec(kind='effect',key='signal_grid',intensity=.38,opacity=.35),
        LayerSpec(kind='effect',key='spectral_echo',intensity=.30,opacity=.25,blend='screen'),
        LayerSpec(kind='filter',key='vintage_70',intensity=.52,opacity=.55),
    ]
    gout,renderer,_=preview_layers(card,640,360,gpu_layers,gpu_mode='auto')
    cv2.imwrite(str(ROOT/'_teste_v030_gpu_stack.jpg'),gout)
    print('[OK] rota gráfica / novos shaders + feedback + filtro:',renderer)

    # Verify that every declared effect/filter can be previewed on CPU fallback.
    for key in EFFECT_PRESETS:
        p=LayerStackProcessor(320,180,[LayerSpec(kind='effect',key=key,intensity=.35)],gpu_mode='cpu',fps=30)
        small=cv2.resize(card,(320,180))
        z,_=p.process(small,ReactiveState(audio=.3,bass=.4,beat=.25,motion=.2)); p.release()
        assert z.shape==(180,320,3)
    print(f'[OK] {len(EFFECT_PRESETS)} efeitos declarados')
    for key in FILTER_PRESETS:
        if key=='none': continue
        p=LayerStackProcessor(320,180,[LayerSpec(kind='filter',key=key,intensity=.5)],gpu_mode='cpu',fps=30)
        z,_=p.process(cv2.resize(card,(320,180)),ReactiveState()); p.release(); assert z.shape==(180,320,3)
    print(f'[OK] {len(FILTER_PRESETS)-1} filtros declarados')

    ff=find_ffmpeg(); print('FFmpeg:',ff)
    for codec in ('h264_nvenc','hevc_nvenc','av1_nvenc'):
        print(f'{codec}:', 'OK' if encoder_works(codec,ff) else 'indisponível neste computador')
    print('\nAUTOTESTE v0.3.0 CONCLUÍDO.')
    print('Imagens geradas:')
    for name in ('_teste_v030_lut.jpg','_teste_v030_cpu_stack.jpg','_teste_v030_gpu_stack.jpg'):
        print(' -',ROOT/name)


if __name__=='__main__':
    main()
