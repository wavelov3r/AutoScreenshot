##AutoScreenshots 4 Fusion360, made by netrun.exe 
## v0.81 RC1

import adsk.core, adsk.fusion, traceback
import threading, time, os, re
import ctypes
import shutil  # Check for ffmpeg availability
import subprocess
import sys
from ctypes import wintypes
from ctypes import windll, byref
from ctypes.wintypes import RECT

# Ottieni il percorso assoluto del file corrente
BASE_DIR = os.path.dirname(__file__)
# Percorso della cartella 'lib' all'interno dell'add-in
LIB_PATH = os.path.join(BASE_DIR, 'lib')
# Aggiungi la cartella alla sys.path se non è già presente
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

import PIL
from PIL import Image

# ---------- Globals ----------
app: adsk.core.Application       = None
ui:  adsk.core.UserInterface     = None
handlers                         = []
capture_thread: threading.Thread = None

isCapturing     = False
save_path       = ''
interval        = 1    # default seconds
resWidth        = 1920 # default width
resHeight       = 1080 # default height
filenamePrefix  = ''
active_doc_name = None  # track active document name
fusion_hwnd     = None  # handle to Fusion 360 window
capture_method  = 'printwindow'  # 'fusion' or 'printwindow' or 'printwindowcropped'
title_bar_height = 0  # Calcolato dinamicamente all'avvio
controls_panel_height = 0  # Calcolato dinamicamente all'avvio

# --- Persistent config for capture_method ---
CONFIG_FILE = os.path.join(BASE_DIR, 'autoscreenshot_config.txt')

def load_capture_method():
    global capture_method
    try:
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                val = f.read().strip()
                if val in ('fusion', 'printwindow', 'printwindowcropped', 'printwindowcroppedsquare'):
                    capture_method = val
    except:
        pass

def save_capture_method():
    global capture_method
    try:
        with open(CONFIG_FILE, 'w') as f:
            f.write(capture_method)
    except:
        pass

cmdDef:  adsk.core.CommandDefinition = None
control: adsk.core.CommandControl    = None
qat_control: adsk.core.CommandControl = None  # Separate control for QAT

# Default folder base = Pictures/Fusion360 AutoScreen
PICTURES = os.path.join(os.path.expanduser("~"), "Pictures")
DEFAULT_BASE_FOLDER = os.path.join(PICTURES, "Fusion360 AutoScreen")

# Path to single 32×32 PNG icon
THIS_DIR      = os.path.dirname(__file__)
ICON_NORMAL32 = os.path.join(THIS_DIR, 'resources', 'normal')
ICON_PAUSED32 = os.path.join(THIS_DIR, 'resources', 'paused')

# Verify icon existence safely
if not os.path.isfile(ICON_NORMAL32):
    try: ui.messageBox(f"Icon not found: {ICON_NORMAL32}")
    except: pass

