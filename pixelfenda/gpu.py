from __future__ import annotations

import numpy as np
import cv2

from .reactive import ReactiveState


GPU_EFFECT_IDS = {
    "ascii_terminal": 1, "digital_rain": 2, "gothic_crimson": 3,
    "spectral_echo": 4, "scanline_melt": 5, "chromatic_vhs": 6,
    "crt_terminal": 7, "void_bloom": 8, "neon_noir": 9,
    "retro_space": 10, "recursive_feedback": 11,
    "cyber_wire": 12, "liquid_chrome": 13, "psx_dither": 14,
    "gothic_halo": 15, "signal_grid": 16,
}
FILTER_IDS = {
    "none": 0, "vintage_70": 1, "vintage_90": 2, "cinematic_teal_amber": 3,
    "cold_archive": 4, "silver_gray": 5, "noir": 6, "odyssey_70": 7,
    "bleach_bypass": 8, "matrix_green": 9, "gothic_iron": 10, "y2k_chrome": 11,
    "dream_white": 12, "neon_night": 13, "space_blue": 14, "antique_sepia": 15,
    "social_cool": 16, "muted_linen": 17, "soft_bw": 18, "infrared_ice": 19,
}

VERTEX = r"""
#version 330
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
    v_uv = in_uv;
}
"""

