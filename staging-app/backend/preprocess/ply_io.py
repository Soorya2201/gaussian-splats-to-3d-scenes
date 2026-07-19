"""Read Gaussian-splat / point-cloud .ply files into (pos, rgb, scale, opacity).

Handles the two common gaussian-splat .ply flavours plus plain coloured point
clouds, dispatching on what the header actually declares:
  * PlayCanvas / splat-transform *compressed* (element `chunk` present) -> bit-packed
  * standard 3DGS (per-vertex `f_dc_*`, `scale_*`, `opacity` floats) -> SH DC + activations
  * plain point cloud (`red`/`green`/`blue`) -> colours as-is
"""
from __future__ import annotations

import numpy as np

SH_C0 = 0.28209479177387814

# PLY scalar type -> numpy dtype code
_PLY_T = {
    "char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1",
    "short": "i2", "int16": "i2", "ushort": "u2", "uint16": "u2",
    "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
    "float": "f4", "float32": "f4", "double": "f8", "float64": "f8",
}


def _read_header(f):
    """Back-compat: return (data_offset, {element_name: count})."""
    off, _fmt, elements = _parse_header(f)
    return off, {name: count for name, count, _props in elements}


def _parse_header(f):
    """Return (data_offset, fmt_string, [(elem_name, count, [(prop_name, ply_type)])]).

    Only scalar vertex properties are described (gaussian-splat plys have no
    `property list` in the vertex element).
    """
    hdr = b""
    while b"end_header" not in hdr:
        chunk = f.read(256)
        if not chunk:
            break
        hdr += chunk
    end = hdr.find(b"end_header") + len(b"end_header") + 1
    text = hdr[:end].decode("ascii", "replace")

    fmt = "binary_little_endian"
    elements = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "format":
            fmt = parts[1]
        elif parts[0] == "element":
            elements.append((parts[1], int(parts[2]), []))
        elif parts[0] == "property" and elements:
            if parts[1] == "list":
                elements[-1][2].append((parts[-1], "list"))
            else:
                elements[-1][2].append((parts[-1], parts[1]))
    return end, fmt, elements


def _byteorder(fmt):
    if "big_endian" in fmt:
        return ">"
    return "<"


def _read_vertex_records(path, off, fmt, elements):
    """Read the `vertex` element as a numpy structured array."""
    order = _byteorder(fmt)
    # advance past any elements declared before `vertex`
    voff = off
    target = None
    for name, count, props in elements:
        if name == "vertex":
            target = (count, props)
            break
        rec = sum(np.dtype(order + _PLY_T[t]).itemsize for _n, t in props if t != "list")
        voff += count * rec
    if target is None:
        raise ValueError("no 'vertex' element in .ply")
    count, props = target
    dt = np.dtype([(n, order + _PLY_T[t]) for n, t in props if t != "list"])
    data = np.fromfile(path, dtype=dt, count=count, offset=voff)
    return data


def load_standard_ply(path, want_opacity_min=0.0):
    """Decode a standard 3DGS (or plain coloured) .ply."""
    with open(path, "rb") as f:
        off, fmt, elements = _parse_header(f)
    v = _read_vertex_records(path, off, fmt, elements)
    names = v.dtype.names
    pos = np.stack([v["x"], v["y"], v["z"]], axis=1).astype(np.float32)

    if {"f_dc_0", "f_dc_1", "f_dc_2"} <= set(names):        # 3DGS SH DC -> colour
        dc = np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], axis=1).astype(np.float32)
        rgb = np.clip(0.5 + SH_C0 * dc, 0.0, 1.0)
    elif {"red", "green", "blue"} <= set(names):            # plain coloured cloud
        rgb = np.stack([v["red"], v["green"], v["blue"]], axis=1).astype(np.float32)
        if rgb.max() > 1.5:
            rgb = rgb / 255.0
    else:
        rgb = np.full((len(pos), 3), 0.6, np.float32)

    if "opacity" in names:                                  # 3DGS stores logit
        opacity = (1.0 / (1.0 + np.exp(-v["opacity"].astype(np.float32)))).astype(np.float32)
    else:
        opacity = np.ones(len(pos), np.float32)

    if {"scale_0", "scale_1", "scale_2"} <= set(names):     # 3DGS stores log-scale
        scale = np.exp(np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], axis=1)).astype(np.float32)
    else:
        scale = np.full((len(pos), 3), 0.01, np.float32)

    if want_opacity_min > 0:
        keep = opacity >= want_opacity_min
        pos, rgb, scale, opacity = pos[keep], rgb[keep], scale[keep], opacity[keep]
    return pos, rgb, scale, opacity


def load_ply(path, want_opacity_min=0.0):
    """Dispatch to the right decoder based on the header's elements."""
    with open(path, "rb") as f:
        _off, _fmt, elements = _parse_header(f)
    names = {name for name, _c, _p in elements}
    if "chunk" in names:
        return load_compressed_ply(path, want_opacity_min=want_opacity_min)
    return load_standard_ply(path, want_opacity_min=want_opacity_min)