# ---------- Capture Loop ----------
def capture_loop():
    global isCapturing, save_path, interval, resWidth, resHeight, filenamePrefix, active_doc_name, fusion_hwnd, capture_method
    global ui
    user32 = ctypes.windll.user32

    while isCapturing:
        try:
            # Verify active document
            current_doc = app.activeDocument
            current_name = current_doc.name if current_doc else None

            # Check if the active document is still open
            open_docs = [doc.name for doc in app.documents]
            if active_doc_name and active_doc_name not in open_docs:
                toggle_capture()
                break

            # Verify Fusion 360 in foreground
            foreground_hwnd = user32.GetForegroundWindow()
            fusion_in_focus = (foreground_hwnd == fusion_hwnd)

            if not fusion_in_focus or current_name != active_doc_name:
                # Aggiorna icona in base allo stato di cattura
                cmdDef.resourceFolder = ICON_PAUSED32
                if control:
                    control.isVisible = False
                    control.isVisible = True
                # Pause until focus returns and project unchanged
                while isCapturing:
                    current_doc = app.activeDocument
                    current_name = current_doc.name if current_doc else None
                    foreground_hwnd = user32.GetForegroundWindow()
                    fusion_in_focus = (foreground_hwnd == fusion_hwnd)

                    # Check again if the active document is still open
                    open_docs = [doc.name for doc in app.documents]
                    if active_doc_name and active_doc_name not in open_docs:
                        toggle_capture()
                        break

                    if fusion_in_focus and current_name == active_doc_name:
                            # Aggiorna icona in base allo stato di cattura
                        cmdDef.resourceFolder = ICON_NORMAL32
                        if control:
                            control.isVisible = False
                            control.isVisible = True
                        break
                    time.sleep(1)
                continue

            # Capture screenshot
            ts = time.strftime('%Y%m%d%H%M%S')
            filename = f"{filenamePrefix}_{ts}.png"
            filepath = os.path.join(save_path, filename)
            if capture_method == 'fusion':
                capture_with_fusionapi(app, filepath)
            elif capture_method == 'printwindowcropped':
                hwnd = fusion_hwnd
                if hwnd:
                    capture_fusion_window_cropped(hwnd, filepath)
                else:
                    ui.messageBox("Unable to get Fusion window handle for GDI cropped capture.")
            elif capture_method == 'printwindowcroppedsquare':
                hwnd = fusion_hwnd
                if hwnd:
                    capture_fusion_window_cropped_square(hwnd, filepath)
                else:
                    ui.messageBox("Unable to get Fusion window handle for GDI cropped square capture.")
            else:
                # gdi method
                hwnd = fusion_hwnd
                if hwnd:
                    capture_fusion_window(hwnd, filepath)
                else:
                    ui.messageBox("Unable to get Fusion window handle for GDI capture.")
        except Exception:
            ui.messageBox(f'Error during capture:\n{traceback.format_exc()}')

        time.sleep(interval)

def capture_with_fusionapi(app, filepath):
    app.activeViewport.refresh()
    adsk.doEvents()
    time.sleep(0.1)
    app.activeViewport.saveAsImageFile(filepath, 0, 0)

def capture_fusion_window(hwnd, filepath):
    # 1) Prendi l’area client (senza chrome)
    rect = RECT()
    windll.user32.GetClientRect(hwnd, byref(rect))
    width  = rect.right - rect.left
    height = rect.bottom - rect.top

    global title_bar_height

    # 2) Prepara DC
    hwndDC   = windll.user32.GetDC(hwnd)
    srcDC    = windll.gdi32.CreateCompatibleDC(hwndDC)
    bmp      = windll.gdi32.CreateCompatibleBitmap(hwndDC, width, height)
    windll.gdi32.SelectObject(srcDC, bmp)

    # 3) Prova PrintWindow con flag 0 (solo client)
    if not windll.user32.PrintWindow(hwnd, srcDC, 0):
        # fallback: usa BitBlt con offset Y
        windll.gdi32.BitBlt(srcDC, 0, 0, width, height, hwndDC, 0, 0, 0x00CC0020)  # SRCCOPY

    # 4) Leggi i bit in un buffer
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_uint32),
            ('biWidth', ctypes.c_int32),
            ('biHeight', ctypes.c_int32),
            ('biPlanes', ctypes.c_uint16),
            ('biBitCount', ctypes.c_uint16),
            ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32),
            ('biXPelsPerMeter', ctypes.c_int32),
            ('biYPelsPerMeter', ctypes.c_int32),
            ('biClrUsed', ctypes.c_uint32),
            ('biClrImportant', ctypes.c_uint32)
        ]
    bmpinfo = BITMAPINFOHEADER()
    bmpinfo.biSize      = ctypes.sizeof(BITMAPINFOHEADER)
    bmpinfo.biWidth     = width
    bmpinfo.biHeight    = -height  # negative = top-down
    bmpinfo.biPlanes    = 1
    bmpinfo.biBitCount  = 32
    bmpinfo.biCompression = 0  # BI_RGB

    buf_len = width * height * 4
    buffer  = ctypes.create_string_buffer(buf_len)
    windll.gdi32.GetDIBits(srcDC, bmp, 0, height, buffer, byref(bmpinfo), 0)

    # 5) Costruisci l’immagine con PIL e croppa i primi title_bar_height px dall'alto
    img = Image.frombuffer('RGBA', (width, height), buffer, 'raw', 'BGRA', 0, 1)
    img_cropped = img.crop((0, title_bar_height, width, height))
    img_cropped.save(filepath)

    # 6) Pulizia
    windll.gdi32.DeleteObject(bmp)
    windll.gdi32.DeleteDC(srcDC)
    windll.user32.ReleaseDC(hwnd, hwndDC)