FRAGMENT = r"""
#version 330
uniform sampler2D u_tex;
uniform sampler2D u_prev;
uniform int u_effect;
uniform int u_filter;
uniform float u_intensity;
uniform float u_filter_strength;
uniform float u_time;
uniform float u_audio;
uniform float u_bass;
uniform float u_treble;
uniform float u_motion;
uniform float u_dx;
uniform float u_dy;
uniform float u_seed;
uniform vec2 u_resolution;
in vec2 v_uv;
out vec4 fragColor;

float hash21(vec2 p){ p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32+u_seed); return fract(p.x*p.y); }
float lum(vec3 c){ return dot(c,vec3(0.299,0.587,0.114)); }
vec3 sat(vec3 c,float s){ float y=lum(c); return mix(vec3(y),c,s); }
vec3 grade(vec3 c,float contrast,float saturation,float lift,vec3 gain){ c=(c-0.5)*contrast+0.5+lift; c=sat(c,saturation); return clamp(c*gain,0.0,1.0); }

vec3 effect(vec2 uv){
    vec2 texel=1.0/u_resolution;
    vec3 c=texture(u_tex,uv).rgb;
    float react=clamp(max(u_audio,u_motion),0.0,1.0);
    float s=clamp(u_intensity*(0.72+0.55*react),0.0,1.0);
    if(u_effect==1){
        vec2 cells=vec2(180.0,100.0); vec2 q=floor(uv*cells)/cells;
        float y=lum(texture(u_tex,q).rgb); float l=floor(y*8.0)/8.0;
        float stroke=step(0.22,fract(uv.x*cells.x))*step(fract(uv.y*cells.y),0.72);
        return vec3(l*0.18,l,l*0.34)*stroke;
    }
    if(u_effect==2){
        float y=lum(c); vec2 p=uv*u_resolution/vec2(14.0,18.0);
        float col=floor(p.x); float fall=fract(p.y + u_time*(0.45+1.6*u_audio)+hash21(vec2(col,2.0))*8.0);
        float rain=smoothstep(0.55,1.0,fall)*step(0.72,hash21(vec2(col,floor(p.y-u_time*2.0))));
        float sparkle=0.15*u_treble*hash21(vec2(floor(p.x),floor(p.y+u_time*5.0)));
        return vec3(0.02, y*0.78+rain*(0.35+0.65*u_bass)+sparkle, 0.06+y*0.10+sparkle*0.25);
    }
    if(u_effect==3){
        float y=lum(c); float e=abs(lum(texture(u_tex,uv+vec2(texel.x,0)).rgb)-lum(texture(u_tex,uv-vec2(texel.x,0)).rgb));
        return vec3(y*0.13, y*0.10, y*0.12+e*(2.0+3.0*s));
    }
    if(u_effect==4){
        vec2 sh=vec2(0.012*s+u_dx*0.018,u_dy*0.012);
        vec3 h=texture(u_prev,clamp(uv+sh,0.0,1.0)).rgb;
        vec3 m=mix(c,h,0.32+0.32*s); m.r=texture(u_tex,clamp(uv-vec2(0.008*s,0),0.0,1.0)).r; return m;
    }
    if(u_effect==5){
        float band=floor(uv.y*u_resolution.y/5.0); float shift=sin(band*0.17+u_time*5.0)*(0.006+0.035*s)+u_dx*0.035;
        return texture(u_tex,vec2(fract(uv.x+shift),uv.y)).rgb;
    }
    if(u_effect==6){
        float j=(hash21(vec2(floor(uv.y*u_resolution.y/6.0),floor(u_time*12.0)))-0.5)*0.020*s;
        float o=0.002+0.012*s+0.010*u_audio; vec2 q=vec2(fract(uv.x+j),uv.y);
        return vec3(texture(u_tex,q-vec2(o,0)).r,texture(u_tex,q).g,texture(u_tex,q+vec2(o,0)).b)*(0.82+0.18*step(0.5,fract(uv.y*u_resolution.y*0.5)));
    }
    if(u_effect==7){
        vec2 p=uv*2.0-1.0; float r=dot(p,p); p*=1.0+0.055*s*r; vec2 q=p*0.5+0.5;
        vec3 z=texture(u_tex,clamp(q,0.0,1.0)).rgb; z*=0.78+0.22*step(0.45,fract(uv.y*u_resolution.y*0.5)); return z;
    }
    if(u_effect==8){
        float y=lum(c); float hi=smoothstep(0.48,0.82,y); vec3 b=vec3(0.03)+c*(0.25+0.15*(1.0-s));
        for(int i=1;i<=4;i++){ float f=float(i); b+=texture(u_tex,uv+vec2(texel.x*f*3.0,0)).rgb*hi*0.07*s; }
        return clamp(b+vec3(hi*0.58,hi*0.52,hi*0.44),0.0,1.0);
    }
    if(u_effect==9){
        float y=lum(c); float ex=abs(lum(texture(u_tex,uv+vec2(texel.x*2.0,0)).rgb)-lum(texture(u_tex,uv-vec2(texel.x*2.0,0)).rgb));
        float ey=abs(lum(texture(u_tex,uv+vec2(0,texel.y*2.0)).rgb)-lum(texture(u_tex,uv-vec2(0,texel.y*2.0)).rgb)); float e=(ex+ey)*3.0;
        return clamp(c*0.30+vec3(e*0.90,e*0.30,e*0.80),0.0,1.0);
    }
    if(u_effect==10){
        vec2 p=floor(uv*u_resolution/3.0); float d=(hash21(mod(p,4.0))-0.5)*0.10*s; vec3 z=floor((c+d)*7.0)/7.0; return z;
    }
    if(u_effect==11){
        vec2 p=(uv-0.5)*(0.985-0.018*s)+0.5+vec2(u_dx,u_dy)*0.006; vec3 h=texture(u_prev,clamp(p,0.0,1.0)).rgb; return clamp(c*0.58+h*0.56,0.0,1.0);
    }
    if(u_effect==12){
        float ex=abs(lum(texture(u_tex,uv+vec2(texel.x*2.0,0)).rgb)-lum(texture(u_tex,uv-vec2(texel.x*2.0,0)).rgb));
        float ey=abs(lum(texture(u_tex,uv+vec2(0,texel.y*2.0)).rgb)-lum(texture(u_tex,uv-vec2(0,texel.y*2.0)).rgb));
        float e=smoothstep(0.035,0.18,ex+ey); float gx=step(0.965,fract(uv.x*34.0)); float gy=step(0.965,fract(uv.y*20.0));
        vec3 wire=vec3(0.10,0.90,1.0)*e + vec3(0.82,0.10,0.86)*(gx+gy)*(0.18+0.35*s); return clamp(c*0.17+wire,0.0,1.0);
    }
    if(u_effect==13){
        float y=lum(c); float bands=floor(y*(5.0+8.0*s))/(5.0+8.0*s); float sheen=pow(abs(sin((uv.x*2.4+uv.y*1.2+u_time*0.22)*6.283)),12.0);
        vec3 metal=mix(vec3(bands*0.35),vec3(bands*0.72,bands*0.84,bands*1.02),0.72); metal+=sheen*(0.10+0.32*s); return clamp(metal,0.0,1.0);
    }
    if(u_effect==14){
        vec2 grid=max(vec2(1.0),floor(u_resolution/vec2(3.0))); vec2 q=(floor(uv*grid)+0.5)/grid; vec3 z=texture(u_tex,q).rgb;
        float d=hash21(floor(uv*u_resolution/3.0)); z=floor((z+(d-0.5)*0.10*s)*31.0)/31.0; return clamp(z,0.0,1.0);
    }
    if(u_effect==15){
        float y=lum(c); float ex=abs(lum(texture(u_tex,uv+vec2(texel.x*3.0,0)).rgb)-lum(texture(u_tex,uv-vec2(texel.x*3.0,0)).rgb));
        float ey=abs(lum(texture(u_tex,uv+vec2(0,texel.y*3.0)).rgb)-lum(texture(u_tex,uv-vec2(0,texel.y*3.0)).rgb)); float halo=smoothstep(0.02,0.15,ex+ey);
        return clamp(vec3(y*0.06,y*0.04,y*0.05)+vec3(0.12,0.04,0.78)*halo*(0.65+0.8*s),0.0,1.0);
    }
    if(u_effect==16){
        vec2 cell=vec2(48.0,27.0); vec2 id=floor(uv*cell); float gate=step(0.88,hash21(id+floor(u_time*3.0))); float sh=(hash21(vec2(id.y,floor(u_time*6.0)))-0.5)*0.05*s*gate;
        vec2 q=vec2(fract(uv.x+sh+u_dx*0.02),uv.y); vec3 z=texture(u_tex,q).rgb; float grid=max(step(0.96,fract(uv.x*cell.x)),step(0.96,fract(uv.y*cell.y))); return clamp(z*(0.92-grid*0.28)+vec3(0.0,0.55,0.72)*grid*0.35,0.0,1.0);
    }
    return c;
}

vec3 filterColor(vec3 c, vec2 uv){
    vec3 src=c;
    float y=lum(c); float n=hash21(uv*u_resolution+floor(u_time*30.0))-0.5;
    if(u_filter==1){ c=grade(c,0.88,0.78,0.035,vec3(0.91,1.0,1.10)); c+=n*0.035; }
    else if(u_filter==2){ c=grade(c,0.94,0.82,0.02,vec3(0.97,1.04,1.04)); c+=n*0.028; }
    else if(u_filter==3){ c=grade(c,1.10,1.02,-0.01,vec3(1.0)); c.b+=max(0.0,0.5-y)*0.10; c.r+=max(0.0,y-0.5)*0.12; }
    else if(u_filter==4){ c=grade(c,0.93,0.58,0.025,vec3(1.10,1.03,0.88)); c+=n*0.04; }
    else if(u_filter==5){ c=vec3(y)*vec3(1.03,1.01,0.98); }
    else if(u_filter==6){ c=vec3(clamp((y-0.5)*1.38+0.465,0.0,1.0)); }
    else if(u_filter==7){ c=grade(c,1.06,0.91,-0.008,vec3(1.015,1.0,1.025)); c+=n*0.014; }
    else if(u_filter==8){ c=mix(c,vec3(y),0.58); c=grade(c,1.28,0.52,-0.015,vec3(1.0)); }
    else if(u_filter==9){ c=vec3(y*0.08,y*0.93,y*0.18); }
    else if(u_filter==10){ c=grade(c,1.20,0.62,-0.035,vec3(1.06,0.94,1.02)); c.r+=max(0.0,y-0.55)*0.08; }
    else if(u_filter==11){ c=grade(c,1.10,0.50,0.045,vec3(1.08,1.05,1.0)); }
    else if(u_filter==12){ c=grade(c,0.78,0.55,0.10,vec3(1.03,1.02,1.04)); }
    else if(u_filter==13){ c=grade(c,1.17,1.18,-0.04,vec3(1.16,1.02,0.92)); }
    else if(u_filter==14){ c=grade(c,1.16,0.72,-0.035,vec3(1.18,1.05,0.80)); c+=n*0.02; }
    else if(u_filter==15){ c=vec3(y*0.72,y*0.88,y*1.06); c+=n*0.035; }
    else if(u_filter==16){ c=grade(c,1.13,1.08,0.01,vec3(1.07,1.02,0.97)); }
    else if(u_filter==17){ c=grade(c,0.86,0.67,0.06,vec3(0.98,1.0,1.04)); }
    else if(u_filter==18){ c=vec3(y); c=grade(c,0.90,0.0,0.025,vec3(1.0)); }
    else if(u_filter==19){ float inv=1.0-y; c=vec3(inv*1.12, inv*0.92+y*0.20, inv*0.70+y*0.35); c=grade(c,1.18,0.86,0.015,vec3(1.0)); }
    return clamp(mix(src,c,clamp(u_filter_strength,0.0,1.0)),0.0,1.0);
}

void main(){ vec3 c=effect(v_uv); c=filterColor(c,v_uv); fragColor=vec4(c,1.0); }
"""


