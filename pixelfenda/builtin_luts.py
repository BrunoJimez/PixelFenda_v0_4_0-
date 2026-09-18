from __future__ import annotations

import base64
import zlib
from pathlib import Path

from ._lutdata_amber import DATA as AMBER
from ._lutdata_cobalt import DATA as COBALT
from ._lutdata_chrome import DATA as CHROME

_BUILTINS = {
    "PixelFenda_AmberCrypt.cube": AMBER,
    "PixelFenda_CobaltNoir.cube": COBALT,
    "PixelFenda_ChromeIce.cube": CHROME,
}

def ensure_builtin_lut(path: str | Path) -> Path:
    p = Path(path)
    if p.exists():
        return p
    chunks = _BUILTINS.get(p.name)
    if chunks is None:
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(chunks).encode("ascii")
    p.write_bytes(zlib.decompress(base64.b64decode(payload)))
    return p

def ensure_all_builtin_luts(directory: str | Path) -> list[Path]:
    d = Path(directory)
    return [ensure_builtin_lut(d / name) for name in sorted(_BUILTINS)]
