from __future__ import annotations

import struct
import io
import enum
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Iterator, List, Tuple

__all__ = [
    "Header",
    "LayerContent",
    "GooFile",
    "read_goo",
]

_BE16 = ">H"
_BE32 = ">I"
_BEF32 = ">f"

MAGIC = b"\x07\x00\x00\x00DLP\x00"
DELIM = b"\x0D\x0A"
ENDING = b"\x00\x00\x00\x07\x00\x00\x00DLP\x00"


def _read_str(b: BinaryIO, n: int) -> str:
    raw = b.read(n)
    return raw.rstrip(b"\x00").decode("ascii", "ignore")


def _read(fmt: str, fh: BinaryIO):
    size = struct.calcsize(fmt)
    return struct.unpack(fmt, fh.read(size))


class ExposureDelay(enum.IntEnum):
    TURN_OFF = 0
    STATIC = 1


@dataclass
class Header:
    version: str
    software_info: str
    software_version: str
    file_time: datetime
    printer_name: str
    printer_type: str
    profile_name: str
    anti_aliasing: int
    grey_level: int
    blur_level: int
    small_preview: bytes  # raw RGB565 data
    big_preview: bytes    # raw RGB565 data
    layer_count: int
    x_res: int
    y_res: int
    x_mirror: bool
    y_mirror: bool
    x_size: float
    y_size: float
    z_size: float
    layer_thickness: float
    exposure_time: float
    exposure_delay: ExposureDelay
    turn_off_time: float
    bottom_before_lift_time: float
    bottom_after_lift_time: float
    bottom_after_retract_time: float
    before_lift_time: float
    after_lift_time: float
    after_retract_time: float
    bottom_exposure_time: float
    bottom_layers: int
    bottom_lift_distance: float
    bottom_lift_speed: float
    lift_distance: float
    lift_speed: float
    bottom_retract_distance: float
    bottom_retract_speed: float
    retract_distance: float
    retract_speed: float
    bottom_second_lift_distance: float
    bottom_second_lift_speed: float
    second_lift_distance: float
    second_lift_speed: float
    bottom_second_retract_distance: float
    bottom_second_retract_speed: float
    second_retract_distance: float
    second_retract_speed: float
    bottom_light_pwm: int
    light_pwm: int
    per_layer_settings: bool
    printing_time: int
    total_volume: float
    total_weight: float
    total_price: float
    price_unit: str
    grey_scale_level: bool
    transition_layers: int

    @classmethod
    def parse(cls, fh: BinaryIO) -> "Header":
        version = _read_str(fh, 4)
        assert fh.read(8) == MAGIC, "magic mismatch"
        software_info = _read_str(fh, 0x20)
        software_version = _read_str(fh, 0x18)
        file_time_raw = _read_str(fh, 0x18)
        file_time = datetime.strptime(file_time_raw, "%Y-%m-%d %H:%M:%S") if file_time_raw else None
        printer_name = _read_str(fh, 0x20)
        printer_type = _read_str(fh, 0x20)
        profile_name = _read_str(fh, 0x20)
        anti_aliasing, grey_level, blur_level = _read(">HHH", fh)
        small_preview = fh.read(116 * 116 * 2)
        assert fh.read(2) == DELIM
        big_preview = fh.read(290 * 290 * 2)
        assert fh.read(2) == DELIM
        (
            layer_count,
            x_res,
            y_res,
            x_mirror,
            y_mirror,
            x_size,
            y_size,
            z_size,
            layer_thickness,
            exposure_time,
            exposure_delay_raw,
            turn_off_time,
            bottom_before_lift_time,
            bottom_after_lift_time,
            bottom_after_retract_time,
            before_lift_time,
            after_lift_time,
            after_retract_time,
            bottom_exposure_time,
            bottom_layers,
            bottom_lift_distance,
            bottom_lift_speed,
            lift_distance,
            lift_speed,
            bottom_retract_distance,
            bottom_retract_speed,
            retract_distance,
            retract_speed,
            bottom_second_lift_distance,
            bottom_second_lift_speed,
            second_lift_distance,
            second_lift_speed,
            bottom_second_retract_distance,
            bottom_second_retract_speed,
            second_retract_distance,
            second_retract_speed,
            bottom_light_pwm,
            light_pwm,
            per_layer_settings,
            printing_time,
            total_volume,
            total_weight,
            total_price,
        ) = _read(
            ">IHH??fff f f f f f f f f I f f f f f f f f f f f f f f f f f f f f ff?I f f f",
            fh,
        )
        price_unit = _read_str(fh, 8)
        _ = fh.read(4)  # skip offset of layer content (not needed here)
        grey_scale_level = bool(struct.unpack(">?", fh.read(1))[0])
        (transition_layers,) = _read(">H", fh)

        return cls(
            version,
            software_info,
            software_version,
            file_time,
            printer_name,
            printer_type,
            profile_name,
            anti_aliasing,
            grey_level,
            blur_level,
            small_preview,
            big_preview,
            layer_count,
            x_res,
            y_res,
            x_mirror,
            y_mirror,
            x_size,
            y_size,
            z_size,
            layer_thickness,
            exposure_time,
            ExposureDelay(exposure_delay_raw),
            turn_off_time,
            bottom_before_lift_time,
            bottom_after_lift_time,
            bottom_after_retract_time,
            before_lift_time,
            after_lift_time,
            after_retract_time,
            bottom_exposure_time,
            bottom_layers,
            bottom_lift_distance,
            bottom_lift_speed,
            lift_distance,
            lift_speed,
            bottom_retract_distance,
            bottom_retract_speed,
            retract_distance,
            retract_speed,
            bottom_second_lift_distance,
            bottom_second_lift_speed,
            second_lift_distance,
            second_lift_speed,
            bottom_second_retract_distance,
            bottom_second_retract_speed,
            second_retract_distance,
            second_retract_speed,
            bottom_light_pwm,
            light_pwm,
            bool(per_layer_settings),
            printing_time,
            total_volume,
            total_weight,
            total_price,
            price_unit,
            grey_scale_level,
            transition_layers,
        )

    # helpers ---------------------------------------------------------------
    def dict(self):
        out = asdict(self)
        out["file_time"] = self.file_time.isoformat() if self.file_time else None
        out["exposure_delay"] = self.exposure_delay.name
        return out


