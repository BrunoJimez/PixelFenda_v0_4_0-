from __future__ import annotations

import math
import cv2
import numpy as np

from .reactive import ReactiveState


def _bayer4(h: int, w: int) -> np.ndarray:
    b = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32)
    return np.tile(b, (math.ceil(h / 4), math.ceil(w / 4)))[:h, :w]


class PersistentVRAMEffect:
    """Persistent 1024×512×16-bit virtual VRAM.

    Layout (authorial simulation):
      - left/top: active framebuffer
      - right/top: texture-page cache
      - right/bottom: temporal history page
      - unused/scratch regions persist between frames

    Glitches operate on the whole memory and may leak texture/history pages into
    the active framebuffer, matching the structural logic of a memory-corruption
    tool without requiring a PlayStation ROM or emulator.
    """

    VRAM_W = 1024
    VRAM_H = 512

    def __init__(self, out_w: int, out_h: int, intensity: float, seed: int, preset: str) -> None:
        self.out_w = out_w
        self.out_h = out_h
        self.intensity = float(np.clip(intensity, 0.0, 1.0))
        self.preset = preset
        self.rng = np.random.default_rng(seed)
        ratio = out_w / max(1, out_h)
        self.fb_w = min(640, 700 if ratio > 1.7 else 560)
        self.fb_h = max(96, int(round(self.fb_w / ratio)))
        if self.fb_h > 360:
            self.fb_h = 360
            self.fb_w = max(96, int(round(self.fb_h * ratio)))
        self.fb_w = min(self.fb_w, 640)
        self.fb_h = min(self.fb_h, 360)
        self.fb_x, self.fb_y = 0, 0
        self.tex_x, self.tex_y = 640, 0
        self.tex_w, self.tex_h = 384, 256
        self.hist_x, self.hist_y = 512, 256
        self.hist_w, self.hist_h = 512, 256
        self.vram = np.zeros((self.VRAM_H, self.VRAM_W), dtype=np.uint16)
        self.frame_index = 0
        self.event_left = 0
        self.event_mode = "mixed"

    @staticmethod
    def _pack(img: np.ndarray) -> np.ndarray:
        b = (img[..., 0].astype(np.uint16) >> 3) & 31
        g = (img[..., 1].astype(np.uint16) >> 3) & 31
        r = (img[..., 2].astype(np.uint16) >> 3) & 31
        return (r << 10) | (g << 5) | b

    @staticmethod
    def _unpack(mem: np.ndarray) -> np.ndarray:
        b = (mem & 31).astype(np.uint8)
        g = ((mem >> 5) & 31).astype(np.uint8)
        r = ((mem >> 10) & 31).astype(np.uint8)
        return np.dstack([(b << 3) | (b >> 2), (g << 3) | (g >> 2), (r << 3) | (r >> 2)])

    def _new_event(self, reactive: ReactiveState) -> None:
        modes = {
            "corrupted_memory": ["tiles", "palette", "address", "mixed", "sparse", "mixed"],
            "tile_storm": ["tiles", "tiles", "mixed"],
            "palette_collapse": ["palette", "palette", "mixed"],
            "address_shift": ["address", "address", "mixed"],
            "controlled": ["sparse", "tiles", "palette"],
            "full_corruption": ["mixed", "address", "palette", "tiles", "mixed"],
        }
        self.event_mode = str(self.rng.choice(modes.get(self.preset, modes["corrupted_memory"])))
        base = int(self.rng.integers(5, 25))
        if self.preset == "controlled":
            base = int(self.rng.integers(16, 46))
        if reactive.beat > 0.7:
            base = max(3, base // 2)
        self.event_left = base

    def _wrap_blit(self, sx: int, sy: int, w: int, h: int, dx: int, dy: int) -> None:
        # modulo wrapping approximates VRAM edge behavior
        xs = (np.arange(w) + sx) % self.VRAM_W
        ys = (np.arange(h) + sy) % self.VRAM_H
        xd = (np.arange(w) + dx) % self.VRAM_W
        yd = (np.arange(h) + dy) % self.VRAM_H
        tile = self.vram[np.ix_(ys, xs)].copy()
        self.vram[np.ix_(yd, xd)] = tile

    def _corrupt(self, sev: float, reactive: ReactiveState) -> None:
        h, w = self.VRAM_H, self.VRAM_W
        mode = self.event_mode
        n = max(1, int(2 + sev * 16 + reactive.combined * 8))
        if mode in ("tiles", "mixed"):
            for _ in range(n):
                tw = int(self.rng.integers(8, 170))
                th = int(self.rng.integers(4, 110))
                sx = int(self.rng.integers(0, w)); sy = int(self.rng.integers(0, h))
                dx = int(self.rng.integers(0, w)); dy = int(self.rng.integers(0, h))
                self._wrap_blit(sx, sy, tw, th, dx, dy)
        if mode in ("address", "mixed", "sparse"):
            bands = max(1, int(1 + sev * 14))
            flow_shift = int(reactive.motion_dx * 120)
            for _ in range(bands):
                y0 = int(self.rng.integers(0, h))
                bh = int(self.rng.integers(1, 70))
                y1 = min(h, y0 + bh)
                sh = int(self.rng.integers(-280, 281)) + flow_shift
                self.vram[y0:y1] = np.roll(self.vram[y0:y1], sh, axis=1)
        if mode in ("palette", "mixed"):
            masks = np.array([0x001F, 0x03E0, 0x7C00, 0x4210, 0x2108, 0x7FFF], np.uint16)
            for _ in range(max(1, int(2 + sev * 10))):
                x0 = int(self.rng.integers(0, w - 1)); y0 = int(self.rng.integers(0, h - 1))
                x1 = int(self.rng.integers(x0 + 1, w + 1)); y1 = int(self.rng.integers(y0 + 1, h + 1))
                block = self.vram[y0:y1, x0:x1]
                mask = np.uint16(self.rng.choice(masks))
                op = int(self.rng.integers(0, 4))
                if op == 0: block ^= mask
                elif op == 1: block[:] = (block | mask) & np.uint16(0x7FFF)
                elif op == 2: block &= mask
                else:
                    s = int(self.rng.integers(1, 6))
                    block[:] = ((block << s) | (block >> (15 - s))) & np.uint16(0x7FFF)
        if self.rng.random() < 0.01 + sev * 0.05 + reactive.beat * 0.08:
            # reinterpret a large linear memory span with the wrong starting address
            y0 = int(self.rng.integers(0, 400)); bh = int(self.rng.integers(24, min(180, 512-y0)))
            band = self.vram[y0:y0+bh].reshape(-1)
            band[:] = np.roll(band, int(self.rng.integers(-5000, 5001)))

    def process(self, frame: np.ndarray, reactive: ReactiveState) -> np.ndarray:
        self.frame_index += 1
        if self.event_left <= 0:
            self._new_event(reactive)
        self.event_left -= 1

        small = cv2.resize(frame, (self.fb_w, self.fb_h), interpolation=cv2.INTER_AREA)
        b = _bayer4(self.fb_h, self.fb_w)
        dither = ((b / 15.0) - 0.5) * (6 + self.intensity * 14)
        small = np.clip(small.astype(np.float32) + dither[..., None], 0, 255).astype(np.uint8)
        packed = self._pack(small)

        # Save previous framebuffer into history page before writing the new one.
        old = self.vram[self.fb_y:self.fb_y+self.fb_h, self.fb_x:self.fb_x+self.fb_w]
        hist = cv2.resize(old, (self.hist_w, self.hist_h), interpolation=cv2.INTER_NEAREST)
        self.vram[self.hist_y:self.hist_y+self.hist_h, self.hist_x:self.hist_x+self.hist_w] = hist
        self.vram[self.fb_y:self.fb_y+self.fb_h, self.fb_x:self.fb_x+self.fb_w] = packed

        # Texture page holds a differently sampled copy; corruption can leak this back.
        tex_rgb = cv2.resize(small, (self.tex_w, self.tex_h), interpolation=cv2.INTER_NEAREST)
        tex = self._pack(tex_rgb)
        self.vram[self.tex_y:self.tex_y+self.tex_h, self.tex_x:self.tex_x+self.tex_w] = tex

        sev = self.intensity
        if self.preset == "controlled": sev *= 0.48
        if self.preset == "full_corruption": sev = min(1.0, 0.28 + sev * 0.92)
        sev = float(np.clip(sev * (0.82 + 0.55 * reactive.combined), 0.0, 1.0))
        self._corrupt(sev, reactive)

        mem = self.vram[self.fb_y:self.fb_y+self.fb_h, self.fb_x:self.fb_x+self.fb_w].copy()
        out = self._unpack(mem)
        if self.event_mode == "palette" or self.preset in ("palette_collapse", "full_corruption"):
            hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
            hsv[..., 1] = np.clip(hsv[..., 1].astype(np.float32) * (1.1 + sev * 1.5), 0, 255).astype(np.uint8)
            out = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        return cv2.resize(out, (self.out_w, self.out_h), interpolation=cv2.INTER_NEAREST)


class CPUEffectEngine:
    def __init__(self, width: int, height: int, seed: int = 1337) -> None:
        self.width, self.height = width, height
        self.rng = np.random.default_rng(seed)
        self.prev: np.ndarray | None = None
        self.frame_index = 0

    def _reactive_strength(self, intensity: float, r: ReactiveState) -> float:
        return float(np.clip(intensity * (0.72 + 0.55 * r.combined), 0.0, 1.0))

    def process(self, frame: np.ndarray, key: str, intensity: float, r: ReactiveState) -> np.ndarray:
        self.frame_index += 1
        s = self._reactive_strength(intensity, r)
        out = frame.copy()
        h, w = out.shape[:2]

        if key == "ascii_terminal":
            scale_w = max(80, min(240, w // 5))
            scale_h = max(45, int(scale_w * h / w * 0.52))
            g = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
            g = cv2.resize(g, (scale_w, scale_h), interpolation=cv2.INTER_AREA)
            levels = (g // 32) * 32
            # Horizontal terminal glyph illusion: short bright strokes per cell.
            term = np.zeros((scale_h * 2, scale_w * 2, 3), np.uint8)
            term[..., 1] = np.repeat(np.repeat(levels, 2, 0), 2, 1)
            term[..., 2] = (term[..., 1] * 0.38).astype(np.uint8)
            term[1::2, ::4] = 0
            out = cv2.resize(term, (w, h), interpolation=cv2.INTER_NEAREST)
        elif key == "digital_rain":
            g = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            base = np.zeros_like(out)
            base[..., 1] = np.clip((g ** 0.8) * 190, 0, 255).astype(np.uint8)
            columns = max(24, w // 22)
            rain = np.zeros((h, w), np.uint8)
            speed = 2.0 + 14.0 * (0.2 + r.audio + r.beat)
            for c in range(columns):
                x = int((c + 0.5) * w / columns)
                y = int((self.frame_index * speed + c * 43) % (h + 120) - 120)
                cv2.line(rain, (x, max(0, y-85)), (x, min(h-1, y)), 90, max(1, w // 500))
            glow = cv2.GaussianBlur(rain, (0,0), 5)
            base[..., 1] = np.maximum(base[..., 1], glow)
            out = base
        elif key == "gothic_crimson":
            gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 55, 145)
            dark = np.clip((gray.astype(np.float32)-35) * 0.78, 0, 255).astype(np.uint8)
            out = cv2.cvtColor(dark, cv2.COLOR_GRAY2BGR)
            out[..., 2] = np.maximum(out[..., 2], (edges.astype(np.float32) * (0.32 + 0.60*s)).astype(np.uint8))
            out[..., 0] = (out[..., 0].astype(np.float32)*0.82).astype(np.uint8)
        elif key == "spectral_echo":
            if self.prev is not None:
                dx = int(r.motion_dx * 34 + math.sin(self.frame_index*0.09)*8*s)
                dy = int(r.motion_dy * 24)
                hist = np.roll(self.prev, (dy, dx), axis=(0,1))
                out = cv2.addWeighted(out, 0.67, hist, 0.33 + 0.25*s, 0)
                out[..., 0] = np.roll(out[..., 0], int(5+15*s), axis=1)
            self.prev = out.copy()
        elif key == "pixel_sort":
            core_w = min(480, w); core_h = max(80, int(core_w*h/w))
            core = cv2.resize(out, (core_w, core_h), interpolation=cv2.INTER_AREA)
            lum = cv2.cvtColor(core, cv2.COLOR_BGR2GRAY)
            rows = self.rng.choice(core_h, size=max(4, int(8+32*s)), replace=False)
            for y in rows:
                threshold = int(70 + self.rng.integers(0,120))
                mask = lum[y] > threshold
                idx = np.flatnonzero(mask)
                if idx.size > 4:
                    vals = core[y, idx]
                    order = np.argsort(np.sum(vals.astype(np.int32), axis=1))
                    core[y, idx] = vals[order]
            out = cv2.resize(core, (w,h), interpolation=cv2.INTER_NEAREST)
        elif key == "scanline_melt":
            step = max(2, int(9-6*s))
            for y in range(0,h,step):
                bh = min(step, h-y)
                shift = int(math.sin((y*0.037)+(self.frame_index*0.11))*w*0.045*s + r.motion_dx*w*0.05)
                out[y:y+bh] = np.roll(out[y:y+bh], shift, axis=1)
        elif key == "chromatic_vhs":
            off = max(1, int(2+10*s+7*r.audio))
            b,g,rr = cv2.split(out)
            b = np.roll(b, off, axis=1); rr = np.roll(rr, -off, axis=1)
            out = cv2.merge([b,g,rr])
            out[::2] = (out[::2].astype(np.float32)*0.82).astype(np.uint8)
            if self.frame_index % 5 == 0:
                y=int(self.rng.integers(0,h)); bh=int(self.rng.integers(2,max(3,h//12)))
                out[y:min(h,y+bh)] = np.roll(out[y:min(h,y+bh)], int(self.rng.integers(-w//12,w//12+1)), axis=1)
            noise=self.rng.normal(0,5+12*s,out.shape).astype(np.float32)
            out=np.clip(out.astype(np.float32)+noise,0,255).astype(np.uint8)
        elif key == "crt_terminal":
            out[1::2] = (out[1::2].astype(np.float32)*(0.72-0.14*s)).astype(np.uint8)
            out[...,0] = np.roll(out[...,0], 1, axis=1)
            out[...,2] = np.roll(out[...,2], -1, axis=1)
            # mild barrel-ish warp via remap
            yy,xx=np.indices((h,w),dtype=np.float32)
            nx=(xx-w/2)/(w/2); ny=(yy-h/2)/(h/2); rad=nx*nx+ny*ny
            k=0.035*s
            mapx=(nx*(1+k*rad)*(w/2)+w/2).astype(np.float32)
            mapy=(ny*(1+k*rad)*(h/2)+h/2).astype(np.float32)
            out=cv2.remap(out,mapx,mapy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        elif key == "void_bloom":
            gray=cv2.cvtColor(out,cv2.COLOR_BGR2GRAY)
            _,sil=cv2.threshold(gray, int(118+30*(1-s)),255,cv2.THRESH_BINARY)
            glow=cv2.GaussianBlur(sil,(0,0),max(2.0,min(h,w)/70.0))
            dark=(out.astype(np.float32)*(0.36+0.2*(1-s))).astype(np.uint8)
            dark[...,0]=np.maximum(dark[...,0], glow)
            dark[...,1]=np.maximum(dark[...,1], (glow*0.85).astype(np.uint8))
            dark[...,2]=np.maximum(dark[...,2], (glow*0.70).astype(np.uint8))
            out=dark
        elif key == "neon_noir":
            gray=cv2.cvtColor(out,cv2.COLOR_BGR2GRAY)
            edges=cv2.Laplacian(gray,cv2.CV_16S,ksize=3)
            edges=np.clip(np.abs(edges),0,255).astype(np.uint8)
            base=(out.astype(np.float32)*0.42).astype(np.uint8)
            base[...,0]=np.maximum(base[...,0],edges)
            base[...,2]=np.maximum(base[...,2],np.roll(edges,3,axis=1))
            out=cv2.GaussianBlur(base,(0,0),0.35)
        elif key == "retro_space":
            core_w=min(400,w); core_h=max(80,int(core_w*h/w))
            core=cv2.resize(out,(core_w,core_h),interpolation=cv2.INTER_AREA)
            b=_bayer4(core_h,core_w)
            core=np.clip(core.astype(np.float32)+(b[...,None]-7.5)*(1.2+2.0*s),0,255)
            core=(np.floor(core/32)*32).astype(np.uint8)
            out=cv2.resize(core,(w,h),interpolation=cv2.INTER_NEAREST)
        elif key == "datamosh_flow":
            if self.prev is not None:
                block=max(8,int(48-24*s)); dx=int(r.motion_dx*block*2); dy=int(r.motion_dy*block*2)
                hist=np.roll(self.prev,(dy,dx),axis=(0,1))
                mask=cv2.cvtColor(cv2.absdiff(out,hist),cv2.COLOR_BGR2GRAY)
                mask=(mask < int(50+80*s)).astype(np.uint8)
                mask=cv2.resize(cv2.resize(mask,(max(1,w//block),max(1,h//block)),interpolation=cv2.INTER_AREA),(w,h),interpolation=cv2.INTER_NEAREST)
                out=np.where(mask[...,None]>0,hist,out)
            self.prev=out.copy()
        elif key == "recursive_feedback":
            if self.prev is not None:
                M=cv2.getRotationMatrix2D((w/2,h/2), math.sin(self.frame_index*0.07)*0.8*s, 0.985-0.015*s)
                hist=cv2.warpAffine(self.prev,M,(w,h),borderMode=cv2.BORDER_REFLECT)
                out=cv2.addWeighted(out,0.60,hist,0.56,0)
            self.prev=out.copy()
        elif key == "brutalist_collage":
            core=out.copy(); tiles=max(3,int(4+7*s))
            for _ in range(tiles):
                tw=int(self.rng.integers(max(20,w//10),max(21,w//3))); th=int(self.rng.integers(max(20,h//10),max(21,h//3)))
                sx=int(self.rng.integers(0,max(1,w-tw))); sy=int(self.rng.integers(0,max(1,h-th)))
                tile=core[sy:sy+th,sx:sx+tw]
                zoom=float(self.rng.uniform(0.8,1.7)); nw=max(1,int(tw*zoom)); nh=max(1,int(th*zoom))
                tile=cv2.resize(tile,(nw,nh),interpolation=cv2.INTER_LINEAR)
                dx=int(self.rng.integers(0,max(1,w-min(nw,w)))); dy=int(self.rng.integers(0,max(1,h-min(nh,h))))
                out[dy:dy+min(nh,h-dy),dx:dx+min(nw,w-dx)]=tile[:min(nh,h-dy),:min(nw,w-dx)]
            edges=cv2.Canny(cv2.cvtColor(out,cv2.COLOR_BGR2GRAY),70,150)
            bright=np.clip(out.astype(np.int16)+45,0,255).astype(np.uint8)
            out=np.where(edges[...,None]>0,bright,out).astype(np.uint8)
        elif key == "cyber_wire":
            gray=cv2.cvtColor(out,cv2.COLOR_BGR2GRAY)
            edges=cv2.Canny(gray,45,135)
            wire=np.zeros_like(out)
            wire[...,0]=edges
            wire[...,1]=np.maximum(wire[...,1],edges)
            wire[...,2]=np.roll(edges,max(1,int(3+8*s)),axis=1)
            step=max(24,int(70-30*s))
            wire[:,::step,1]=np.maximum(wire[:,::step,1],120)
            wire[::step,:,0]=np.maximum(wire[::step,:,0],120)
            out=cv2.addWeighted(out,0.18,wire,0.95,0)
        elif key == "liquid_chrome":
            g=cv2.cvtColor(out,cv2.COLOR_BGR2GRAY).astype(np.float32)/255.0
            bands=np.floor(g*(6+10*s))/(6+10*s)
            sheen=(0.5+0.5*np.sin(np.linspace(0,math.pi*8,w,dtype=np.float32)+self.frame_index*0.04))[None,:]
            metal=np.dstack([bands*0.85,bands*0.93,bands*1.08])
            metal += sheen[...,None]*(0.05+0.18*s)
            out=np.clip(metal*255,0,255).astype(np.uint8)
        elif key == "psx_dither":
            scale=max(1,int(2+4*s))
            sw=max(64,w//scale); sh=max(48,h//scale)
            core=cv2.resize(out,(sw,sh),interpolation=cv2.INTER_AREA).astype(np.float32)
            b=_bayer4(sh,sw)
            core=np.clip(core+(b[...,None]-7.5)*(0.8+2.2*s),0,255)
            core=(np.floor(core/8)*8).astype(np.uint8)
            out=cv2.resize(core,(w,h),interpolation=cv2.INTER_NEAREST)
        elif key == "gothic_halo":
            gray=cv2.cvtColor(out,cv2.COLOR_BGR2GRAY)
            edges=cv2.Canny(gray,40,120)
            halo=cv2.GaussianBlur(edges,(0,0),max(1.4,min(h,w)/140.0))
            base=(gray.astype(np.float32)*0.12).astype(np.uint8)
            out=cv2.cvtColor(base,cv2.COLOR_GRAY2BGR)
            out[...,2]=np.maximum(out[...,2],np.clip(halo.astype(np.float32)*(1.2+1.6*s),0,255).astype(np.uint8))
            out[...,0]=np.maximum(out[...,0],(halo*0.16).astype(np.uint8))
        elif key == "signal_grid":
            cell=max(18,int(58-30*s));
            for y in range(0,h,cell):
                if self.rng.random()<0.28+0.35*s:
                    bh=min(cell,h-y); sh=int(self.rng.integers(-cell,cell+1))
                    out[y:y+bh]=np.roll(out[y:y+bh],sh,axis=1)
            out[:,::cell]=np.clip(out[:,::cell].astype(np.int16)+np.array([80,120,0]),0,255).astype(np.uint8)
            out[::cell,:]=np.clip(out[::cell,:].astype(np.int16)+np.array([40,75,0]),0,255).astype(np.uint8)
        elif key == "temporal_shred":
            src=self.prev if self.prev is not None else out
            band=max(8,int(42-24*s)); result=out.copy()
            for x0 in range(0,w,band):
                if ((x0//band)+self.frame_index)%3==0 or self.rng.random()<0.18+0.42*s:
                    x1=min(w,x0+band); shift=int((r.motion_dx*95+math.sin(self.frame_index*.19+x0*.03)*36)*s)
                    result[:,x0:x1]=np.roll(src[:,x0:x1],shift,axis=0)
            out=cv2.addWeighted(out,0.55,result,0.62,0); self.prev=out.copy()
        elif key == "prism_rift":
            center=(w/2+r.motion_dx*w*.12,h/2+r.motion_dy*h*.12)
            scales=(1.0+.018*s,1.0,1.0-.016*s); chans=cv2.split(out); warped=[]
            for ch,sc in zip(chans,scales):
                M=cv2.getRotationMatrix2D(center,0,sc); warped.append(cv2.warpAffine(ch,M,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT))
            out=cv2.merge(warped)
            if r.beat>.55: out=np.roll(out,int((4+18*s)*(1 if self.frame_index%2 else -1)),axis=1)
        elif key == "edge_strobe":
            gray=cv2.cvtColor(out,cv2.COLOR_BGR2GRAY); edge=cv2.Canny(gray,50,140)
            pulse=float(np.clip(max(r.beat,r.treble*.75),0,1)); glow=cv2.GaussianBlur(edge,(0,0),1.2+4*s)
            base=(out.astype(np.float32)*(0.38+0.35*(1-s))).astype(np.uint8)
            base[...,1]=np.maximum(base[...,1],np.clip(glow*(.35+1.7*pulse*s),0,255).astype(np.uint8))
            base[...,2]=np.maximum(base[...,2],np.clip(np.roll(glow,2,axis=1)*(.25+1.5*pulse*s),0,255).astype(np.uint8)); out=base
        elif key == "data_bloom":
            gray=cv2.cvtColor(out,cv2.COLOR_BGR2GRAY); hi=np.where(gray>int(165-55*s),gray,0).astype(np.uint8)
            bloom=cv2.GaussianBlur(hi,(0,0),3+12*s); b,g,rr=cv2.split(out)
            rr=np.maximum(rr,np.clip(bloom*(.45+1.1*s),0,255).astype(np.uint8)); g=np.maximum(g,np.clip(bloom*(.25+.65*s),0,255).astype(np.uint8)); out=cv2.merge([b,g,rr])
            block=max(10,int(46-26*s));
            if self.frame_index%3==0:
                for y0 in range(0,h,block):
                    if self.rng.random()<.12+.32*s: out[y0:min(h,y0+block)]=np.roll(out[y0:min(h,y0+block)],int(self.rng.integers(-block*2,block*2+1)),axis=1)
        elif key == "motion_tunnel":
            if self.prev is not None:
                zoom=.975-.035*s; M=cv2.getRotationMatrix2D((w/2,h/2),math.sin(self.frame_index*.08)*1.2*s,zoom)
                M[0,2]+=r.motion_dx*w*.018; M[1,2]+=r.motion_dy*h*.018
                hist=cv2.warpAffine(self.prev,M,(w,h),borderMode=cv2.BORDER_REFLECT); out=cv2.addWeighted(out,.58,hist,.58,0)
            self.prev=out.copy()

        return out
