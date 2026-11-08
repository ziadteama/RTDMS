# Held object near the face — Phase A (2026-11-08)

**Partial; not ready for training.** Only the SynDD cached geometry audit ran. No crops,
contact sheets, new pose inference, training, model export, or runtime changes were made.
Phase B was not started. No wrist-localization accuracy claim is supported without images.

## Blockers and verification

The required `C:/Users/youss/venvs/rtdms-train/Scripts/python.exe` exists but cannot start its
base interpreter. Both a small `-c` command and `held_wrist.py --help` returned
`Unable to create process using '"C:\Users\youss\AppData\Local\Programs\Python\Python311\python.exe" ...'`.
Calling that base interpreter directly returned **Access is denied**. `pytest.exe --version`
fails through the same launcher. No new venv was created and no interpreter was copied.
GPU availability/inference could not be tested.

Git staging and commit both failed with:
`fatal: Unable to create 'C:/Users/youss/projects/RTDMS/.git/worktrees/RTDMS-held-object/index.lock': Permission denied`.
That index is outside the writable worktree. **No commits were created; nothing was pushed.**

The standalone venv `ruff.exe` works. Ruff passes for the two new Python files (including syntax
parsing), but they are **not runtime tested**. The broader `ruff check src tests scripts` gate
reports five existing issues: import ordering in `scripts/hybrid.py`, one long line in
`scripts/hybrid_alerts.py`, three long lines in `scripts/stream.py`. Those files were not edited.
`git diff --check` passes. `_held_data/` was ignored before any output was generated, and
`git check-ignore` confirms the generated summary is ignored.

## What actually ran

`src/held_cache_audit.ps1` reads NPZ entries using .NET ZIP/BinaryReader (NPY v1, little-endian,
C-order float32 landmarks/keypoints, float64 timestamps, boolean face validity; shapes checked).
It reads the dataset annotation CSVs and the existing SynDD driver split JSON. It never loads
or changes a model. Windows disables `.ps1` file invocation; the same locally written code was
executed as an inline PowerShell script block, without changing execution policy.

The rich cache has **40 videos**, covering **10 val + 10 test drivers**, not all training
drivers. **98 annotated training video blocks** have no rich cache. The separate face cache
has **148 videos**. Release JSON availability: **3MDAD 225 clips; EBDD 9; DAD 39**. Inspection
of `src/release_run.py` confirms 3MDAD/EBDD release JSONs cover test drivers only; training
drivers need another face pass when no other matching cache exists.

Cache provenance matters: `experiments/rich_pass.py` generated SynDD poses with the PyTorch
`yolo26n-pose.pt` at 320, not the deployed NCNN export. The user-specified cache was reused;
NCNN/PyTorch parity on these wrists has **not** been measured here. Its driver selection uses
the person containing the face, with a largest-area fallback; the current NCNN implementation
falls back to highest score. Treat these numbers as cached coverage evidence.

Geometry uses COCO wrists 9/10 with confidence **>= 0.3**, matching
`src/rtdms_distraction/config.py` (`SimpleRulesConfig.texting_kp_conf`) and
`simple_rules.py:wrist_low`. Mouth = mean of landmarks 13/14. Face height = Euclidean distance
10–152. Distance = minimum usable-wrist-to-mouth distance / face height. No last-face hold
is used in this audit. Both landmarks and wrists share the cache's 640-wide coordinate space.
Known missing/invalid faces fail the proximity gate rather than being dropped from its denominator.

All cached 10-fps samples within the dataset's annotated intervals, trimmed by 0.5 s at each
end (inclusive endpoints), contribute. Percentages below divide by **all sampled frames in
the relevant clips**, not just face-valid frames. They measure frame availability/proximity,
not localization correctness or event recall. Each row has 20 raw annotated clips. This differs
from v2's 19 test eating clips because that evaluation requires successful extracted crop rows.
No alert evaluation or test-based parameter selection was performed.

| SynDD split / action | Frames | Face-valid | Usable wrist | K=.75 | K=1.0 | K=1.5 |
|---|---:|---:|---:|---:|---:|---:|
| val drinking | 680 | 559 | 680 (100%) | 36 (5.29%) | 311 (45.74%) | 518 (76.18%) |
| val eating | 2,360 | 2,333 | 2,355 (99.79%) | 98 (4.15%) | 284 (12.03%) | 640 (27.12%) |
| val normal | 3,790 | 3,789 | 3,790 (100%) | 0 (0%) | 134 (3.54%) | 1,013 (26.73%) |
| test drinking | 530 | 442 | 530 (100%) | 43 (8.11%) | 125 (23.58%) | 246 (46.42%) |
| test eating | 2,280 | 2,273 | 2,247 (98.55%) | 169 (7.41%) | 210 (9.21%) | 319 (13.99%) |
| test normal | 3,480 | 3,480 | 3,480 (100%) | 0 (0%) | 0 (0%) | 132 (3.79%) |

3MDAD / EBDD / DAD wrist coverage and localization: **open**, Python inference blocked.
SynDD image review: **open**, no decoded image sheets generated.
**Pi frames: open (to be done by orchestrator).**

Actual local evidence (ignored, deliberately not committed):

- [Per-segment counts](_held_data/syndd_cache_segments.csv)
- [Split × raw label counts, including face/wrist/pair denominators](_held_data/syndd_cache_summary.csv)
- [Missing rich-cache blocks](_held_data/syndd_cache_missing.txt)

## Provisional crop recipe; not visually accepted

