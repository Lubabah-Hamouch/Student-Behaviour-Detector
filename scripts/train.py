"""Train YOLOv8 on the split dataset and evaluate the best checkpoint on val and test.

Local replacement for the training (14) and evaluation (16) cells of notebooks/YOLO_Controle.ipynb.
Run scripts/prepare_dataset.py first: this script trains on data/dataset/data.yaml, which points
at data/dataset_split/.

What it does:
  1. Trains with Ultralytics into runs/<name>/ (weights, results.csv, plots).
  2. Copies the best checkpoint to models/best.pt.
  3. Runs val() on the val split and on the test split with that checkpoint.
  4. Writes a readable metrics_summary.json into the run folder and into results/.

Usage (from the project root, inside the project venv):
    python scripts/train.py                      # 100 epochs, batch 8, imgsz 640
    python scripts/train.py --epochs 2 --name smoke_test   # quick pipeline check
    python scripts/train.py --batch 16           # may run out of memory on an 8 GB GPU
"""
import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import torch
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = PROJECT_ROOT / "data" / "dataset" / "data.yaml"
RUNS_DIR = PROJECT_ROOT / "runs"
MODELS_DIR = PROJECT_ROOT / "models"
RESULTS_DIR = PROJECT_ROOT / "results"

DEFAULT_BATCH = 8
BATCH_WARN_ABOVE = 8  # yolov8m at 640 px is tight on an 8 GB GPU above this

# Augmentation settings carried over from the notebook (Ultralytics' own online augmentation).
AUGMENTATION = dict(
    hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
    degrees=10.0, translate=0.1, scale=0.9, shear=0.0, perspective=0.0,
    flipud=0.0, fliplr=0.5,
    mosaic=1.0, mixup=0.1, close_mosaic=10,
)


def fmt_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--model", default="yolov8m.pt",
                   help="pretrained weights; a bare name is stored in/downloaded to models/pretrained/")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--batch", type=int, default=DEFAULT_BATCH, help="-1 lets Ultralytics pick from free VRAM")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--patience", type=int, default=20, help="early-stopping patience in epochs")
    p.add_argument("--optimizer", default="AdamW")
    p.add_argument("--lr0", type=float, default=0.001,
                   help="initial learning rate. The notebook left this at 0.01, which is the SGD default and "
                        "~9x higher than Ultralytics' own AdamW choice for a run this size")
    p.add_argument("--workers", type=int, default=4, help="dataloader workers")
    p.add_argument("--cache", choices=["ram", "disk", "none"], default="ram",
                   help="cache decoded images (the whole dataset is ~54 MB of jpg)")
    p.add_argument("--device", default=None, help="e.g. 0 or cpu; default is GPU 0 if CUDA is available")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--name", default="student_behavior",
                   help="run name under runs/ (an existing name gets a numeric suffix, never overwritten)")
    return p.parse_args()


def resolve_device(requested):
    if requested is not None:
        return requested
    if torch.cuda.is_available():
        return 0
    raise SystemExit("CUDA is not available. Check the venv (torch must be the +cu118 build), "
                     "or pass --device cpu to train on the CPU (very slow).")


def resolve_pretrained(model_arg):
    """A bare file name lives in models/pretrained/ (Ultralytics downloads it there if missing)."""
    path = Path(model_arg)
    if path.parent == Path("."):
        path = MODELS_DIR / "pretrained" / path.name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def make_eta_callback():
    started = time.time()
    first_epoch_end = []

    def on_epoch_end(trainer):
        done = trainer.epoch + 1
        if done > trainer.epochs:  # Ultralytics fires this hook once more after the final validation
            return
        now = time.time()
        if not first_epoch_end:
            first_epoch_end.append(now)  # epoch 1 includes one-off warm-up, so it is left out of the rate
            print(f"[time] epoch 1/{trainer.epochs} | elapsed {fmt_duration(now - started)} (includes warm-up)")
            return
        per_epoch = (now - first_epoch_end[0]) / (done - 1)
        print(f"[time] epoch {done}/{trainer.epochs} | elapsed {fmt_duration(now - started)} | "
              f"{per_epoch:.1f}s/epoch | at most {fmt_duration(per_epoch * (trainer.epochs - done))} left "
              f"(early stopping may end sooner)")
    return on_epoch_end


def metrics_to_dict(m):
    """Flatten an Ultralytics DetMetrics object into plain numbers."""
    per_class = {}
    for pos, cls_idx in enumerate(m.ap_class_index):
        p, r, ap50, ap = m.box.class_result(pos)
        entry = {"precision": float(p), "recall": float(r), "mAP50": float(ap50), "mAP50-95": float(ap)}
        nt = getattr(m, "nt_per_class", None)
        if nt is not None:
            entry["instances"] = int(nt[int(cls_idx)])
        per_class[m.names[int(cls_idx)]] = entry
    return {
        "mAP50": float(m.box.map50),
        "mAP50-95": float(m.box.map),
        "precision": float(m.box.mp),
        "recall": float(m.box.mr),
        "per_class": per_class,
        "classes_without_instances": [n for i, n in m.names.items() if i not in set(map(int, m.ap_class_index))],
    }


