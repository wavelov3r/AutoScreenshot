# AutoScreenshot for Fusion 360

**AutoScreenshot** is a plugin for Autodesk Fusion 360 that automatically captures screenshots of your project over time. It's ideal for documenting your workflow, creating time-lapse videos, or reviewing your design progress.

---

## ✨ Features

- 📷 **Four capture modes**:
  1. **Fusion API-based** — Uses Fusion's internal `viewport.saveAsImage()` (may cause the viewcube to freeze).
  2. **GDI capture with UI** — Captures the entire Fusion window including interface elements.
  3. **GDI capture without UI** — Captures only the modeling area.
  4. **GDI square no-UI** — Captures a square portion of the modeling area, ideal for social media content.

- ⏸ **Automatic pause and resume**:
  - Capture **pauses automatically** when Fusion is minimized or when you switch to another document.
  - It **resumes automatically** when the original document is reactivated.

- 📁 **File naming and ordering**:
  - Screenshots are saved with filenames based on the current date and time, ensuring alphabetical order.
  - This approach:
    - Prevents duplicate files during multiple capture sessions.
    - Maintains an ordered sequence for time-lapse creation.
    - Facilitates manual editing or trimming before merging.
  - ⚠ **Important**: Renaming the files manually is discouraged — tools like `ffmpeg` rely on the alphabetical order of filenames to merge frames correctly into a video.

---

## 🧪 Installation

### 1. Install FFmpeg on Windows

1. Download FFmpeg from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html).
2. Extract the zip to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your system `PATH`:

```text
   - Press Win + R, type sysdm.cpl, and press Enter.
   - Go to Advanced > Environment Variables.
   - Under System variables, find Path, click Edit, then New, and add:
     C:\ffmpeg\bin
   - Click OK and restart the terminal or your PC.