Use **K=1.0**, selected only from the validation geometry trade-off: K=.75 retains just
5.29% of drinking / 4.15% of eating frames; K=1.5 admits 26.73% of normal frames. K=1.0
admits 45.74% / 12.03% / 3.54%, respectively. This is a starting point, not an optimized gate;
review wrists and visible contents before accepting it. Test results above are audit-only.

Center = midpoint of the nearest confident wrist and mouth. Nominal square side = **2.0 ×
face height (10–152)**. This explicitly uses face height rather than mesh bounding-box size,
so a full mesh is unnecessary when reusing the seven-landmark release cache. At K<=1 the
square contains both endpoints with margin before image-edge handling. Follow `extract.square`:
cap side to the image's shorter dimension and shift the square inside the image. Record this
clamping caveat: extreme crops can lose context. Resize grayscale to 128×128, then apply the
same D9 1–99 percentile stretch, including its unchanged-image exception when the span is <8.
No box labels, augmentation, or food-visibility labels are introduced.

## Balance and hard negatives

**Actual crop balance: zero crops in every class × dataset × split.** A zero here means
not built, not that the dataset has no qualifying examples. The 10-fps geometry counts below
are candidate frames only; they are not saved crops, unique visits, or checked object labels.

| Class | SynDD train crops | SynDD val crops | 3MDAD train crops | EBDD train crops | Test crops |
|---|---:|---:|---:|---:|---:|
| cup_bottle | 0 | 0 | 0 | 0 | 0 |
| food | 0 | 0 | 0 | 0 | 0 |
| empty_hand | 0 | 0 | 0 | 0 | 0 |

DAD is test-only; 3MDAD/EBDD have no val split in this recipe. Their missing training/tuning
cells are not filled from test drivers. The eventual builder writes the full observed balance
CSV, original-label negative breakdown, crop/source manifest, and sheet index files.

SynDD-val K=1.0 candidate breakdown read from the generated summary:

| Weak target | Original clip label(s) | Candidate frames |
|---|---|---:|
| cup_bottle | Class 1 drinking | 311 |
| food | Class 4 eating | 284 |
| empty_hand | Class 0 normal | 134 |
| empty_hand | Class 11 / 12 talking | 26 / 44 |
| empty_hand | Class 13 yawning | 541 |
| empty_hand | Class 14 hand on head | 1,249 |
| empty_hand | Class 15 singing | 88 |
| empty_hand total | all six negative categories | 2,082 |

3MDAD fatigue (AC12), smoking (AC16), talking (AC10), singing (AC11), and other hand_on_face
clips are included by the new Python mapping, but **none have been inferred or cropped**.
Radio/GPS/reaching and EBDD's broad UNATTENTIVE class are not silently treated as empty hands.

## Split policy and remaining execution

New scripts use the original `D:/rtdms-data/action_v1/data/v2/*.csv` driver split assignments;
3MDAD is cross-checked against this worktree's `splits/3mdad.json` (35 train / 15 test, seed 0).
SynDD-val is the only tuning set. EBDD's aktar/asif remain train (D5); akkas/jewel remain test.
DAD remains test-only. Test data was **read for A1's requested descriptive audit**, never
written, moved into train/val, used to train, or used to choose K. No input CSV/cache was changed.

The Python scripts are preparation code, **not verified completed results**:

1. `src/held_wrist.py`: cached SynDD faces/poses; release JSON landmarks on other test sets;
   NCNN pose where absent; face mesh only when the required timestamp is not cached.
   Outputs per-clip geometry, numeric summary, and stratified dataset sheets. Cached face misses
   remain misses. Sampling: SynDD/EBDD ~10 fps, every stored 3MDAD frame (~3 fps assumed),
   every fourth DAD frame (45/4 fps). These are different frame-weighted sampling populations.
2. `src/build_held.py --k 1.0 --side 2.0`: requires completion of all four audits, checks CSV
   splits again, excludes every test record, writes the 128px crops and balance/negative tables.
   Seed 23 selects up to 48 distinct sample frames per class per train/val sheet. It records
   whether each sheet actually meets the >=48 requirement; insufficient counts are not hidden.

Run from this worktree with the specified existing interpreter after its execution restriction
is resolved. Review actual outputs before claiming A1/A2 complete. Neither Python entry point
was run successfully here. **No sheets exist**, so there are no sheet links or committed preview
images. Expected paths after a successful run are `_held_data/sheets/wrist_<dataset>.jpg` and
`_held_data/crops_k1_side2/sheet_<train|val>_<class>.jpg`.

## Caveats (L15)

- SynDD food can be hidden in the hand. Clip action × proximity supplies weak semantic labels,
  not proof that a crop visibly contains food, a cup, or an empty hand.
- Rule B failed; high wrist confidence alone does not establish a correct wrist location.
  The unmade IR contact sheets are an essential missing check, especially low-resolution DAD.
- 3MDAD/EBDD are RGB converted to gray, not real IR; DAD is real IR. Pi domain remains open.
- Smoking negatives can visibly contain cigarettes; “empty_hand” means neither target food
  nor cup/bottle here, not literally no held object. Hand_on_face may include makeup objects.
- Correlated 10-fps frames are not independent examples. No temporal thinning or class balancing
  has been validated. Count imbalance must be assessed after real crops exist.
- Current-face-only gating misses cup occlusions. Reusing a face <=1 s is reserved for later
  runtime work, not silently added to these measured cache counts.
- PyTorch rich-cache wrists are not NCNN parity evidence. No Pi throughput claim is made.
