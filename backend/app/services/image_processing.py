"""Local preprocessing for imaging uploads.

This module converts common hackathon/demo medical image formats into a
normalized PNG that the imaging_report skill can send to a vision model. It
does not diagnose or interpret. It only handles file loading, display
windowing, OCR, and ROI annotation.

Supported inputs:
    - Chest X-ray raster files: .png, .jpg, .jpeg
    - DICOM single-frame images: .dcm, .dicom
    - CT/MRI NIfTI volumes: .nii, .nii.gz
    - fastMRI-style HDF5 files: .h5, .hdf5
    - Scanned reports for OCR: raster images and PDFs
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import cv2

    _CV2 = True
except ImportError:
    cv2 = None
    _CV2 = False

try:
    import fitz

    _PYMUPDF = True
except ImportError:
    fitz = None
    _PYMUPDF = False

try:
    import h5py

    _H5PY = True
except ImportError:
    h5py = None
    _H5PY = False

try:
    import nibabel as nib

    _NIBABEL = True
except ImportError:
    nib = None
    _NIBABEL = False

try:
    import pydicom

    _PYDICOM = True
except ImportError:
    pydicom = None
    _PYDICOM = False

try:
    import pytesseract

    _PYTESSERACT = True
except ImportError:
    pytesseract = None
    _PYTESSERACT = False


MAX_MODEL_IMAGE_SIDE = 1568

CT_WINDOWS = {
    "lung": (-600, 1500),
    "soft_tissue": (40, 400),
    "bone": (400, 1800),
}
DEFAULT_CT_WINDOW = "lung"


@dataclass(frozen=True)
class PreparedImage:
    png_path: str
    modality: str
    width: int
    height: int
    extra: dict[str, Any]

    def asdict(self) -> dict[str, Any]:
        return {
            "png_path": self.png_path,
            "modality": self.modality,
            "width": self.width,
            "height": self.height,
            "extra": self.extra,
        }


def prepare_image(
    file_path: str | Path,
    modality_hint: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Convert a supported imaging file into a normalized PNG.

    Args:
        file_path: Raw upload path.
        modality_hint: Optional "xray", "ct", "mri", "dicom", or "fastmri".
        output_dir: Where to write the prepared PNG. Defaults to input folder.

    Returns:
        Dict with png_path, modality, width, height, and extra metadata.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    out_dir = Path(output_dir) if output_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    modality = _detect_modality(path, modality_hint)
    if modality == "xray":
        img, extra = _load_xray(path)
    elif modality == "dicom":
        img, extra, modality = _load_dicom(path)
    elif modality == "ct":
        img, extra = _load_ct(path)
    elif modality == "mri":
        img, extra = _load_mri(path)
    elif modality == "fastmri":
        img, extra = _load_fastmri(path)
        modality = "mri"
    else:
        raise ValueError(f"Unsupported modality: {modality}")

    img = _resize_for_model(img)
    out_path = out_dir / f"{_safe_output_stem(path)}_prepared.png"
    img.save(out_path, format="PNG")

    return PreparedImage(
        png_path=str(out_path),
        modality=modality,
        width=img.width,
        height=img.height,
        extra=extra,
    ).asdict()


def load_image(path: str | Path) -> np.ndarray:
    """Load an image-like file as a numpy array for lower-level processing."""
    prepared = prepare_image(path)
    return np.asarray(Image.open(prepared["png_path"]))


def ocr(path: str | Path) -> str:
    """OCR a scanned report image or PDF into text.

    This is intended for scanned radiology reports or referral letters, not for
    interpreting image pixels. It returns an empty string when OCR is available
    but no text is detected.
    """
    if not _PYTESSERACT:
        raise ImportError("pytesseract is required for OCR: pip install pytesseract")

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"OCR input not found: {file_path}")

    images = _render_ocr_pages(file_path)
    text_pages = []
    for img in images:
        prepped = _preprocess_for_ocr(img)
        text_pages.append(pytesseract.image_to_string(prepped))
    return "\n\n".join(page.strip() for page in text_pages if page.strip())


def annotate_image(
    png_path: str | Path,
    regions_of_interest: list[dict[str, Any]],
    output_dir: str | Path | None = None,
) -> str:
    """Draw fractional ROI bounding boxes onto a prepared PNG.

    ROI bbox format is [x_min, y_min, x_max, y_max], normalized to 0..1.
    ROIs without valid boxes are skipped.
    """
    path = Path(png_path)
    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size
    font = _load_label_font()

    colors = ["#ff3b30", "#007aff", "#34c759", "#ffcc00", "#af52de", "#ff9500"]

    for idx, roi in enumerate(regions_of_interest):
        bbox = roi.get("bbox")
        if not _is_valid_bbox(bbox):
            continue

        label = str(roi.get("label") or f"ROI {idx + 1}")
        color = colors[idx % len(colors)]
        x0, y0, x1, y1 = _bbox_to_pixels(bbox, width, height)
        if x1 <= x0 or y1 <= y0:
            continue

        for offset in range(3):
            draw.rectangle([x0 - offset, y0 - offset, x1 + offset, y1 + offset], outline=color)

        text_bbox = draw.textbbox((x0, y0), label, font=font)
        label_w = min(text_bbox[2] - text_bbox[0] + 8, width - x0)
        label_h = text_bbox[3] - text_bbox[1] + 6
        label_y = y0 - label_h if y0 - label_h >= 0 else y0 + 2

        draw.rectangle([x0, label_y, x0 + label_w, label_y + label_h], fill=color)
        draw.text((x0 + 4, label_y + 3), label, fill="white", font=font)

    out_dir = Path(output_dir) if output_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{path.stem}_annotated.png"
    img.save(out_path, format="PNG")
    return str(out_path)


def draft_preliminary_report(filename: str) -> dict[str, Any]:
    """Compatibility endpoint used by /imaging/report.

    The real report drafting now happens in skills/imaging_report/skill.py.
    This endpoint returns preprocessing readiness for quick manual checks.
    """
    return {
        "filename": filename,
        "status": "preprocessing_ready",
        "supported_formats": [".png", ".jpg", ".jpeg", ".dcm", ".dicom", ".nii", ".nii.gz", ".h5", ".hdf5"],
        "note": "Use /engine/run/imaging_report with image_path for the full AI draft.",
    }


def _detect_modality(path: Path, hint: str | None) -> str:
    normalized_hint = hint.lower().strip() if hint else None
    if normalized_hint in {"xray", "ct", "mri", "dicom", "fastmri"}:
        return normalized_hint

    suffix = path.suffix.lower()
    name = path.name.lower()

    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        return "xray"
    if suffix in {".dcm", ".dicom"}:
        return "dicom"
    if suffix in {".h5", ".hdf5"}:
        return "fastmri"
    if suffix == ".nii" or name.endswith(".nii.gz"):
        if any(token in name for token in ("t1", "t2", "flair", "t1ce", "brain", "brats")):
            return "mri"
        return "ct"

    raise ValueError(f"Cannot detect imaging modality from extension: {suffix}")


def _load_xray(path: Path) -> tuple[Image.Image, dict[str, Any]]:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    arr = _percentile_normalize(np.asarray(img, dtype=np.float32))
    return Image.fromarray(arr, mode="L").convert("RGB"), {
        "source_format": path.suffix.lower(),
        "original_size": list(img.size),
    }


def _load_dicom(path: Path) -> tuple[Image.Image, dict[str, Any], str]:
    if not _PYDICOM:
        raise ImportError("pydicom is required for DICOM files: pip install pydicom")

    ds = pydicom.dcmread(str(path))
    arr = ds.pixel_array.astype(np.float32)
    arr = _apply_dicom_rescale(ds, arr)

    dicom_modality = str(getattr(ds, "Modality", "OT")).upper()
    photometric = str(getattr(ds, "PhotometricInterpretation", "")).upper()

    if dicom_modality == "CT":
        arr = _window_hu(arr, *CT_WINDOWS[DEFAULT_CT_WINDOW])
        modality = "ct"
        window = DEFAULT_CT_WINDOW
    elif dicom_modality == "MR":
        arr = _zscore_normalize(arr)
        modality = "mri"
        window = None
    else:
        arr = _percentile_normalize(arr)
        modality = "xray"
        window = None

    if photometric == "MONOCHROME1":
        arr = 255 - arr

    img = Image.fromarray(arr.astype(np.uint8), mode="L").convert("RGB")
    extra = {
        "dicom_modality_tag": dicom_modality,
        "study_description": str(getattr(ds, "StudyDescription", "")),
        "series_description": str(getattr(ds, "SeriesDescription", "")),
        "body_part_examined": str(getattr(ds, "BodyPartExamined", "")),
    }
    if window:
        extra["window"] = window
    return img, extra, modality


def _load_ct(path: Path, window: str = DEFAULT_CT_WINDOW) -> tuple[Image.Image, dict[str, Any]]:
    if not _NIBABEL:
        raise ImportError("nibabel is required for NIfTI CT files: pip install nibabel")

    volume, spacing = _load_nifti_volume(path)
    selected_slice = _choose_high_variance_slice(volume)
    arr = _window_hu(volume[:, :, selected_slice], *CT_WINDOWS[window])
    arr = np.rot90(arr)

    return Image.fromarray(arr, mode="L").convert("RGB"), {
        "n_slices": int(volume.shape[2]),
        "selected_slice": int(selected_slice),
        "window": window,
        "voxel_spacing": spacing,
    }


def _load_mri(path: Path) -> tuple[Image.Image, dict[str, Any]]:
    if not _NIBABEL:
        raise ImportError("nibabel is required for NIfTI MRI files: pip install nibabel")

    volume, spacing = _load_nifti_volume(path)
    selected_slice = _choose_bright_slice(volume)
    arr = _zscore_normalize(volume[:, :, selected_slice])
    arr = np.rot90(arr)

    return Image.fromarray(arr, mode="L").convert("RGB"), {
        "n_slices": int(volume.shape[2]),
        "selected_slice": int(selected_slice),
        "sequence": _infer_mri_sequence(path.name),
        "voxel_spacing": spacing,
    }


def _load_fastmri(path: Path) -> tuple[Image.Image, dict[str, Any]]:
    if not _H5PY:
        raise ImportError("h5py is required for fastMRI HDF5 files: pip install h5py")

    with h5py.File(path, "r") as handle:
        if "reconstruction_rss" in handle:
            volume = np.asarray(handle["reconstruction_rss"], dtype=np.float32)
            source = "reconstruction_rss"
        elif "reconstruction_esc" in handle:
            volume = np.asarray(handle["reconstruction_esc"], dtype=np.float32)
            source = "reconstruction_esc"
        elif "kspace" in handle:
            volume = _rss_from_kspace(np.asarray(handle["kspace"]))
            source = "kspace_ifft_rss"
        else:
            keys = ", ".join(handle.keys())
            raise ValueError(f"fastMRI file has no supported image dataset. Keys: {keys}")

        attrs = {key: _json_safe_attr(value) for key, value in handle.attrs.items()}

    if volume.ndim == 2:
        arr = volume
        selected_slice = 0
        n_slices = 1
    else:
        n_slices = int(volume.shape[0])
        selected_slice = _choose_high_variance_slice(volume, slice_axis=0)
        arr = volume[selected_slice]

    arr = _percentile_normalize(arr.astype(np.float32))
    return Image.fromarray(arr, mode="L").convert("RGB"), {
        "n_slices": n_slices,
        "selected_slice": int(selected_slice),
        "fastmri_source": source,
        "fastmri_attrs": attrs,
    }


def _render_ocr_pages(path: Path) -> list[Image.Image]:
    if path.suffix.lower() == ".pdf":
        if not _PYMUPDF:
            raise ImportError("PyMuPDF is required for PDF OCR: pip install PyMuPDF")

        pages = []
        with fitz.open(path) as doc:
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pages.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return pages

    return [Image.open(path).convert("RGB")]


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(ImageOps.exif_transpose(img))
    arr = np.asarray(gray, dtype=np.uint8)

    if not _CV2:
        return Image.fromarray(_percentile_normalize(arr.astype(np.float32)), mode="L")

    arr = cv2.fastNlMeansDenoising(arr)
    arr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    arr = _deskew_binary(arr)
    return Image.fromarray(arr, mode="L")


def _deskew_binary(arr: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(arr < 255))
    if coords.size == 0:
        return arr

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.25:
        return arr

    height, width = arr.shape[:2]
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(arr, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _load_nifti_volume(path: Path) -> tuple[np.ndarray, list[float]]:
    nii = nib.load(str(path))
    volume = nii.get_fdata(dtype=np.float32)
    if volume.ndim == 4:
        volume = volume[..., 0]
    if volume.ndim != 3:
        raise ValueError(f"Expected 3-D NIfTI volume, got shape {volume.shape}")
    return volume, [float(value) for value in nii.header.get_zooms()]


def _choose_high_variance_slice(volume: np.ndarray, slice_axis: int = 2) -> int:
    moved = np.moveaxis(volume, slice_axis, 0)
    n_slices = moved.shape[0]
    start = n_slices // 3
    end = max(start + 1, 2 * n_slices // 3)
    scores = [float(np.std(moved[idx])) for idx in range(start, end)]
    return start + int(np.argmax(scores))


def _choose_bright_slice(volume: np.ndarray) -> int:
    n_slices = volume.shape[2]
    start = n_slices // 4
    end = max(start + 1, 3 * n_slices // 4)
    scores = [float(np.percentile(volume[:, :, idx], 95)) for idx in range(start, end)]
    return start + int(np.argmax(scores))


def _apply_dicom_rescale(ds: Any, arr: np.ndarray) -> np.ndarray:
    slope = float(getattr(ds, "RescaleSlope", 1))
    intercept = float(getattr(ds, "RescaleIntercept", 0))
    return arr * slope + intercept


def _window_hu(arr: np.ndarray, center: float, width: float) -> np.ndarray:
    low = center - width / 2
    high = center + width / 2
    clipped = np.clip(arr, low, high)
    return ((clipped - low) / (high - low) * 255.0).astype(np.uint8)


def _zscore_normalize(arr: np.ndarray) -> np.ndarray:
    mean = float(np.mean(arr))
    std = float(np.std(arr)) or 1.0
    z = np.clip((arr - mean) / std, -3, 3)
    return ((z + 3) / 6.0 * 255.0).astype(np.uint8)


def _percentile_normalize(arr: np.ndarray) -> np.ndarray:
    low, high = np.percentile(arr, [2, 98])
    if high <= low:
        return np.zeros_like(arr, dtype=np.uint8)
    scaled = (arr - low) / (high - low) * 255.0
    return np.clip(scaled, 0, 255).astype(np.uint8)


def _rss_from_kspace(kspace: np.ndarray) -> np.ndarray:
    image = np.fft.ifftshift(np.fft.ifft2(np.fft.fftshift(kspace, axes=(-2, -1)), axes=(-2, -1)), axes=(-2, -1))
    magnitude = np.abs(image)
    if magnitude.ndim >= 4:
        return np.sqrt(np.sum(magnitude**2, axis=1))
    return magnitude


def _resize_for_model(img: Image.Image, max_side: int = MAX_MODEL_IMAGE_SIDE) -> Image.Image:
    width, height = img.size
    if max(width, height) <= max_side:
        return img
    scale = max_side / max(width, height)
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return img.resize(size, Image.LANCZOS)


def _infer_mri_sequence(filename: str) -> str:
    name = filename.lower()
    for sequence in ("flair", "t1ce", "t1", "t2"):
        if sequence in name:
            return sequence.upper()
    return "unknown"


def _safe_output_stem(path: Path) -> str:
    if path.name.lower().endswith(".nii.gz"):
        return path.name[:-7]
    return path.stem


def _load_label_font() -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, 14)
        except OSError:
            continue
    return ImageFont.load_default()


def _is_valid_bbox(bbox: Any) -> bool:
    return isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox)


def _bbox_to_pixels(bbox: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = [max(0.0, min(1.0, float(value))) for value in bbox]
    return int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height)


def _json_safe_attr(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode(errors="ignore")
    return value
