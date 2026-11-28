"""Halve a Radiance .hdr (RGBE) image: 2x2 box filter in linear float, written back as run-length RGBE.

性能会话：给“流畅”画质用的小天空图。
    .venv\\Scripts\\python.exe tools\\hdr_half.py web/public/tex/sky.hdr web/public/tex/sky_1k.hdr
"""
import sys

import numpy as np


def read_hdr(path):
    data = open(path, 'rb').read()
    pos = 0
    while True:                                  # header lines up to the blank line
        end = data.index(b'\n', pos)
        line = data[pos:end]
        pos = end + 1
        if not line.strip():
            break
    end = data.index(b'\n', pos)
    dims = data[pos:end].split()
    pos = end + 1
    assert dims[0] == b'-Y' and dims[2] == b'+X', dims
    h, w = int(dims[1]), int(dims[3])
    out = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        if data[pos] == 2 and data[pos + 1] == 2 and (data[pos + 2] << 8 | data[pos + 3]) == w:
            pos += 4
            for c in range(4):
                x = 0
                while x < w:
                    n = data[pos]
                    pos += 1
                    if n > 128:
                        n -= 128
                        out[y, x:x + n, c] = data[pos]
                        pos += 1
                    else:
                        out[y, x:x + n, c] = np.frombuffer(data, np.uint8, n, pos)
                        pos += n
                    x += n
        else:                                    # flat scanline
            out[y] = np.frombuffer(data, np.uint8, w * 4, pos).reshape(w, 4)
            pos += w * 4
    e = out[..., 3].astype(np.int32)
    scale = np.where(e > 0, np.ldexp(1.0, e - 136), 0.0)
    return out[..., :3].astype(np.float64) * scale[..., None]


def rle(row):
    """Run-length encode one channel of one scanline (new-style RGBE)."""
    out, i, n = bytearray(), 0, len(row)
    while i < n:
        j = i
        while j < n and j - i < 127 and row[j] == row[i]:
            j += 1
        if j - i >= 3:
            out += bytes([128 + j - i, row[i]])
            i = j
            continue
        j = i                                    # literal run up to the next run of 3
        while j < n and j - i < 128 and not (j + 2 < n and row[j] == row[j + 1] == row[j + 2]):
            j += 1
        out += bytes([j - i]) + bytes(row[i:j])
        i = j
    return out


def write_hdr(path, rgb):
    h, w, _ = rgb.shape
    m = rgb.max(axis=2)
    mant, ex = np.frexp(m)
    ok = m > 1e-32
    k = np.where(ok, mant * 256.0 / np.where(ok, m, 1.0), 0.0)
    rgbe = np.zeros((h, w, 4), np.uint8)
    rgbe[..., :3] = np.clip(rgb * k[..., None], 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.where(ok, ex + 128, 0).astype(np.uint8)
    body = bytearray()
    for y in range(h):
        body += bytes([2, 2, w >> 8, w & 255])
        for c in range(4):
            body += rle(rgbe[y, :, c].tobytes())
    head = f'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {h} +X {w}\n'.encode()
    open(path, 'wb').write(head + bytes(body))


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    img = read_hdr(src)
    h, w, _ = img.shape
    half = img[:h // 2 * 2, :w // 2 * 2].reshape(h // 2, 2, w // 2, 2, 3).mean(axis=(1, 3))
    write_hdr(dst, half)
    back = read_hdr(dst)
    err = np.abs(back - half).max() / max(half.max(), 1e-9)
    print(f'{src} {w}x{h} -> {dst} {w // 2}x{h // 2}, max rel. error {err:.4f}')
