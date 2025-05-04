"""
stl_to_goo_cli.py  (single‑file slicer)
======================================
A *streaming* STL → Elegoo **.goo** converter in ~250 lines of pure
Python.  Each layer is rasterised, run‑length‑encoded, and flushed
directly to disk, so RAM stays flat even with 12K × 5K plates.

Quick start
-----------
```bash
pip install "trimesh>=4" pillow shapely typer rich tqdm numpy
python stl_to_goo_cli.py model.stl -o model.goo
```

Key features
------------
* Works on **huge** displays (default 11 520 × 5120 for Saturn 4 Ultra).
* Streams layers — no giant numpy stack, no MemoryError.
* Generates valid headers for modern Elegoo machines (Mars 4, Saturn 4).
* Zero supports / anti‑alias for now → focus is minimal usable core.

Have fun & resin responsibly.  PRs to extend the header or add fancy
features are welcome! 🖖
"""

from __future__ import annotations
import struct
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

import typer
from PIL import Image, ImageDraw
from rich.console import Console
from tqdm import tqdm
import trimesh
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

app = typer.Typer(add_completion=False)
console = Console()

# ──────────────────────────── .goo constants ────────────────────────────
MAGIC = b"\x07\x00\x00\x00DLP\x00"
DELIM = b"\x0D\x0A"
ENDING = b"\x00\x00\x00\x07\x00\x00\x00DLP\x00"

# ───────────────────────── header helper ──────────────────────────


@dataclass
class GooHeader:
    layers: int
    x_px: int
    y_px: int
    x_mm: float
    y_mm: float
    z_mm: float
    layer_h: float
    exp: float
    bottom_exp: float = 30.0
    bottom_layers: int = 3

    def pack(self, small_prev: bytes, big_prev: bytes) -> bytearray:
        def s(txt: str, n: int) -> bytes:
            return txt.encode("ascii", "ignore").ljust(n, b"\x00")[:n]

        out = bytearray()
        out += s("EGOO", 4) + MAGIC
        out += s("py‑mslicer", 0x20) + s("0.3.0", 0x18)
        out += s(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0x18)
        out += s("Elegoo", 0x20) + s("Saturn 4 Ultra", 0x20) + \
            s("Std 0.05 mm", 0x20)
        out += struct.pack(">HHH", 1, 1, 0)          # antialias, grey, blur
        out += small_prev + DELIM + big_prev + DELIM

        # pack core numeric block ---------------------
        core_fmt = (
            ">IHH??"        # layers, x_px, y_px, mirror flags
            "fff"           # bed size (x_mm, y_mm, z_mm)
            "fff"           # layer_h, exp, exposure delay
            "ffffff"        # six motion zeros
            "fI"            # bottom_exp, bottom_layers
            "ff"            # bottom lift dist/speed
            "ff"            # lift dist/speed
            "ff"            # bottom retract dist/speed
            "ff"            # retract dist/speed
            "ff"            # second bottom lift dist/speed
            "ff"            # second lift dist/speed
            "ff"            # second bottom retract dist/speed
            "ff"            # second retract dist/speed
            "BB"            # light PWM
            "?I"            # per-layer flag, print time
            "fff"           # volume, weight, price
        )
        args = [
            self.layers,
            self.x_px, self.y_px,
            False, False,
            self.x_mm, self.y_mm, self.z_mm,
            self.layer_h, self.exp, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            self.bottom_exp, self.bottom_layers,
            5.0, 65.0,
            5.0, 65.0,
            5.0, 150.0,
            5.0, 150.0,
            0.0, 0.0,
            0.0, 0.0,
            0.0, 0.0,
            0.0, 0.0,
            255, 255,
            False, int(self.layers * (self.exp + 0.5)),
            0.0, 0.0, 0.0,
        ]
        core = struct.pack(core_fmt, *args)
        out += core
        # end core block
        out += s("USD", 8)truct.pack(">H", l)+bytes([v])
        i += l
    return bytes(out)

# ───────────────────────── raster helper ──────────────────────────


def raster(section: trimesh.Path3D | None, x_px: int, y_px: int, x_mm: float, y_mm: float) -> bytes:
    if not section:
        return bytes(x_px*y_px)
    planar = section.to_2D() if hasattr(
        section, "to_2D") else section.to_planar()[0]
    polys = planar.polygons_full
    if not polys:
        return bytes(x_px*y_px)
    union = unary_union(polys)
    img = Image.new("1", (x_px, y_px), 0)
    draw = ImageDraw.Draw(img)
    sx, sy = x_px/x_mm, y_px/y_mm
    rings = ([union.exterior.coords] if isinstance(union, Polygon)
             else [g.exterior.coords for g in union.geoms])
    for ring in rings:
        pts = [(int((x+x_mm/2)*sx), int((y_mm/2-y)*sy)) for x, y in ring]
        if len(pts) >= 3:
            draw.polygon(pts, fill=1)
    return img.tobytes()

# ───────────────────────── CLI main ──────────────────────────


@app.command()
def convert(
    stl: Path = typer.Argument(..., help="Input STL"),
    output: Path = typer.Option("out.goo", "-o", "--output"),
    x_res: int = 11520, y_res: int = 5120,
    x_mm: float = 218.88, y_mm: float = 122.904,
    layer_h: float = 0.05, exp: float = 3.0,
):
    console.print(f"[bold]Mesh:[/] {stl}")
    mesh = trimesh.load_mesh(stl, force="mesh")
    layers = int((mesh.bounds[1][2]/layer_h)+0.9999)
    console.print(f"[bold]Layers:[/] {layers}")

    hdr = GooHeader(layers, x_res, y_res, x_mm, y_mm, 220.0, layer_h, exp).pack(
        bytes(116*116*2), bytes(290*290*2)
    )
    with open(output, "wb") as fh:
        fh.write(hdr)
        for i in tqdm(range(layers), desc="slicing", unit="lyr"):
            z = i*layer_h
            sec = mesh.section([0, 0, z], [0, 0, 1])
            fh.write(rle(raster(sec, x_res, y_res, x_mm, y_mm)))
        fh.write(ENDING)
    console.print(f"[green]✔ written:[/] {output}")


if __name__ == "__main__":
    app()