def capture_fusion_window_cropped(hwnd, filepath):
    # Screenshot e crop di title_bar_height + controls_panel_height
    rect = RECT()
    windll.user32.GetClientRect(hwnd, byref(rect))
    width  = rect.right - rect.left
    height = rect.bottom - rect.top

    global title_bar_height, controls_panel_height

    hwndDC   = windll.user32.GetDC(hwnd)
    srcDC    = windll.gdi32.CreateCompatibleDC(hwndDC)
    bmp      = windll.gdi32.CreateCompatibleBitmap(hwndDC, width, height)
    windll.gdi32.SelectObject(srcDC, bmp)

    if not windll.user32.PrintWindow(hwnd, srcDC, 0):
        windll.gdi32.BitBlt(srcDC, 0, 0, width, height, hwndDC, 0, 0, 0x00CC0020)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_uint32),
            ('biWidth', ctypes.c_int32),
            ('biHeight', ctypes.c_int32),
            ('biPlanes', ctypes.c_uint16),
            ('biBitCount', ctypes.c_uint16),
            ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32),
            ('biXPelsPerMeter', ctypes.c_int32),
            ('biYPelsPerMeter', ctypes.c_int32),
            ('biClrUsed', ctypes.c_uint32),
            ('biClrImportant', ctypes.c_uint32)
        ]
    bmpinfo = BITMAPINFOHEADER()
    bmpinfo.biSize      = ctypes.sizeof(BITMAPINFOHEADER)
    bmpinfo.biWidth     = width
    bmpinfo.biHeight    = -height
    bmpinfo.biPlanes    = 1
    bmpinfo.biBitCount  = 32
    bmpinfo.biCompression = 0

    buf_len = width * height * 4
    buffer  = ctypes.create_string_buffer(buf_len)
    windll.gdi32.GetDIBits(srcDC, bmp, 0, height, buffer, byref(bmpinfo), 0)

    # Crop title_bar_height + controls_panel_height dall'alto
    crop_top = controls_panel_height - title_bar_height 
    img = Image.frombuffer('RGBA', (width, height), buffer, 'raw', 'BGRA', 0, 1)
    img_cropped = img.crop((0, crop_top, width, height))
    img_cropped.save(filepath)

    windll.gdi32.DeleteObject(bmp)
    windll.gdi32.DeleteDC(srcDC)
    windll.user32.ReleaseDC(hwnd, hwndDC)

