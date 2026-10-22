"""Build the train/val/test split used for training.

Local replacement for the data-prep cells (6 and 10) of notebooks/YOLO_Controle.ipynb.

What it does:
  1. Reads the labelled frames in data/dataset/ and looks up each frame's source video
     in data/raw_frames/frame_mapping.txt.
  2. Assigns whole videos to train / val / test (VIDEO_SPLIT below), so no two frames
     from the same video can land in different splits.
  3. Copies images and cleaned labels into data/dataset_split/{train,val,test}/{images,labels}.
  4. Balances classes by augmenting the TRAIN split only (val/test stay untouched).
  5. Rewrites data/dataset/data.yaml to point at the split folders.

The source dataset (data/dataset/) is only read, never modified.

Usage (from the project root, inside the project venv):
    python scripts/prepare_dataset.py --dry-run     # show the split plan, write nothing
    python scripts/prepare_dataset.py               # build the split
    python scripts/prepare_dataset.py --overwrite   # rebuild an existing split
"""
import argparse
import csv
import os
import random
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import albumentations as A
import cv2
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

DEFAULT_IMAGES = DATA_DIR / "dataset" / "images"
DEFAULT_LABELS = DATA_DIR / "dataset" / "labels"
DEFAULT_CLASSES = DATA_DIR / "dataset" / "classes.txt"
DEFAULT_MAPPING = DATA_DIR / "raw_frames" / "frame_mapping.txt"
DEFAULT_OUTPUT = DATA_DIR / "dataset_split"
DEFAULT_YAML = DATA_DIR / "dataset" / "data.yaml"

# Which source videos (the `source_video` column of frame_mapping.txt) go to which split.
# Every video must appear exactly once. Chosen so that val and test each contain all 5
# classes; see the discussion in the PR/chat for the trade-offs of this 3/1/1 split.
VIDEO_SPLIT = {
    "train": ["handraising", "concentrating", "telephone"],
    "val": ["Handraise+tel"],
    "test": ["sleeping+variety"],
}
SPLITS = ("train", "val", "test")

TARGET_RATIO = 0.55  # minority classes are augmented up to this fraction of the largest class
SEED = 42
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


@dataclass
class Sample:
    stem: str
    image_path: Path
    video: str
    boxes: list  # [(class_id, x_center, y_center, width, height)], normalised YOLO format


# --------------------------------------------------------------------------- reading

def load_class_names(path):
    names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not names:
        raise SystemExit(f"No class names found in {path}")
    return names


def load_frame_mapping(path):
    """image stem -> source video name."""
    with open(path, newline="", encoding="utf-8") as f:
        return {Path(row["image_name"]).stem: row["source_video"] for row in csv.DictReader(f)}


def read_label(path, num_classes):
    """Parse a YOLO label file. Returns (boxes, number_of_malformed_lines).

    Accepts class ids written as floats ('3.0'), clamps coordinates to [0, 1] and drops
    lines that are malformed, have an unknown class id, or have an empty box.
    """
    boxes, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            cls = int(float(parts[0]))
            x, y, w, h = (min(max(float(v), 0.0), 1.0) for v in parts[1:5])
        except ValueError:
            bad += 1
            continue
        if not 0 <= cls < num_classes or w <= 0 or h <= 0:
            bad += 1
            continue
        boxes.append((cls, x, y, w, h))
    return boxes, bad


def collect_samples(images_dir, labels_dir, mapping, num_classes, keep_unlabeled):
    samples, unlabeled, unmapped, bad_lines = [], [], [], 0
    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    for img in images:
        video = mapping.get(img.stem)
        if video is None:
            unmapped.append(img.name)
            continue
        label_path = labels_dir / f"{img.stem}.txt"
        boxes = []
        if label_path.exists():
            boxes, bad = read_label(label_path, num_classes)
            bad_lines += bad
        if not boxes:
            unlabeled.append(img.name)
            if not keep_unlabeled:
                continue
        samples.append(Sample(img.stem, img, video, boxes))
    if unmapped:
        raise SystemExit(f"{len(unmapped)} images have no row in the frame mapping, cannot assign them "
                         f"to a video: {unmapped[:5]}")
    return samples, unlabeled, bad_lines


# --------------------------------------------------------------------------- splitting

def assign_splits(samples, video_split):
    video_to_split = {}
    for split, videos in video_split.items():
        for video in videos:
            if video in video_to_split:
                raise SystemExit(f"Video '{video}' is assigned to more than one split")
            video_to_split[video] = split
    present = {s.video for s in samples}
    if present - set(video_to_split):
        raise SystemExit(f"Videos missing from VIDEO_SPLIT: {sorted(present - set(video_to_split))}")
    if set(video_to_split) - present:
        raise SystemExit(f"VIDEO_SPLIT lists videos with no labelled frames: "
                         f"{sorted(set(video_to_split) - present)}")
    by_split = {split: [] for split in SPLITS}
    for s in samples:
        by_split[video_to_split[s.video]].append(s)
    return by_split


# --------------------------------------------------------------------------- writing