def load_compressed_ply(path, want_opacity_min=0.0):
    with open(path, "rb") as f:
        data_off, counts = _read_header(f)
        f.seek(data_off)
        n_chunk = counts["chunk"]
        n_vert = counts["vertex"]
        n_sh = counts.get("sh", 0)

        chunks = np.frombuffer(f.read(n_chunk * 18 * 4), dtype="<f4").reshape(n_chunk, 18)
        verts = np.frombuffer(f.read(n_vert * 4 * 4), dtype="<u4").reshape(n_vert, 4)
        # sh bytes intentionally skipped

    packed_pos = verts[:, 0]
    packed_scale = verts[:, 2]
    packed_col = verts[:, 3]

    # which chunk each vertex belongs to
    cidx = np.arange(n_vert) // 256
    cidx = np.minimum(cidx, n_chunk - 1)
    cmin = chunks[cidx]  # (N,18)

    def unpack_11_10_11(p):
        x = (p >> 21) & 0x7FF
        y = (p >> 11) & 0x3FF
        z = p & 0x7FF
        return (x / 2047.0).astype(np.float32), (y / 1023.0).astype(np.float32), (z / 2047.0).astype(np.float32)

    fx, fy, fz = unpack_11_10_11(packed_pos)
    pos = np.empty((n_vert, 3), np.float32)
    pos[:, 0] = cmin[:, 0] + fx * (cmin[:, 3] - cmin[:, 0])
    pos[:, 1] = cmin[:, 1] + fy * (cmin[:, 4] - cmin[:, 1])
    pos[:, 2] = cmin[:, 2] + fz * (cmin[:, 5] - cmin[:, 2])

    sx, sy, sz = unpack_11_10_11(packed_scale)
    scale = np.empty((n_vert, 3), np.float32)
    scale[:, 0] = cmin[:, 6] + sx * (cmin[:, 9] - cmin[:, 6])
    scale[:, 1] = cmin[:, 7] + sy * (cmin[:, 10] - cmin[:, 7])
    scale[:, 2] = cmin[:, 8] + sz * (cmin[:, 11] - cmin[:, 8])
    scale = np.exp(scale)  # stored as log-scale

    r = ((packed_col >> 24) & 0xFF).astype(np.float32) / 255.0
    g = ((packed_col >> 16) & 0xFF).astype(np.float32) / 255.0
    b = ((packed_col >> 8) & 0xFF).astype(np.float32) / 255.0
    a = (packed_col & 0xFF).astype(np.float32) / 255.0
    rgb = np.empty((n_vert, 3), np.float32)
    rgb[:, 0] = cmin[:, 12] + r * (cmin[:, 15] - cmin[:, 12])
    rgb[:, 1] = cmin[:, 13] + g * (cmin[:, 16] - cmin[:, 13])
    rgb[:, 2] = cmin[:, 14] + b * (cmin[:, 17] - cmin[:, 14])
    rgb = np.clip(rgb, 0.0, 1.0)

    if want_opacity_min > 0:
        keep = a >= want_opacity_min
        pos, rgb, scale, a = pos[keep], rgb[keep], scale[keep], a[keep]
    return pos, rgb, scale, a


def to_splat_bytes(pos, rgb, scale, opacity, isotropic=True):
    """Encode gaussians into the antimatter15/drei .splat format (32 B/splat):
    pos 3xf32 | scale 3xf32 (linear) | color 4xu8 RGBA | rot 4xu8 quaternion.

    We use an isotropic scale + identity rotation so the splats render as smooth
    round gaussians with correct orientation and no quaternion-order ambiguity.
    """
    n = len(pos)
    buf = np.zeros((n, 32), np.uint8)
    buf[:, 0:12] = pos.astype("<f4").view(np.uint8).reshape(n, 12)
    if isotropic:
        iso = np.mean(scale, axis=1, keepdims=True) * np.ones((1, 3), np.float32)
        sc = iso.astype("<f4")
    else:
        sc = scale.astype("<f4")
    buf[:, 12:24] = sc.view(np.uint8).reshape(n, 12)
    buf[:, 24] = np.clip(rgb[:, 0] * 255, 0, 255)
    buf[:, 25] = np.clip(rgb[:, 1] * 255, 0, 255)
    buf[:, 26] = np.clip(rgb[:, 2] * 255, 0, 255)
    buf[:, 27] = np.clip(opacity * 255, 0, 255)
    # identity quaternion (w=1,x=y=z=0) -> (255,128,128,128)
    buf[:, 28] = 255
    buf[:, 29:32] = 128
    return buf.tobytes()


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "../3dgs_compressed.ply"
    pos, rgb, sc, a = load_compressed_ply(p)
    print(f"vertices: {len(pos):,}")
    print("pos p1/p99:", np.round(np.percentile(pos, 1, 0), 2), np.round(np.percentile(pos, 99, 0), 2))
    print("rgb mean:", np.round(rgb.mean(0), 3), "| opacity mean:", round(float(a.mean()), 3))
    print("scale mean (m):", np.round(sc.mean(0), 4), "| median:", np.round(np.median(sc, 0), 4))
