# Prediction Rating UI — Team Guide

> **Version:** 1.0 &nbsp;|&nbsp; **Audience:** Rating Team &nbsp;|&nbsp; **App URL:** `http://localhost:8000` (run by your system admin)

---

## Table of Contents

1. [What Is This App?](#1-what-is-this-app)
2. [Opening the App](#2-opening-the-app)
3. [The 5-Step Workflow (Overview)](#3-the-5-step-workflow-overview)
4. [Step 1 — Load Prediction Images](#4-step-1--load-prediction-images)
5. [Step 2 — Link Results CSV (Optional)](#5-step-2--link-results-csv-optional)
6. [Step 3 — Link Scale Profile (Optional)](#6-step-3--link-scale-profile-optional)
7. [Step 4 — Review Images](#7-step-4--review-images)
8. [Step 5 — Export Results](#8-step-5--export-results)
9. [Drawing Polygon Corrections](#9-drawing-polygon-corrections)
10. [Keyboard Shortcuts](#10-keyboard-shortcuts)
11. [Understanding the Queue](#11-understanding-the-queue)
12. [Frequently Asked Questions](#12-frequently-asked-questions)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. What Is This App?

The **Prediction Rating UI** is an internal tool for reviewing road surface images that have been analysed by an AI model. Your job as a rater is to:

| Decision | Meaning |
|----------|---------|
| ✓ **Correct** | The model's prediction for this image is accurate |
| ✗ **Wrong** | The model's prediction is incorrect — you can then draw a correction polygon |

After reviewing, you export the results so the engineering team can update the model's training data.

---

## 2. Opening the App

1. Make sure the server is running (ask your admin if unsure).
2. Open your browser and go to: **`http://localhost:8000`**
3. You will see the workflow guide bar at the top showing **5 numbered steps**.

> The app saves your progress automatically. If you close and reopen the browser, your previous session will be restored.

---

## 3. The 5-Step Workflow (Overview)

The green circles at the very top of the page show your progress. Each circle turns **green** as you complete that step.

```
① Load Images  ──  ② Link CSV  ──  ③ Scale Profile  ──  ④ Review  ──  ⑤ Export
   (required)       (optional)        (optional)         (main work)
```

Steps **2** and **3** are optional enhancements — you can skip them and still review and export.

---

## 4. Step 1 — Load Prediction Images

This is the only **required** step before you can start reviewing.

### Option A — Import from your PC (recommended)

1. Click **📂 Import Folder From PC** in the top-right of the header.
2. A file browser opens — navigate to the folder containing the prediction images.
3. Select the folder (you select the folder itself, not individual files).
4. Wait for the upload to complete — a progress indicator will appear.

### Option B — Load by server path

1. In the **Step 1** row of the Setup Panel, paste the full path to the folder:
   ```
   C:\Projects\S25\predictions\20250509
   ```
2. Click **Load Path**.

> **Path tip:** Both forward slashes (`/`) and backslashes (`\`) work. You can also paste paths directly from Windows Explorer.

### What you see after loading

- The **Queue** panel on the left fills with image thumbnails.
- The **Stats bar** shows: Total images, Correct, Wrong, Annotated.
- The progress bar shows how many images you have reviewed.
- The first unreviewed image loads automatically in the viewer.

---

## 5. Step 2 — Link Results CSV (Optional)

Linking a CSV file shows the **model's bounding boxes** drawn over each image, so you can see exactly what the model predicted before deciding correct or wrong.

### What the CSV provides

- Coloured dashed rectangles drawn over the image for each detected object.
- Each box is labelled with the class name and confidence score.
- Required if you want to export an **Updated CSV** at the end.

### How to link

**Option A — Browse from your PC:**
1. In the **Step 2** row, click **Browse…**
2. Select your `detailed_results.csv` file.

**Option B — Paste the server path:**
1. Paste the path into the CSV field, e.g.:
   ```
   D:\S25_DRR\results\detailed_results.csv
   ```
2. Click **Load Path**.

### Bounding box toggle

Once linked, a toggle appears above the image:

- ☐ **Show model bounding boxes** — off by default, tick to show the coloured boxes.
- You can turn them on/off at any time while reviewing.

---

## 6. Step 3 — Link Scale Profile (Optional)

A **scale profile** is a calibration file (`scale_profile.csv`) from the XenomatiX camera. When linked, the app automatically calculates the **real-world size** of any polygon you draw:

- **Area classes** (Alligator Crack, Patching, Pothole, Pavement): area in **m²**
- **Crack class**: length in **m**

The calculated value appears inside the polygon badge on screen and is written into the exported CSV.

### How to link

**Option A — Browse from your PC:**
1. In the **Step 3** row, click **Browse…**
2. Select your `scale_profile.csv` file.

**Option B — Paste the server path:**
1. Paste the path, e.g.:
   ```
   D:\S25_DRR\update_xeno_model\new\20250509_1\debug\scale_profile.csv
   ```
2. Click **Load Path**.

> If no scale profile is linked, polygon corrections are still saved — they just won't have a real-world measurement in the export.

---

## 7. Step 4 — Review Images

This is the main part of your work. Images appear one at a time in the viewer on the right.

### Navigation

| Action | How |
|--------|-----|
| Go to next image | Click **Next →** button, or press **`D`** or **`→`** |
| Go to previous image | Click **← Prev** button, or press **`A`** or **`←`** |
| Jump to a specific image | Click its name in the Queue list on the left |

### Making a decision

For each image, press one of the three decision buttons at the bottom:

| Button | Key | Meaning |
|--------|-----|---------|
| **✓ Correct** | `C` | Model prediction is accurate |
| **✗ Wrong** | `W` | Model prediction is wrong — annotation toolbar appears |
| **Reset** | `U` | Clear this image's decision (back to Unreviewed) |

> After pressing **Correct** or **Wrong**, the app automatically advances to the next unreviewed image.

### Status indicator

The coloured pill at the bottom-left of the viewer shows the current image's status:

- 🔘 **Unreviewed** — not yet rated
- 🟢 **Correct** — marked as correct
- 🔴 **Wrong** — marked as wrong

---

## 8. Step 5 — Export Results

After reviewing, use the **Step 5** row in the Setup Panel to export your work.

### Export options

| Button | What it produces | When to use |
|--------|-----------------|-------------|
| **Export Updated CSV** | A corrected version of the Results CSV. Wrong+annotated images get polygon rows with real-world values (m^2 or m). | When you need to update the model training data |
| **Export ZIP** | A structured zip file ready for model retraining (see structure below) | When the engineering team needs labelled image data |
| **Export TXT** | A plain text list of filenames marked as Wrong | Quick reference or for scripting |

### ZIP export — contents

The exported ZIP is organised into folders so the engineering team can use it directly with YOLO or similar training pipelines:

```
rating_export.zip
│
├── images/                  ← Clean original images (use these for model training)
│   └── filename.jpg
│
├── annotated/               ← Same images with your polygons drawn on them
│   └── filename_annotated.jpg      (for visual review and quality checking)
│
├── labels/                  ← YOLO segmentation label files (one per image)
│   └── filename.txt                (class_id x1 y1 x2 y2 … xn yn, normalised 0–1)
│
├── classes.txt              ← Class ID to name mapping
├── manifest.json            ← Full session metadata
└── manifest.csv             ← Summary table
```

**`classes.txt`** contains:
```
0: alligator crack
1: crack
2: patching
3: pothole
4: pavement
```

**`labels/filename.txt`** example (YOLO segmentation format):
```
3 0.12 0.31 0.48 0.31 0.48 0.67 0.12 0.67
1 0.60 0.10 0.88 0.10 0.88 0.42 0.60 0.42
```
Each line = one polygon: `class_id x1 y1 x2 y2 … xn yn` (coordinates are normalised 0–1 relative to image size).

> Images **without** polygon annotations are still exported to `images/` as clean files but will not have entries in `annotated/` or `labels/`.

### For ZIP export — set the target image path first

ZIP export maps each wrong prediction image to its matching **original target image**. Before exporting:

1. In the Step 5 row, paste the path to the folder of original images:
   ```
   D:\S25_DRR\original_images\20250509
   ```
2. Click **Save** or **Choose…** to browse.

> **Updated CSV** and **Export TXT** do **not** require the target image path.

---

## 9. Drawing Polygon Corrections

When an image is marked **Wrong**, an annotation toolbar appears below the image. Use it to draw a polygon that shows where the correct detection should be.

### Step-by-step

1. **Choose the defect class** from the dropdown (Alligator Crack, Crack, Patching, Pothole, Pavement).
2. Click **✏️ Draw Polygon** (or press `P`).
   - The cursor changes to a crosshair ✛.
3. **Click** on the image to place each corner point of the polygon.
4. **Close the polygon** by:
   - Double-clicking anywhere, **or**
   - Clicking back on the first point (a white circle appears when you're close enough to snap), **or**
   - Rapidly clicking twice.
5. The polygon is saved automatically.
   - If a scale profile is linked, the area or length is calculated and shown inside the polygon badge.

### Multiple polygons

- You can draw **more than one polygon** on the same image.
- Each polygon can have a **different class** — change the dropdown before drawing each one.
- All polygons are saved together for that image.

### Editing polygons

| Action | How |
|--------|-----|
| Cancel a polygon in progress | Press `Esc` |
| Undo the last placed point | Click **Undo** (while actively drawing) |
| Remove the last completed polygon | Click **Undo** (when not in draw mode) |
| Remove all polygons on this image | Click **Clear All** |

### How polygons look on screen

Each completed polygon shows a **dark badge** at its centre with:
- A coloured dot matching the polygon stroke
- The class name in bold white
- The calculated measurement below (e.g. `3.29 m^2`) — only if scale profile is linked

---

## 10. Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `A` or `←` | Previous image |
| `D` or `→` | Next image |
| `C` | Mark image as Correct |
| `W` | Mark image as Wrong |
| `U` | Reset (Unreviewed) |
| `P` | Toggle Draw Polygon mode (only when image is Wrong) |
| `Esc` | Cancel polygon drawing |

> Shortcuts are **disabled** while typing in any text input field.

---

## 11. Understanding the Queue

The left panel lists all images in the current folder. Use the **filter chips** to switch views:

| Filter | Shows |
|--------|-------|
| **Unreviewed** | Images not yet rated (default) |
| **Reviewed** | All images that have been rated (correct or wrong) |
| **Selected** | Only images marked as Wrong |

### Badge colours on queue items

| Badge | Meaning |
|-------|---------|
| 🔘 Unreviewed | Not yet rated |
| 🟢 Correct | Marked as correct |
| 🔴 Wrong | Marked as wrong |
| 🟣 *N* polygons | Correction polygons have been drawn |

---

## 12. Frequently Asked Questions

**Q: Do I need to save manually?**
> No. The app saves every decision and polygon automatically within a second of you making it. You can close the browser and return later — your progress will be there.

**Q: The bounding boxes look wrong — should I mark it Wrong?**
> Yes. If the model's boxes don't match what you see on the road surface, mark the image as Wrong and draw your own polygon(s) showing the correct area.

**Q: Can I change a decision after I've moved on?**
> Yes. Click the image in the Queue list to go back to it, then press `C`, `W`, or `U` to change its rating.

**Q: What if a polygon I drew is the wrong class?**
> Click the image in the queue, then use **Undo** to remove the last polygon (or **Clear All** to start fresh), then redraw with the correct class selected.

**Q: I don't have a scale profile — can I still annotate?**
> Yes. Polygons work fine without a scale profile. The `Value` column in the exported CSV will just be empty. The engineering team can fill it in later.

**Q: What does "Annotated" mean in the stats?**
> It counts images that are marked Wrong **and** have at least one polygon drawn on them. The polygon is what goes into the updated CSV for model retraining.

**Q: The path I pasted has backslashes — is that OK?**
> Yes. Both `C:\path\to\folder` and `C:/path/to/folder` are accepted.

---

## 13. Troubleshooting

### "Folder not found" when loading a path
- Check for typos in the path.
- Make sure the folder exists and is accessible from the server machine.
- Try using the **Import Folder From PC** button instead.

### Bounding boxes don't appear after linking CSV
- Make sure you ticked the **Show model bounding boxes** checkbox above the image.
- Check that the CSV's `Image Filename` column matches the actual filenames in your folder.

### Scale profile linked but no area shows on polygon
- Make sure the image was loaded *after* the scale profile was linked (reload the image if needed).
- Check that the scale profile has `in_roi = 1` rows covering the Y pixel range of your polygon.

### "No supported image files" error on import
- Supported formats: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`, `.tif`, `.tiff`
- Other file types (PDFs, videos, etc.) are ignored.

### Export ZIP fails with "Target image path does not contain matching files"
- The filename in the prediction folder must exactly match the filename in the original target folder.
- Check for differences in case, extension, or naming convention.

### Progress bar shows 100% but some images still show Unreviewed
- Switch the queue filter to **Unreviewed** to see any remaining images.
- The progress bar counts images that have been rated (Correct + Wrong).

---

*For technical issues or feature requests, contact your system administrator.*
