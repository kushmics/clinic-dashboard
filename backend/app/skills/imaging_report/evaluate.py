"""Evaluation harness for the imaging_report skill.

Verifies skill outputs against NIH Chest X-ray ground truth (disease labels
and radiologist-drawn bounding boxes) and uses fastMRI-style reconstruction
quality metrics (SSIM, PSNR, NMSE) to verify the image preprocessing
pipeline.

Data sources:
    NIH Chest X-ray   — BBox_List_2017.csv + Data_Entry_2017.csv
    fastMRI evaluate   — SSIM / PSNR / NMSE on kspace→image reconstruction

Usage:
    python -m app.skills.imaging_report.evaluate [--images-dir DIR] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

# ---------------------------------------------------------------------------
# Paths (relative to repo root, run from backend/)
# ---------------------------------------------------------------------------
_REPO_DATA = Path(__file__).resolve().parents[4] / "data" / "sample_imaging"
_NIH_DIR = _REPO_DATA / "nih_chest_xray"
_FASTMRI_DIR = _REPO_DATA / "fastmri_fixture"

NIH_BBOX_CSV = _NIH_DIR / "ground_truth" / "BBox_List_2017.csv"
NIH_ENTRY_CSV = _NIH_DIR / "ground_truth" / "Data_Entry_2017.csv"
NIH_IMAGES_DIR = _NIH_DIR / "images"


# ═══════════════════════════════════════════════════════════════════════════
# § 1  Ground-truth loaders
# ═══════════════════════════════════════════════════════════════════════════

def load_nih_labels(entry_csv: Path = NIH_ENTRY_CSV) -> dict[str, list[str]]:
    """Return {image_filename: [label, ...]} from Data_Entry_2017.csv."""
    import csv
    labels: dict[str, list[str]] = {}
    with open(entry_csv) as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            filename = row[0]
            findings = [s.strip() for s in row[1].split("|")]
            labels[filename] = findings
    return labels


def load_nih_bboxes(bbox_csv: Path = NIH_BBOX_CSV) -> dict[str, list[dict[str, Any]]]:
    """Return {image_filename: [{label, bbox_xywh, bbox_fractional}, ...]}."""
    import csv
    bboxes: dict[str, list[dict]] = {}
    with open(bbox_csv) as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            filename = row[0]
            label = row[1]
            x, y, w, h = float(row[2]), float(row[3]), float(row[4]), float(row[5])
            entry = {
                "label": label,
                "bbox_xywh": [x, y, w, h],
                "bbox_fractional": _xywh_to_fractional(x, y, w, h, 1024, 1024),
            }
            bboxes.setdefault(filename, []).append(entry)
    return bboxes


def _xywh_to_fractional(
    x: float, y: float, w: float, h: float, img_w: int, img_h: int,
) -> list[float]:
    """Convert pixel [x, y, w, h] to fractional [x_min, y_min, x_max, y_max]."""
    return [x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h]


# ═══════════════════════════════════════════════════════════════════════════
# § 2  Evaluation metrics
# ═══════════════════════════════════════════════════════════════════════════

def compute_iou(box_a: list[float], box_b: list[float]) -> float:
    """IoU between two [x_min, y_min, x_max, y_max] boxes (any coord system)."""
    x0 = max(box_a[0], box_b[0])
    y0 = max(box_a[1], box_b[1])
    x1 = min(box_a[2], box_b[2])
    y1 = min(box_a[3], box_b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def match_findings_to_gt(
    predicted_findings: list[str],
    gt_labels: list[str],
) -> dict[str, Any]:
    """Soft-match predicted finding strings against GT disease labels.

    Uses case-insensitive substring matching: a predicted finding like
    "bilateral pleural effusion" matches GT label "Effusion".
    """
    gt_set = {lbl.lower() for lbl in gt_labels if lbl.lower() != "no finding"}
    pred_lower = [f.lower() for f in predicted_findings]

    true_pos = set()
    matched_preds = set()
    for gt_label in gt_set:
        for i, pred in enumerate(pred_lower):
            if gt_label in pred or any(word in pred for word in gt_label.split("_")):
                true_pos.add(gt_label)
                matched_preds.add(i)
                break

    false_neg = gt_set - true_pos
    false_pos_count = len(pred_lower) - len(matched_preds)

    precision = len(true_pos) / max(1, len(matched_preds) + false_pos_count)
    recall = len(true_pos) / max(1, len(gt_set))
    f1 = 2 * precision * recall / max(1e-9, precision + recall)

    return {
        "gt_labels": sorted(gt_set),
        "true_positives": sorted(true_pos),
        "false_negatives": sorted(false_neg),
        "unmatched_predictions": false_pos_count,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def match_bboxes(
    predicted_rois: list[dict],
    gt_bboxes: list[dict],
    iou_threshold: float = 0.1,
) -> dict[str, Any]:
    """Match predicted ROI bboxes to GT bboxes and compute IoU scores.

    Uses a generous IoU threshold (0.1) because GPT-4o provides rough
    localization, not pixel-precise boxes.
    """
    pred_boxes = []
    for roi in predicted_rois:
        bbox = roi.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            pred_boxes.append({"label": roi.get("label", ""), "bbox": bbox})

    matches = []
    unmatched_gt = list(range(len(gt_bboxes)))
    unmatched_pred = list(range(len(pred_boxes)))

    iou_matrix = np.zeros((len(pred_boxes), len(gt_bboxes)))
    for i, pred in enumerate(pred_boxes):
        for j, gt in enumerate(gt_bboxes):
            iou_matrix[i, j] = compute_iou(pred["bbox"], gt["bbox_fractional"])

    while iou_matrix.size > 0:
        best = np.unravel_index(np.argmax(iou_matrix), iou_matrix.shape)
        best_iou = iou_matrix[best]
        if best_iou < iou_threshold:
            break
        i, j = int(best[0]), int(best[1])
        matches.append({
            "pred_label": pred_boxes[i]["label"],
            "gt_label": gt_bboxes[j]["label"],
            "pred_bbox": pred_boxes[i]["bbox"],
            "gt_bbox": gt_bboxes[j]["bbox_fractional"],
            "iou": round(float(best_iou), 4),
        })
        if i in unmatched_pred:
            unmatched_pred.remove(i)
        if j in unmatched_gt:
            unmatched_gt.remove(j)
        iou_matrix[i, :] = -1
        iou_matrix[:, j] = -1

    mean_iou = float(np.mean([m["iou"] for m in matches])) if matches else 0.0

    return {
        "n_predicted": len(pred_boxes),
        "n_ground_truth": len(gt_bboxes),
        "n_matched": len(matches),
        "matches": matches,
        "unmatched_gt_indices": unmatched_gt,
        "unmatched_pred_indices": unmatched_pred,
        "mean_iou": round(mean_iou, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════
# § 3  fastMRI reconstruction quality (SSIM / PSNR / NMSE)
# ═══════════════════════════════════════════════════════════════════════════

def fastmri_reconstruction_metrics(h5_path: Path) -> dict[str, Any]:
    """Compare our kspace→image reconstruction against the GT reconstruction.

    For H5 files that contain both kspace and a ground truth reconstruction
    (reconstruction_rss or reconstruction_esc), we reconstruct from kspace
    using our _rss_from_kspace pipeline and compare against the stored GT.
    """
    import h5py
    from app.services.image_processing import _rss_from_kspace, _percentile_normalize

    with h5py.File(h5_path, "r") as f:
        has_kspace = "kspace" in f
        has_gt_rss = "reconstruction_rss" in f
        has_gt_esc = "reconstruction_esc" in f

        if not has_kspace or not (has_gt_rss or has_gt_esc):
            return {"skipped": True, "reason": "missing kspace or GT reconstruction"}

        kspace = np.asarray(f["kspace"])
        if has_gt_rss:
            gt_recon = np.asarray(f["reconstruction_rss"], dtype=np.float32)
            gt_key = "reconstruction_rss"
        else:
            gt_recon = np.asarray(f["reconstruction_esc"], dtype=np.float32)
            gt_key = "reconstruction_esc"

    our_recon = _rss_from_kspace(kspace).astype(np.float32)

    if our_recon.shape != gt_recon.shape:
        min_slices = min(our_recon.shape[0], gt_recon.shape[0])
        min_h = min(our_recon.shape[-2], gt_recon.shape[-2])
        min_w = min(our_recon.shape[-1], gt_recon.shape[-1])
        our_recon = our_recon[:min_slices, :min_h, :min_w]
        gt_recon = gt_recon[:min_slices, :min_h, :min_w]

    mse_val = float(np.mean((gt_recon - our_recon) ** 2))
    nmse_val = float(np.linalg.norm(gt_recon - our_recon) ** 2 /
                      max(1e-10, np.linalg.norm(gt_recon) ** 2))
    maxval = float(gt_recon.max())

    psnr_val = float(peak_signal_noise_ratio(
        gt_recon, our_recon, data_range=maxval,
    ))

    ssim_vals = []
    for s in range(gt_recon.shape[0]):
        ssim_vals.append(structural_similarity(
            gt_recon[s], our_recon[s], data_range=maxval,
        ))
    ssim_val = float(np.mean(ssim_vals))

    gt_norm = _percentile_normalize(gt_recon[gt_recon.shape[0] // 2])
    our_norm = _percentile_normalize(our_recon[our_recon.shape[0] // 2])

    return {
        "skipped": False,
        "gt_key": gt_key,
        "shape": list(gt_recon.shape),
        "mse": round(mse_val, 6),
        "nmse": round(nmse_val, 6),
        "psnr_db": round(psnr_val, 2),
        "ssim": round(ssim_val, 4),
    }


def evaluate_fastmri_preprocessing(fastmri_dir: Path = _FASTMRI_DIR) -> list[dict]:
    """Run reconstruction metrics on all fastMRI fixture H5 files with GT."""
    results = []
    for h5_path in sorted(fastmri_dir.rglob("*.h5")):
        rel = str(h5_path.relative_to(fastmri_dir))
        metrics = fastmri_reconstruction_metrics(h5_path)
        metrics["file"] = rel
        results.append(metrics)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# § 4  End-to-end skill evaluation
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class EvalResult:
    image: str
    gt_labels: list[str]
    gt_bboxes: list[dict]
    draft: dict
    finding_metrics: dict
    bbox_metrics: dict
    urgency_predicted: str
    urgency_appropriate: bool | None = None
    errors: list[str] = field(default_factory=list)


def evaluate_skill_on_nih(
    images_dir: Path = NIH_IMAGES_DIR,
    verbose: bool = False,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Run the imaging_report skill on NIH chest X-rays and score against GT."""
    from app.skills.imaging_report.skill import ImagingReportSkill
    from app.skills.base import SkillInput

    all_labels = load_nih_labels()
    all_bboxes = load_nih_bboxes()
    skill = ImagingReportSkill(model_override=model_override)

    image_files = sorted(
        p for p in images_dir.glob("*.png")
        if "_prepared" not in p.name and "_annotated" not in p.name
    )
    if not image_files:
        return {"error": f"No PNG images found in {images_dir}"}

    results: list[dict] = []
    agg_finding = {"precision": [], "recall": [], "f1": []}
    agg_bbox = {"mean_iou": [], "n_matched": 0, "n_gt": 0, "n_pred": 0}

    for img_path in image_files:
        filename = img_path.name
        gt_labels = all_labels.get(filename, ["No Finding"])
        gt_bbox_list = all_bboxes.get(filename, [])

        if verbose:
            print(f"\n{'='*60}")
            print(f"Image: {filename}")
            print(f"  GT labels:  {gt_labels}")
            print(f"  GT bboxes:  {len(gt_bbox_list)}")

        patient_context = {
            "modality_hint": "xray",
            "history": f"Evaluate for: {', '.join(gt_labels)}",
        }
        inp = SkillInput(
            image_path=str(img_path),
            text="",
            context=patient_context,
        )

        errors = []
        try:
            result = skill.run(inp)
            draft = result.draft
        except Exception as e:
            errors.append(str(e))
            draft = {"findings": [], "regions_of_interest": [], "urgency": "routine"}

        findings = draft.get("findings", [])
        rois = draft.get("regions_of_interest", [])
        urgency = draft.get("urgency", "routine")

        finding_metrics = match_findings_to_gt(findings, gt_labels)
        bbox_metrics = match_bboxes(rois, gt_bbox_list)

        has_serious = any(
            lbl in gt_labels
            for lbl in ["Pneumothorax", "Mass", "Pneumonia", "Infiltrate"]
        )
        urgency_appropriate = None
        if has_serious:
            urgency_appropriate = urgency in ("soon", "urgent")
        elif gt_labels == ["No Finding"]:
            urgency_appropriate = urgency == "routine"

        agg_finding["precision"].append(finding_metrics["precision"])
        agg_finding["recall"].append(finding_metrics["recall"])
        agg_finding["f1"].append(finding_metrics["f1"])
        agg_bbox["mean_iou"].append(bbox_metrics["mean_iou"])
        agg_bbox["n_matched"] += bbox_metrics["n_matched"]
        agg_bbox["n_gt"] += bbox_metrics["n_ground_truth"]
        agg_bbox["n_pred"] += bbox_metrics["n_predicted"]

        entry = {
            "image": filename,
            "gt_labels": gt_labels,
            "n_gt_bboxes": len(gt_bbox_list),
            "predicted_findings": findings,
            "predicted_rois": rois,
            "predicted_urgency": urgency,
            "urgency_appropriate": urgency_appropriate,
            "finding_metrics": finding_metrics,
            "bbox_metrics": bbox_metrics,
            "errors": errors,
        }
        results.append(entry)

        if verbose:
            print(f"  Predicted findings: {findings}")
            print(f"  Finding P/R/F1: {finding_metrics['precision']}/{finding_metrics['recall']}/{finding_metrics['f1']}")
            print(f"  Predicted ROIs: {len(rois)}, Matched: {bbox_metrics['n_matched']}, Mean IoU: {bbox_metrics['mean_iou']}")
            print(f"  Urgency: {urgency} (appropriate: {urgency_appropriate})")
            if errors:
                print(f"  ERRORS: {errors}")

    n = len(results)
    summary = {
        "n_images": n,
        "finding_detection": {
            "mean_precision": round(np.mean(agg_finding["precision"]), 3),
            "mean_recall": round(np.mean(agg_finding["recall"]), 3),
            "mean_f1": round(np.mean(agg_finding["f1"]), 3),
        },
        "bbox_localization": {
            "total_gt_boxes": agg_bbox["n_gt"],
            "total_pred_boxes": agg_bbox["n_pred"],
            "total_matched": agg_bbox["n_matched"],
            "detection_rate": round(agg_bbox["n_matched"] / max(1, agg_bbox["n_gt"]), 3),
            "mean_iou_when_matched": round(
                float(np.mean([m for m in agg_bbox["mean_iou"] if m > 0])) if any(m > 0 for m in agg_bbox["mean_iou"]) else 0, 4
            ),
        },
        "urgency_assessment": {
            "n_assessed": sum(1 for r in results if r["urgency_appropriate"] is not None),
            "n_appropriate": sum(1 for r in results if r["urgency_appropriate"] is True),
            "accuracy": round(
                sum(1 for r in results if r["urgency_appropriate"] is True)
                / max(1, sum(1 for r in results if r["urgency_appropriate"] is not None)),
                3,
            ),
        },
    }

    return {"summary": summary, "per_image": results}