class GPUPipeline:
    def __init__(self, width: int, height: int, seed: int = 1337) -> None:
        import moderngl  # lazy import: CPU fallback remains dependency-light
        self.moderngl = moderngl
        self.width, self.height = int(width), int(height)
        self.seed = float(seed % 100000)
        self.ctx = moderngl.create_context(standalone=True, require=330)
        self.renderer = str(self.ctx.info.get("GL_RENDERER", "OpenGL GPU"))
        self.program = self.ctx.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
        verts = np.array([
            -1,-1, 0,0,
             1,-1, 1,0,
            -1, 1, 0,1,
             1, 1, 1,1,
        ], dtype="f4")
        self.vbo = self.ctx.buffer(verts.tobytes())
        self.vao = self.ctx.vertex_array(self.program, [(self.vbo, "2f 2f", "in_pos", "in_uv")])
        self.tex = self.ctx.texture((self.width,self.height), 3, dtype="f1")
        self.prev = self.ctx.texture((self.width,self.height), 3, dtype="f1")
        self.output = self.ctx.texture((self.width,self.height), 3, dtype="f1")
        self.fbo = self.ctx.framebuffer([self.output])
        self.tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.prev.filter = (moderngl.LINEAR, moderngl.LINEAR)
        black = np.zeros((self.height,self.width,3), np.uint8)
        self.prev.write(black.tobytes())
        self.program["u_tex"].value = 0
        self.program["u_prev"].value = 1
        self.program["u_resolution"].value = (float(self.width),float(self.height))
        self.program["u_seed"].value = self.seed
        self.frame_index = 0

    def _set_uniform(self, name: str, value) -> bool:
        """Set a shader uniform only when it survived GLSL optimization.

        OpenGL drivers are allowed to remove uniforms that do not contribute to the
        final fragment output. ModernGL then raises KeyError when Python tries to
        address that optimized-out uniform. Treating optional/reactive uniforms as
        optional keeps the pipeline portable across NVIDIA/AMD/Intel drivers.
        """
        try:
            self.program[name].value = value
            return True
        except KeyError:
            return False

    def set_prev_frame(self, frame_bgr: np.ndarray) -> None:
        """Inject a layer-specific previous frame into the shared GPU pipeline."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        self.prev.write(np.flipud(rgb).copy().tobytes())

    def process(self, frame_bgr: np.ndarray, effect_key: str, filter_key: str,
                intensity: float, r: ReactiveState, fps: float, filter_strength: float = 1.0,
                time_seconds: float | None = None) -> np.ndarray:
        self.frame_index += 1
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb_gl = np.flipud(rgb).copy()
        self.tex.write(rgb_gl.tobytes())
        self.tex.use(0); self.prev.use(1)
        self._set_uniform("u_effect", int(GPU_EFFECT_IDS.get(effect_key,0)))
        self._set_uniform("u_filter", int(FILTER_IDS.get(filter_key,0)))
        self._set_uniform("u_intensity", float(np.clip(intensity,0.0,1.0)))
        self._set_uniform("u_filter_strength", float(np.clip(filter_strength,0.0,1.0)))
        self._set_uniform("u_time", float(time_seconds if time_seconds is not None else self.frame_index/max(1.0,fps)))
        self._set_uniform("u_audio", float(r.audio))
        self._set_uniform("u_bass", float(r.bass))
        self._set_uniform("u_treble", float(r.treble))
        self._set_uniform("u_motion", float(r.motion))
        self._set_uniform("u_dx", float(r.motion_dx))
        self._set_uniform("u_dy", float(r.motion_dy))
        self.fbo.use(); self.ctx.viewport=(0,0,self.width,self.height)
        self.vao.render(mode=self.moderngl.TRIANGLE_STRIP)
        raw=self.fbo.read(components=3,alignment=1)
        arr=np.frombuffer(raw,np.uint8).reshape(self.height,self.width,3)
        arr=np.flipud(arr).copy()
        self.prev.write(np.flipud(arr).copy().tobytes())
        return cv2.cvtColor(arr,cv2.COLOR_RGB2BGR)

    def release(self) -> None:
        for obj in (self.fbo,self.output,self.prev,self.tex,self.vao,self.vbo,self.program):
            try: obj.release()
            except Exception: pass
        try: self.ctx.release()
        except Exception: pass


def create_gpu_pipeline(width: int, height: int, seed: int = 1337) -> GPUPipeline:
    return GPUPipeline(width,height,seed)