@dataclass
class LayerContent:
    # minimal subset – we mainly expose metadata; raw bytes kept for actual image decoding
    pause: bool
    layer_position_z: float
    light_pwm: int
    data: bytes
    checksum: int

    @classmethod
    def parse(cls, fh: BinaryIO) -> "LayerContent":
        (pause_flag,) = _read(">H", fh)
        (pause_z, layer_z) = _read(">ff", fh)
        fh.seek(0x30, io.SEEK_CUR)  # skip timing & motion params (we rarely need)
        (light_pwm,) = _read(">H", fh)
        assert fh.read(2) == DELIM
        (dsize,) = _read(">I", fh)
        assert fh.read(1) == b"\x55"
        data = fh.read(dsize - 2)
        (checksum,) = _read("B", fh)
        assert fh.read(2) == DELIM
        return cls(bool(pause_flag), layer_z, light_pwm, data, checksum)


class GooFile:
    """Wrapper for a parsed `.goo` file."""

    def __init__(self, header: Header, layers: List[LayerContent]):
        self.header = header
        self.layers = layers

    @classmethod
    def parse(cls, fh: BinaryIO) -> "GooFile":
        header = Header.parse(fh)
        layers = [LayerContent.parse(fh) for _ in range(header.layer_count)]
        assert fh.read(len(ENDING)) == ENDING, "ending string mismatch"
        return cls(header, layers)

    # helpers ---------------------------------------------------------------
    def __iter__(self) -> Iterator[LayerContent]:
        return iter(self.layers)

    def __len__(self):
        return len(self.layers)


# CLI utility --------------------------------------------------------------

def read_goo(path: str | Path) -> GooFile:
    with open(path, "rb") as fh:
        return GooFile.parse(fh)


def _cli():
    import argparse, json, sys, textwrap

    p = argparse.ArgumentParser(
        prog="goo_inspect",
        description="Inspect Elegoo .goo file header + optional layer count.",
    )
    p.add_argument("file", help="path to .goo file")
    p.add_argument("--layers", action="store_true", help="print per‑layer summary")
    ns = p.parse_args()

    goo = read_goo(ns.file)
    print(json.dumps({"header": goo.header.dict(), "layer_count": len(goo)}, indent=2))
    if ns.layers:
        for i, lyr in enumerate(goo):
            print(
                textwrap.shorten(
                    f"layer {i+1}: z={lyr.layer_position_z:.3f} mm pwm={lyr.light_pwm} pause={lyr.pause}",
                    width=120,
                )
            )


if __name__ == "__main__":
    _cli()