def capture_fusion_window_cropped_square(hwnd, filepath):
    # Screenshot quadrato centrato sull'area client, croppando equamente dai lati
    rect = RECT()
    windll.user32.GetClientRect(hwnd, byref(rect))
    width  = rect.right - rect.left
    height = rect.bottom - rect.top

    global title_bar_height, controls_panel_height

    hwndDC   = windll.user32.GetDC(hwnd)
    srcDC    = windll.gdi32.CreateCompatibleDC(hwndDC)
    bmp      = windll.gdi32.CreateCompatibleBitmap(hwndDC, width, height)
    windll.gdi32.SelectObject(srcDC, bmp)

    if not windll.user32.PrintWindow(hwnd, srcDC, 0):
        windll.gdi32.BitBlt(srcDC, 0, 0, width, height, hwndDC, 0, 0, 0x00CC0020)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_uint32),
            ('biWidth', ctypes.c_int32),
            ('biHeight', ctypes.c_int32),
            ('biPlanes', ctypes.c_uint16),
            ('biBitCount', ctypes.c_uint16),
            ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32),
            ('biXPelsPerMeter', ctypes.c_int32),
            ('biYPelsPerMeter', ctypes.c_int32),
            ('biClrUsed', ctypes.c_uint32),
            ('biClrImportant', ctypes.c_uint32)
        ]
    bmpinfo = BITMAPINFOHEADER()
    bmpinfo.biSize      = ctypes.sizeof(BITMAPINFOHEADER)
    bmpinfo.biWidth     = width
    bmpinfo.biHeight    = -height
    bmpinfo.biPlanes    = 1
    bmpinfo.biBitCount  = 32
    bmpinfo.biCompression = 0

    buf_len = width * height * 4
    buffer  = ctypes.create_string_buffer(buf_len)
    windll.gdi32.GetDIBits(srcDC, bmp, 0, height, buffer, byref(bmpinfo), 0)

    # Crop title_bar_height + controls_panel_height dall'alto
    crop_top = controls_panel_height - title_bar_height 
    img = Image.frombuffer('RGBA', (width, height), buffer, 'raw', 'BGRA', 0, 1)
    img_cropped = img.crop((0, crop_top, width, height))

    # Crop quadrato centrato
    square_size = img_cropped.height
    left = max(0, (img_cropped.width - square_size) // 2)
    right = left + square_size
    img_square = img_cropped.crop((left, 0, right, square_size))
    img_square.save(filepath)

    windll.gdi32.DeleteObject(bmp)
    windll.gdi32.DeleteDC(srcDC)
    windll.user32.ReleaseDC(hwnd, hwndDC)

# ---------- Control Capture ----------
def start_capture():
    global capture_thread, isCapturing, filenamePrefix, save_path, active_doc_name
    if not isCapturing:
        try:
            doc = app.activeDocument
            if doc:
                if active_doc_name != doc.name:
                    base = os.path.splitext(doc.name)[0]
                    base = re.sub(r'v\d+(\.\d+)*$', '', base)
                    filenamePrefix = re.sub(r'\s+', '_', base).rstrip('_')
                    save_path = os.path.join(DEFAULT_BASE_FOLDER, filenamePrefix)
                active_doc_name = doc.name
            else:
                filenamePrefix = 'Project'
                save_path = os.path.join(DEFAULT_BASE_FOLDER, filenamePrefix)
                active_doc_name = None
        except:
            filenamePrefix = 'Project'
            save_path = os.path.join(DEFAULT_BASE_FOLDER, filenamePrefix)
            active_doc_name = None
        os.makedirs(save_path, exist_ok=True)
    if not capture_thread or not capture_thread.is_alive():
        isCapturing = True
        capture_thread = threading.Thread(target=capture_loop)
        capture_thread.start()

def stop_capture():
    global isCapturing
    isCapturing = False

# ---------- UI Update ----------
def update_button():
    global cmdDef, control, isCapturing
    if not cmdDef: return
    tooltipstring = (
        "Captures screenshots at fixed intervals while Fusion 360 is in the foreground and a project is open. "
        "Capture automatically pauses if you switch projects or Fusion is not active, and resumes when it is.\n\n"
        "To stop, relaunch the add-in and press Stop.\n\n"
        "Screenshots are saved in the user's Pictures/Fusion360 AutoScreen folder and are never deleted — manage them manually. "
        "Changing the folder or filename is possible but not recommended because you could have issues with ffmpeg automatic video encoding.\n\n"
        "Files are timestamped and alphabetically ordered, allowing ffmpeg to generate a video and letting you pause/resume "
        "recording at any time without using sequential numbers."
    )

    cmdDef.name = 'AutoScreenshot (STOP)' if isCapturing else 'Auto Screenshot (START)'
    cmdDef.tooltip = 'Stop recording screenshots' if isCapturing else tooltipstring
    try:
        for panel in ui.allToolbarPanels:
            for i in range(panel.controls.count):
                try:
                    ctrl = panel.controls.item(i)
                    if ctrl.id == 'AutoScreenshotCmd':
                        ctrl.isVisible = False
                        ctrl.isVisible = True
                except:
                    continue
    except:
        pass

def define_screenshot_area():
    global title_bar_height, controls_panel_height
    # Dynamically calculate title_bar_height
    try:
        if fusion_hwnd:
            rect_win = RECT()
            rect_cli = RECT()
            windll.user32.GetWindowRect(fusion_hwnd, byref(rect_win))
            windll.user32.GetClientRect(fusion_hwnd, byref(rect_cli))
            pt = wintypes.POINT()
            pt.x = rect_cli.left
            pt.y = rect_cli.top
            windll.user32.ClientToScreen(fusion_hwnd, byref(pt))
            client_top = pt.y
            title_bar_height = client_top - rect_win.top
            # Calculate controls_panel_height
            # Find the position of the viewport relative to the client
            try:
                # Make the process DPI-aware (important)
                user32 = ctypes.windll.user32
                if hasattr(user32, 'SetProcessDPIAware'):
                    user32.SetProcessDPIAware()

                # 1) Get the height of the work area (screen minus taskbar)
                SPI_GETWORKAREA = 0x0030
                work_rect = wintypes.RECT()
                user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, byref(work_rect), 0)
                work_height = work_rect.bottom - work_rect.top

                # 2) Read the "logical" height of the viewport
                vp = app.activeViewport
                vp_logical = vp.height  # height according to Fusion API

                # 3) Calculate DPI scaling to convert to physical pixels
                hdc = user32.GetDC(None)
                gdi = ctypes.windll.gdi32
                LOGPIXELSY = 90
                dpi = gdi.GetDeviceCaps(hdc, LOGPIXELSY)
                user32.ReleaseDC(None, hdc)
                scale = dpi / 96.0
                vp_physical = int(vp_logical * scale)

                # 4) Difference = space occupied by toolbars/panels
                controls_panel_height = work_height - vp_physical

                # DEBUG — you can remove in production
               # ui.messageBox(
               #     f"DEBUG:\n"
               #     f" work_height     = {work_height}\n"
               #     f" vp.logical      = {vp_logical}\n"
               #     f" dpi scaling     = {dpi} ⇒ scale={scale:.2f}\n"
               #     f" vp.physical     = {vp_physical}\n"
               #     f" controls height = {controls_panel_height}"
               # )
            except Exception as e:
                controls_panel_height = 0
                #ui.messageBox(f"DEBUG: error calculating controls_panel_height: {e}")
        else:
            title_bar_height = 0
            controls_panel_height = 0
    except:
        title_bar_height = 0
        controls_panel_height = 0


