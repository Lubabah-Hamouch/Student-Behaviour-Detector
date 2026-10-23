# Known limitations and evaluation notes

This document records the constraints of the dataset and the current model (`models/best.pt`, run `full_run_v1`), and what the evaluation numbers do and do not support. All metrics below are copied from `results/metrics_summary.json`.

## Summary

- The dataset is small: 5 source videos of one classroom, about 425 labelled frames. Metrics are measured on one held-out video per split, so they are noisy and should be read as indicative, not precise.
- Three of the five classes (`concentrating`, `hand_raised`, `phone`) are detected reasonably well on the held-out test video. `distracted` is weak, and `sleeping` fails on the test video (test precision and recall are 0.000 at the default operating point, mAP50 0.216).
- The `sleeping` failure is a data-coverage problem: the training footage contains almost no head-down-on-desk sleeping, which is the pose that makes up about 86% of the test video's `sleeping` labels. More varied sleeping footage is the fix. The label review found no clear evidence of random labeling errors, but the observed labels use a broader definition of `sleeping` than the original annotation guide (see section 2).

## 1. Dataset and split

**Source data.** Five videos (68 to 95 s each) recorded in the same classroom with the same camera position, sampled at 1 frame per second (`extract-images.py`). After dropping 5 frames that have no valid boxes, 425 labelled frames remain. Frames are 832 x 464 pixels. The frames and videos show real students, so they are not included in the public repository; the label files, `classes.txt` and the frame-to-video mapping are.

**Split by whole video.** `scripts/prepare_dataset.py` assigns entire videos to a split:

| Split | Source video | Frames |
|---|---|---|
| train | handraising, concentrating, telephone | 268 original (+154 augmented copies = 422) |
| val | Handraise+tel | 90 |
| test | sleeping+variety | 67 |

Class balancing augmentation is applied to the train split only.

**Why not a random frame-level split.** Frames sampled at 1 fps from one continuous recording are near-duplicates of their neighbours (same people, same pose, same lighting). With a random split, almost every validation or test frame has a nearly identical twin in training, so the model is partly being scored on frames it has effectively seen. The earlier pipeline also augmented the dataset before splitting, so augmented copies of one frame could land in different splits. Both effects inflate metrics. Splitting by whole video removes both.

**What the split cannot remove.** All videos show the same classroom, and many of the same students appear in several of them. The metrics therefore estimate performance on new footage of this classroom, not on other rooms, cameras or cohorts.

**Why this particular 3 / 1 / 1 assignment.** Every video contains most classes (each frame shows many students), but only two videos contain all five classes in meaningful numbers (Handraise+tel and sleeping+variety). They were used as val and test so that both have at least 13 instances of every class. The cost is that the training set loses its two most varied videos.

**Boxes per class (original frames, before augmentation):**

| Class | train | val | test |
|---|---|---|---|
| distracted | 301 | 173 | 173 |
| concentrating | 1841 | 445 | 324 |
| hand_raised | 143 | 118 | 39 |
| phone | 188 | 205 | 33 |
| sleeping | 157 | 13 | 118 |

`concentrating` is much more frequent than the other classes. Balancing is done by augmenting images that contain minority classes (target 0.55 x the largest class, counted in images), so box counts remain imbalanced after augmentation.

## 2. The `sleeping` class: a data-coverage gap

**Observation.** On the test video the `sleeping` class has mAP50 0.216 and precision and recall of 0.000 (Ultralytics reports precision and recall at a single confidence operating point, chosen from the F1 curve averaged over classes; mAP integrates over all thresholds, which is why mAP is non-zero while the point estimates are 0). On the validation video `sleeping` has only 13 instances, so it cannot be evaluated meaningfully there.

**Investigation.** All 157 `sleeping` boxes in the training videos and all 118 in the test video were reviewed manually as zoomed head crops, with a reference set of `concentrating` faces to calibrate what open eyes look like at this resolution. Each crop was recorded as eyes closed, eyes open, cannot tell, or eyes not visible (head down or occluded). This was a single-reviewer visual check, and the per-crop reads are not part of this repository.

| Group | Boxes | Eyes look closed | Eyes look open | Cannot tell | Eyes not visible |
|---|---|---|---|---|---|
| train: handraising + concentrating | 110 | 37 | 7 | 53 | 13 |
| train: telephone | 47 | 1 | 2 | 25 | 19 |
| **train total** | **157** | **38 (24%)** | **9 (6%)** | **78 (50%)** | **32 (20%)** |
| **test: sleeping+variety** | **118** | **4 (3%)** | **5 (4%)** | **8 (7%)** | **101 (86%)** |

Per-crop reads: [`docs/eye_state_review.csv`](eye_state_review.csv) (one row per reviewed box; `image` is a frame name in `data/dataset/images/`, which is not included in the public repository for privacy, and `label_line` is the 0-based line of the box in the matching `data/dataset/labels/` file; the validation video was not reviewed).

**Findings.**

