"""
DracoGS: In-memory 3D Gaussian Splat compression via modified Draco.

Usage:
    from compression_decompression import read_gs_ply, encode_dracogs, decode_dracogs, save_gs_ply

    gs = read_gs_ply("input.ply")
    bitstream = encode_dracogs(gs, qp=16, qfd=8, qo=8, qs=8, qr=8)
    gs_dec = decode_dracogs(bitstream)
    save_gs_ply(gs_dec, "output.ply")
"""

import sys
import numpy as np
from pathlib import Path
from plyfile import PlyData, PlyElement

_this_dir = Path(__file__).resolve().parent
_so_dir = _this_dir.parent / "build" / "compression"
if _so_dir.is_dir() and str(_so_dir) not in sys.path:
    sys.path.insert(0, str(_so_dir))

import _dracogs


def read_gs_ply(path: str) -> dict:
    """Read a 3DGS PLY file and return attributes as a dict of numpy arrays."""
    plydata = PlyData.read(str(path))
    v = plydata.elements[0]

    positions = np.stack([np.asarray(v["x"]),
                          np.asarray(v["y"]),
                          np.asarray(v["z"])], axis=1).astype(np.float32)

    f_dc = np.stack([np.asarray(v["f_dc_0"]),
                     np.asarray(v["f_dc_1"]),
                     np.asarray(v["f_dc_2"])], axis=1).astype(np.float32)

    opacity = np.asarray(v["opacity"]).astype(np.float32).reshape(-1, 1)

    scale_names = sorted(
        [p.name for p in v.properties if p.name.startswith("scale_")],
        key=lambda x: int(x.split("_")[-1]),
    )
    scale = np.stack([np.asarray(v[n]) for n in scale_names],
                     axis=1).astype(np.float32)

    rot_names = sorted(
        [p.name for p in v.properties if p.name.startswith("rot_")],
        key=lambda x: int(x.split("_")[-1]),
    )
    rotation = np.stack([np.asarray(v[n]) for n in rot_names],
                        axis=1).astype(np.float32)

    rest_names = sorted(
        [p.name for p in v.properties if p.name.startswith("f_rest_")],
        key=lambda x: int(x.split("_")[-1]),
    )

    n_rest = len(rest_names)
    f_rest_1 = np.empty((len(positions), 0), dtype=np.float32)
    f_rest_2 = np.empty((len(positions), 0), dtype=np.float32)
    f_rest_3 = np.empty((len(positions), 0), dtype=np.float32)

    if n_rest >= 9:
        f_rest_1 = np.stack(
            [np.asarray(v[f"f_rest_{i}"]) for i in range(9)],
            axis=1,
        ).astype(np.float32)
    if n_rest >= 24:
        f_rest_2 = np.stack(
            [np.asarray(v[f"f_rest_{i}"]) for i in range(9, 24)],
            axis=1,
        ).astype(np.float32)
    if n_rest >= 45:
        f_rest_3 = np.stack(
            [np.asarray(v[f"f_rest_{i}"]) for i in range(24, 45)],
            axis=1,
        ).astype(np.float32)

    return {
        "positions": positions,
        "f_dc": f_dc,
        "f_rest_1": f_rest_1,
        "f_rest_2": f_rest_2,
        "f_rest_3": f_rest_3,
        "opacity": opacity,
        "scale": scale,
        "rotation": rotation,
    }


def encode_dracogs(
    gs_data: dict,
    qp: int = 16,
    qfd: int = 16,
    qfr1: int = 16,
    qfr2: int = 16,
    qfr3: int = 16,
    qo: int = 16,
    qs: int = 16,
    qr: int = 16,
    cl: int = 7,
) -> bytes:
    """Compress 3DGS attributes into a Draco bitstream (in memory).

    Parameters
    ----------
    gs_data : dict
        As returned by read_gs_ply().
    qp, qfd, qfr1, qfr2, qfr3, qo, qs, qr : int
        Quantization bits per attribute (0=lossless, negative=drop attribute).
    cl : int
        Compression level 0-10.

    Returns
    -------
    bytes
        Compressed Draco bitstream.
    """
    return _dracogs.encode(
        gs_data["positions"],
        gs_data["f_dc"],
        gs_data["f_rest_1"],
        gs_data["f_rest_2"],
        gs_data["f_rest_3"],
        gs_data["opacity"],
        gs_data["scale"],
        gs_data["rotation"],
        qp=qp, qfd=qfd, qfr1=qfr1, qfr2=qfr2, qfr3=qfr3,
        qo=qo, qs=qs, qr=qr, cl=cl,
    )


def decode_dracogs(bitstream: bytes) -> dict:
    """Decompress a Draco bitstream back to 3DGS attribute arrays.

    Parameters
    ----------
    bitstream : bytes
        As returned by encode_dracogs().

    Returns
    -------
    dict
        Same structure as read_gs_ply() output: "positions", "f_dc",
        "f_rest_1", "f_rest_2", "f_rest_3", "opacity", "scale", "rotation".
    """
    result = _dracogs.decode(bitstream)
    N = result["num_points"]

    gs = {}
    for key in ("positions", "f_dc", "f_rest_1", "f_rest_2", "f_rest_3",
                "opacity", "scale", "rotation"):
        if key in result:
            gs[key] = result[key]
        else:
            gs[key] = np.empty((N, 0), dtype=np.float32)
    return gs


def save_gs_ply(gs_data: dict, path: str, binary: bool = True) -> None:
    """Write 3DGS attributes to a PLY file.

    Parameters
    ----------
    gs_data : dict
        As returned by read_gs_ply() or decode_dracogs().
    path : str
        Output PLY file path.
    binary : bool
        If True write binary little-endian, else ASCII.
    """
    pos = gs_data["positions"]
    N = pos.shape[0]

    names = ["x", "y", "z"]
    arrays = [pos[:, 0], pos[:, 1], pos[:, 2]]

    normals = np.zeros(N, dtype=np.float32)
    for n in ("nx", "ny", "nz"):
        names.append(n)
        arrays.append(normals)

    f_dc = gs_data["f_dc"]
    for i in range(f_dc.shape[1]):
        names.append(f"f_dc_{i}")
        arrays.append(f_dc[:, i])

    for band_key, offset in [("f_rest_1", 0), ("f_rest_2", 9), ("f_rest_3", 24)]:
        band = gs_data.get(band_key, np.empty((N, 0), dtype=np.float32))
        for i in range(band.shape[1]):
            names.append(f"f_rest_{offset + i}")
            arrays.append(band[:, i])

    opacity = gs_data["opacity"]
    names.append("opacity")
    arrays.append(opacity.ravel())

    scale = gs_data["scale"]
    for i in range(scale.shape[1]):
        names.append(f"scale_{i}")
        arrays.append(scale[:, i])

    rotation = gs_data["rotation"]
    for i in range(rotation.shape[1]):
        names.append(f"rot_{i}")
        arrays.append(rotation[:, i])

    dtype_full = [(name, "f4") for name in names]
    elements = np.empty(N, dtype=dtype_full)
    for i, name in enumerate(names):
        elements[name] = arrays[i].astype(np.float32)

    el = PlyElement.describe(elements, "vertex")

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    PlyData([el], text=(not binary)).write(str(out_path))