def _print_nih_summary(s: dict) -> None:
    print(f"\n{'─'*40}")
    print("FINDING DETECTION")
    print(f"  Precision: {s['finding_detection']['mean_precision']}")
    print(f"  Recall:    {s['finding_detection']['mean_recall']}")
    print(f"  F1:        {s['finding_detection']['mean_f1']}")
    print(f"\nBBOX LOCALIZATION")
    print(f"  GT boxes:       {s['bbox_localization']['total_gt_boxes']}")
    print(f"  Predicted:      {s['bbox_localization']['total_pred_boxes']}")
    print(f"  Matched:        {s['bbox_localization']['total_matched']}")
    print(f"  Detection rate: {s['bbox_localization']['detection_rate']}")
    print(f"  Mean IoU:       {s['bbox_localization']['mean_iou_when_matched']}")
    print(f"\nURGENCY ASSESSMENT")
    print(f"  Accuracy: {s['urgency_assessment']['accuracy']} "
          f"({s['urgency_assessment']['n_appropriate']}/{s['urgency_assessment']['n_assessed']})")


def benchmark_models(
    models: list[str],
    images_dir: Path = NIH_IMAGES_DIR,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run the evaluation across multiple models and produce a comparison."""
    all_results: dict[str, Any] = {}

    for model in models:
        print(f"\n{'='*60}")
        print(f"  MODEL: {model}")
        print(f"{'='*60}")
        try:
            result = evaluate_skill_on_nih(
                images_dir=images_dir,
                verbose=verbose,
                model_override=model,
            )
            all_results[model] = result
            _print_nih_summary(result["summary"])
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results[model] = {"error": str(e)}

    # Print comparison table
    print(f"\n{'='*60}")
    print("MODEL COMPARISON")
    print(f"{'='*60}")
    header = f"{'Model':<20} {'Prec':>6} {'Rec':>6} {'F1':>6} {'BBox%':>6} {'IoU':>6} {'Urg%':>6}"
    print(header)
    print("─" * len(header))

    for model in models:
        r = all_results.get(model, {})
        if "error" in r:
            print(f"{model:<20} {'ERROR':>6}")
            continue
        s = r["summary"]
        fd = s["finding_detection"]
        bb = s["bbox_localization"]
        ua = s["urgency_assessment"]
        print(
            f"{model:<20} "
            f"{fd['mean_precision']:>6.3f} "
            f"{fd['mean_recall']:>6.3f} "
            f"{fd['mean_f1']:>6.3f} "
            f"{bb['detection_rate']:>6.3f} "
            f"{bb['mean_iou_when_matched']:>6.4f} "
            f"{ua['accuracy']:>6.3f}"
        )

    return all_results


# ═══════════════════════════════════════════════════════════════════════════
# § 5  CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Evaluate imaging_report skill")
    parser.add_argument("--images-dir", type=Path, default=NIH_IMAGES_DIR)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--skip-nih", action="store_true")
    parser.add_argument("--skip-fastmri", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--models", nargs="+", default=None,
        help="Benchmark multiple models (e.g. --models gpt-4o gpt-4.1 gpt-4.1-mini)",
    )
    args = parser.parse_args()

    output_dir = args.output or (_NIH_DIR / "eval_results")
    output_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {}

    if args.models:
        # Multi-model benchmark mode
        benchmark = benchmark_models(
            models=args.models,
            images_dir=args.images_dir,
            verbose=args.verbose,
        )
        report["model_benchmark"] = benchmark

        bench_output = output_dir / "model_benchmark.json"
        with open(bench_output, "w") as f:
            json.dump(benchmark, f, indent=2, default=str)
        print(f"\nBenchmark results: {bench_output}")

    elif not args.skip_nih:
        print("=" * 60)
        print("NIH Chest X-ray Evaluation")
        print("=" * 60)
        nih_results = evaluate_skill_on_nih(args.images_dir, verbose=args.verbose)
        report["nih_chest_xray"] = nih_results
        _print_nih_summary(nih_results["summary"])

        nih_output = output_dir / "nih_eval_results.json"
        with open(nih_output, "w") as f:
            json.dump(nih_results, f, indent=2, default=str)
        print(f"\nDetailed results: {nih_output}")

    if not args.skip_fastmri and not args.models:
        print(f"\n{'='*60}")
        print("fastMRI Reconstruction Quality")
        print("=" * 60)
        fastmri_results = evaluate_fastmri_preprocessing()
        report["fastmri_reconstruction"] = fastmri_results

        evaluated = [r for r in fastmri_results if not r.get("skipped")]
        skipped = [r for r in fastmri_results if r.get("skipped")]

        if evaluated:
            mean_ssim = np.mean([r["ssim"] for r in evaluated])
            mean_psnr = np.mean([r["psnr_db"] for r in evaluated])
            mean_nmse = np.mean([r["nmse"] for r in evaluated])

            print(f"\n  Files evaluated: {len(evaluated)}")
            print(f"  Files skipped:   {len(skipped)} (no GT reconstruction)")
            print(f"  Mean SSIM:       {mean_ssim:.4f}")
            print(f"  Mean PSNR:       {mean_psnr:.2f} dB")
            print(f"  Mean NMSE:       {mean_nmse:.6f}")

            for r in evaluated:
                if args.verbose:
                    print(f"\n  {r['file']}:")
                    print(f"    SSIM={r['ssim']:.4f}  PSNR={r['psnr_db']:.2f}dB  NMSE={r['nmse']:.6f}")

            report["fastmri_summary"] = {
                "n_evaluated": len(evaluated),
                "n_skipped": len(skipped),
                "mean_ssim": round(float(mean_ssim), 4),
                "mean_psnr_db": round(float(mean_psnr), 2),
                "mean_nmse": round(float(mean_nmse), 6),
            }
        else:
            print("  No files with both kspace and GT reconstruction found.")

        fastmri_output = output_dir / "fastmri_eval_results.json"
        with open(fastmri_output, "w") as f:
            json.dump(fastmri_results, f, indent=2, default=str)
        print(f"\n  Detailed results: {fastmri_output}")

    full_output = output_dir / "full_eval_report.json"
    with open(full_output, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nFull report: {full_output}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    main()