# Helper functions for QAT management
def add_to_qat():
    global qat_control, cmdDef
    if cmdDef:
        qat = ui.toolbars.itemById('QAT')
        if qat:
            # Remove any existing control
            existing = qat.controls.itemById('AutoScreenshotCmd')
            if existing: existing.deleteMe()
            # Add to QAT
            qat_control = qat.controls.addCommand(cmdDef)
            qat_control.isVisible = True

def remove_from_qat():
    global qat_control
    if qat_control:
        qat_control.deleteMe()
        qat_control = None

def toggle_capture():
    global save_path, isCapturing
    if not (save_path and os.path.isdir(save_path)):
        ui.messageBox('Please set a valid folder first!')
        return
    
    if isCapturing: 
        stop_capture()
        remove_from_qat()  # Remove from QAT when stopping
    else: 
        start_capture()
        add_to_qat()  # Add to QAT when starting
    
    update_button()


# ---------- input.txt Support ----------
def ensure_input_txt_exists():
    global save_path
    input_txt = os.path.join(save_path, 'input.txt')
    if not os.path.isfile(input_txt):
        try:
            with open(input_txt, 'w'): pass
        except Exception as e:
            ui.messageBox(f"Failed to create input.txt:\n{e}")

def update_input_txt(file_list):
    global save_path
    input_txt = os.path.join(save_path, 'input.txt')
    try:
        with open(input_txt, 'w') as f:
            for fn in file_list:
                f.write(f"file '{os.path.join(save_path, fn)}'\n")
    except Exception as e:
        ui.messageBox(f"Failed to update input.txt:\n{e}")