- The training `sleeping` examples are mostly **upright dozing**: head up, eyes closed or heavy-lidded. Where eye state could be judged, closed eyes outnumber open eyes 38 to 9. By manual count, about 70% of the front-row training boxes (roughly 76 of 110) are the same student, who sits in the same seat in the handraising and concentrating videos. The rest come from a few other students, mainly in the telephone video.
- The training videos contain **almost no head-down-on-desk sleeping.** The 32 training boxes with hidden eyes are mostly a student bowing his head in the telephone video (which could be sleeping or looking at a phone; this cannot be determined from the frames) and a few head-down students in the front row.
- The test video is **about 86% head-down-on-desk sleeping** (head on folded arms), with the face hidden. This is the pose that dominates the test set and is nearly absent from training.
- The model therefore learned a narrow slice of the `sleeping` appearance (upright, lowered lids, a few individuals) and was tested on a different slice it rarely saw.
- **The review did not find clear evidence of systematic mislabeling.** The test labels match the head-down definition of sleeping, and the training labels match the upright-dozing definition for the crops where eye state is readable. A minority of crops look awake (9 of 157 in train, 5 of 118 in test), and half the training crops cannot be judged at this resolution (heads are about 80 px wide in the front row and about 37 px in the telephone video, so eyes are 3 to 10 px). Isolated label errors, or frames adjacent to a doze, cannot be ruled out. A single still also cannot separate a blink from a doze.
- **The written annotation guide and the observed labels use different definitions of `sleeping`.** The original annotation guide (written in French, not included in this repository) defines it strictly as "La tête est posée sur le bureau", "Les yeux semblent fermés" and "L'angle de la tête est supérieur à 45° vers le bas" (head resting on the desk, eyes appear closed, head angle more than 45° downward), whereas the observed training labels also cover upright dozing with eyes closed and the head up, which is a likely contributor to the difference between the training and test label patterns, alongside the video-content domain gap described above.

**What would fix it.** More training footage covering head-down sleeping across multiple people and sessions, so that both appearances of the class (head-down and upright dozing) are represented in training and evaluated on held-out people or videos. Higher-resolution footage would also make eye state checkable.

## 3. Small-data caveats

- **Test and validation sets are small.** Each split is one video: 67 test and 90 validation images. Per-class results rest on few instances: `hand_raised` has 39 test instances, `phone` has 33, and `sleeping` has 13 in validation. Differences of a few points between classes or runs are within noise. A single video also means a single set of people and behaviours.
- **Model selection is noisy.** Early stopping and best-checkpoint choice (best epoch 52, stopped at 72) use the validation video, whose `sleeping` class has 13 instances.
- **Distracted is a weak class.** Test mAP50 is 0.267 against 0.575 on validation. This class is visually less distinct than the others.
- **Few independent samples per behaviour.** Many frames show the same student in the same pose across consecutive seconds, so the number of independent examples is smaller than the image count suggests.

## 4. Results

Model: YOLOv8m (`yolov8m.pt` pretrained), 72 of 100 epochs (early stopping, patience 20), batch 8, image size 640, AdamW with lr0 = 0.001, seed 42, training time 35m19s. Evaluated with `best.pt` using Ultralytics defaults (conf 0.001, IoU 0.7).

**Overall**

| Split | mAP50 | mAP50-95 | Precision | Recall |
|---|---|---|---|---|
| val | 0.620 | 0.326 | 0.541 | 0.655 |
| test | 0.502 | 0.278 | 0.482 | 0.437 |

**Per class, validation (Handraise+tel)**

| Class | Instances | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| distracted | 173 | 0.357 | 0.584 | 0.575 | 0.287 |
| concentrating | 445 | 0.680 | 0.733 | 0.761 | 0.418 |
| hand_raised | 118 | 0.694 | 0.839 | 0.820 | 0.412 |
| phone | 205 | 0.741 | 0.811 | 0.768 | 0.431 |
| sleeping | 13 | 0.234 | 0.308 | 0.176 | 0.083 |

**Per class, test (sleeping+variety)**

| Class | Instances | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|---|
| distracted | 173 | 0.290 | 0.309 | 0.267 | 0.122 |
| concentrating | 324 | 0.695 | 0.634 | 0.728 | 0.368 |
| hand_raised | 39 | 0.692 | 0.846 | 0.845 | 0.554 |
| phone | 33 | 0.733 | 0.394 | 0.455 | 0.272 |
| sleeping | 118 | 0.000 | 0.000 | 0.216 | 0.074 |

## 5. Comparison with earlier results

These numbers are not comparable to the figures reported in the original notebook (validation mAP50 of about 0.77 in its training log). That notebook split randomly at frame level after augmenting, so near-duplicate and augmented frames leaked between train and validation, which inflates its scores; its saved output contains no test-set metrics.

## 6. Reproducing and extending

- `scripts/prepare_dataset.py` rebuilds the split (`--dry-run` shows the plan without writing).
- `scripts/train.py` trains and evaluates, and writes `results/metrics_summary.json`.
- With more footage, the most informative next step is leave-one-video-out evaluation, which gives one score per held-out video instead of a single noisy test number.

## 7. Data and model usage

- The code in this repository is released under the MIT License (see `LICENSE`).
- The training frames and source videos show real students and are not included. The label files, class list and frame-to-video mapping are included.
- `models/best.pt` was trained on that private footage. The MIT license covers the code, not the weights or the underlying data, and the weights should not be assumed freely redistributable. Check with the author before redistributing them or using them outside this project.
- The model was fitted to one classroom, so it should not be used to make decisions about individual students (see sections 1 to 3).
