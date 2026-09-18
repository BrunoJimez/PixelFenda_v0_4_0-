from __future__ import annotations

import os
import threading
import traceback
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from .engine import preview_layers, probe_video, render_video_layers
from .ffmpeg_utils import make_output_path
from .layering import (
    BLEND_BY_LABEL, BLEND_MODES, MOD_BY_LABEL, MOD_SOURCES,
    SCENE_BY_LABEL, SCENE_MODES,
)
from .model import LayerSpec, ProjectDocument, RenderJob
from .presets import (
    AUDIO_BY_LABEL, AUDIO_MODES, EFFECT_BY_LABEL, EFFECT_PRESETS,
    ENCODER_BY_LABEL, ENCODER_MODES, FILTER_BY_LABEL, FILTER_PRESETS,
    GPU_BY_LABEL, GPU_MODES, REACTIVE_BY_LABEL, REACTIVE_MODES,
    RESIZE_BY_LABEL, RESIZE_MODES, RESOLUTION_BY_LABEL, RESOLUTION_PRESETS,
)
from .scene import analyze_scenes
from .stems import demucs_available, separate_vocals
from .masks import MASK_BY_LABEL, MASK_MODES
from .rhythm import BeatAnalysis, analyze_beats
from .temporal import EASING_BY_LABEL, EASING_MODES, make_beat_pulse_keyframes


class ScrollableFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, bg="#11161d")
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(3, "units"))

    def _wheel(self, event):
        self.canvas.yview_scroll((-1 if event.delta > 0 else 1) * 3, "units")


class PixelFendaApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PixelFenda v0.4.0 — Temporal Director")
        self.geometry("1220x830")
        self.minsize(820, 610)
        self.configure(bg="#0e141b")
        self.worker: threading.Thread | None = None
        self.preview_photo = None
        self.layers: list[LayerSpec] = [
            LayerSpec(kind="effect", key="corrupted_memory", intensity=0.72, opacity=1.0),
            LayerSpec(kind="filter", key="vintage_70", intensity=0.82, opacity=1.0, enabled=False),
        ]
        self.jobs: list[RenderJob] = []
        self.beat_analysis: BeatAnalysis | None = None
        self._selected_layer: int | None = 0
        self._style()
        self._vars()
        self._build_ui()
        self._refresh_layers()
        self._update_states()

    def _vars(self) -> None:
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.music_var = tk.StringVar()
        self.stem_vocals_var = tk.StringVar()
        self.stem_inst_var = tk.StringVar()
        self.res_var = tk.StringVar(value=RESOLUTION_PRESETS[0].label)
        self.custom_w = tk.StringVar(value="1080")
        self.custom_h = tk.StringVar(value="1920")
        self.resize_var = tk.StringVar(value=RESIZE_MODES["crop"])
        self.encoder_var = tk.StringVar(value=ENCODER_MODES["auto"])
        self.gpu_var = tk.StringVar(value=GPU_MODES["auto"])
        self.seed_var = tk.StringVar(value="1337")
        self.reactive_var = tk.StringVar(value=REACTIVE_MODES["none"])
        self.scene_mode_var = tk.StringVar(value=SCENE_MODES["off"])
        self.scene_threshold_var = tk.DoubleVar(value=22.0)
        self.audio_mode_var = tk.StringVar(value=AUDIO_MODES["original"])
        self.status_var = tk.StringVar(value="Pronto.")
        self.preview_pos_var = tk.DoubleVar(value=50.0)
        self.queue_dir_var = tk.StringVar()
        # Layer editor variables.
        self.le_enabled = tk.BooleanVar(value=True)
        self.le_kind = tk.StringVar(value="effect")
        self.le_preset = tk.StringVar(value=EFFECT_PRESETS["corrupted_memory"])
        self.le_lut = tk.StringVar()
        self.le_intensity = tk.DoubleVar(value=72.0)
        self.le_opacity = tk.DoubleVar(value=100.0)
        self.le_blend = tk.StringVar(value=BLEND_MODES["normal"])
        self.le_mod = tk.StringVar(value=MOD_SOURCES["none"])
        self.le_mod_amount = tk.DoubleVar(value=0.0)
        self.le_scene_reset = tk.BooleanVar(value=False)
        self.le_name = tk.StringVar()
        # v0.4 temporal/mask editor variables
        self.tm_layer_name = tk.StringVar(value="Camada selecionada")
        self.tm_start = tk.StringVar(value="0.0")
        self.tm_end = tk.StringVar(value="-1.0")
        self.tm_fade_in = tk.StringVar(value="0.0")
        self.tm_fade_out = tk.StringVar(value="0.0")
        self.tm_ease = tk.StringVar(value=EASING_MODES["smooth"])
        self.kf_time = tk.StringVar(value="0.0")
        self.kf_intensity = tk.DoubleVar(value=72.0)
        self.kf_opacity = tk.DoubleVar(value=100.0)
        self.kf_mod = tk.DoubleVar(value=0.0)
        self.mask_kind_var = tk.StringVar(value=MASK_MODES["full"])
        self.mask_x_var = tk.DoubleVar(value=50.0)
        self.mask_y_var = tk.DoubleVar(value=50.0)
        self.mask_w_var = tk.DoubleVar(value=60.0)
        self.mask_h_var = tk.DoubleVar(value=60.0)
        self.mask_feather_var = tk.DoubleVar(value=8.0)
        self.mask_angle_var = tk.DoubleVar(value=0.0)
        self.mask_invert_var = tk.BooleanVar(value=False)
        self.mask_track_var = tk.BooleanVar(value=False)
        self.mask_track_strength_var = tk.DoubleVar(value=100.0)
        self.beat_peak_var = tk.DoubleVar(value=100.0)
        self.beat_decay_var = tk.StringVar(value="0.12")
        self.beat_status_var = tk.StringVar(value="Grade de batidas ainda não analisada.")

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        bg="#0e141b"; panel="#151d27"; field="#1e2a36"; fg="#dce6ef"; muted="#8195a8"; accent="#87b8cb"
        style.configure(".", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("Panel.TLabel", background=panel, foreground=fg)
        style.configure("Muted.TLabel", background=bg, foreground=muted)
        style.configure("TButton", background=field, foreground=fg, padding=(9, 6))
        style.map("TButton", background=[("active", "#2a3948")])
        style.configure("Accent.TButton", background="#244b60", foreground="#f0fbff", font=("Segoe UI",10,"bold"), padding=(14,8))
        style.map("Accent.TButton", background=[("active", "#31647e")])
        style.configure("TEntry", fieldbackground=field, foreground=fg, insertcolor=fg)
        style.configure("TCombobox", fieldbackground=field, background=field, foreground=fg, arrowcolor=fg)
        style.configure("TCheckbutton", background=panel, foreground=fg)
        style.configure("TLabelframe", background=panel, foreground=fg, bordercolor="#293948")
        style.configure("TLabelframe.Label", background=panel, foreground=accent, font=("Segoe UI",10,"bold"))
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", background="#18222d", foreground=muted, padding=(13,8))
        style.map("TNotebook.Tab", background=[("selected", "#233240")], foreground=[("selected", fg)])
        style.configure("Treeview", background="#141c25", fieldbackground="#141c25", foreground=fg, rowheight=25)
        style.configure("Treeview.Heading", background="#22303d", foreground=fg)
        style.map("Treeview", background=[("selected", "#2b4c60")])
        style.configure("TProgressbar", troughcolor="#1d2934", background="#7da9bb")

    def _section(self, parent, title: str) -> ttk.LabelFrame:
        f = ttk.LabelFrame(parent, text=title)
        f.pack(fill="x", padx=14, pady=(0,10))
        return f

    def _build_ui(self) -> None:
        head = ttk.Frame(self)
        head.pack(fill="x", padx=16, pady=(12,7))
        ttk.Label(head, text="PIXELFENDA", font=("Segoe UI", 23, "bold")).pack(side="left")
        ttk.Label(head, text="v0.4.0 · TEMPORAL DIRECTOR", style="Muted.TLabel").pack(side="left", padx=12, pady=(8,0))
        pbar = ttk.Frame(head); pbar.pack(side="right")
        ttk.Button(pbar, text="Abrir projeto", command=self._load_project).pack(side="left", padx=3)
        ttk.Button(pbar, text="Salvar projeto", command=self._save_project).pack(side="left", padx=3)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=4)
        self.tab_project = ScrollableFrame(self.notebook)
        self.tab_layers = ttk.Frame(self.notebook)
        self.tab_auto = ScrollableFrame(self.notebook)
        self.tab_temporal = ScrollableFrame(self.notebook)
        self.tab_audio = ScrollableFrame(self.notebook)
        self.tab_queue = ttk.Frame(self.notebook)
        self.tab_preview = ttk.Frame(self.notebook)
        for tab, label in [
            (self.tab_project,"Projeto"),(self.tab_layers,"Camadas"),(self.tab_auto,"Automação"),
            (self.tab_temporal,"Tempo & Máscara"),(self.tab_audio,"Áudio / Stems"),(self.tab_queue,"Fila"),(self.tab_preview,"Prévia"),
        ]:
            self.notebook.add(tab, text=label)
        self._build_project_tab(self.tab_project.inner)
        self._build_layers_tab(self.tab_layers)
        self._build_auto_tab(self.tab_auto.inner)
        self._build_temporal_tab(self.tab_temporal.inner)
        self._build_audio_tab(self.tab_audio.inner)
        self._build_queue_tab(self.tab_queue)
        self._build_preview_tab(self.tab_preview)

        foot = ttk.Frame(self)
        foot.pack(fill="x", padx=12, pady=(5,10))
        self.progress = ttk.Progressbar(foot, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0,10))
        ttk.Label(foot, textvariable=self.status_var, width=48).pack(side="left", padx=(0,10))
        self.render_btn = ttk.Button(foot, text="GERAR VÍDEO", style="Accent.TButton", command=self._start_render)
        self.render_btn.pack(side="right")

    def _build_project_tab(self, root) -> None:
        files = self._section(root, "1 · Arquivos")
        for label, var, cmd in [
            ("Vídeo", self.input_var, self._choose_input), ("Saída", self.output_var, self._choose_output),
        ]:
            row=ttk.Frame(files,style="Panel.TFrame"); row.pack(fill="x",padx=10,pady=6)
            ttk.Label(row,text=label,width=9,style="Panel.TLabel").pack(side="left")
            ttk.Entry(row,textvariable=var).pack(side="left",fill="x",expand=True)
            ttk.Button(row,text="Selecionar…",command=cmd).pack(side="left",padx=(8,0))
        fmt = self._section(root, "2 · Formato e renderização")
        g=ttk.Frame(fmt,style="Panel.TFrame"); g.pack(fill="x",padx=10,pady=8)
        for c in (1,3): g.columnconfigure(c,weight=1)
        ttk.Label(g,text="Resolução",style="Panel.TLabel").grid(row=0,column=0,sticky="w",pady=5)
        rc=ttk.Combobox(g,textvariable=self.res_var,state="readonly",values=[p.label for p in RESOLUTION_PRESETS]); rc.grid(row=0,column=1,sticky="ew",padx=(7,14)); rc.bind("<<ComboboxSelected>>",lambda _e:self._update_states())
        custom=ttk.Frame(g,style="Panel.TFrame"); custom.grid(row=0,column=2,columnspan=2,sticky="e")
        ttk.Label(custom,text="W",style="Panel.TLabel").pack(side="left"); self.custom_w_entry=ttk.Entry(custom,textvariable=self.custom_w,width=7); self.custom_w_entry.pack(side="left",padx=(4,8))
        ttk.Label(custom,text="H",style="Panel.TLabel").pack(side="left"); self.custom_h_entry=ttk.Entry(custom,textvariable=self.custom_h,width=7); self.custom_h_entry.pack(side="left",padx=(4,0))
        ttk.Label(g,text="Enquadramento",style="Panel.TLabel").grid(row=1,column=0,sticky="w",pady=5)
        ttk.Combobox(g,textvariable=self.resize_var,state="readonly",values=list(RESIZE_MODES.values())).grid(row=1,column=1,sticky="ew",padx=(7,14))
        ttk.Label(g,text="Encoder",style="Panel.TLabel").grid(row=1,column=2,sticky="w",pady=5)
        ttk.Combobox(g,textvariable=self.encoder_var,state="readonly",values=list(ENCODER_MODES.values())).grid(row=1,column=3,sticky="ew",padx=(7,0))
        ttk.Label(g,text="Processamento",style="Panel.TLabel").grid(row=2,column=0,sticky="w",pady=5)
        ttk.Combobox(g,textvariable=self.gpu_var,state="readonly",values=list(GPU_MODES.values())).grid(row=2,column=1,sticky="ew",padx=(7,14))
        ttk.Label(g,text="Seed",style="Panel.TLabel").grid(row=2,column=2,sticky="w",pady=5)
        ttk.Entry(g,textvariable=self.seed_var).grid(row=2,column=3,sticky="ew",padx=(7,0))
        info=self._section(root,"3 · Arquitetura v0.4")
        ttk.Label(info,text="A pilha da v0.3 foi preservada. Na v0.4 cada camada também possui janela temporal, keyframes, fades, máscara espacial e tracking opcional.\nVRAM 1024×512, shaders OpenGL/RTX, filtros, LUTs .cube, scene automation e beat-sync coexistem no mesmo projeto.",style="Panel.TLabel",wraplength=980,justify="left").pack(anchor="w",padx=10,pady=10)

    def _build_layers_tab(self, root) -> None:
        top=ttk.Frame(root); top.pack(fill="x",padx=10,pady=9)
        ttk.Button(top,text="+ Efeito",command=lambda:self._add_layer("effect")).pack(side="left",padx=3)
        ttk.Button(top,text="+ Filtro",command=lambda:self._add_layer("filter")).pack(side="left",padx=3)
        ttk.Button(top,text="+ LUT .cube",command=lambda:self._add_layer("lut")).pack(side="left",padx=3)
        ttk.Button(top,text="Duplicar",command=self._duplicate_layer).pack(side="left",padx=(15,3))
        ttk.Button(top,text="Remover",command=self._remove_layer).pack(side="left",padx=3)
        ttk.Button(top,text="↑",width=3,command=lambda:self._move_layer(-1)).pack(side="left",padx=(15,2))
        ttk.Button(top,text="↓",width=3,command=lambda:self._move_layer(1)).pack(side="left",padx=2)
        cols=("on","type","name","intensity","opacity","blend","mod")
        self.layer_tree=ttk.Treeview(root,columns=cols,show="headings",height=10,selectmode="browse")
        widths={"on":45,"type":70,"name":320,"intensity":75,"opacity":75,"blend":90,"mod":150}
        labels={"on":"ON","type":"Tipo","name":"Preset/LUT","intensity":"Int.","opacity":"Mix","blend":"Blend","mod":"Modulação"}
        for c in cols:
            self.layer_tree.heading(c,text=labels[c]); self.layer_tree.column(c,width=widths[c],anchor="center" if c not in {"name","mod"} else "w")
        self.layer_tree.pack(fill="x",padx=10,pady=(0,7))
        self.layer_tree.bind("<<TreeviewSelect>>",self._on_layer_select)
        editor=ttk.LabelFrame(root,text="Editor da camada selecionada"); editor.pack(fill="both",expand=True,padx=10,pady=(0,10))
        g=ttk.Frame(editor,style="Panel.TFrame"); g.pack(fill="x",padx=10,pady=8)
        for c in (1,3): g.columnconfigure(c,weight=1)
        ttk.Checkbutton(g,text="Ativa",variable=self.le_enabled).grid(row=0,column=0,sticky="w")
        ttk.Label(g,text="Tipo",style="Panel.TLabel").grid(row=0,column=2,sticky="w",padx=(14,0))
        self.kind_combo=ttk.Combobox(g,textvariable=self.le_kind,state="readonly",values=["effect","filter","lut"]); self.kind_combo.grid(row=0,column=3,sticky="ew",padx=(7,0)); self.kind_combo.bind("<<ComboboxSelected>>",lambda _e:self._layer_editor_kind())
        ttk.Label(g,text="Preset",style="Panel.TLabel").grid(row=1,column=0,sticky="w",pady=5)
        self.preset_combo=ttk.Combobox(g,textvariable=self.le_preset,state="readonly"); self.preset_combo.grid(row=1,column=1,columnspan=3,sticky="ew",padx=(7,0),pady=5)
        ttk.Label(g,text="LUT",style="Panel.TLabel").grid(row=2,column=0,sticky="w",pady=5)
        self.lut_entry=ttk.Entry(g,textvariable=self.le_lut); self.lut_entry.grid(row=2,column=1,columnspan=2,sticky="ew",padx=(7,7),pady=5)
        self.lut_btn=ttk.Button(g,text="Abrir .cube",command=self._choose_lut); self.lut_btn.grid(row=2,column=3,sticky="ew",pady=5)
        ttk.Label(g,text="Intensidade",style="Panel.TLabel").grid(row=3,column=0,sticky="w",pady=5)
        ttk.Scale(g,from_=0,to=100,variable=self.le_intensity).grid(row=3,column=1,sticky="ew",padx=(7,7)); ttk.Label(g,textvariable=self.le_intensity,style="Panel.TLabel",width=6).grid(row=3,column=2,sticky="w")
        ttk.Label(g,text="Opacidade/Mix",style="Panel.TLabel").grid(row=4,column=0,sticky="w",pady=5)
        ttk.Scale(g,from_=0,to=100,variable=self.le_opacity).grid(row=4,column=1,sticky="ew",padx=(7,7)); ttk.Label(g,textvariable=self.le_opacity,style="Panel.TLabel",width=6).grid(row=4,column=2,sticky="w")
        ttk.Label(g,text="Blend",style="Panel.TLabel").grid(row=5,column=0,sticky="w",pady=5)
        ttk.Combobox(g,textvariable=self.le_blend,state="readonly",values=list(BLEND_MODES.values())).grid(row=5,column=1,sticky="ew",padx=(7,14))
        ttk.Label(g,text="Modulação",style="Panel.TLabel").grid(row=5,column=2,sticky="w")
        ttk.Combobox(g,textvariable=self.le_mod,state="readonly",values=list(MOD_SOURCES.values())).grid(row=5,column=3,sticky="ew",padx=(7,0))
        ttk.Label(g,text="Força modulação",style="Panel.TLabel").grid(row=6,column=0,sticky="w",pady=5)
        ttk.Scale(g,from_=0,to=100,variable=self.le_mod_amount).grid(row=6,column=1,sticky="ew",padx=(7,7)); ttk.Label(g,textvariable=self.le_mod_amount,style="Panel.TLabel",width=6).grid(row=6,column=2,sticky="w")
        ttk.Checkbutton(g,text="Resetar memória desta camada em cortes de cena",variable=self.le_scene_reset).grid(row=7,column=0,columnspan=2,sticky="w",pady=5)
        ttk.Label(g,text="Nome opcional",style="Panel.TLabel").grid(row=7,column=2,sticky="w")
        ttk.Entry(g,textvariable=self.le_name).grid(row=7,column=3,sticky="ew",padx=(7,0))
        ttk.Button(g,text="APLICAR ALTERAÇÕES",style="Accent.TButton",command=self._apply_layer_editor).grid(row=8,column=0,columnspan=4,sticky="ew",pady=(10,2))
        self._layer_editor_kind()

    def _build_auto_tab(self, root) -> None:
        r=self._section(root,"1 · Reatividade global")
        g=ttk.Frame(r,style="Panel.TFrame"); g.pack(fill="x",padx=10,pady=10); g.columnconfigure(1,weight=1)
        ttk.Label(g,text="Análise global",style="Panel.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Combobox(g,textvariable=self.reactive_var,state="readonly",values=list(REACTIVE_MODES.values())).grid(row=0,column=1,sticky="ew",padx=(10,0))
        ttk.Label(g,text="Mesmo com 'Livre', uma camada que use Beat/Bass/Motion ativa automaticamente a análise necessária.",style="Panel.TLabel",wraplength=900).grid(row=1,column=0,columnspan=2,sticky="w",pady=(7,0))
        s=self._section(root,"2 · Automação por cena")
        q=ttk.Frame(s,style="Panel.TFrame"); q.pack(fill="x",padx=10,pady=10); q.columnconfigure(1,weight=1)
        ttk.Label(q,text="Modo",style="Panel.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Combobox(q,textvariable=self.scene_mode_var,state="readonly",values=list(SCENE_MODES.values())).grid(row=0,column=1,sticky="ew",padx=(10,0))
        ttk.Label(q,text="Sensibilidade",style="Panel.TLabel").grid(row=1,column=0,sticky="w",pady=7)
        ttk.Scale(q,from_=7,to=55,variable=self.scene_threshold_var).grid(row=1,column=1,sticky="ew",padx=(10,10)); ttk.Label(q,textvariable=self.scene_threshold_var,style="Panel.TLabel",width=6).grid(row=1,column=2)
        ttk.Label(q,text="Auto Scene Mutator mantém a ordem das camadas, mas cria uma nova variação determinística de intensidade a cada corte. 'Reset' limpa VRAM/feedback temporal.",style="Panel.TLabel",wraplength=900).grid(row=2,column=0,columnspan=3,sticky="w")
        btn=ttk.Frame(s,style="Panel.TFrame"); btn.pack(fill="x",padx=10,pady=(0,8))
        ttk.Button(btn,text="Analisar cortes deste vídeo",command=self._analyze_scenes).pack(side="left")
        self.scene_summary=tk.Text(s,height=10,bg="#111923",fg="#c9d7e3",insertbackground="#c9d7e3",relief="flat")
        self.scene_summary.pack(fill="x",padx=10,pady=(0,10))

    def _build_temporal_tab(self, root) -> None:
        title=self._section(root,"1 · Camada selecionada / janela temporal")
        ttk.Label(title,textvariable=self.tm_layer_name,style="Panel.TLabel",font=("Segoe UI",11,"bold")).pack(anchor="w",padx=10,pady=(9,3))
        g=ttk.Frame(title,style="Panel.TFrame"); g.pack(fill="x",padx=10,pady=(2,10))
        for c in (1,3): g.columnconfigure(c,weight=1)
        ttk.Label(g,text="Início (s)",style="Panel.TLabel").grid(row=0,column=0,sticky="w",pady=4); ttk.Entry(g,textvariable=self.tm_start).grid(row=0,column=1,sticky="ew",padx=(7,14))
        ttk.Label(g,text="Fim (s; -1 = final)",style="Panel.TLabel").grid(row=0,column=2,sticky="w",pady=4); ttk.Entry(g,textvariable=self.tm_end).grid(row=0,column=3,sticky="ew",padx=(7,0))
        ttk.Label(g,text="Fade in (s)",style="Panel.TLabel").grid(row=1,column=0,sticky="w",pady=4); ttk.Entry(g,textvariable=self.tm_fade_in).grid(row=1,column=1,sticky="ew",padx=(7,14))
        ttk.Label(g,text="Fade out (s)",style="Panel.TLabel").grid(row=1,column=2,sticky="w",pady=4); ttk.Entry(g,textvariable=self.tm_fade_out).grid(row=1,column=3,sticky="ew",padx=(7,0))
        ttk.Label(g,text="Interpolação",style="Panel.TLabel").grid(row=2,column=0,sticky="w",pady=4); ttk.Combobox(g,textvariable=self.tm_ease,state="readonly",values=list(EASING_MODES.values())).grid(row=2,column=1,sticky="ew",padx=(7,14))
        ttk.Button(g,text="APLICAR TEMPO + MÁSCARA",style="Accent.TButton",command=self._apply_temporal_editor).grid(row=2,column=2,columnspan=2,sticky="ew",padx=(7,0),pady=(5,2))

        k=self._section(root,"2 · Keyframes — intensidade / opacidade / modulação")
        self.keyframe_tree=ttk.Treeview(k,columns=("time","intensity","opacity","mod"),show="headings",height=8)
        for col,label,width in (("time","Tempo (s)",120),("intensity","Intensidade",130),("opacity","Opacidade",130),("mod","Modulação",130)):
            self.keyframe_tree.heading(col,text=label); self.keyframe_tree.column(col,width=width,anchor="center")
        self.keyframe_tree.pack(fill="x",padx=10,pady=(8,5)); self.keyframe_tree.bind("<<TreeviewSelect>>",self._on_keyframe_select)
        row=ttk.Frame(k,style="Panel.TFrame"); row.pack(fill="x",padx=10,pady=(2,6)); row.columnconfigure(1,weight=1)
        ttk.Label(row,text="Tempo (s)",style="Panel.TLabel").grid(row=0,column=0,sticky="w"); ttk.Entry(row,textvariable=self.kf_time,width=10).grid(row=0,column=1,sticky="w",padx=6)
        ttk.Label(row,text="Int.%",style="Panel.TLabel").grid(row=0,column=2); ttk.Scale(row,from_=0,to=100,variable=self.kf_intensity).grid(row=0,column=3,sticky="ew",padx=5)
        ttk.Label(row,text="Op.%",style="Panel.TLabel").grid(row=0,column=4); ttk.Scale(row,from_=0,to=100,variable=self.kf_opacity).grid(row=0,column=5,sticky="ew",padx=5)
        ttk.Label(row,text="Mod.%",style="Panel.TLabel").grid(row=0,column=6); ttk.Scale(row,from_=0,to=100,variable=self.kf_mod).grid(row=0,column=7,sticky="ew",padx=5)
        for c in (3,5,7): row.columnconfigure(c,weight=1)
        br=ttk.Frame(k,style="Panel.TFrame"); br.pack(fill="x",padx=10,pady=(0,9))
        ttk.Button(br,text="Adicionar / atualizar keyframe",command=self._add_keyframe).pack(side="left")
        ttk.Button(br,text="Remover selecionado",command=self._remove_keyframe).pack(side="left",padx=6)
        ttk.Button(br,text="Limpar keyframes",command=self._clear_keyframes).pack(side="left")

        m=self._section(root,"3 · Máscara espacial + tracking")
        q=ttk.Frame(m,style="Panel.TFrame"); q.pack(fill="x",padx=10,pady=9)
        for c in (1,3): q.columnconfigure(c,weight=1)
        ttk.Label(q,text="Máscara",style="Panel.TLabel").grid(row=0,column=0,sticky="w"); ttk.Combobox(q,textvariable=self.mask_kind_var,state="readonly",values=list(MASK_MODES.values())).grid(row=0,column=1,sticky="ew",padx=(7,14))
        ttk.Label(q,text="Ângulo",style="Panel.TLabel").grid(row=0,column=2,sticky="w"); ttk.Scale(q,from_=-180,to=180,variable=self.mask_angle_var).grid(row=0,column=3,sticky="ew",padx=(7,0))
        for r,(label,var) in enumerate((("Centro X %",self.mask_x_var),("Centro Y %",self.mask_y_var),("Largura %",self.mask_w_var),("Altura %",self.mask_h_var),("Feather %",self.mask_feather_var)),start=1):
            col=0 if r<=3 else 2; rr=r if r<=3 else r-3
            ttk.Label(q,text=label,style="Panel.TLabel").grid(row=rr,column=col,sticky="w",pady=4); ttk.Scale(q,from_=0 if "Centro" in label or "Feather" in label else 1,to=100,variable=var).grid(row=rr,column=col+1,sticky="ew",padx=(7,14 if col==0 else 0))
        ttk.Checkbutton(q,text="Inverter máscara",variable=self.mask_invert_var).grid(row=4,column=0,sticky="w",pady=5)
        ttk.Checkbutton(q,text="Rastrear centro por optical flow (retângulo/elipse)",variable=self.mask_track_var).grid(row=4,column=1,columnspan=2,sticky="w",pady=5)
        ttk.Scale(q,from_=0,to=100,variable=self.mask_track_strength_var).grid(row=4,column=3,sticky="ew",padx=(7,0))

        b=self._section(root,"4 · Beat Grid / sincronização musical")
        ttk.Label(b,textvariable=self.beat_status_var,style="Panel.TLabel",wraplength=980).pack(anchor="w",padx=10,pady=(9,4))
        rr=ttk.Frame(b,style="Panel.TFrame"); rr.pack(fill="x",padx=10,pady=5)
        ttk.Button(rr,text="Analisar grade de batidas",command=self._analyze_beats).pack(side="left")
        ttk.Label(rr,text="Pico %",style="Panel.TLabel").pack(side="left",padx=(18,4)); ttk.Scale(rr,from_=0,to=100,variable=self.beat_peak_var,length=180).pack(side="left")
        ttk.Label(rr,text="Decay (s)",style="Panel.TLabel").pack(side="left",padx=(18,4)); ttk.Entry(rr,textvariable=self.beat_decay_var,width=8).pack(side="left")
        ttk.Button(rr,text="Gerar pulsos nos keyframes",command=self._apply_beat_pulses).pack(side="left",padx=(18,0))
        ttk.Label(b,text="A grade usa os transientes já extraídos pelo motor FFT do PixelFenda e cria keyframes reproduzíveis; não exige API nem serviço online.",style="Panel.TLabel",wraplength=980).pack(anchor="w",padx=10,pady=(2,9))

    def _build_audio_tab(self, root) -> None:
        a=self._section(root,"1 · Saída de áudio")
        g=ttk.Frame(a,style="Panel.TFrame"); g.pack(fill="x",padx=10,pady=10); g.columnconfigure(1,weight=1)
        ttk.Label(g,text="Modo",style="Panel.TLabel").grid(row=0,column=0,sticky="w")
        ac=ttk.Combobox(g,textvariable=self.audio_mode_var,state="readonly",values=list(AUDIO_MODES.values())); ac.grid(row=0,column=1,columnspan=2,sticky="ew",padx=(8,0)); ac.bind("<<ComboboxSelected>>",lambda _e:self._update_states())
        ttk.Label(g,text="Nova música",style="Panel.TLabel").grid(row=1,column=0,sticky="w",pady=6)
        self.music_entry=ttk.Entry(g,textvariable=self.music_var); self.music_entry.grid(row=1,column=1,sticky="ew",padx=(8,7)); self.music_btn=ttk.Button(g,text="Abrir",command=self._choose_music); self.music_btn.grid(row=1,column=2)
        stems=self._section(root,"2 · Separação de voz/música — Demucs opcional")
        q=ttk.Frame(stems,style="Panel.TFrame"); q.pack(fill="x",padx=10,pady=9); q.columnconfigure(1,weight=1)
        ttk.Label(q,text="Voz",style="Panel.TLabel").grid(row=0,column=0,sticky="w"); ttk.Entry(q,textvariable=self.stem_vocals_var).grid(row=0,column=1,sticky="ew",padx=(8,0))
        ttk.Label(q,text="Instrumental",style="Panel.TLabel").grid(row=1,column=0,sticky="w",pady=6); ttk.Entry(q,textvariable=self.stem_inst_var).grid(row=1,column=1,sticky="ew",padx=(8,0))
        buttons=ttk.Frame(stems,style="Panel.TFrame"); buttons.pack(fill="x",padx=10,pady=(0,8))
        ttk.Button(buttons,text="Separar voz + instrumental",command=self._separate_stems).pack(side="left")
        ttk.Button(buttons,text="Verificar Demucs",command=self._check_demucs).pack(side="left",padx=7)
        ttk.Label(stems,text="O Demucs não faz parte das dependências básicas. A integração é local, sem API; se instalado com PyTorch/CUDA, pode usar a RTX 4060. A primeira execução baixa o modelo escolhido.",style="Panel.TLabel",wraplength=920).pack(anchor="w",padx=10,pady=(0,10))

    def _build_queue_tab(self, root) -> None:
        top=ttk.Frame(root); top.pack(fill="x",padx=10,pady=9)
        ttk.Button(top,text="Adicionar trabalho atual",command=self._queue_current).pack(side="left",padx=3)
        ttk.Button(top,text="Adicionar vários vídeos",command=self._queue_multiple).pack(side="left",padx=3)
        ttk.Button(top,text="Remover",command=self._queue_remove).pack(side="left",padx=(15,3))
        ttk.Button(top,text="Limpar",command=self._queue_clear).pack(side="left",padx=3)
        ttk.Button(top,text="RENDERIZAR FILA",style="Accent.TButton",command=self._start_queue).pack(side="right")
        d=ttk.Frame(root); d.pack(fill="x",padx=10,pady=(0,7))
        ttk.Label(d,text="Pasta de saída em lote").pack(side="left"); ttk.Entry(d,textvariable=self.queue_dir_var).pack(side="left",fill="x",expand=True,padx=8); ttk.Button(d,text="Escolher",command=self._choose_queue_dir).pack(side="left")
        self.queue_tree=ttk.Treeview(root,columns=("input","output"),show="headings",height=18)
        self.queue_tree.heading("input",text="Entrada"); self.queue_tree.heading("output",text="Saída")
        self.queue_tree.column("input",width=480); self.queue_tree.column("output",width=480)
        self.queue_tree.pack(fill="both",expand=True,padx=10,pady=(0,10))

    def _build_preview_tab(self, root) -> None:
        top=ttk.Frame(root); top.pack(fill="x",padx=10,pady=9)
        ttk.Button(top,text="Gerar comparação antes/depois",command=self._preview).pack(side="left")
        ttk.Label(top,text="Posição no vídeo").pack(side="left",padx=(18,5))
        ttk.Scale(top,from_=0,to=100,variable=self.preview_pos_var).pack(side="left",fill="x",expand=True)
        ttk.Label(top,textvariable=self.preview_pos_var,width=6).pack(side="left",padx=5)
        self.preview_label=ttk.Label(root,anchor="center")
        self.preview_label.pack(fill="both",expand=True,padx=10,pady=(0,10))

    # ------------------------------- files/settings -------------------------------
    def _choose_input(self):
        p=filedialog.askopenfilename(title="Selecione um vídeo",filetypes=[("Vídeos","*.mp4 *.mov *.mkv *.avi *.webm *.m4v"),("Todos","*.*")])
        if p:
            self.input_var.set(p); self.output_var.set(make_output_path(p,"v040"))
            if not self.queue_dir_var.get(): self.queue_dir_var.set(str(Path(p).parent))
    def _choose_output(self):
        p=filedialog.asksaveasfilename(title="Salvar vídeo",defaultextension=".mp4",filetypes=[("MP4","*.mp4")]);
        if p: self.output_var.set(p)
    def _choose_music(self):
        p=filedialog.askopenfilename(title="Selecione música/áudio",filetypes=[("Áudio","*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.mp4"),("Todos","*.*")]);
        if p: self.music_var.set(p)
    def _choose_lut(self):
        p=filedialog.askopenfilename(title="Selecione LUT .cube",filetypes=[("LUT Cube","*.cube"),("Todos","*.*")]);
        if p: self.le_lut.set(p)
    def _choose_queue_dir(self):
        p=filedialog.askdirectory(title="Pasta de saída da fila");
        if p: self.queue_dir_var.set(p)

    def _resolve_size(self):
        inp=self.input_var.get().strip()
        if not inp: raise ValueError("Selecione um vídeo de entrada.")
        p=RESOLUTION_BY_LABEL[self.res_var.get()]
        if p.key=="original":
            i=probe_video(inp); return i.width,i.height
        if p.key=="custom":
            w,h=int(self.custom_w.get()),int(self.custom_h.get())
            if w<64 or h<64: raise ValueError("A resolução personalizada deve ter pelo menos 64×64.")
            return w,h
        return int(p.width),int(p.height)

    def _update_states(self):
        custom=RESOLUTION_BY_LABEL[self.res_var.get()].key=="custom"
        for e in (self.custom_w_entry,self.custom_h_entry): e.configure(state="normal" if custom else "disabled")
        mode=AUDIO_BY_LABEL[self.audio_mode_var.get()]
        need_music=mode in {"replace","mix"}
        self.music_entry.configure(state="normal" if need_music else "disabled"); self.music_btn.configure(state="normal" if need_music else "disabled")

    # --------------------------------- layers ---------------------------------
    def _layer_label(self,spec:LayerSpec)->str:
        if spec.name: return spec.name
        if spec.kind=="effect": return EFFECT_PRESETS.get(spec.key,spec.key)
        if spec.kind=="filter": return FILTER_PRESETS.get(spec.key,spec.key)
        return Path(spec.lut_path or "LUT").name

    def _refresh_layers(self):
        if not hasattr(self,"layer_tree"): return
        for item in self.layer_tree.get_children(): self.layer_tree.delete(item)
        for i,s in enumerate(self.layers):
            self.layer_tree.insert("","end",iid=str(i),values=("✓" if s.enabled else "—",s.kind,self._layer_label(s),f"{s.intensity*100:.0f}",f"{s.opacity*100:.0f}",BLEND_MODES.get(s.blend,s.blend),MOD_SOURCES.get(s.mod_source,s.mod_source)))
        if self.layers:
            idx=min(self._selected_layer or 0,len(self.layers)-1); self._selected_layer=idx; self.layer_tree.selection_set(str(idx)); self._load_layer_editor(idx)

    def _add_layer(self,kind:str):
        if len(self.layers)>=12:
            messagebox.showwarning("PixelFenda","A interface limita a pilha a 12 camadas para manter projetos administráveis."); return
        if kind=="effect": s=LayerSpec(kind="effect",key="cyber_wire",intensity=.65)
        elif kind=="filter": s=LayerSpec(kind="filter",key="cinematic_teal_amber",intensity=.75)
        else:
            p=filedialog.askopenfilename(title="Selecione LUT .cube",filetypes=[("LUT Cube","*.cube")])
            if not p: return
            s=LayerSpec(kind="lut",key="custom_lut",lut_path=p,intensity=1.0)
        self.layers.append(s); self._selected_layer=len(self.layers)-1; self._refresh_layers()

    def _on_layer_select(self,_e=None):
        sel=self.layer_tree.selection()
        if not sel: return
        self._selected_layer=int(sel[0]); self._load_layer_editor(self._selected_layer)

    def _load_layer_editor(self,idx:int):
        s=self.layers[idx]
        self.le_enabled.set(s.enabled); self.le_kind.set(s.kind); self.le_intensity.set(s.intensity*100); self.le_opacity.set(s.opacity*100)
        self.le_blend.set(BLEND_MODES.get(s.blend,BLEND_MODES["normal"])); self.le_mod.set(MOD_SOURCES.get(s.mod_source,MOD_SOURCES["none"])); self.le_mod_amount.set(s.mod_amount*100); self.le_scene_reset.set(s.scene_reset); self.le_name.set(s.name or ""); self.le_lut.set(s.lut_path or "")
        if s.kind=="effect": self.le_preset.set(EFFECT_PRESETS.get(s.key,s.key))
        elif s.kind=="filter": self.le_preset.set(FILTER_PRESETS.get(s.key,s.key))
        else: self.le_preset.set("")
        self._layer_editor_kind()
        if hasattr(self, "keyframe_tree"):
            self._load_temporal_editor(idx)

    def _layer_editor_kind(self):
        kind=self.le_kind.get()
        if kind=="effect": vals=list(EFFECT_PRESETS.values()); state="readonly"; lut_state="disabled"
        elif kind=="filter": vals=[v for k,v in FILTER_PRESETS.items() if k!="none"]; state="readonly"; lut_state="disabled"
        else: vals=[]; state="disabled"; lut_state="normal"
        self.preset_combo.configure(values=vals,state=state); self.lut_entry.configure(state=lut_state); self.lut_btn.configure(state=lut_state)
        if vals and self.le_preset.get() not in vals: self.le_preset.set(vals[0])

    def _apply_layer_editor(self):
        if self._selected_layer is None or self._selected_layer>=len(self.layers): return
        kind=self.le_kind.get(); old=self.layers[self._selected_layer]
        if kind=="effect": key=EFFECT_BY_LABEL.get(self.le_preset.get(),"corrupted_memory"); lut=None
        elif kind=="filter": key=FILTER_BY_LABEL.get(self.le_preset.get(),"vintage_70"); lut=None
        else:
            lut=self.le_lut.get().strip() or None
            if not lut or not Path(lut).is_file(): messagebox.showerror("PixelFenda","Selecione um arquivo .cube válido."); return
            key="custom_lut"
        data=old.to_dict(); data.update(dict(kind=kind,key=key,intensity=self.le_intensity.get()/100,opacity=self.le_opacity.get()/100,blend=BLEND_BY_LABEL.get(self.le_blend.get(),"normal"),mod_source=MOD_BY_LABEL.get(self.le_mod.get(),"none"),mod_amount=self.le_mod_amount.get()/100,enabled=self.le_enabled.get(),scene_reset=self.le_scene_reset.get(),lut_path=lut,name=self.le_name.get().strip() or None,uid=old.uid))
        self.layers[self._selected_layer]=LayerSpec.from_dict(data)
        self._refresh_layers()

    def _duplicate_layer(self):
        if self._selected_layer is None or not self.layers:return
        s=LayerSpec.from_dict(self.layers[self._selected_layer].to_dict()); s.uid=LayerSpec().uid; self.layers.insert(self._selected_layer+1,s); self._selected_layer+=1; self._refresh_layers()
    def _remove_layer(self):
        if self._selected_layer is None or not self.layers:return
        del self.layers[self._selected_layer]; self._selected_layer=max(0,min(self._selected_layer,len(self.layers)-1)) if self.layers else None; self._refresh_layers()
    def _move_layer(self,d:int):
        if self._selected_layer is None:return
        j=self._selected_layer+d
        if j<0 or j>=len(self.layers):return
        self.layers[self._selected_layer],self.layers[j]=self.layers[j],self.layers[self._selected_layer]; self._selected_layer=j; self._refresh_layers()

    # -------------------------------- project --------------------------------
    def _snapshot_project(self)->ProjectDocument:
        res=RESOLUTION_BY_LABEL[self.res_var.get()]
        return ProjectDocument(name="Projeto PixelFenda",input_path=self.input_var.get().strip(),output_path=self.output_var.get().strip(),resolution=res.key,width=int(self.custom_w.get() or 1080),height=int(self.custom_h.get() or 1920),resize_mode=RESIZE_BY_LABEL[self.resize_var.get()],encoder_mode=ENCODER_BY_LABEL[self.encoder_var.get()],gpu_mode=GPU_BY_LABEL[self.gpu_var.get()],seed=int(self.seed_var.get()),reactive_mode=REACTIVE_BY_LABEL[self.reactive_var.get()],scene_mode=SCENE_BY_LABEL[self.scene_mode_var.get()],scene_threshold=self.scene_threshold_var.get()/100,audio_mode=AUDIO_BY_LABEL[self.audio_mode_var.get()],music_path=self.music_var.get().strip() or None,stem_vocals_path=self.stem_vocals_var.get().strip() or None,stem_instrumental_path=self.stem_inst_var.get().strip() or None,layers=[LayerSpec.from_dict(x.to_dict()) for x in self.layers])

    def _save_project(self):
        try: doc=self._snapshot_project()
        except Exception as exc: messagebox.showerror("PixelFenda",str(exc)); return
        p=filedialog.asksaveasfilename(title="Salvar projeto PixelFenda",defaultextension=".pixelfenda.json",filetypes=[("Projeto PixelFenda","*.pixelfenda.json"),("JSON","*.json")])
        if p: doc.save(p); self.status_var.set(f"Projeto salvo · {Path(p).name}")
    def _load_project(self):
        p=filedialog.askopenfilename(title="Abrir projeto PixelFenda",filetypes=[("Projeto PixelFenda","*.pixelfenda.json *.json")]);
        if not p:return
        try: self._apply_project(ProjectDocument.load(p)); self.status_var.set(f"Projeto carregado · {Path(p).name}")
        except Exception as exc: messagebox.showerror("PixelFenda",self._format_error(exc,"Abrir projeto"))
    def _apply_project(self,d:ProjectDocument):
        self.input_var.set(d.input_path); self.output_var.set(d.output_path); self.res_var.set(next((x.label for x in RESOLUTION_PRESETS if x.key==d.resolution),RESOLUTION_PRESETS[0].label)); self.custom_w.set(str(d.width)); self.custom_h.set(str(d.height)); self.resize_var.set(RESIZE_MODES.get(d.resize_mode,RESIZE_MODES["crop"])); self.encoder_var.set(ENCODER_MODES.get(d.encoder_mode,ENCODER_MODES["auto"])); self.gpu_var.set(GPU_MODES.get(d.gpu_mode,GPU_MODES["auto"])); self.seed_var.set(str(d.seed)); self.reactive_var.set(REACTIVE_MODES.get(d.reactive_mode,REACTIVE_MODES["none"])); self.scene_mode_var.set(SCENE_MODES.get(d.scene_mode,SCENE_MODES["off"])); self.scene_threshold_var.set(d.scene_threshold*100); self.audio_mode_var.set(AUDIO_MODES.get(d.audio_mode,AUDIO_MODES["original"])); self.music_var.set(d.music_path or ""); self.stem_vocals_var.set(d.stem_vocals_path or ""); self.stem_inst_var.set(d.stem_instrumental_path or ""); self.layers=d.layers or [LayerSpec()]; self._selected_layer=0; self._refresh_layers(); self._update_states()

    # ---------------------------- temporal / masks / beat ----------------------------
    def _load_temporal_editor(self,idx:int):
        if idx<0 or idx>=len(self.layers): return
        spec=self.layers[idx]; self.tm_layer_name.set(self._layer_label(spec))
        self.tm_start.set(f"{spec.start_s:.3f}"); self.tm_end.set(f"{spec.end_s:.3f}"); self.tm_fade_in.set(f"{spec.fade_in_s:.3f}"); self.tm_fade_out.set(f"{spec.fade_out_s:.3f}")
        self.tm_ease.set(EASING_MODES.get(spec.keyframe_ease,EASING_MODES["smooth"]))
        self.mask_kind_var.set(MASK_MODES.get(spec.mask_kind,MASK_MODES["full"])); self.mask_x_var.set(spec.mask_x*100); self.mask_y_var.set(spec.mask_y*100); self.mask_w_var.set(spec.mask_w*100); self.mask_h_var.set(spec.mask_h*100); self.mask_feather_var.set(spec.mask_feather*100); self.mask_angle_var.set(spec.mask_angle); self.mask_invert_var.set(spec.mask_invert); self.mask_track_var.set(spec.mask_track); self.mask_track_strength_var.set(spec.mask_track_strength*100)
        self._refresh_keyframes()

    def _apply_temporal_editor(self):
        if self._selected_layer is None or self._selected_layer>=len(self.layers): return
        try:
            spec=self.layers[self._selected_layer]
            spec.start_s=max(0.0,float(self.tm_start.get())); spec.end_s=float(self.tm_end.get()); spec.fade_in_s=max(0.0,float(self.tm_fade_in.get())); spec.fade_out_s=max(0.0,float(self.tm_fade_out.get())); spec.keyframe_ease=EASING_BY_LABEL.get(self.tm_ease.get(),"smooth")
            spec.mask_kind=MASK_BY_LABEL.get(self.mask_kind_var.get(),"full"); spec.mask_x=self.mask_x_var.get()/100; spec.mask_y=self.mask_y_var.get()/100; spec.mask_w=max(.01,self.mask_w_var.get()/100); spec.mask_h=max(.01,self.mask_h_var.get()/100); spec.mask_feather=self.mask_feather_var.get()/100; spec.mask_angle=self.mask_angle_var.get(); spec.mask_invert=self.mask_invert_var.get(); spec.mask_track=self.mask_track_var.get(); spec.mask_track_strength=self.mask_track_strength_var.get()/100
            spec.normalized(); self._refresh_layers(); self.status_var.set("Tempo/máscara aplicados à camada.")
        except Exception as exc: messagebox.showerror("PixelFenda",self._format_error(exc,"Editor temporal"))

    def _refresh_keyframes(self):
        if not hasattr(self,"keyframe_tree"): return
        for x in self.keyframe_tree.get_children(): self.keyframe_tree.delete(x)
        if self._selected_layer is None or self._selected_layer>=len(self.layers): return
        for i,k in enumerate(self.layers[self._selected_layer].keyframes):
            self.keyframe_tree.insert("","end",iid=str(i),values=(f"{k.get('time',0):.3f}",f"{k.get('intensity',self.layers[self._selected_layer].intensity)*100:.1f}%",f"{k.get('opacity',self.layers[self._selected_layer].opacity)*100:.1f}%",f"{k.get('mod_amount',self.layers[self._selected_layer].mod_amount)*100:.1f}%"))

    def _on_keyframe_select(self,_e=None):
        sel=self.keyframe_tree.selection()
        if not sel or self._selected_layer is None: return
        k=self.layers[self._selected_layer].keyframes[int(sel[0])]
        self.kf_time.set(f"{k.get('time',0):.3f}"); self.kf_intensity.set(k.get('intensity',self.layers[self._selected_layer].intensity)*100); self.kf_opacity.set(k.get('opacity',self.layers[self._selected_layer].opacity)*100); self.kf_mod.set(k.get('mod_amount',self.layers[self._selected_layer].mod_amount)*100)

    def _add_keyframe(self):
        if self._selected_layer is None: return
        try: t=max(0.0,float(self.kf_time.get()))
        except ValueError: messagebox.showerror("PixelFenda","Tempo do keyframe inválido."); return
        spec=self.layers[self._selected_layer]; row={"time":t,"intensity":self.kf_intensity.get()/100,"opacity":self.kf_opacity.get()/100,"mod_amount":self.kf_mod.get()/100}
        spec.keyframes=[k for k in spec.keyframes if abs(float(k.get("time",0))-t)>1e-5]+[row]; spec.normalized(); self._refresh_keyframes()

    def _remove_keyframe(self):
        if self._selected_layer is None: return
        sel=self.keyframe_tree.selection()
        if not sel:return
        i=int(sel[0]); spec=self.layers[self._selected_layer]
        if 0<=i<len(spec.keyframes): del spec.keyframes[i]
        self._refresh_keyframes()

    def _clear_keyframes(self):
        if self._selected_layer is None:return
        self.layers[self._selected_layer].keyframes=[]; self._refresh_keyframes()

    def _analyze_beats(self):
        inp=self.input_var.get().strip()
        if not inp or not os.path.isfile(inp): messagebox.showerror("PixelFenda","Selecione um vídeo válido."); return
        if self.worker and self.worker.is_alive(): return
        try:
            info=probe_video(inp); music=self.music_var.get().strip(); source=music if music and os.path.isfile(music) else inp; loop=source!=inp
        except Exception as exc: messagebox.showerror("PixelFenda",str(exc)); return
        self.status_var.set("Analisando beat grid…")
        def prog(v,t): self.after(0,lambda:self._set_progress(v,t))
        def work():
            try:
                r=analyze_beats(source,info.fps,max(1,info.frames),loop=loop,progress=prog); self.after(0,lambda:self._beats_done(r,Path(source).name))
            except Exception as exc:
                detail=self._format_error(exc,"Beat grid"); self.after(0,lambda t=detail:self._failed(t))
        self.worker=threading.Thread(target=work,daemon=True); self.worker.start()

    def _beats_done(self,r:BeatAnalysis,name:str):
        self.beat_analysis=r; self.progress["value"]=100; self.beat_status_var.set(f"{name} · {len(r.beat_times)} batidas · BPM estimado {r.bpm:.1f} · duração {r.duration:.2f}s"); self.status_var.set("Beat grid concluído.")

    def _apply_beat_pulses(self):
        if self._selected_layer is None or self.beat_analysis is None:
            messagebox.showinfo("PixelFenda","Analise a grade de batidas primeiro."); return
        try: decay=max(.02,float(self.beat_decay_var.get()))
        except ValueError: messagebox.showerror("PixelFenda","Decay inválido."); return
        spec=self.layers[self._selected_layer]; spec.keyframes=make_beat_pulse_keyframes(self.beat_analysis.beat_times,base_intensity=spec.intensity,peak_intensity=self.beat_peak_var.get()/100,decay_s=decay,duration=self.beat_analysis.duration); spec.keyframe_ease="ease_out"; self.tm_ease.set(EASING_MODES["ease_out"]); self._refresh_keyframes(); self.status_var.set(f"Beat-sync criado · {len(spec.keyframes)} keyframes")

    # ------------------------------- scene/stems -------------------------------
    def _analyze_scenes(self):
        inp=self.input_var.get().strip()
        if not inp or not os.path.isfile(inp): messagebox.showerror("PixelFenda","Selecione um vídeo válido."); return
        if self.worker and self.worker.is_alive(): return
        threshold=self.scene_threshold_var.get()/100; self.status_var.set("Analisando cenas…")
        def prog(v,t): self.after(0,lambda:self._set_progress(v,t))
        def work():
            try:
                ev=analyze_scenes(inp,threshold,progress=prog)
                text=f"Cenas detectadas: {len(ev)}\n\n"+"\n".join(f"{i+1:03d} · {e.seconds:8.3f}s · score {e.score:.3f}" for i,e in enumerate(ev[:500]))
                self.after(0,lambda:self._scene_done(text))
            except Exception as exc:
                detail=self._format_error(exc,"Análise de cenas"); self.after(0,lambda t=detail:self._failed(t))
        self.worker=threading.Thread(target=work,daemon=True); self.worker.start()
    def _scene_done(self,text): self.progress["value"]=100; self.status_var.set("Análise de cenas concluída"); self.scene_summary.delete("1.0","end"); self.scene_summary.insert("1.0",text)
    def _check_demucs(self): messagebox.showinfo("PixelFenda", "Demucs detectado neste ambiente." if demucs_available() else "Demucs não detectado. Consulte README: instalação opcional de stems.")
    def _separate_stems(self):
        inp=self.input_var.get().strip()
        if not inp or not os.path.isfile(inp): messagebox.showerror("PixelFenda","Selecione um vídeo/áudio válido."); return
        if self.worker and self.worker.is_alive(): return
        outdir=str(Path(inp).parent/"pixelfenda_stems")
        def prog(v,t): self.after(0,lambda:self._set_progress(v,t))
        def work():
            try:
                r=separate_vocals(inp,outdir,progress=prog)
                self.after(0,lambda:self._stems_done(r))
            except Exception as exc:
                detail=self._format_error(exc,"Separação Demucs"); self.after(0,lambda t=detail:self._failed(t))
        self.worker=threading.Thread(target=work,daemon=True); self.worker.start(); self.status_var.set("Separando stems…")
    def _stems_done(self,r): self.stem_vocals_var.set(r["vocals"]); self.stem_inst_var.set(r["instrumental"]); self.progress["value"]=100; self.status_var.set("Stems concluídos"); messagebox.showinfo("PixelFenda",f"Stems gerados em:\n{r['folder']}")

    # -------------------------------- preview --------------------------------
    def _preview(self):
        try:
            inp=self.input_var.get().strip(); w,h=self._resolve_size(); cap=cv2.VideoCapture(inp)
            if not cap.isOpened(): raise RuntimeError("Não foi possível abrir o vídeo.")
            n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0); pos=self.preview_pos_var.get()/100
            if n: cap.set(cv2.CAP_PROP_POS_FRAMES,max(0,min(n-1,int((n-1)*pos))))
            ok,frame=cap.read(); cap.release()
            if not ok: raise RuntimeError("Não foi possível ler o quadro de prévia.")
            layers=[LayerSpec.from_dict(x.to_dict()) for x in self.layers]
            fitted=cv2.resize(frame,(w,h),interpolation=cv2.INTER_AREA) if frame.shape[1]!=w or frame.shape[0]!=h else frame.copy()
            info=probe_video(inp); preview_time=info.duration*pos if info.duration>0 else 0.0
            out,renderer,_meta=preview_layers(frame,w,h,layers,resize_mode=RESIZE_BY_LABEL[self.resize_var.get()],seed=int(self.seed_var.get()),gpu_mode=GPU_BY_LABEL[self.gpu_var.get()],scene_mode=SCENE_BY_LABEL[self.scene_mode_var.get()],scene_threshold=self.scene_threshold_var.get()/100,time_s=preview_time,duration=info.duration)
            # Build a side-by-side comparison with labels baked into the image.
            from .engine import fit_frame
            before=fit_frame(frame,w,h,RESIZE_BY_LABEL[self.resize_var.get()])
            max_h=560; scale=min(1.0,max_h/max(1,h)); dw=max(1,int(w*scale)); dh=max(1,int(h*scale))
            b=cv2.resize(before,(dw,dh),interpolation=cv2.INTER_AREA); a=cv2.resize(out,(dw,dh),interpolation=cv2.INTER_AREA)
            cv2.putText(b,"ANTES",(18,36),cv2.FONT_HERSHEY_SIMPLEX,0.8,(235,235,235),2,cv2.LINE_AA); cv2.putText(a,"DEPOIS",(18,36),cv2.FONT_HERSHEY_SIMPLEX,0.8,(235,235,235),2,cv2.LINE_AA)
            comp=cv2.hconcat([b,a]); rgb=cv2.cvtColor(comp,cv2.COLOR_BGR2RGB); im=Image.fromarray(rgb); im.thumbnail((1120,600)); self.preview_photo=ImageTk.PhotoImage(im); self.preview_label.configure(image=self.preview_photo); self.status_var.set(f"Prévia · {renderer} · {sum(x.enabled for x in layers)} camadas")
        except Exception as exc: messagebox.showerror("PixelFenda",self._format_error(exc,"Falha na prévia"))

    # --------------------------------- queue ---------------------------------
    def _queue_current(self):
        inp=self.input_var.get().strip(); out=self.output_var.get().strip()
        if not inp or not out: messagebox.showerror("PixelFenda","Defina entrada e saída primeiro."); return
        self.jobs.append(RenderJob(inp,out,Path(inp).name)); self._refresh_queue()
    def _queue_multiple(self):
        paths=filedialog.askopenfilenames(title="Adicionar vídeos",filetypes=[("Vídeos","*.mp4 *.mov *.mkv *.avi *.webm *.m4v")]);
        if not paths:return
        outdir=Path(self.queue_dir_var.get().strip() or Path(paths[0]).parent); outdir.mkdir(parents=True,exist_ok=True)
        for p in paths:
            q=Path(p); out=outdir/f"{q.stem}_pixelfenda_v040.mp4"; self.jobs.append(RenderJob(str(q),str(out),q.name))
        self._refresh_queue()
    def _refresh_queue(self):
        for x in self.queue_tree.get_children(): self.queue_tree.delete(x)
        for i,j in enumerate(self.jobs): self.queue_tree.insert("","end",iid=str(i),values=(j.input_path,j.output_path))
    def _queue_remove(self):
        sel=self.queue_tree.selection()
        if not sel:return
        for i in sorted((int(x) for x in sel),reverse=True): del self.jobs[i]
        self._refresh_queue()
    def _queue_clear(self): self.jobs.clear(); self._refresh_queue()
    def _start_queue(self):
        if not self.jobs: messagebox.showinfo("PixelFenda","A fila está vazia."); return
        if self.worker and self.worker.is_alive(): return
        try:
            doc=self._snapshot_project(); jobs=[RenderJob.from_dict(x.to_dict()) for x in self.jobs]
            if doc.audio_mode in {"vocals_only", "instrumental_only"}:
                raise ValueError("Modos de stem Demucs não são aplicados automaticamente à fila multi-vídeo. Use áudio original/silencioso/replace/mix ou renderize os stems individualmente.")
        except Exception as exc: messagebox.showerror("PixelFenda",str(exc)); return
        self.render_btn.configure(state="disabled"); self.progress["value"]=0
        def work():
            try:
                results=[]
                for idx,j in enumerate(jobs):
                    info=probe_video(j.input_path); w,h=self._size_for_doc(doc,j.input_path,info)
                    def prog(v,t,idx=idx): self.after(0,lambda:self._set_progress((idx+v)/len(jobs),f"Fila {idx+1}/{len(jobs)} · {t}"))
                    results.append(render_video_layers(j.input_path,j.output_path,w,h,doc.layers,resize_mode=doc.resize_mode,seed=doc.seed,reactive_mode=doc.reactive_mode,scene_mode=doc.scene_mode,scene_threshold=doc.scene_threshold,audio_mode=doc.audio_mode,music_path=doc.music_path,stem_vocals_path=doc.stem_vocals_path,stem_instrumental_path=doc.stem_instrumental_path,encoder_mode=doc.encoder_mode,gpu_mode=doc.gpu_mode,progress=prog))
                self.after(0,lambda:self._queue_done(results))
            except Exception as exc:
                detail=self._format_error(exc,"Render da fila"); self.after(0,lambda t=detail:self._failed(t))
        self.worker=threading.Thread(target=work,daemon=True); self.worker.start()
    def _queue_done(self,results): self.render_btn.configure(state="normal"); self.progress["value"]=100; self.status_var.set(f"Fila concluída · {len(results)} vídeos"); messagebox.showinfo("PixelFenda",f"Fila concluída: {len(results)} vídeos.")

    # -------------------------------- render --------------------------------
    def _size_for_doc(self,d:ProjectDocument,inp:str,info=None):
        p=next((x for x in RESOLUTION_PRESETS if x.key==d.resolution),RESOLUTION_PRESETS[0])
        if p.key=="original": info=info or probe_video(inp); return info.width,info.height
        if p.key=="custom": return d.width,d.height
        return int(p.width),int(p.height)
    def _start_render(self):
        if self.worker and self.worker.is_alive(): return
        try:
            doc=self._snapshot_project(); inp=doc.input_path; out=doc.output_path
            if not inp or not os.path.isfile(inp): raise ValueError("Selecione um arquivo de vídeo válido.")
            if not out: raise ValueError("Informe o arquivo de saída.")
            w,h=self._size_for_doc(doc,inp)
            if doc.audio_mode in {"replace","mix"} and (not doc.music_path or not os.path.isfile(doc.music_path)): raise ValueError("Selecione uma música/áudio válida.")
            if doc.audio_mode=="vocals_only" and (not doc.stem_vocals_path or not os.path.isfile(doc.stem_vocals_path)): raise ValueError("Gere/selecione o stem de voz primeiro.")
            if doc.audio_mode=="instrumental_only" and (not doc.stem_instrumental_path or not os.path.isfile(doc.stem_instrumental_path)): raise ValueError("Gere/selecione o stem instrumental primeiro.")
        except Exception as exc: messagebox.showerror("PixelFenda",self._format_error(exc,"Validação antes do render")); return
        self.render_btn.configure(state="disabled"); self.progress["value"]=0; self.status_var.set("Iniciando render por camadas…")
        def prog(v,t): self.after(0,lambda:self._set_progress(v,t))
        def work():
            try:
                r=render_video_layers(inp,out,w,h,doc.layers,resize_mode=doc.resize_mode,seed=doc.seed,reactive_mode=doc.reactive_mode,scene_mode=doc.scene_mode,scene_threshold=doc.scene_threshold,audio_mode=doc.audio_mode,music_path=doc.music_path,stem_vocals_path=doc.stem_vocals_path,stem_instrumental_path=doc.stem_instrumental_path,encoder_mode=doc.encoder_mode,gpu_mode=doc.gpu_mode,progress=prog)
                self.after(0,lambda:self._done(r))
            except Exception as exc:
                detail=self._format_error(exc,"Falha durante a renderização"); self.after(0,lambda t=detail:self._failed(t))
        self.worker=threading.Thread(target=work,daemon=True); self.worker.start()

    def _format_error(self,exc:BaseException,context:str)->str:
        msg=str(exc).strip() or repr(exc); detail=f"{type(exc).__name__}: {msg}"
        try:
            log=Path(__file__).resolve().parent.parent/"pixelfenda_error.log"; stamp=datetime.now().isoformat(timespec="seconds"); trace="".join(traceback.format_exception(type(exc),exc,exc.__traceback__)); log.open("a",encoding="utf-8").write(f"\n[{stamp}] {context}\n{trace}\n")
        except Exception: pass
        return detail
    def _set_progress(self,v,t): self.progress["value"]=max(0,min(100,v*100)); self.status_var.set(t)
    def _done(self,r): self.render_btn.configure(state="normal"); self.progress["value"]=100; self.status_var.set(f"Concluído · {r['encoder']} · {r['gpu_renderer']} · {r['active_layers']} camadas"); messagebox.showinfo("PixelFenda",f"Vídeo gerado com sucesso:\n{r['output']}")
    def _failed(self,t): self.render_btn.configure(state="normal"); self.status_var.set("Falha."); messagebox.showerror("PixelFenda",t)


def run_gui() -> None:
    PixelFendaApp().mainloop()