# ---------- Command Handlers ----------
class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        global filenamePrefix, save_path, resWidth, resHeight, active_doc_name, fusion_hwnd, capture_method
        # --- Load persisted capture_method ---
        load_capture_method()
        # --- Define screenshot area ---
        if not isCapturing:
            define_screenshot_area()
        # Detect desktop resolution
        try:
            user32 = ctypes.windll.user32
            if hasattr(user32, 'SetProcessDPIAware'):
                user32.SetProcessDPIAware()
            resWidth = user32.GetSystemMetrics(78)
            resHeight = user32.GetSystemMetrics(79)
            if resWidth <= 0 or resHeight <= 0:
                raise ValueError("Invalid resolution detected")
        except:
            resWidth, resHeight = 1920, 1080
        # Initialize doc name and window handle
        if not isCapturing:
            try:
                active_doc_name = app.activeDocument.name
            except:
                active_doc_name = None
            try:
                fusion_hwnd = ctypes.windll.user32.GetForegroundWindow()
            except:
                fusion_hwnd = None
            try:
                doc = app.activeDocument
                if doc:
                    base = os.path.splitext(doc.name)[0]
                    base = re.sub(r'v\d+(\.\d+)*$', '', base)
                    filenamePrefix = re.sub(r'\s+', '_', base).rstrip('_')
                else:
                    filenamePrefix = 'Project'
            except:
                filenamePrefix = 'Project'
            save_path = os.path.join(DEFAULT_BASE_FOLDER, filenamePrefix)
        cmd = args.command
        inputs = cmd.commandInputs
        global prefixInput, savePathInput, intervalInput, videoNameInput, fpsInput, ffmpegButton
        prefix_label = 'Active project' if isCapturing else 'File Name (Prefix)'
        prefixInput   = inputs.addStringValueInput('filePrefix', prefix_label, filenamePrefix)
        savePathInput = inputs.addStringValueInput('savePath', 'Save Folder', save_path)
        intervalInput = inputs.addValueInput('interval', 'Interval (s)', 's', adsk.core.ValueInput.createByReal(interval))
        # --- Capture method section ---
        inputs.addTextBoxCommandInput('captureMethodLabel', '', 'Capture method', 1, True)
        global fusionCaptureInput, printWindowInput, printWindowCroppedInput, printWindowCroppedSquareInput
        fusionCaptureInput = inputs.addBoolValueInput('fusionCapture', 'Fusion API (no UI)', True, '', capture_method == 'fusion')
        printWindowInput = inputs.addBoolValueInput('gdiCapture', 'GDI (with UI)', True, '', capture_method == 'printwindow')
        printWindowCroppedInput = inputs.addBoolValueInput('gdiCroppedCapture', 'GDI (no UI)', True, '', capture_method == 'printwindowcropped')
        printWindowCroppedSquareInput = inputs.addBoolValueInput('gdiCroppedSquareCapture', 'GDI (no UI, squared)', True, '', capture_method == 'printwindowcroppedsquare')
        fusionCaptureInput.isEnabled = not isCapturing
        printWindowInput.isEnabled = not isCapturing
        printWindowCroppedInput.isEnabled = not isCapturing
        printWindowCroppedSquareInput.isEnabled = not isCapturing
        # --- End capture method section ---
        resolution_info = f"Resolution: {resWidth}x{resHeight}"
        inputs.addTextBoxCommandInput('resolutionInfo', '', resolution_info, 1, True)
        inputs.addTextBoxCommandInput('description', '', 'Create FFmpeg video', 1, True)
        videoNameInput = inputs.addStringValueInput('videoName', 'Name:', 'animation.mp4')
        fpsInput       = inputs.addValueInput('fps', 'FPS:', '', adsk.core.ValueInput.createByReal(30))
        ffmpegButton   = inputs.addBoolValueInput('createVideo', 'Create Video', False, '', False)
        ffmpegButton.isEnabled = not isCapturing
        for inp in [prefixInput, savePathInput, intervalInput, videoNameInput, fpsInput]:
            inp.isEnabled = not isCapturing
        onInput = CommandInputChangedHandler()
        cmd.inputChanged.add(onInput); handlers.append(onInput)
        cmd.okButtonText = 'STOP' if isCapturing else 'CAPTURE'
        cmd.cancelButtonText = 'Cancel'
        onExec = CommandExecuteHandler()
        cmd.execute.add(onExec); handlers.append(onExec)
        onDst = CommandDestroyHandler()
        cmd.destroy.add(onDst); handlers.append(onDst)

