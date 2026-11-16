# Task 6: Dataset Preparation and Preprocessing (version 3)

**Project:** Real-Time Driver Monitoring System (RTDMS)
**Scope:** face monitoring, and phone / drink / food (distraction) detection
**Prepared by:** Youssef Medhat
**Date:** 16 November 2026
**Programme:** B.Sc. Graduation Project, Computer Engineering, AASTMT

> Version 3 replaces version 2 (October 2026). Version 2 is kept unchanged in the same folder.
> This version tells the story in date order, from the first plan to now.
> Every number has a source tag in square brackets. The tags are listed in section 9.

---

## 1. Summary

- I started with a plan for a camera at the centre mirror and a small object detector.
- I tried ready models first, then trained my own on public datasets.
- The data that mattered most was SynDD: driver video from a camera at the rear-view mirror,
  like ours.
- My release detector (YOLO26n, gray images, 512 px) found phone calls well on SynDD. On the
  real Pi camera it missed calls at the near ear, where the hand hides the phone.
- So I moved phone detection to an **action classifier**, which looks at the driver's whole
  upper body. This is what runs on the Pi now.
- **The Pi currently gives no drinking or eating alerts.** Section 8 explains why.
- My best drinking model is newer and **not set up on the Pi yet**. Eating does not work.

---

## 2. The story, in date order

### 2.1 The plan (May 2026)

In Project 1 we planned [CL]:
- A Raspberry Pi 5 with the AI HAT+ (26 TOPS).
- A Pi IR camera, 5 MP, 160°.
- MediaPipe Face Mesh for the eyes, gaze and head pose.
- YOLOv5 for phone detection.

The datasets we chose were UTA-RLDD, AUC Distracted Driver, MRL Eye, DG-Unicamp and WESAD.
We also reviewed CEW, Drive&Act and NDS [CL]. The target was at least 85–90 % accuracy and
less than 500 ms end to end [CL].

### 2.2 First face model (27–28 August 2026)

I built the face model on Google's MediaPipe FaceLandmarker [S 08-28].
- It finds the face points.
- Simple geometry then gives eye openness (EAR), blinks, PERCLOS, head pose and gaze.
- It needs no training data, because the Google model is already trained.

I made three choices then, each for a reason given at the time [S 08-27]:
- I used the new MediaPipe Tasks API, because the old one is gone in MediaPipe 1.0.
- I ran the face model on the CPU. It is small: 0.6 M parameters [S 08-27]. That leaves the
  AI HAT for phone detection.
- I set the eye-closure alert earlier than planned: 1.5 s instead of 2–3 s [Face Subsystem note].

### 2.3 Eye tests with CEW and MRL Eye (date not recorded)

I tested the eye part on CEW and trained a small eye-state CNN on MRL Eye as a comparison. I did
this outside Claude Code. **The original files were lost in the PC reset.**

What version 2 of this report said, from the old report and not verified [OLD]:
- CEW: 2,423 face photos (1,192 closed, 1,231 open), split 30 % for tuning and 70 % for testing.
- MRL Eye: 84,898 infrared eye images from 37 people, split by person.
- The old report gave no accuracy numbers.

I do not count this work in the final results.

### 2.4 First phone / drink / food prototype (28 August 2026)

I researched the lightest detector for the Pi [S 08-28]:
- The research picked one small YOLOv8n with four classes: phone, bottle, cup and food.
- The reason was that YOLOv8n keeps its accuracy best after INT8 on the Hailo chip: 37.0 → 36.4
  mAP in Hailo's model zoo [S 08-28].
- It also found that no public driver dataset has object boxes. I would have to make the boxes
  myself, with a large model [S 08-28].

I built a prototype with the stock COCO YOLOv8n, without any training, and tested it on my
laptop webcam. Then I asked: do I need a bigger model? I compared four models on the same
210-frame clip [S 08-28]:

| Model | ms per image | Frames with the phone found | Median phone confidence |
|---|---|---|---|
| yolov8n | 23.6 | 38 / 210 | 0.21 |
| yolov8s | 87.0 | 44 / 210 | 0.28 |
| yolo11n | 64.9 | 28 / 210 | 0.44 |
| yolo11x | 263.0 | 45 / 210 | 0.66 |

A model 25 times slower found the phone in only 7 more frames. So I kept the small model. I
decided to train it on in-car data instead [S 08-28].

### 2.5 Version 1: a ready State Farm classifier (25 September 2026)

Our team's first phone model was a ready image classifier (built by Ziad Teama) [PHN]:
- YOLOv8n-cls weights trained on State Farm, from Hugging Face.
- Its 10 classes were folded into 3: safe, phone, eating.
- The model card claims about 99 % top-1. We never measured it on held-out data [PHN].

This is what version 1 of this report described. It had a problem: State Farm photos are colour
and taken from the passenger side [PHN]. Our camera is infrared and sits at the centre mirror.

### 2.6 The Pi camera and the face model on the Pi (9–10 October 2026)

I connected a camera to the Pi on 9 October. It was a cheap OV5647 colour camera, a temporary
stand-in until the IR module arrived [PIT].

The face model ran on the Pi through LiteRT. MediaPipe itself does not run on the Pi's Python
3.13 [S 10-09]. Results on the Pi, face model alone [FEV]:
- 30 frames per second (the camera's limit).
- 13.5 ms per frame for the face mesh.
- 73 % of one CPU core, 133 MB of memory, no throttling.

The COCO YOLOv8n prototype also ran on the Pi: 102 ms per run, at 5 runs per second [S 10-09].

Later, after 10 October, I replaced the stand-in with the **IR NoIR 160° camera module**. The
exact date was not recorded [OWN].

### 2.7 First trained detector, on Open Images (10 October 2026)

I started a new distraction package around **YOLO26n**. The reason for choosing YOLO26n over
YOLOv8n is not recorded.

I also decided **not to record my own training data**. I would train on public data made to look
like my camera, and keep my own clips for testing only [DATA].

My first training set was Open Images V7: everyday photos with boxes for phones, cups, food and
hands [EVI].
- I converted each photo to look like my camera: gray, cropped to head and shoulders, bent like a
  fisheye lens, and with a real hand pasted over the object.
- I filled missing boxes with larger "teacher" models: YOLO26m at 1280 px for phones and cups,
  and YOLO-World for food.
- Training set: 13,623 images [EVI].

On Open Images' own test set the new model looked good: phone precision 0.82, recall 0.83 [EVI].
On a real webcam clip (S01) it found the phone at the ear in **0 %** of frames [EVI]. My
conclusion then: photos do not transfer to a real cabin camera. I needed in-car video [EVI].

### 2.8 Crop classifiers and the laptop webcam (11 October 2026)

For a few days I tested on my laptop webcam, in colour. The IR Pi camera was parked [DATA].

I trained two small crop classifiers [MOR]:
- **Ear crop:** phone, hand without phone, or nothing.
- **Mouth crop:** drink, food, or nothing.
- Data: 3MDAD front-camera video (50 drivers) plus Open Images. Split by driver, 70 / 15 / 15.
- The drink labels came from CLIP, because the box models missed most cups at the lips [DATA].

On held-out drivers the ear model scored phone precision 0.963 and recall 0.905 [MOR]. Live, it
gave the phone a probability of **0.00** [DATA]. The reason: 3MDAD's camera is low on the
dashboard and sees the phone from the side. From the mirror, the phone hides behind the hand.
I turned both crop classifiers off [DATA].

I also wrote a camera placement report [S 10-11]:
- Centre rear-view mirror, 0.6–0.8 m from the face.
- Turned 20–30° toward the driver, tilted 5–15° down.
- 1296 × 972 capture, infrared LEDs at night.

### 2.9 PC reset, and SynDD becomes the main dataset (16 October 2026)

My PC was reset and my local project was lost [S 10-16]. The dataset drive survived. I rebuilt
the setup.

Then I downloaded **SynDD** (AI City Challenge 2024, Track 3) [SRT]:
- I took the rear-view mirror camera only: 69 drivers, about 93 GB.
- The video is gray. A pixel check later found it to be monochrome daylight video, not active
  infrared [INV]. The earlier project documents called it infrared.
- I fixed the driver split: 49 training, 10 validation, 10 test drivers [SRT].

I retrained the crop classifiers on SynDD in gray [SRT]:
- Ear: macro F1 0.921.
- Mouth: macro F1 0.794.

They stayed off by default later [DET2].

Next I made boxes on SynDD and EBDD video automatically [LOG]:
- A teacher model drew the boxes.
- I kept a box only if it matched the action label.
- Frames were taken every 0.5 s in actions and every 1.5 s in normal driving [`label_video_boxes.py`].
- SynDD gave **18,318 frames from 1,653 clips**. EBDD gave **2,093 frames** [LOG].

### 2.10 Detector v2, back to infrared (17–18 October 2026)

I merged five sources into one training set [DET2] (sizes in section 4):
- SynDD.
- EBDD.
- Open Images.
- Two Roboflow sets: DMS_Project and ADMS_FINAL_3.

I cleaned it in four ways [DET2]:
- Roboflow images with boxes larger than 12 % of the image (8 % for drinks) were removed.
- I added 7,010 gray copies of colour images.
- I added 7,913 phone images with a real hand pasted over 30–60 % of the phone.
- The training set had **53,889 images** [LOG].

**det_v2b** (416 px) found the phone at the ear in 71.5 % and 91.6 % of frames on the test
drivers. The teacher found it in 82.4 % and 79.2 % [DET2].

Then I tested at the **alert** level, the way the Pi works: 10 frames per second, with rules
[OVR]. I made four changes:
- Fixing labels and adding hard negatives (det_v2c) made things **worse**: 13.7 false phone alarms
  per hour on the test drivers instead of 1.7 [OVR]. I dropped it.
- Training on **gray images only, at 512 px**, with thresholds chosen on the validation drivers,
  gave **det_v2d**. Phone false alarms on validation fell from 36.1 to 5.2 per hour [OVR]. This
  became my release model.
- I tried eight more ideas: tracking, a temporal model, a second zoomed pass, SynDD A2
  pseudo-labels, copy-paste, SAM 2 boxes, the other SynDD camera views, and a fisheye-trained
  model. **None beat det_v2d** [OVR].
- One rule helped: texting = head down + wrist low. It raised texting from 36.6 % to 41.5 % on
  the test drivers [OVR].

A 5-fold test by driver showed how much results depend on the drivers [OVR]:
- Calls at the right ear were caught 73–100 % of the time, depending on the group.
- Phone false alarms were 2.8–22.4 per hour, depending on the group.

**Eating could not be learned.** In SynDD's mirror view the food is almost never visible. Only
**3 training frames** had a matching food box [LOG].

On 18 October I rewrote Task 6 and Task 7 as version 2 [S 10-18].

### 2.11 Tests on unseen datasets, and the release (18–19 October 2026)

I tested det_v2d on two datasets it had never seen [OVR]:
- **3MDAD:** 50 drivers, colour turned to gray. It caught 80 % and 92 % of calls, and 68–80 % of
  drinks. It gave a false phone alert on 8 % of normal clips.
- **DAD:** real infrared, 3 drivers. It caught 4 of 5 calls and 2 of 2 drinks. But it gave **69
  false phone alarms per hour**: it read the steering wheel as a phone.

I put the release models in GitHub on 19 October [MOD].

### 2.12 Live on the Pi: the near-ear problem (25 October 2026)

I ran det_v2d on the Pi with the face model [S 10-25]:
- With the detector on every 2nd frame, the stream ran at **24.5 frames per second** at 58 °C.

Then I tested a phone call live. The phone at the **far** ear was found. The phone at the
**near** ear was not. The numbers from my recording [S 10-25]:

| Ear | Median phone score | Alert rule active |
|---|---|---|
| Far ear | 0.63 | 89 % of the time |
| Near ear | 0.18 | 11 % of the time |

The reason: my hand hid the phone. I tried a lower threshold near the ear. On the SynDD test
drivers it raised right-ear calls from 80 % to 90 %, but added 3.4 false alarms per hour [S 10-25].
That was not good enough.

### 2.13 Action classifier v1, then hybrid v2 (26 October 2026)

So I changed the approach. Instead of finding the phone as a box, I classify **what the driver is
doing** from a crop of the upper body [S 10-26]. My goals were:
- Catch calls and texting even when the phone is hidden.
- Do **not** alert when a hand just rests on the face.
- Run at 15 frames per second or more on the Pi.

The training data [AV1]:
- SynDD: 52,125 frames.
- **3MDAD: 60,655 frames**. I now used 35 of its drivers for training and kept 15 for testing.
  This is a change from version 2, where 3MDAD was test only [DEC].
- EBDD: 5,972 frames.
- Simulated fisheye frames from SynDD: 6,188.
- DAD stayed test only: 11,349 frames.
- I balanced the classes to 62,085 training crops.

**v1** was one action model (YOLO26n-cls, 224 px, 7 classes) plus an ear phone check [AV1]:
- It caught more calls: 37 of 39 vs 34 of 39 for det_v2d on SynDD.
- But it gave 14.5 false alarms per hour on normal and hand-on-face clips. det_v2d gave 0.

**v2** fixed this [AV2]:
- A second phone check on a crop under the chin (the lap) confirms texting.
- Drinking and eating come from det_v2d's cup and food boxes near the mouth.
- I also tried a larger model and an extra "smoking" class. Neither helped, so I dropped them [DEC].

| Test set | det_v2d: calls, texting, false alarms / h | v2: calls, texting, false alarms / h |
|---|---|---|
| SynDD (10 drivers) | 34/39, 14/41, 0 | **37/39, 18/41, 0** |
| 3MDAD (15 drivers) | 24/30, 17/30, **14.2** | **30/30, 24/30**, 19.6 |
| DAD (real IR) | 4/5, 5/6, 79.2 | **5/5**, 4/6, **3.6** |

Source: [AV2]. v2 is better on calls everywhere and has far fewer false alarms on real IR video.
It is a little worse on 3MDAD false alarms.

The three v2 models are INT8 and 1.6 MB each [MOD].

### 2.14 v2 on the Pi (26 October – 8 November 2026)

v2 ran live on the Pi on 26 October with the face mesh and PERCLOS, at about 30 frames per second
[S 10-26]. On 8 November I merged it into the main branch and set it as the Pi's start script
[git `981a822`, `pi/start_stream.sh`]. The detector is switched off in that script.

### 2.15 A better drinking model from hand-at-mouth crops (8–15 November 2026)

The cup and food boxes came from a teacher model that rarely saw food. So I asked a simpler
question: **is the hand at the mouth holding something?** [S 11-08]

- I cut crops around the hand when it is near the mouth: 22,612 crops, with no test drivers
  [S 11-13].
- The cup / bottle crops looked clean. The food crops did not: food was visible in only about
  7 of 48 [S 11-13].
- So I trained a two-class model first: **cup / bottle vs empty hand**.
- I built a frozen infrared test set. It has 20 drinking and 19 eating events, short of the 30 +
  30 I wanted, because no more IR data with labels was available [S 11-14].

The best version, **IR-3**, was trained with 1,500 phone-in-hand crops as negative examples. I
chose it on the validation drivers only [S 11-14]:

| Infrared test set | IR-3: drinks caught | IR-3: false alarms / h | Old box detector |
|---|---|---|---|
| SynDD | 16 / 18 | 1.07 | 16 / 18 |
| DAD (real IR) | 2 / 2 | 1.58 | 2 / 2, at 8.7 false alarms / h |
| **Total** | **18 / 20 (90 %)** | | |

Source: [S 11-14].

**Eating still does not work.** A hand-to-mouth + chewing rule caught 0 of 19 eating clips
[S 11-14]. No eating model was trained, because there are no hand-checked food labels.

The code for this stage is on a branch called `overnight/held-object`. I could not find it on
GitHub on 16 November, so these numbers come from the session record.

---

## 3. How the data is prepared now

### 3.1 Labels

- **Action labels:**
  - SynDD gives the start and end of each action [SRT].
  - I mapped every dataset's labels to 7 classes: normal, call, texting, drinking, eating,
    hand_on_face, other [`action_v1/class_map.json`].
  - SynDD "pick up from floor" and 3MDAD "having picture" are skipped [DEC].
- **Box labels (release detector):** YOLO format, one line per box: class, x, y, width, height,
  all 0–1 [DET2]. Classes: 0 phone, 1 drink, 2 food.
- Boxes on video come from a teacher model (YOLO26m at 1280 px; YOLO-World for food) and are kept
  only if they match the action [DET2], [`configs/data.yaml`].

### 3.2 Preprocessing

| Step | Release detector (det_v2d) | Action model + phone checks (v2) |
|---|---|---|
| Frames from video | every 0.5 s in actions, 1.5 s in normal driving [`label_video_boxes.py`] | 2.5 per second, 0.5 s dropped at each segment edge [AV1] |
| Colour | gray, copied to 3 channels [MOD] | gray, with a contrast stretch per crop [DEC D9] |
| Crop | driver area | upper body 2.5 × face size; ear crops; lap crop under the chin [MOD] |
| Size | stored at most 960 px; model input 512 × 512 [MOD] | 224 px (action), 128 px (phone checks) [MOD] |
| Augmentation | mosaic, flip, zoom ±50 %, shift ±10 %, rotate ±5°, brightness ±40 % [`train.py`] | lens / fisheye, tilt ±15°, brightness, contrast, blur, noise [PROG] |
| Balancing | gray copies + hand-occluded phone copies [DET2] | no class more than 3 × the smallest (eating) [AV1] |

### 3.3 Splits

All splits are **by driver**: nobody in the test set appears in training.

| Dataset | Train | Validation | Test | Source |
|---|---|---|---|---|
| SynDD | 49 drivers | 10 | 10 | [SRT] |
| 3MDAD | 35 drivers (action model only) | — | 15 | [DEC D6] |
| EBDD | 11 drivers (action model; the detector kept 2 of them for validation) | — | 2 (akkas, jewel) | [DEC D5], [LOG] |
| DAD | — | — | 3 drivers (test only) | [AV1] |
| Open Images, Roboflow | their own published splits | | | [DET2] |

Thresholds are chosen on validation drivers only. Test drivers are scored once [OVR].

---

## 4. Datasets

| Dataset | IR / RGB | Size | Classes used | Used or dropped | Reason |
|---|---|---|---|---|---|
| SynDD A1, rear-view mirror | Gray; monochrome daylight per pixel check [INV] | 69 drivers, 138 rear-view videos [S 10-26]; 18,318 labelled frames from 1,653 clips [LOG] | calls L/R, texting, drinking, eating, normal, look-alikes | **Used** (main) | Same camera position as ours |
| SynDD A1, dashboard + side views | same | 20 drivers downloaded [OVR] | same | Dropped | Phone false alarms rose from 5.2 to 24.1 per hour [OVR] |
| SynDD A2 | same | 21 GB; 15 entries in the folder [S 10-26], but 10 drivers in a later inventory [INV] (conflicting) | no labels | Dropped | Pseudo-labels too noisy; more false alarms [OVR] |
| Open Images V7 | RGB photos | 16,996 photos [LOG] | phone, drink, food | **Used** | Teaches what the objects look like |
| Roboflow DMS_Project v2 | IR + colour | 10,198 images (from old report, not verified) | phone, drinking, eating | **Used** | Driver-camera images with boxes |
| Roboflow ADMS_FINAL_3 v1 | RGB | 2,698 images (from old report, not verified) | phone, drinking | **Used** | In-car images with boxes |
| EBDD | RGB → gray | 13 drivers; 2,093 labelled frames [LOG] | calls, texting, eating | **Used** | Driver video with eating |
| 3MDAD Day-RGB2 front | RGB → gray | 50 drivers; 60,655 frames for the action model [AV1] | 16 actions | **Used** | Test for det_v2d; training (35 drivers) for the action model |
| DAD part 1 | **real IR** | 3 drivers, 66 min normal driving per camera [OVR] | calls, texting, drinking | **Used, test only** | The only real-IR test video |
| State Farm | RGB | — (pre-trained weights only) | 10 classes | Dropped | Passenger-side view [DATA] |
| AUC Distracted Driver | RGB | about 44 drivers, on disk [INV] | 10 classes | Not used | Passenger-side view [DATA] |
| Drive&Act | NIR | 15 drivers, videos on disk [INV] | many | Not used | Annotation files missing [INV] |
| DMD, 100-Driver | IR + RGB | — | many | Not used | Requested, never received [INV] |
| YawDD | RGB | — | yawning | Not used | Never placed on disk [MOR] |
| CEW | RGB | 2,423 photos (from old report, not verified) | eyes open / closed | Early test only | Files lost in the reset; not counted |
| MRL Eye | IR | 84,898 images (from old report, not verified) | eyes open / closed | Early test only | Files lost in the reset; not counted |
| My own Pi-camera recordings | IR | none yet | — | Planned (Task 7) | Not recorded yet |

Detector training set by split [LOG], [S 10-18]:

| Split | Images | Notes |
|---|---|---|
| Train | 53,889 | 38,966 source images + 7,010 gray copies + 7,913 hand-occluded copies |
| Validation | 6,557 | |
| Test | 4,780 | |

The per-class box counts in version 2 (for example 30,193 phone boxes) are from the old report,
not verified.

SynDD training frames per action [LOG]:

| Action | Frames |
|---|---|
| Phone at the ear (right + left) | 4,424 (2,207 + 2,217) |
| Phone in hand (texting) | 2,803 |
| Drinking | 409 |
| Eating | 3 |
| Normal driving | 1,158 |
| Look-alikes (hand on head, singing, talking, yawning) | 4,588 |

---

## 5. Model comparison

"—" means the source gives no such number. Call / drink results are "caught / total" at the alert
level.

| Model | Dataset (test) | Accuracy | Precision | Recall | F1 | Other metrics | Decision |
|---|---|---|---|---|---|---|---|
| COCO YOLOv8n, no training | my webcam clip | — | — | — | — | phone in 38/210 frames; 23.6 ms [S 08-28] | Keep the small model |
| COCO YOLO11x, no training | my webcam clip | — | — | — | — | phone in 45/210 frames; 263 ms [S 08-28] | Too slow for little gain |
| State Farm YOLOv8n-cls (team v1) | none (ours) | ~99 % top-1 claimed by the model card, not measured [PHN] | — | — | — | ~11 ms ONNX on a PC [PHN] | Dropped: wrong camera view |
| Eye-state CNN (early) | MRL Eye | — | — | — | — | from old report, not verified | Not counted |
| YOLO26n v1_512 | Open Images test | — | phone 0.82 | phone 0.83 | — | AP50 0.87; real clip: phone at ear 0 % [EVI] | Dropped: did not transfer |
| Ear crop classifier | 3MDAD test drivers | — | phone 0.963 | phone 0.905 | val 0.910 | live P(phone) 0.00 [MOR], [DATA] | Turned off: wrong angle |
| Ear crop classifier (SynDD) | SynDD test | — | phone 0.983 | phone 0.867 | macro 0.921 | [SRT] | Off by default |
| Mouth crop classifier (SynDD) | SynDD test | — | drink 1.000 | drink 0.771 | macro 0.794 | food P/R 0.683/0.573 [SRT] | Off by default |
| det_v2b (416 px) | SynDD test, boxes | — | phone 0.77 | phone 0.67 | — | AP50 0.78 [DET2] | Replaced by det_v2d |
| det_v2c (hard negatives) | SynDD test | — | — | — | — | 13.7 false alarms/h vs 1.7 [OVR] | Rejected |
| **det_v2d (512 px, gray)** | SynDD test | — | phone 0.818 (val frames) | phone 0.628 (val frames) | — | AP50 0.771 [OVR]; calls 80 % / 100 %, drinks 90 %, texting 41.5 %, 0 false alarms/h; DAD 69/h [MOD] | Release model; **off on the Pi** |
| det_v2d INT8 | SynDD val | — | phone 0.831 | phone 0.629 | — | AP50 0.772; 2.8 MB; 22.6 ms [OVR] | Ready for the Pi |
| det_v2h (fisheye) | simulated fisheye val | — | — | — | — | phone AP50 0.795 vs 0.770 [OVR] | Kept as an alternative |
| det_v2i (3 SynDD views) | SynDD val | — | — | — | — | 24.1 false alarms/h [OVR] | Rejected |
| Action v1 (act_n224) | SynDD test | 0.67 (per frame) | — | — | — | calls 37/39; 14.5 false alarms/h [AV1] | Replaced by v2 |
| Action v1, larger "s" model | SynDD val | top-1 0.664 | — | — | — | about 3× slower [PROG] | Rejected |
| Action v1 + smoking class | SynDD val | top-1 0.657 | — | — | — | smoking false alarms 7 → 7 [DEC] | Rejected |
| **v2 hybrid (action + ear + lap checks)** | SynDD / 3MDAD / DAD test | — | — | — | — | calls 37/39, 30/30, 5/5; false alarms 0, 19.6, 3.6 per h; lap check AUC 0.84 [AV2] | **Runs on the Pi** (calls, texting) |
| **IR-3 drinking model** | infrared test set | — | — | 18/20 drinks (90 %) | — | false alarms 1.07/h (SynDD), 1.58/h (DAD) [S 11-14] | **Best drinking model; not on the Pi** |
| Eating rule (hand to mouth + chewing) | SynDD test | — | — | 0/19 | — | [S 11-14] | Does not work |

---

## 6. What I learned

- **Training data must look like my camera.** Photos and other camera angles raised false alarms
  (sections 2.7, 2.8, 2.10).
- **Finding a box is not enough when the hand hides the object.** That is why calls moved to an
  action classifier (section 2.12).
- **Results change a lot between driver groups.** One 10-driver test can be off by 10–20 points
  [OVR].
- **Eating is not visible from the mirror** in the data I have.

---

## 7. Data quality and ethics

| Check | Status |
|---|---|
| Test drivers never seen in training | Done: SynDD, 3MDAD, EBDD split by driver; DAD test only |
| Thresholds chosen fairly | Done: on validation drivers only [OVR], [S 11-14] |
| Licences | SynDD research licence; EBDD research use; Open Images CC BY; Roboflow CC BY 4.0; DAD academic; 3MDAD CC BY-NC-ND 4.0 [DATA], [MOD] |
| Data kept private | Datasets stay on the local drive, never in git [DATA] |
| Labels checked by a person | Not done: 495 test frames were prepared for a hand check [OVR]; no record that it was done |
| Numbers that could not be verified | CEW, MRL Eye, DMS_Project and ADMS sizes, and the box counts are marked "from old report, not verified" |

---

## 8. Current state of the project (16 November 2026)

**On the Raspberry Pi now** [`pi/start_stream.sh`], [S 11-08]:
- Camera: the IR NoIR 160° module at the centre mirror [OWN]. It is not fisheye-calibrated yet
  (`rectify.enabled: false`) [`configs/profiles/pi.yaml`].
- Face model: face mesh, eye closure, blinks, PERCLOS.
- Phone: the v2 action classifier with the ear and lap phone checks. It gives **call** and
  **texting** alerts.
- Speed: about 30 frames per second (the camera's limit), about 15 ms of model time per frame
  [S 11-08].

**The Pi gives no drinking and no eating alerts right now.** Why:
- In v2, drinking and eating come only from the det_v2d box detector [DEC D17]. The Pi starts
  with the detector switched off (`--no-detect`).
- Turning it back on costs speed. On every frame it was estimated at 15.1 frames per second in
  the worst case [DEC D22]. On every 2nd frame it costs about 22 ms per frame, so about 20 frames
  per second, and its false phone alerts come back: about 79 per hour on real IR video
  [S 10-26].
- My best drinking model, IR-3 (18 of 20 drinks), is **not set up on the Pi yet**. I could not
  export it for the Pi, because my PC blocked the export tool and the Pi was not reachable
  [S 11-14].
- Eating has no working model at all.

**Best models so far:**
- Calls and texting: v2 hybrid (section 2.13).
- Drinking: IR-3 (section 2.15), not on the Pi.
- Release box detector: det_v2d, in GitHub, used for testing [MOD].
- Eating: none.

**Still to do:**
1. Put IR-3 on the Pi for drinking, and measure the speed with everything running together.
2. Record my own drivers with the Pi camera, day and night (Task 7). I have no own recordings yet.
3. Calibrate the fisheye lens.
4. Get eating data where the food is visible, or leave eating out of the alerts.
5. Hand-check the 495 test frames.

---

## 9. Sources

| Tag | Source |
|---|---|
| [CL] | `CLAUDE.md` (Project 1 summary) |
| [OLD] | Task 6 version 2 report (this folder). Numbers marked "from old report, not verified" |
| [OWN] | My own answers, 16 November 2026 |
| [S mm-dd] | Claude Code session record of that date (2026) |
| [LOG] | Data-build logs on the data drive, printed in the session of 18 October 2026 (`det_v2_syndd.log`, `det_v2_ebdd.log`, `build_openimages.log`, `build_det_v2b.log`) |
| [INV] | Dataset inventory of the data drive, session of 14 November 2026 |
| [PHN] | `models/phone/docs/EVIDENCE.md` |
| [PIT] | `Subsystems/Raspberry Pi 5 Target.md` |
| [FEV] | `models/face/docs/EVIDENCE.md` |
| [EVI] | `models/distraction/docs/EVIDENCE.md` |
| [DATA] | `models/distraction/docs/DATA.md` |
| [MOR] | `models/distraction/docs/MORNING_REPORT.md` |
| [SRT] | `models/distraction/docs/SYNDD_RETRAIN.md` |
| [DET2] | `models/distraction/docs/DETECTOR_V2.md` |
| [OVR] | `models/distraction/docs/OVERNIGHT_REPORT.md` |
| [MOD] | `models/distraction/models/README.md` |
| [AV1] | `models/distraction/action_v1/REPORT.md` |
| [AV2] | `models/distraction/action_v1/REPORT_v2.md` |
| [DEC] | `models/distraction/action_v1/DECISIONS.md` |
| [PROG] | `models/distraction/action_v1/PROGRESS.md` |
| Face Subsystem note | `Subsystems/Face Subsystem.md` |

The full date-by-date history is in `timeline.md`. The comparison with version 2 is in
`report_vs_project.md` (both in this folder).

## Questions for me

1. The `overnight/held-object` branch is not on GitHub. Where is it? Until it is found, IR-3's
   numbers rest on the session record only.
2. Why did I choose YOLO26n over YOLOv8n on 10 October? Not recorded.
3. Did the eating head trained on 14–15 November finish? Its result is not recorded.
4. Was the hand check of the 495 test frames ever done?
