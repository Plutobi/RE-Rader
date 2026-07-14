"""
Run once to generate the extension icons:
  python generate_icons.py

Requires no external libraries — uses Python stdlib only.
Creates icons/icon16.png, icon32.png, icon48.png, icon128.png
"""
import struct
import zlib
import os
import math

os.makedirs('icons', exist_ok=True)

def make_png(size, pixels):
    """Build a minimal PNG from a list of (r,g,b,a) tuples, row-major."""
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)  # RGBA
    raw = b''
    for y in range(size):
        raw += b'\x00'  # filter type None
        for x in range(size):
            r, g, b, a = pixels[y * size + x]
            raw += bytes([r, g, b, a])

    png = (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr)
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b'')
    )
    return png

def draw_icon(size):
    """Draw a simple house icon on indigo background."""
    pixels = []
    cx, cy = size / 2, size / 2
    r = size / 2

    for y in range(size):
        for x in range(size):
            # Distance from center → rounded square (squircle)
            nx = (x - cx) / r
            ny = (y - cy) / r
            inside_bg = (abs(nx) ** 3.5 + abs(ny) ** 3.5) < 0.85

            if not inside_bg:
                pixels.append((0, 0, 0, 0))
                continue

            # Background colour: indigo #4f46e5
            bg = (79, 70, 229, 255)

            # Simple house shape in white
            # Normalise coords to -1..1
            fx = (x - cx) / (r * 0.7)
            fy = (y - cy) / (r * 0.7)

            # Roof triangle: top half, triangle
            in_roof = (fy < -0.05) and (abs(fx) < (-fy - 0.05))
            # House body: rectangle bottom half
            in_body = (-0.5 < fx < 0.5) and (-0.1 < fy < 0.52)
            # Door: small rectangle at bottom centre
            in_door = (abs(fx) < 0.15) and (0.18 < fy < 0.52)

            if in_roof or in_body:
                # White house, door excluded slightly to show opening
                alpha = 230 if not in_door else 180
                pixels.append((255, 255, 255, alpha))
            else:
                pixels.append(bg)

    return pixels

for size in [16, 32, 48, 128]:
    pixels = draw_icon(size)
    data = make_png(size, pixels)
    path = f'icons/icon{size}.png'
    with open(path, 'wb') as f:
        f.write(data)
    print(f'Created {path} ({size}x{size})')

print('\nAll icons created. Load the extension via chrome://extensions → Load unpacked.')
