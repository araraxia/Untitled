"""
Convert sprite/mesh-texture images to lossless WebP.

WebP (lossless mode) is a straight upgrade over this project's PNG
convention for the same use case: identical exact-value guarantee (no
lossy artifacts on hard sprite edges, alpha cutouts, or packed param-map
channels), full alpha support, typically 20-30% smaller on disk. It does
NOT change anything at the GPU/VRAM level -- every loader in this engine
(gpu_sprite_sheet.py, material_loader.py, ui/theme.py) does
``Image.open(path).convert("RGBA")`` regardless of source format, so the
saving here is disk/repo size only, not runtime texture memory.

Greyscale mode (--greyscale):
  Converts the image to luminance-only (+ alpha, if present) before
  saving, for use with the material system's luminance-driven combiner
  variants (shader_cache.py's FS_RAMP colour-ramp and FS_COSINE cosine
  palette shaders) -- both remap a per-pixel Rec. 601 luminance value
  through a LUT/procedural palette rather than using the albedo's colour
  directly. An albedo authored as true greyscale skips the redundant
  colour data entirely (2 channels -- L + A -- instead of 4) and is
  bit-for-bit equivalent once the shader takes its luminance anyway:
  PIL's ``Image.convert("L")`` already uses the same ITU-R BT.601 weights
  (0.299, 0.587, 0.114) as FS_RAMP's ``dot(base.rgb, vec3(0.299, 0.587,
  0.114))``, so no custom weighting is needed here to match.

  Every loader's ``.convert("RGBA")`` replicates a greyscale L (or LA)
  image's luminance into R, G, and B on load, so a greyscale WebP drops
  straight into the same albedo texture slot -- no renderer changes
  required. Pick the colour later via the entity/material's runtime
  overrides ('hue_shift' for FS_HUE, 'cosine_params' for FS_COSINE, or a
  color_ramp LUT for FS_RAMP -- see shader_cache.py).

Usage:
    # Single file, lossless colour WebP next to the source.
    python tools/convert_to_webp.py frontend/assets/images/sprites/lantern_atlas.png

    # Whole directory tree, greyscale + alpha, for combiner-driven sprites.
    python tools/convert_to_webp.py frontend/assets/images/sprites/human --greyscale

    # Explicit output location (mirrors subdirectories under a directory input).
    python tools/convert_to_webp.py frontend/assets/pending -o frontend/assets/images/converted

    # Delete the original raster files once converted (off by default).
    python tools/convert_to_webp.py frontend/assets/pending --delete-originals
"""

import argparse
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif"}

# Matches FS_RAMP's luminance weights exactly (shader_cache.py) -- documented
# here only so the equivalence is obvious; PIL's built-in "L" conversion
# already applies these ITU-R BT.601 weights, so no custom math is used.
_REC_601_NOTE = (0.299, 0.587, 0.114)


def _to_greyscale(img: Image.Image) -> Image.Image:
    """Convert *img* to luminance (+ alpha, if present).

    Uses PIL's builtin "L" conversion, which already applies Rec. 601
    weights matching shader_cache.py's FS_RAMP/FS_COSINE combiner
    shaders -- see module docstring.
    """
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    rgba = img.convert("RGBA")
    grey = rgba.convert("L")
    if has_alpha:
        alpha = rgba.getchannel("A")
        return Image.merge("LA", (grey, alpha))
    return grey


def _normalize_color(img: Image.Image) -> Image.Image:
    """Normalize a non-greyscale image to a mode WebP handles cleanly."""
    if img.mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        return img.convert("RGBA")
    return img


def convert_image(src: Path, dst: Path, greyscale: bool) -> None:
    """Convert one image file at *src* to a lossless WebP at *dst*."""
    img = Image.open(src)
    img = _to_greyscale(img) if greyscale else _normalize_color(img)

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, format="WEBP", lossless=True, quality=100, method=6)


def _output_path(src: Path, src_root: Path, out_root: Path, greyscale: bool) -> Path:
    """Compute the destination .webp path for *src*, mirroring its position
    relative to *src_root* under *out_root*, and tagging greyscale outputs
    with a '_grey' suffix so they don't collide with a colour conversion of
    the same source.
    """
    rel = src.relative_to(src_root)
    suffix = "_grey" if greyscale else ""
    return (out_root / rel).with_name(rel.stem + suffix + ".webp")


def run(
    input_path: str,
    output_path: "str | None",
    greyscale: bool,
    recursive: bool,
    delete_originals: bool,
) -> None:
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input path does not exist: {src}")

    if src.is_file():
        if output_path:
            out = Path(output_path)
        else:
            suffix = "_grey" if greyscale else ""
            out = src.with_name(src.stem + suffix + ".webp")
        targets = [(src, out)]
    else:
        pattern_iter = src.rglob("*") if recursive else src.iterdir()
        files = sorted(
            p
            for p in pattern_iter
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )
        out_root = Path(output_path) if output_path else src
        targets = [(f, _output_path(f, src, out_root, greyscale)) for f in files]

    if not targets:
        print("No matching images found.")
        return

    converted = 0
    errors = 0
    for src_file, dst_file in targets:
        try:
            convert_image(src_file, dst_file, greyscale)
        except Exception as exc:  # noqa: BLE001 -- report and continue the batch
            print(f"  [ERROR] {src_file}: {exc}")
            errors += 1
            continue
        converted += 1
        print(f"  {src_file} -> {dst_file}")
        if delete_originals:
            src_file.unlink()

    print(
        f"\nConverted {converted} image(s) to lossless"
        f"{' greyscale' if greyscale else ''} WebP"
        f"{', ' + str(errors) + ' error(s)' if errors else ''}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert images to lossless WebP for this project's sprite/mesh "
            "texture pipeline (optionally greyscale, for the material "
            "system's colour-combiner shaders)."
        )
    )
    parser.add_argument(
        "input",
        help="Source image file, or a directory to convert in bulk.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help=(
            "Output file (single-file input) or output directory (directory "
            "input, subdirectories mirrored). Defaults to alongside the "
            "source with a .webp extension."
        ),
    )
    parser.add_argument(
        "-g",
        "--greyscale",
        action="store_true",
        help=(
            "Convert to luminance (+ alpha) instead of colour, for albedo "
            "textures driven by the FS_RAMP/FS_COSINE colour combiner "
            "shaders. Output filenames get a '_grey' suffix."
        ),
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="When input is a directory, only convert its top-level files.",
    )
    parser.add_argument(
        "--delete-originals",
        action="store_true",
        help="Delete each source file after it converts successfully.",
    )
    parser.set_defaults(recursive=True)
    args = parser.parse_args()

    run(
        args.input,
        args.output,
        args.greyscale,
        args.recursive,
        args.delete_originals,
    )


if __name__ == "__main__":
    main()