class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        global save_path, interval, resWidth, resHeight, filenamePrefix, active_doc_name, capture_method
        pref = prefixInput.value.strip()
        path = savePathInput.value.strip()
        # --- Read capture method from UI ---
        if fusionCaptureInput.value:
            capture_method = 'fusion'
        elif printWindowInput.value:
            capture_method = 'printwindow'
        elif printWindowCroppedInput.value:
            capture_method = 'printwindowcropped'
        elif printWindowCroppedSquareInput.value:
            capture_method = 'printwindowcroppedsquare'
        if not isCapturing:
            if pref:
                filenamePrefix = pref
            else:
                try:
                    doc = app.activeDocument
                    if doc:
                        base = os.path.splitext(doc.name)[0]
                        base = re.sub(r'v\d+(\.\d+)*$', '', base)
                        filenamePrefix = re.sub(r'\s+', '_', base).rstrip('_')
                    else:
                        filenamePrefix = 'Project'
                except:
                    filenamePrefix = 'Project'
            if path and os.path.isdir(path):
                save_path = path
            else:
                save_path = os.path.join(DEFAULT_BASE_FOLDER, filenamePrefix)
            active_doc_name = app.activeDocument.name if app.activeDocument else None
            os.makedirs(save_path, exist_ok=True)
            ensure_input_txt_exists()
        interval = max(1, intervalInput.value)
        toggle_capture()
        try:
            for inp in [prefixInput, savePathInput, intervalInput, videoNameInput, fpsInput, ffmpegButton, fusionCaptureInput, printWindowInput, printWindowCroppedInput, printWindowCroppedSquareInput]:
                inp.isEnabled = not isCapturing
        except:
            pass

class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        global save_path, filenamePrefix, videoNameInput, fpsInput, ffmpegButton, fusionCaptureInput, printWindowInput, printWindowCroppedInput, printWindowCroppedSquareInput, capture_method
        # --- Interlocked capture method flags ---
        changed = False
        if args.input.id == 'fusionCapture' and fusionCaptureInput.value:
            capture_method = 'fusion'
            printWindowInput.value = False
            printWindowCroppedInput.value = False
            printWindowCroppedSquareInput.value = False
            changed = True
        elif args.input.id == 'gdiCapture' and printWindowInput.value:
            capture_method = 'printwindow'
            fusionCaptureInput.value = False
            printWindowCroppedInput.value = False
            printWindowCroppedSquareInput.value = False
            changed = True
        elif args.input.id == 'gdiCroppedCapture' and printWindowCroppedInput.value:
            capture_method = 'printwindowcropped'
            fusionCaptureInput.value = False
            printWindowInput.value = False
            printWindowCroppedSquareInput.value = False
            changed = True
        elif args.input.id == 'gdiCroppedSquareCapture' and printWindowCroppedSquareInput.value:
            capture_method = 'printwindowcroppedsquare'
            fusionCaptureInput.value = False
            printWindowInput.value = False
            printWindowCroppedInput.value = False
            changed = True
        if changed:
            save_capture_method()
        if args.input.id == 'createVideo' and ffmpegButton.value:
            ffmpegButton.value = False
            if not shutil.which("ffmpeg"):
                ui.messageBox('FFmpeg is not installed or not in PATH.')
                return
            video_name = videoNameInput.value.strip()
            if not video_name:
                ui.messageBox('Please provide a valid video name.')
                return
            try:
                fps = int(fpsInput.value)
                if fps <= 0:
                    raise ValueError
            except:
                ui.messageBox('Please provide a valid FPS value.')
                return
            ensure_input_txt_exists()
            pngs = sorted([f for f in os.listdir(save_path)
                           if f.startswith(f"{filenamePrefix}_") and f.endswith(".png")])
            update_input_txt(pngs)
            input_txt = os.path.join(save_path, "input.txt")
            output_v  = os.path.join(save_path, video_name)
            cmd_line  = (
                f'ffmpeg -r {fps} -f concat -safe 0 -i "{input_txt}" '
                f'-c:v libx264 -preset slow -crf 22 -pix_fmt yuv420p -an "{output_v}"'
            )
            try:
                os.system(f'start cmd /k "{cmd_line}"')
            except Exception as e:
                ui.messageBox(f"Failed to execute ffmpeg:\n{e}")

class CommandDestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        update_button()
        try:
            for inp in [prefixInput, savePathInput, intervalInput, videoNameInput, fpsInput, ffmpegButton, fusionCaptureInput, printWindowInput, printWindowCroppedInput, printWindowCroppedSquareInput]:
                inp.isEnabled = True
        except:
            pass