def evaluate(best_path, args, device, save_dir, split):
    print(f"\n=== Evaluating best.pt on the {split} split ===")
    model = YOLO(str(best_path))
    metrics = model.val(data=str(args.data), split=split, imgsz=args.imgsz, batch=args.batch,
                        device=device, workers=args.workers, plots=True,
                        project=str(save_dir), name=f"eval_{split}", exist_ok=True)
    return metrics_to_dict(metrics)


def print_metrics_table(summary):
    print("\n=== Final metrics (best.pt) ===")
    print(f"{'split':6}{'mAP50':>9}{'mAP50-95':>10}{'precision':>11}{'recall':>9}")
    for split in ("val", "test"):
        m = summary[split]
        print(f"{split:6}{m['mAP50']:>9.3f}{m['mAP50-95']:>10.3f}{m['precision']:>11.3f}{m['recall']:>9.3f}")
    for split in ("val", "test"):
        print(f"\nPer class ({split}):  mAP50 / mAP50-95 / instances")
        for name, c in summary[split]["per_class"].items():
            print(f"   {name:15}{c['mAP50']:>7.3f}{c['mAP50-95']:>8.3f}{c.get('instances', '?'):>8}")
        if summary[split]["classes_without_instances"]:
            print(f"   no instances in this split: {', '.join(summary[split]['classes_without_instances'])}")


def main():
    args = parse_args()

    if not args.data.exists():
        raise SystemExit(f"{args.data} not found")
    if not (PROJECT_ROOT / "data" / "dataset_split" / "train" / "images").exists():
        raise SystemExit("data/dataset_split/ is missing. Run scripts/prepare_dataset.py first.")
    if args.batch > BATCH_WARN_ABOVE:
        print(f"NOTE: batch={args.batch} is above {BATCH_WARN_ABOVE}. yolov8m at {args.imgsz} px may run out of "
              f"GPU memory on an 8 GB card; if it does, re-run with --batch {BATCH_WARN_ABOVE}.")

    device = resolve_device(args.device)
    if device != "cpu":
        print(f"GPU: {torch.cuda.get_device_name(0)} | torch {torch.__version__}")
    print(f"Training {args.model} for up to {args.epochs} epochs | batch {args.batch} | imgsz {args.imgsz} | "
          f"{args.optimizer} lr0={args.lr0} | patience {args.patience}")

    model = YOLO(str(resolve_pretrained(args.model)))
    model.add_callback("on_fit_epoch_end", make_eta_callback())

    started = time.time()
    try:
        model.train(
            data=str(args.data),
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            patience=args.patience,
            optimizer=args.optimizer,
            lr0=args.lr0,
            cos_lr=True,
            workers=args.workers,
            cache=False if args.cache == "none" else args.cache,
            device=device,
            seed=args.seed,
            project=str(RUNS_DIR),
            name=args.name,
            exist_ok=False,
            **AUGMENTATION,
        )
    except torch.cuda.OutOfMemoryError:
        raise SystemExit(f"CUDA out of memory at batch {args.batch}. Re-run with a smaller --batch "
                         f"(for example --batch {max(args.batch // 2, 2)}).")
    train_seconds = time.time() - started

    trainer = model.trainer
    run_dir = Path(trainer.save_dir)
    best = Path(trainer.best)
    if not best.exists():
        raise SystemExit(f"Training finished but {best} was not found")

    MODELS_DIR.mkdir(exist_ok=True)
    shutil.copy2(best, MODELS_DIR / "best.pt")
    print(f"\nTraining took {fmt_duration(train_seconds)} ({trainer.epoch + 1} epochs). "
          f"Best weights copied to {MODELS_DIR / 'best.pt'}")

    summary = {
        "run": run_dir.name,
        "run_dir": run_dir.relative_to(PROJECT_ROOT).as_posix(),
        "finished": datetime.now().isoformat(timespec="seconds"),
        "model": args.model,
        "epochs_requested": args.epochs,
        "epochs_completed": trainer.epoch + 1,
        "training_time": fmt_duration(train_seconds),
        "batch": args.batch,
        "imgsz": args.imgsz,
        "optimizer": args.optimizer,
        "lr0": args.lr0,
        "patience": args.patience,
        "seed": args.seed,
        "best_weights": "models/best.pt",
        "val": evaluate(best, args, device, run_dir, "val"),
        "test": evaluate(best, args, device, run_dir, "test"),
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    text = json.dumps(summary, indent=2)
    (run_dir / "metrics_summary.json").write_text(text, encoding="utf-8")
    (RESULTS_DIR / "metrics_summary.json").write_text(text, encoding="utf-8")
    print_metrics_table(summary)
    print(f"\nMetrics written to {RESULTS_DIR / 'metrics_summary.json'} (copy in {run_dir})")


if __name__ == "__main__":
    sys.exit(main())
