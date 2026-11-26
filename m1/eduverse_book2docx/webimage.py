"""Make any picture from a Word file something a browser can draw.

Word keeps pictures as PNG, JPEG and GIF, but also TIFF, BMP, EMF and WMF. Browsers
show none of the last four (Chrome cannot show TIFF; nobody shows EMF or WMF), and
they used to be stored under a .png name, so they came out as broken images.

to_web(data) -> (bytes, ext, problem). PNG, JPEG, GIF, WebP and SVG pass through.
Anything else is converted to PNG: Pillow for TIFF and BMP; LibreOffice, Inkscape or
ImageMagick (whichever is installed) for EMF and WMF. If nothing can convert it, a
plain placeholder PNG is returned with `problem` set, so the reviewer sees a box that
says what to replace instead of a broken image.

The same file lives in converter/eduverse_convert/webimage.py; keep the two in step.
"""
import io
import os
import shutil
import subprocess
import tempfile

WEB = {"png", "jpg", "gif", "webp", "svg"}


def sniff(data: bytes) -> str:
    h = data[:64]
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if h[:2] == b"\xff\xd8":
        return "jpg"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "webp"
    if h[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if h[:2] == b"BM":
        return "bmp"
    if len(data) > 44 and data[40:44] == b" EMF":
        return "emf"
    if h[:4] == b"\xd7\xcd\xc6\x9a" or h[:4] in (b"\x01\x00\x09\x00", b"\x02\x00\x09\x00"):
        return "wmf"
    if h.lstrip()[:5] in (b"<?xml", b"<svg ") or b"<svg" in data[:400]:
        return "svg"
    return "unknown"


def _png(im) -> bytes:
    from PIL import Image
    if im.mode not in ("RGB", "RGBA", "L", "LA"):
        im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def _external(data: bytes, kind: str) -> bytes | None:
    """EMF/WMF to PNG with a command-line tool, if one is installed."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "pic." + kind)
        with open(src, "wb") as f:
            f.write(data)
        tries = []
        office = shutil.which("soffice") or shutil.which("libreoffice")
        if office:
            tries.append(([office, "--headless", "--norestore", f"-env:UserInstallation=file://{tmp}/profile",
                           "--convert-to", "png", "--outdir", tmp, src], os.path.join(tmp, "pic.png")))
        if shutil.which("inkscape"):
            tries.append((["inkscape", src, "--export-type=png", f"--export-filename={tmp}/ink.png"], os.path.join(tmp, "ink.png")))
        if shutil.which("convert"):
            tries.append((["convert", "-density", "200", src, os.path.join(tmp, "im.png")], os.path.join(tmp, "im.png")))
        for cmd, out in tries:
            try:
                subprocess.run(cmd, capture_output=True, timeout=90)
                if os.path.exists(out) and os.path.getsize(out) > 100:
                    with open(out, "rb") as f:
                        return f.read()
            except Exception:
                continue
    return None


def placeholder(kind: str, size=(480, 300)) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, (245, 245, 245))
    d = ImageDraw.Draw(im)
    d.rectangle([2, 2, size[0] - 3, size[1] - 3], outline=(200, 200, 200), width=2)
    msg = [f"Picture in {kind.upper()} format", "could not be converted.", "Replace it during review."]
    for i, line in enumerate(msg):
        d.text((24, size[1] // 2 - 30 + i * 20), line, fill=(90, 90, 90))
    return _png(im)


def to_web(data: bytes) -> tuple[bytes, str, str]:
    kind = sniff(data)
    if kind in WEB:
        return data, kind, ""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            return _png(im), "png", ""
    except Exception:
        pass
    if kind in ("emf", "wmf", "unknown"):
        out = _external(data, kind if kind != "unknown" else "emf")
        if out:
            return out, "png", ""
    return placeholder(kind), "png", f"picture in {kind.upper()} format could not be converted (install LibreOffice on the server)"