# ---------- run / stop ----------
def run(context):
    global app, ui, cmdDef, control, qat_control, isCapturing, active_doc_name, fusion_hwnd, title_bar_height, controls_panel_height
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface
        try:
            active_doc_name = app.activeDocument.name
        except:
            active_doc_name = None
        try:
            fusion_hwnd = ctypes.windll.user32.GetForegroundWindow()
        except:
            fusion_hwnd = None

        # --- Load persisted capture_method at startup ---
        load_capture_method()
        
        stop_capture()
        isCapturing = False

        # Clean up existing command
        cmdDefs = ui.commandDefinitions
        cmdDef = cmdDefs.itemById('AutoScreenshotCmd')
        if cmdDef:
            cmdDef.deleteMe()

        # Create command definition
        cmdDef = cmdDefs.addButtonDefinition(
            'AutoScreenshotCmd',
            'Auto Screenshot',
            'Automatically capture screenshots of the active project',
            ICON_NORMAL32
        )
        onCreate = CommandCreatedHandler()
        cmdDef.commandCreated.add(onCreate)
        handlers.append(onCreate)

        # Try to add the command to the "Utilità" panel (ID: TSplineUtilitiesPanel)
        panel_found = False
        
        # Safer approach to find the panel - don't rely on activeProduct
        try:
            # Try to find the specific panel by ID in any workspace
            for workspace in ui.workspaces:
                try:
                    # Check if this workspace has toolbar tabs before iterating
                    if workspace.isValid and workspace.toolbarTabs:
                        for tab in workspace.toolbarTabs:
                            try:
                                panel = tab.toolbarPanels.itemById('SolidScriptsAddinsPanel')
                                if panel:
                                    existing = panel.controls.itemById('AutoScreenshotCmd')
                                    if existing: existing.deleteMe()
                                    control = panel.controls.addCommand(cmdDef)
                                    control.isPromoted = True
                                    control.isVisible = False
                                    control.isVisible = True
                                    panel_found = True
                                    break
                            except:
                                continue
                    if panel_found:
                        break
                except:
                    continue
        except:
            pass
            
        # If panel not found, try using product types
        if not panel_found:
            try:
                # If active document exists, try its product
                if app.activeDocument:
                    product = app.activeDocument.products.itemByProductType('DesignProductType')
                    if product:
                        designWS = ui.workspacesByProductType('DesignProductType').itemById('FusionSolidEnvironment')
                        if designWS:
                            for tab in designWS.toolbarTabs:
                                if "utilit" in tab.id.lower() or "utilit" in tab.name.lower():
                                    for panel in tab.toolbarPanels:
                                        existing = panel.controls.itemById('AutoScreenshotCmd')
                                        if existing: existing.deleteMe()
                                        control = panel.controls.addCommand(cmdDef)
                                        control.isPromoted = True
                                        control.isVisible = False
                                        control.isVisible = True
                                        panel_found = True
                                        break
                                if panel_found:
                                    break
            except:
                pass

        # Fallback to traditional location if TSplineUtilitiesPanel not found
        if not panel_found:
            designWS = ui.workspaces.itemById('FusionSolidEnvironment')
            toolsTab = designWS.toolbarTabs.itemById('ToolsTab')
            utilitiesPanel = toolsTab.toolbarPanels.itemById('SolidScriptsAddinsPanel')
            if utilitiesPanel:
                existing = utilitiesPanel.controls.itemById('AutoScreenshotCmd')
                if existing: existing.deleteMe()
                control = utilitiesPanel.controls.addCommand(cmdDef)
                control.isPromoted = True
                control.isVisible = False
                control.isVisible = True
            else:
                ui.messageBox("SolidScriptsAddinsPanel not found in ToolsTab. Using Quick Access Toolbar only.")

        # Only add to QAT if already capturing (which should be false on startup)
        qat_control = None
        if isCapturing:
            add_to_qat()

        update_button()
        adsk.autoTerminate(False)
    except:
        ui.messageBox(f'Error in run():\n{traceback.format_exc()}')

def stop(context):
    global control, cmdDef
    try:
        stop_capture()
        if control:
            control.deleteMe(); control = None
        if cmdDef:
            cmdDef.deleteMe();   cmdDef = None
    except:
        ui.messageBox(f'stop() error():\n{traceback.format_exc()}')