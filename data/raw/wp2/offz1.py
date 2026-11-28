# zoom1 official-map crop around local ground points: name x z [half_size_m]
import sys, json, numpy as np
sys.path.insert(0, 'E:/Claude/三维南信大/tools')
from official_crop import tile, A, T
from PIL import Image
def crop(x, z, hs=30):
    c = np.array([[x - hs, z - hs, 0, 1], [x + hs, z - hs, 0, 1], [x + hs, z + hs, 0, 1], [x - hs, z + hs, 0, 1]]) @ A
    x0, y0 = c.min(0); x1, y1 = c.max(0)
    out = Image.new('RGB', (int(x1 - x0), int(y1 - y0)), (240, 240, 240))
    for tx in range(int(x0 // T), int(x1 // T) + 1):
        for ty in range(int(y0 // T), int(y1 // T) + 1):
            im = tile(tx, ty)
            if im is not None: out.paste(im, (int(tx * T - x0), int(ty * T - y0)))
    return out
if __name__ == '__main__':
    args = sys.argv[1:]; ims = []
    for i in range(0, len(args), 3):
        ims.append(crop(float(args[i + 1]), float(args[i + 2]), 25).resize((360, 360)))
    W = len(ims) * 364; out = Image.new('RGB', (W, 360), 'white')
    for k, im in enumerate(ims): out.paste(im, (k * 364, 0))
    out.save('E:/Claude/三维南信大/data/raw/wp2/offz1_sidewalks.jpg', quality=88); print(out.size)
