# AutoScreenshot for Fusion 360

**AutoScreenshot** is a plugin for Autodesk Fusion 360 that automatically captures screenshots of the active document over time. It is designed for users who want to document their design process, create time-lapses, or analyze their modeling progress.

---

## ✨ Features

- 📷 **Four capture modes**:
  1. **Fusion API-based** — Uses Fusion's internal `viewport.saveAsImage()` (may cause the viewcube to freeze in some cases).
  2. **GDI capture with UI** — Captures the full Fusion window including toolbars and UI.
  3. **GDI capture without UI** — Captures only the modeling area, without Fusion's UI.
  4. **GDI square no-UI** — Captures a square region of the modeling area (optimized for social media content).

- ⏸ **Automatic Pause & Resume**:
  - Capture automatically **pauses** when you open another document or close the one being recorded.
  - It **resumes** when you re-open the document.
  - The system checks periodically whether the active document is still available.

- 📁 **File naming & ordering**:
  - Filenames are generated with timestamp-based naming, which is **alphabetically sortable**.
  - This avoids file collisions in repeated sessions and ensures proper frame order for time-lapse creation.
  - ⚠ **Important**: Do not rename the screenshots manually — this can break the sequence order required by tools like `ffmpeg`.

---

## 🛠 How it works

Once started, AutoScreenshot saves images to a folder inside your plugin directory (`AutoScreenshot/output`). Each image is named using the date and time in the format:

```text
YYYY-MM-DD_HH-MM-SS.png