def format_label(boxes):
    return "".join(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n" for c, x, y, w, h in boxes)


def prepare_output_dirs(output, overwrite):
    existing = [output / s for s in SPLITS if (output / s).exists() and any((output / s).rglob("*"))]
    if existing and not overwrite:
        raise SystemExit(f"{output} already contains a split. Re-run with --overwrite to rebuild it.")
    for split in SPLITS:
        shutil.rmtree(output / split, ignore_errors=True)
        (output / split / "images").mkdir(parents=True)
        (output / split / "labels").mkdir(parents=True)


def copy_split(samples, output, split):
    for s in samples:
        shutil.copy2(s.image_path, output / split / "images" / s.image_path.name)
        (output / split / "labels" / f"{s.stem}.txt").write_text(format_label(s.boxes), encoding="utf-8")


# --------------------------------------------------------------------------- augmentation

def build_augmentation_pipeline(seed):
    """Same augmentations as the notebook, ported to the albumentations 2.x API.

    Ported parameters (checked against albumentations 2.0.8):
      GaussNoise       var_limit=(5, 25) [pixel^2]        -> std_range=(0.01, 0.02)
                       (std of 2.2-5.0 grey levels, expressed as a fraction of 255)
      ImageCompression quality_lower=75, quality_upper=95 -> quality_range=(75, 95)
      ShiftScaleRotate shift_limit=0.03, scale_limit=0.1, rotate_limit=2
                                                          -> Affine(translate_percent=(-0.03, 0.03),
                                                                    scale=(0.9, 1.1), rotate=(-2, 2))
    No horizontal flip on purpose (it mirrors the scene).
    """
    return A.Compose(
        [
            A.OneOf([
                A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.15, p=1.0),
                A.RandomGamma(gamma_limit=(85, 115), p=1.0),
                A.HueSaturationValue(hue_shift_limit=5, sat_shift_limit=15, val_shift_limit=10, p=1.0),
            ], p=0.8),
            A.OneOf([
                A.GaussNoise(std_range=(0.01, 0.02), p=1.0),
                A.GaussianBlur(blur_limit=(3, 5), p=1.0),
                A.ISONoise(color_shift=(0.01, 0.05), intensity=(0.1, 0.3), p=1.0),
            ], p=0.3),
            A.Affine(
                scale=(0.9, 1.1),
                translate_percent=(-0.03, 0.03),
                rotate=(-2, 2),
                border_mode=cv2.BORDER_CONSTANT,
                fill=0,
                p=0.4,
            ),
            A.ImageCompression(quality_range=(75, 95), p=0.3),
        ],
        # clip=True fixes the "x_min = -5e-07 not in [0, 1]" failures seen in the notebook run
        bbox_params=A.BboxParams(format="yolo", label_fields=["class_labels"],
                                 min_visibility=0.4, clip=True),
        seed=seed,
    )


def augment_sample(sample, aug_stem, pipeline, output, required_cls):
    """Write one augmented copy of `sample` into the train split. Returns True on success.

    Fails (returns False, nothing written) if the image cannot be read or if the augmented
    boxes no longer contain `required_cls`.
    """
    image = cv2.imread(str(sample.image_path))
    if image is None:
        return False
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    try:
        out = pipeline(image=image,
                       bboxes=[list(b[1:]) for b in sample.boxes],
                       class_labels=[b[0] for b in sample.boxes])
    except Exception as exc:
        print(f"   augmentation failed for {sample.stem}: {exc}")
        return False
    if required_cls not in out["class_labels"]:
        return False
    boxes = [(int(c), *(min(max(float(v), 0.0), 1.0) for v in box))
             for box, c in zip(out["bboxes"], out["class_labels"])]
    ext = sample.image_path.suffix
    cv2.imwrite(str(output / "train" / "images" / f"{aug_stem}{ext}"),
                cv2.cvtColor(out["image"], cv2.COLOR_RGB2BGR))
    (output / "train" / "labels" / f"{aug_stem}.txt").write_text(format_label(boxes), encoding="utf-8")
    return True


def balance_train(train, output, names, target_ratio, rng, pipeline):
    """Augment minority classes of the train split up to target_ratio * (largest class).

    Counts are in images containing the class, as in the notebook, and are taken once
    before augmenting. Returns [(augmented_stem, source_stem)].
    """
    print("\nBalancing the train split (images containing each class):")
    class_samples = defaultdict(list)
    for s in train:
        for cls in {b[0] for b in s.boxes}:
            class_samples[cls].append(s)
    max_count = max(len(v) for v in class_samples.values())
    target = int(max_count * target_ratio)
    print(f"   target per class: {target} images ({target_ratio} x largest class = {max_count})")

    created, counter = [], 0
    for cls, name in enumerate(names):
        pool = class_samples.get(cls, [])
        shortage = target - len(pool)
        if shortage <= 0:
            print(f"   {name:15} {len(pool):4d} images, no augmentation needed")
            continue
        if not pool:
            print(f"   {name:15} WARNING: no train images contain this class, cannot augment")
            continue
        generated = attempts = 0
        while generated < shortage and attempts < shortage * 3:
            attempts += 1
            src = rng.choice(pool)
            aug_stem = f"{src.stem}_aug_{counter:04d}"
            if augment_sample(src, aug_stem, pipeline, output, cls):
                created.append((aug_stem, src.stem))
                generated += 1
                counter += 1
        print(f"   {name:15} {len(pool):4d} images, generated {generated}/{shortage}")
    return created


