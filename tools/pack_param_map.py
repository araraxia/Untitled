"""
Pack four greyscale images into a single RGBA parameter map PNG.

Each source image is assigned to one channel:
  R → specular / custom channel 0
  G → emissive mask / custom channel 1
  B → normal offset / custom channel 2
  A → shape mask / custom channel 3

Usage:
    python tools/pack_param_map.py -r R.png -g G.png -b B.png -a A.png -o output.png

Any of the four inputs can be omitted; missing channels default to solid black (0).
"""

import argparse
from pathlib import Path

from PIL import Image


def load_as_greyscale(path: str, size: tuple[int, int]) -> Image.Image:
    """Open an image, convert to greyscale, and resize to match target size."""
    img = Image.open(path).convert("L")
    if img.size != size:
        img = img.resize(size, Image.LANCZOS)
    return img


def pack(
    r_path: str | None,
    g_path: str | None,
    b_path: str | None,
    a_path: str | None,
    output_path: str,
) -> None:
    # Determine canvas size from the first provided input.
    inputs = [p for p in (r_path, g_path, b_path, a_path) if p is not None]
    if not inputs:
        raise ValueError("At least one input image must be provided.")

    reference = Image.open(inputs[0])
    size = reference.size
    reference.close()

    black = Image.new("L", size, 0)

    r = load_as_greyscale(r_path, size) if r_path else black
    g = load_as_greyscale(g_path, size) if g_path else black
    b = load_as_greyscale(b_path, size) if b_path else black
    a = load_as_greyscale(a_path, size) if a_path else black

    packed = Image.merge("RGBA", (r, g, b, a))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    packed.save(out, format="PNG")
    print(f"Saved {size[0]}x{size[1]} parameter map → {out}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pack four greyscale images into one RGBA parameter map PNG."
    )
    parser.add_argument("-r", "--red", metavar="FILE", help="Image for the R channel")
    parser.add_argument("-g", "--green", metavar="FILE", help="Image for the G channel")
    parser.add_argument("-b", "--blue", metavar="FILE", help="Image for the B channel")
    parser.add_argument("-a", "--alpha", metavar="FILE", help="Image for the A channel")
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        required=True,
        help="Output PNG path",
    )
    args = parser.parse_args()

    pack(args.red, args.green, args.blue, args.alpha, args.output)


if __name__ == "__main__":
    main()