# --------------------------------------------------------------------------- reporting

def tally_labels_dir(labels_dir, num_classes):
    return [read_label(p, num_classes)[0] for p in sorted(labels_dir.glob("*.txt"))]


def print_summary(split_boxes, names, aug_counts):
    """split_boxes: {split: [boxes_of_image, ...]}; one entry per image."""
    cols = "".join(f"{n[:13]:>14}" for n in names)
    for title, per_image in (("Instances (boxes) per class", False), ("Images containing each class", True)):
        print(f"\n{title}")
        print(f"{'split':8}{'images':>8}{'(aug)':>7}{cols}")
        for split in SPLITS:
            images = split_boxes[split]
            counts = Counter()
            for boxes in images:
                if per_image:
                    counts.update({b[0] for b in boxes})
                else:
                    counts.update(b[0] for b in boxes)
            row = "".join(f"{counts[i]:>14}" for i in range(len(names)))
            print(f"{split:8}{len(images):>8}{aug_counts.get(split, 0):>7}{row}")
    for split in ("val", "test"):
        seen = {b[0] for boxes in split_boxes[split] for b in boxes}
        missing = [names[i] for i in range(len(names)) if i not in seen]
        if missing:
            print(f"WARNING: {split} split has no instances of: {', '.join(missing)}")


def print_video_plan(by_split):
    print("\nVideo -> split assignment:")
    for split in SPLITS:
        counts = Counter(s.video for s in by_split[split])
        for video, n in counts.items():
            print(f"   {split:6} {video:18} {n:4d} frames")


def write_data_yaml(yaml_path, output, names):
    rel = Path(os.path.relpath(output, yaml_path.parent)).as_posix()
    data = {
        "train": f"{rel}/train/images",
        "val": f"{rel}/val/images",
        "test": f"{rel}/test/images",
        "nc": len(names),
        "names": dict(enumerate(names)),
    }
    header = ("# Generated by scripts/prepare_dataset.py\n"
              "# No 'path:' key on purpose: Ultralytics then resolves the split paths relative to this file.\n")
    yaml_path.write_text(header + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_manifest(output, by_split, created):
    with open(output / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "split", "source_video", "augmented_from"])
        videos = {}
        for split in SPLITS:
            for s in by_split[split]:
                videos[s.stem] = s.video
                writer.writerow([s.image_path.name, split, s.video, ""])
        for aug_stem, src_stem in created:
            writer.writerow([f"{aug_stem}.jpg", "train", videos[src_stem], src_stem])


# --------------------------------------------------------------------------- main

def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    p.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    p.add_argument("--classes", type=Path, default=DEFAULT_CLASSES)
    p.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--yaml", type=Path, default=DEFAULT_YAML, help="data.yaml to (re)write")
    p.add_argument("--target-ratio", type=float, default=TARGET_RATIO)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--no-balance", action="store_true", help="skip augmentation of the train split")
    p.add_argument("--keep-unlabeled", action="store_true",
                   help="keep images without boxes as background images (default: drop them)")
    p.add_argument("--overwrite", action="store_true", help="rebuild train/val/test if they already exist")
    p.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    return p.parse_args()


def main():
    args = parse_args()
    names = load_class_names(args.classes)
    print(f"Classes ({len(names)}): {', '.join(f'{i}={n}' for i, n in enumerate(names))}")

    mapping = load_frame_mapping(args.mapping)
    samples, unlabeled, bad_lines = collect_samples(args.images, args.labels, mapping, len(names),
                                                    args.keep_unlabeled)
    print(f"Usable images: {len(samples)}")
    if unlabeled:
        action = "kept as background" if args.keep_unlabeled else "dropped"
        print(f"   {len(unlabeled)} images without valid boxes, {action}: {', '.join(unlabeled)}")
    if bad_lines:
        print(f"   {bad_lines} malformed label lines ignored")

    by_split = assign_splits(samples, VIDEO_SPLIT)
    print_video_plan(by_split)

    if args.dry_run:
        print("\n--dry-run: split before augmentation, nothing written.")
        print_summary({s: [x.boxes for x in by_split[s]] for s in SPLITS}, names, {})
        return

    prepare_output_dirs(args.output, args.overwrite)
    for split in SPLITS:
        copy_split(by_split[split], args.output, split)

    created = []
    if not args.no_balance:
        pipeline = build_augmentation_pipeline(args.seed)
        created = balance_train(by_split["train"], args.output, names, args.target_ratio,
                                random.Random(args.seed), pipeline)

    write_manifest(args.output, by_split, created)
    write_data_yaml(args.yaml, args.output, names)
    print(f"\nWrote {args.output} and {args.yaml}")

    split_boxes = {s: tally_labels_dir(args.output / s / "labels", len(names)) for s in SPLITS}
    print_summary(split_boxes, names, {"train": len(created)})


if __name__ == "__main__":
    sys.exit(main())
