"""
webcam_capture_server.py
========================
Modulo di acquisizione immagini da webcam con GUI di configurazione e server socket.

Il Live View può restare attivo mentre il server è in funzione.
Un threading.Lock() garantisce che webcam e server non confliggano.

PROTOCOLLO SOCKET (TCP localhost):
-----------------------------------
  Client → Server:  "CAPTURE:nome_immagine.jpg\n"
  Server → Client:  "OK:percorso_completo\n"   oppure   "ERROR:messaggio\n"
  Client → Server:  "STATUS\n"
  Server → Client:  "READY\n"  oppure  "NOT_READY:motivo\n"
"""

import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import socket
import os
import time

# ── Alarm CAN sender (opzionale: richiede python-can + cantools + driver Vector) ──
try:
    from alarm_can_sender import AlarmCanSender, CAN_AVAILABLE
except ImportError:
    AlarmCanSender = None
    CAN_AVAILABLE  = False


# ─────────────────────────────────────────────
#  Stato applicazione
# ─────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.cap = None
        self.webcam_initialized = False
        self.selected_camera = 0
        self.selected_resolution = "1920x1080"
        self.resolution_options = ["640x480", "1280x720", "1920x1080"]

        self.webcam_contrast   = 7
        self.webcam_saturation = 60
        self.webcam_shutter    = -6   # CAP_PROP_EXPOSURE: shutter speed (2^n secondi)
        self.webcam_gain       = 0    # CAP_PROP_GAIN: ISO/gain analogico (0-255)
        self.webcam_focus      = 73
        self.webcam_sharpness  = 128

        self.rois = {}   # {id(int): (x1, y1, x2, y2, rotation)}
                         # rotation: 0, 90, 180, 270

        # ── Correzione prospettica (globale, applicata prima del crop ROI) ──
        self.perspective_points  = []    # lista di 4 (x, y) in coordinate frame reale
        self.perspective_matrix  = None  # matrice 3x3 calcolata da cv2.getPerspectiveTransform
        self.perspective_dst_w   = 0     # larghezza output dopo correzione
        self.perspective_dst_h   = 0     # altezza output dopo correzione

        self.server_running = False
        self.server_socket  = None
        self.server_port    = 5005
        # Quando gira come .exe PyInstaller, __file__ punta alla cartella temp.
        # sys.executable punta invece al vero .exe, quindi usiamo la sua directory.
        import sys
        if getattr(sys, 'frozen', False):
            self.save_directory = os.path.dirname(sys.executable)
        else:
            self.save_directory = os.path.dirname(os.path.abspath(__file__))

        # ── LOCK: accesso esclusivo alla webcam (apertura/chiusura/parametri) ──
        self.cam_lock = threading.Lock()

        # ── Frame grabber thread ──────────────────────────────────────────────
        # Un thread dedicato legge continuamente dalla webcam e salva
        # sempre l'ultimo frame disponibile. Il Live View e il server
        # leggono da qui senza dover aspettare cap.read().
        self.latest_frame      = None       # ultimo frame BGR disponibile
        self.frame_lock        = threading.Lock()   # protegge latest_frame
        self.grabber_running   = False      # flag per fermare il thread

        self.log_fn = print


app = AppState()


# ─────────────────────────────────────────────
#  Configurazione CAN Alarm Sender
#  ← Adattare qui percorso DBC, canale e nome app
# ─────────────────────────────────────────────
# _alarm_sender viene inizializzato dalla GUI quando l'utente seleziona il DBC
_alarm_sender = None


# ─────────────────────────────────────────────
#  Webcam helpers
# ─────────────────────────────────────────────
def initialize_webcam():
    """Apre e configura la webcam. Deve essere chiamata col lock acquisito."""
    try:
        if app.cap is not None and app.cap.isOpened():
            app.cap.release()
            app.cap = None

        try:
            app.cap = cv2.VideoCapture(app.selected_camera, cv2.CAP_DSHOW)
        except Exception:
            app.cap = cv2.VideoCapture(app.selected_camera)

        if not app.cap.isOpened():
            app.log_fn(f"[ERRORE] Impossibile aprire webcam {app.selected_camera}")
            return False

        width, height = map(int, app.selected_resolution.split('x'))
        app.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
        app.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        app.cap.set(cv2.CAP_PROP_FPS,          30)
        app.cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
        app.cap.set(cv2.CAP_PROP_AUTOFOCUS,    0)

        _apply_webcam_params()

        for _ in range(3):
            app.cap.read()

        actual_w = int(app.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(app.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        app.log_fn(f"[OK] Webcam aperta: {actual_w}x{actual_h}")
        app.webcam_initialized = True

        # Avvia il thread grabber se non è già in esecuzione
        if not app.grabber_running:
            threading.Thread(target=start_frame_grabber, daemon=True).start()

        return True

    except Exception as e:
        app.log_fn(f"[ERRORE] Inizializzazione webcam: {e}")
        return False


def _apply_webcam_params():
    if app.cap is None or not app.cap.isOpened():
        return
    app.cap.set(cv2.CAP_PROP_CONTRAST,   float(app.webcam_contrast))
    app.cap.set(cv2.CAP_PROP_SATURATION, float(app.webcam_saturation))
    app.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)              # 1 = manual (DirectShow)
    app.cap.set(cv2.CAP_PROP_EXPOSURE,      float(app.webcam_shutter))
    app.cap.set(cv2.CAP_PROP_GAIN,          float(app.webcam_gain))
    try:
        app.cap.set(cv2.CAP_PROP_FOCUS, float(app.webcam_focus))
    except Exception:
        pass


def release_webcam():
    stop_frame_grabber()
    time.sleep(0.15)   # lascia al grabber il tempo di uscire dal loop
    with app.cam_lock:
        if app.cap is not None and app.cap.isOpened():
            app.cap.release()
            app.cap = None
        app.webcam_initialized = False
    with app.frame_lock:
        app.latest_frame = None


def start_frame_grabber():
    """
    Thread dedicato che legge continuamente dalla webcam alla massima velocità
    e salva sempre l'ultimo frame in app.latest_frame.
    Il Live View e il server leggono da lì, senza mai bloccarsi su cap.read().
    """
    app.grabber_running = True
    app.log_fn("[GRABBER] Thread acquisizione frame avviato")

    while app.grabber_running:
        with app.cam_lock:
            if app.cap is None or not app.cap.isOpened():
                # Webcam non disponibile: aspetta un po' e riprova
                time.sleep(0.1)
                continue
            ret, frame = app.cap.read()

        if ret and frame is not None:
            with app.frame_lock:
                app.latest_frame = frame
        else:
            time.sleep(0.01)   # piccola pausa se il frame non è disponibile

    app.log_fn("[GRABBER] Thread acquisizione frame fermato")


def stop_frame_grabber():
    app.grabber_running = False


def grab_color_frame():
    """
    Restituisce l'ultimo frame disponibile (già letto dal grabber thread).
    Velocissimo: non blocca su cap.read(), non usa cam_lock.
    """
    with app.frame_lock:
        if app.latest_frame is None:
            return None
        return app.latest_frame.copy()


def grab_fresh_frame_for_capture():
    """
    Per il server: restituisce il frame più recente disponibile.
    Il grabber thread lo tiene sempre aggiornato.
    """
    with app.frame_lock:
        if app.latest_frame is None:
            return None
        return app.latest_frame.copy()


def capture_roi(frame, area_id):
    """Ritaglia il frame sull'area e applica la rotazione configurata."""
    roi = app.rois.get(area_id)
    if roi is None:
        return frame
    x1, y1, x2, y2, rotation = roi
    h, w = frame.shape[:2]
    x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
    y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return frame
    cropped = frame[y1:y2, x1:x2]

    # Applica rotazione
    if rotation == 90:
        cropped = cv2.rotate(cropped, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        cropped = cv2.rotate(cropped, cv2.ROTATE_180)
    elif rotation == 270:
        cropped = cv2.rotate(cropped, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return cropped


def save_image(frame, filepath):
    try:
        cv2.imwrite(filepath, frame)
        return True
    except Exception as e:
        app.log_fn(f"[ERRORE] Salvataggio immagine: {e}")
        return False


def apply_perspective_correction(frame):
    """
    Applica la correzione prospettica globale al frame se configurata.
    Trasforma il quadrilatero definito dai 4 angoli in un rettangolo perfetto.
    Se non configurata, ritorna il frame invariato.
    """
    if app.perspective_matrix is None:
        return frame
    try:
        corrected = cv2.warpPerspective(
            frame,
            app.perspective_matrix,
            (app.perspective_dst_w, app.perspective_dst_h)
        )
        return corrected
    except Exception as e:
        app.log_fn(f"[WARN] Correzione prospettica fallita: {e}")
        return frame


def compute_perspective_matrix():
    """
    Calcola la matrice di trasformazione prospettica dai 4 punti selezionati.
    Ordine punti (senso orario): TL, TR, BR, BL.
    La dimensione di output viene calcolata automaticamente dalla geometria dei 4 punti.
    """
    if len(app.perspective_points) != 4:
        return False
    try:
        import numpy as np
        pts = np.float32(app.perspective_points)

        # Ordine punti: TL, TR, BR, BL  (senso orario)
        tl, tr, br, bl = pts

        # Larghezza output = media delle due larghezze (top e bottom)
        w_top    = np.linalg.norm(tr - tl)
        w_bot    = np.linalg.norm(br - bl)
        dst_w    = int(max(w_top, w_bot))

        # Altezza output = media delle due altezze (left e right)
        h_left   = np.linalg.norm(bl - tl)
        h_right  = np.linalg.norm(br - tr)
        dst_h    = int(max(h_left, h_right))

        if dst_w <= 0 or dst_h <= 0:
            return False

        src_pts = np.float32([tl, tr, br, bl])
        dst_pts = np.float32([
            [0,         0        ],   # TL
            [dst_w - 1, 0        ],   # TR
            [dst_w - 1, dst_h - 1],   # BR
            [0,         dst_h - 1]    # BL
        ])

        app.perspective_matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        app.perspective_dst_w  = dst_w
        app.perspective_dst_h  = dst_h
        app.log_fn(f"[OK] Matrice prospettica calcolata → output: {dst_w}x{dst_h}px")
        return True
    except Exception as e:
        app.log_fn(f"[ERRORE] Calcolo matrice prospettica: {e}")
        return False


# ─────────────────────────────────────────────
#  Server socket
# ─────────────────────────────────────────────
def start_socket_server(port, log_fn):
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('127.0.0.1', port))
        srv.listen(5)
        srv.settimeout(1.0)
        app.server_socket = srv
        app.server_running = True
        log_fn(f"[SERVER] In ascolto su 127.0.0.1:{port}")

        while app.server_running:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=_handle_client,
                args=(conn, addr, log_fn),
                daemon=True
            ).start()

    except Exception as e:
        log_fn(f"[ERRORE SERVER] {e}")
    finally:
        try:
            srv.close()
        except Exception:
            pass
        app.server_running = False
        log_fn("[SERVER] Fermato")


def _handle_client(conn, addr, log_fn):
    try:
        conn.settimeout(10.0)
        data = b""
        while b"\n" not in data:
            chunk = conn.recv(1024)
            if not chunk:
                break
            data += chunk

        command = data.decode(errors="replace").strip()
        log_fn(f"[SERVER] Comando da {addr}: {command!r}")
        response = _process_command(command, log_fn)
        conn.sendall((response + "\n").encode())

    except Exception as e:
        log_fn(f"[SERVER] Errore client {addr}: {e}")
        try:
            conn.sendall(f"ERROR:{e}\n".encode())
        except Exception:
            pass
    finally:
        conn.close()


def _process_command(command, log_fn):
    if command.strip().upper() == "STATUS":
        if app.cap is None or not app.cap.isOpened():
            return "NOT_READY:webcam non aperta"
        if not app.rois:
            return "NOT_READY:nessuna area selezionata"
        return f"READY:aree={list(app.rois.keys())}"

    if command.upper().startswith("CAPTURE:"):
        rest = command[len("CAPTURE:"):].strip()

        # Protocollo: CAPTURE:area_id:nome_file
        # es.  CAPTURE:1:misura.jpg   oppure   CAPTURE:2:C:/foto/img.png
        parts = rest.split(":", 1)
        if len(parts) != 2:
            return ("ERROR:formato errato. Usa CAPTURE:area_id:nome_file  "
                    f"(es. CAPTURE:1:immagine.jpg)  |  aree disponibili: {list(app.rois.keys())}")

        try:
            area_id = int(parts[0].strip())
        except ValueError:
            return f"ERROR:area_id deve essere un numero intero (ricevuto: {parts[0]!r})"

        # area_id=0 → cattura l'intero frame (dopo correzione prospettica se attiva)
        if area_id == 0:
            frame = grab_fresh_frame_for_capture()
            if frame is None:
                return "ERROR:impossibile acquisire frame dalla webcam"
            frame = apply_perspective_correction(frame)
            if save_image(frame, filepath):
                log_fn(f"[SERVER] Frame intero → {filepath}")
                return f"OK:{filepath}"
            else:
                return f"ERROR:salvataggio fallito → {filepath}"

        if area_id not in app.rois:
            return (f"ERROR:area {area_id} non esiste  |  "
                    f"aree disponibili: {list(app.rois.keys())}")

        filename = parts[1].strip()
        if not filename:
            return "ERROR:nome file mancante"

        if not os.path.isabs(filename):
            filepath = os.path.join(app.save_directory, filename)
        else:
            filepath = filename

        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        frame = grab_fresh_frame_for_capture()
        if frame is None:
            return "ERROR:impossibile acquisire frame dalla webcam"

        # Pipeline: prospettiva → crop ROI → rotazione → salva
        frame     = apply_perspective_correction(frame)
        roi_frame = capture_roi(frame, area_id)

        if save_image(roi_frame, filepath):
            log_fn(f"[SERVER] Area {area_id} → {filepath}")
            return f"OK:{filepath}"
        else:
            return f"ERROR:salvataggio fallito → {filepath}"

    if command.strip().upper().startswith("SHOW_ALARM:"):
        alarm_id = command.split(":", 1)[1].strip()
        if _alarm_sender is None:
            return "ERROR:CAN non inizializzato (alarm_can_sender non disponibile)"
        ok = _alarm_sender.show_alarm(alarm_id)
        return f"OK:shown:{alarm_id}" if ok else f"ERROR:allarme {alarm_id} non trovato nel dizionario"

    if command.strip().upper() == "CLEAR_ALARM":
        if _alarm_sender is None:
            return "ERROR:CAN non inizializzato (alarm_can_sender non disponibile)"
        _alarm_sender.clear_alarm()
        return "OK:cleared"

    if command.strip().upper() == "LIST_ALARMS":
        if AlarmCanSender is None:
            return "ERROR:alarm_can_sender non disponibile"
        alarms = AlarmCanSender.list_alarms()
        return f"OK:{','.join(alarms)}"

    return f"ERROR:comando non riconosciuto → {command!r}"


# ─────────────────────────────────────────────
#  Selezione area OpenCV
# ─────────────────────────────────────────────
_select_state = {"drawing": False, "start": None, "current": None, "done": False}


def _mouse_select_area(event, x, y, flags, param):
    s = _select_state
    display = param["frame"].copy()

    if event == cv2.EVENT_LBUTTONDOWN:
        s["drawing"] = True
        s["start"]   = (x, y)
        s["current"] = (x, y)
    elif event == cv2.EVENT_MOUSEMOVE and s["drawing"]:
        s["current"] = (x, y)
    elif event == cv2.EVENT_LBUTTONUP and s["drawing"]:
        s["drawing"] = False
        s["current"] = (x, y)
        s["done"]    = True

    if s["start"] and s["current"]:
        x1, y1 = s["start"]
        x2, y2 = s["current"]
        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(display,
                    f"ROI: ({min(x1,x2)},{min(y1,y2)}) - ({max(x1,x2)},{max(y1,y2)})",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow("Seleziona Area - ENTER conferma | ESC annulla", display)


def open_area_selection_window(log_fn):
    # Prende un frame con il lock
    with app.cam_lock:
        if not (app.cap and app.cap.isOpened()):
            if not initialize_webcam():
                log_fn("[ERRORE] Webcam non disponibile per la selezione area")
                return
        ret, frame = app.cap.read()

    if not ret or frame is None:
        log_fn("[ERRORE] Impossibile acquisire frame per selezione area")
        return

    _select_state.update({"drawing": False, "start": None, "current": None, "done": False})

    win_name = "Seleziona Area - ENTER conferma | ESC annulla"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 960, 540)
    cv2.setMouseCallback(win_name, _mouse_select_area, {"frame": frame})
    cv2.imshow(win_name, frame)

    log_fn("[INFO] Disegna l'area con il mouse. ENTER = conferma, ESC = annulla")

    while True:
        key = cv2.waitKey(30) & 0xFF
        if key == 13:  # ENTER
            if _select_state["done"] and _select_state["start"] and _select_state["current"]:
                x1, y1 = _select_state["start"]
                x2, y2 = _select_state["current"]
                x1, x2 = min(x1, x2), max(x1, x2)
                y1, y2 = min(y1, y2), max(y1, y2)
                if x2 > x1 and y2 > y1:
                    app.roi = (x1, y1, x2, y2)
                    log_fn(f"[OK] Area: ({x1},{y1}) - ({x2},{y2})  →  {x2-x1}x{y2-y1} px")
                else:
                    log_fn("[WARN] Area non valida, ignorata")
            else:
                log_fn("[WARN] Nessuna area disegnata")
            break
        elif key == 27:  # ESC
            log_fn("[INFO] Selezione area annullata")
            break

    cv2.destroyWindow(win_name)


# ─────────────────────────────────────────────
#  ScrollableFrame
# ─────────────────────────────────────────────
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.canvas    = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg="#f0f0f0")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner   = tk.Frame(self.canvas, bg="#f0f0f0")
        self._win_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>",  self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Rotella del mouse attiva solo quando il cursore è sopra
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _on_inner_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self._win_id, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ─────────────────────────────────────────────
#  GUI principale
# ─────────────────────────────────────────────
class WebcamCaptureGUI:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("Webcam Capture Server")

        self.root.minsize(850, 620)
        self.root.resizable(True, True)
        self.root.state("zoomed")   # fullscreen su Windows; su Linux/Mac: self.root.attributes("-zoomed", True)

        self._live_running   = False

        # Stato selezione area direttamente sull'anteprima
        self._selecting_area = False
        self._sel_start      = None
        self._sel_current    = None
        self._next_area_id   = 1     # ID che verrà assegnato alla prossima area

        # Stato selezione angoli correzione prospettica
        self._selecting_perspective = False   # True mentre si stanno selezionando i 4 angoli
        self._persp_points_display  = []      # punti in coordinate display (per disegnarli)
        # Parametri di scala usati nell'ultimo frame visualizzato
        # servono per convertire coordinate display → coordinate frame reale
        self._disp_scale     = 1.0
        self._disp_x_off     = 0
        self._disp_y_off     = 0

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────
    #  Costruzione UI
    # ─────────────────────────────────────────
    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=6, pady=6)

        left_container = tk.Frame(main, width=310)
        left_container.pack(side="left", fill="y", padx=(0, 6))
        left_container.pack_propagate(False)

        self.scroll_frame = ScrollableFrame(left_container)
        self.scroll_frame.pack(fill="both", expand=True)
        left = self.scroll_frame.inner

        right = tk.Frame(main)
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, p):
        opt = {"fill": "x", "pady": 4, "padx": 4}

        # ── Webcam ──────────────────────────────
        frm = tk.LabelFrame(p, text="Webcam", font=("Arial", 9, "bold"))
        frm.pack(**opt)

        tk.Label(frm, text="Camera Index:", font=("Arial", 8)).pack(anchor="w", padx=5, pady=(4, 0))
        self.cam_var = tk.StringVar(value="Webcam 0")
        cb = ttk.Combobox(frm, textvariable=self.cam_var,
                          values=["Webcam 0", "Webcam 1", "Webcam 2"],
                          state="readonly", width=18)
        cb.pack(fill="x", padx=5, pady=2)
        cb.bind("<<ComboboxSelected>>", self._on_camera_change)

        tk.Label(frm, text="Risoluzione:", font=("Arial", 8)).pack(anchor="w", padx=5)
        self.res_var = tk.StringVar(value=app.selected_resolution)
        rb = ttk.Combobox(frm, textvariable=self.res_var,
                          values=app.resolution_options,
                          state="readonly", width=18)
        rb.pack(fill="x", padx=5, pady=(2, 5))
        rb.bind("<<ComboboxSelected>>", self._on_resolution_change)

        # ── Parametri Webcam ─────────────────────
        frm2 = tk.LabelFrame(p, text="Parametri Webcam", font=("Arial", 9, "bold"))
        frm2.pack(**opt)

        self.contrast_sl   = self._slider(frm2, "Contrasto",        0,   10,  app.webcam_contrast,  self._on_contrast)
        self.saturation_sl = self._slider(frm2, "Saturazione",      0,   200, app.webcam_saturation,self._on_saturation)
        self.shutter_sl    = self._slider(frm2, "Shutter (2^n sec)",-11, -1,  app.webcam_shutter,   self._on_shutter)
        self.gain_sl       = self._slider(frm2, "Gain / ISO",        0,   255, app.webcam_gain,      self._on_gain)
        self.focus_sl      = self._slider(frm2, "Focus",             0,   255, app.webcam_focus,     self._on_focus)
        self.sharp_sl      = self._slider(frm2, "Nitidezza",         0,   255, app.webcam_sharpness, self._on_sharpness)


        # ── Live View ────────────────────────────
        frm3 = tk.LabelFrame(p, text="Live View", font=("Arial", 9, "bold"))
        frm3.pack(**opt)

        self.live_status = tk.Label(frm3, text="● Inattivo", fg="gray",
                                    font=("Arial", 8, "bold"))
        self.live_status.pack(anchor="w", padx=5, pady=(3, 0))

        self.live_btn = tk.Button(frm3, text="▶  Start Live View",
                                  command=self._toggle_live_view,
                                  bg="#8cff8c", font=("Arial", 9, "bold"), height=1)
        self.live_btn.pack(fill="x", padx=5, pady=4)

        # ── Correzione Prospettica ───────────────
        frm_persp = tk.LabelFrame(p, text="Correzione Prospettica", font=("Arial", 9, "bold"))
        frm_persp.pack(**opt)

        tk.Label(frm_persp,
                 text="Ordine angoli (senso orario):\n"
                      "1-TopLeft  2-TopRight  3-BotRight  4-BotLeft",
                 font=("Arial", 8), justify="left", fg="#555"
                 ).pack(anchor="w", padx=5, pady=(3, 1))

        self.persp_status = tk.Label(frm_persp, text="Non attiva",
                                     font=("Arial", 8, "bold"), fg="gray")
        self.persp_status.pack(anchor="w", padx=5)

        btn_row_p = tk.Frame(frm_persp)
        btn_row_p.pack(fill="x", padx=5, pady=3)

        self.persp_btn = tk.Button(btn_row_p, text="Seleziona 4 angoli",
                                   command=self._start_perspective_selection,
                                   bg="#c8e6ff", font=("Arial", 9, "bold"), height=1)
        self.persp_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))

        tk.Button(btn_row_p, text="Reset",
                  command=self._clear_perspective,
                  bg="#ffcccc", font=("Arial", 9, "bold"), height=1
                  ).pack(side="left")

        # ── Aree di Acquisizione ─────────────────
        frm4 = tk.LabelFrame(p, text="Aree di Acquisizione", font=("Arial", 9, "bold"))
        frm4.pack(**opt)

        list_frame = tk.Frame(frm4)
        list_frame.pack(fill="x", padx=5, pady=(3, 0))

        self.area_listbox = tk.Listbox(list_frame, height=4, font=("Courier", 8),
                                       selectmode=tk.SINGLE, bg="#f9f9f9",
                                       xscrollcommand=lambda *a: sb_h.set(*a))
        self.area_listbox.grid(row=0, column=0, sticky="nsew")

        sb_areas = tk.Scrollbar(list_frame, orient="vertical",
                                command=self.area_listbox.yview)
        sb_areas.grid(row=0, column=1, sticky="ns")

        sb_h = tk.Scrollbar(list_frame, orient="horizontal",
                            command=self.area_listbox.xview)
        sb_h.grid(row=1, column=0, sticky="ew")

        self.area_listbox.configure(yscrollcommand=sb_areas.set,
                                    xscrollcommand=sb_h.set)
        list_frame.columnconfigure(0, weight=1)

        rot_row = tk.Frame(frm4)
        rot_row.pack(fill="x", padx=5, pady=(3, 0))
        tk.Label(rot_row, text="Rotazione:", font=("Arial", 8)).pack(side="left")
        self.rotation_var = tk.StringVar(value="0°")
        rot_cb = ttk.Combobox(rot_row, textvariable=self.rotation_var,
                              values=["0°", "90°", "180°", "270°"],
                              state="readonly", width=6)
        rot_cb.pack(side="left", padx=6)

        btn_row = tk.Frame(frm4)
        btn_row.pack(fill="x", padx=5, pady=3)

        tk.Button(btn_row, text="+ Aggiungi Area",
                  command=self._select_area,
                  bg="#ffd080", font=("Arial", 9, "bold"), height=1
                  ).pack(side="left", fill="x", expand=True, padx=(0, 2))

        tk.Button(btn_row, text="- Rimuovi",
                  command=self._remove_selected_area,
                  bg="#ff9999", font=("Arial", 9, "bold"), height=1
                  ).pack(side="left", fill="x", expand=True)

        tk.Button(frm4, text="Rimuovi tutte",
                  command=self._clear_all_areas,
                  font=("Arial", 8)
                  ).pack(fill="x", padx=5, pady=(0, 3))

        # ── Directory Salvataggio ────────────────
        frm5 = tk.LabelFrame(p, text="Directory Salvataggio", font=("Arial", 9, "bold"))
        frm5.pack(**opt)

        self.dir_var = tk.StringVar(value=app.save_directory)
        e = tk.Entry(frm5, textvariable=self.dir_var, font=("Arial", 8))
        e.pack(fill="x", padx=5, pady=4)
        e.bind("<FocusOut>", lambda ev: setattr(app, "save_directory", self.dir_var.get()))

        # ── CAN Alarm Sender (solo se alarm_can_sender.py è presente) ──
        if AlarmCanSender is not None:
            self._build_can_panel(p, opt)

        # ── Server Socket ─────────────────────────
        frm6 = tk.LabelFrame(p, text="Server Socket", font=("Arial", 9, "bold"))
        frm6.pack(**opt)

        pr = tk.Frame(frm6)
        pr.pack(fill="x", padx=5, pady=4)
        tk.Label(pr, text="Porta:", font=("Arial", 8)).pack(side="left")
        self.port_var = tk.StringVar(value=str(app.server_port))
        tk.Entry(pr, textvariable=self.port_var, width=8,
                 font=("Arial", 8)).pack(side="left", padx=6)

        self.server_btn = tk.Button(frm6, text="▶  Start Server",
                                    command=self._toggle_server,
                                    bg="#8cff8c", font=("Arial", 9, "bold"), height=1)
        self.server_btn.pack(fill="x", padx=5, pady=4)

        self.server_status = tk.Label(frm6, text="● Offline",
                                      fg="red", font=("Arial", 9, "bold"))
        self.server_status.pack(padx=5, pady=(0, 5))

        # ── Test Acquisizione ────────────────────
        frm7 = tk.LabelFrame(p, text="Test Acquisizione", font=("Arial", 9, "bold"))
        frm7.pack(**opt)

        tk.Label(frm7, text="Nome file da salvare:", font=("Arial", 8)).pack(anchor="w", padx=5, pady=(4, 0))
        self.test_name_var = tk.StringVar(value="test_capture.jpg")
        tk.Entry(frm7, textvariable=self.test_name_var,
                 font=("Arial", 8)).pack(fill="x", padx=5, pady=2)

        tk.Button(frm7, text="Cattura ora",
                  command=self._test_capture,
                  bg="#80ccff", font=("Arial", 9, "bold"), height=1
                  ).pack(fill="x", padx=5, pady=4)

        tk.Label(p, text="", height=2).pack()  # spazio extra per scroll

    def _build_right(self, parent):
        # PanedWindow verticale: l'utente trascina il divisore per ridimensionare
        # preview e log indipendentemente
        paned = tk.PanedWindow(parent, orient=tk.VERTICAL,
                               sashrelief=tk.RAISED, sashwidth=5,
                               bg="#cccccc")
        paned.pack(fill="both", expand=True)

        # ── Pannello superiore: anteprima webcam ──
        pf = tk.LabelFrame(paned, text="Anteprima Webcam", font=("Arial", 9, "bold"))

        self.preview_panel = tk.Label(pf, bg="black",
                                      text="Live View non attiva",
                                      fg="white", font=("Arial", 12))
        self.preview_panel.pack(fill="both", expand=True, padx=4, pady=4)

        self.preview_panel.bind("<ButtonPress-1>",   self._on_preview_press)
        self.preview_panel.bind("<B1-Motion>",        self._on_preview_drag)
        self.preview_panel.bind("<ButtonRelease-1>", self._on_preview_release)

        paned.add(pf, stretch="always", minsize=150)

        # ── Pannello inferiore: log scrollabile ──
        lf = tk.LabelFrame(paned, text="Log", font=("Arial", 9, "bold"))

        li = tk.Frame(lf)
        li.pack(fill="both", expand=True, padx=4, pady=4)

        self.log_text = tk.Text(li, height=7, font=("Courier", 8), bg="#f5f5f5",
                                wrap="none")
        self.log_text.pack(side="left", fill="both", expand=True)

        # Scrollbar verticale
        sb_v = tk.Scrollbar(li, orient="vertical", command=self.log_text.yview)
        sb_v.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=sb_v.set)

        paned.add(lf, stretch="never", minsize=80)

        app.log_fn = self._log

    # ─────────────────────────────────────────
    #  Slider helper
    # ─────────────────────────────────────────
    def _slider(self, parent, label, from_, to, init, cmd):
        sl = tk.Scale(parent, from_=from_, to=to, orient="horizontal",
                      label=label, command=cmd, font=("Arial", 8), length=260)
        sl.set(init)
        sl.pack(fill="x", padx=5, pady=2)
        return sl

    # ─────────────────────────────────────────
    #  Log
    # ─────────────────────────────────────────
    def _log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}\n"
        try:
            self.root.after(0, self._log_insert, line)
        except Exception:
            pass

    def _log_insert(self, line):
        self.log_text.insert("end", line)
        self.log_text.see("end")
        n = int(self.log_text.index("end-1c").split(".")[0])
        if n > 500:
            self.log_text.delete("1.0", f"{n-500}.0")

    # ─────────────────────────────────────────
    #  Callback slider webcam
    # ─────────────────────────────────────────
    def _on_contrast(self, v):
        app.webcam_contrast = int(float(v))
        with app.cam_lock:
            if app.cap and app.cap.isOpened():
                app.cap.set(cv2.CAP_PROP_CONTRAST, app.webcam_contrast)

    def _on_saturation(self, v):
        app.webcam_saturation = int(float(v))
        with app.cam_lock:
            if app.cap and app.cap.isOpened():
                app.cap.set(cv2.CAP_PROP_SATURATION, app.webcam_saturation)

    def _on_focus(self, v):
        app.webcam_focus = int(float(v))
        with app.cam_lock:
            if app.cap and app.cap.isOpened():
                try:
                    app.cap.set(cv2.CAP_PROP_FOCUS, app.webcam_focus)
                except Exception:
                    pass

    def _on_sharpness(self, v):
        app.webcam_sharpness = int(float(v))
        with app.cam_lock:
            if app.cap and app.cap.isOpened():
                try:
                    app.cap.set(cv2.CAP_PROP_SHARPNESS, app.webcam_sharpness)
                except Exception:
                    pass

    def _on_shutter(self, v):
        """Shutter speed = CAP_PROP_EXPOSURE su DirectShow.
        n -> tempo = 2^n secondi  (es. -6 = 1/64 s = 15.6 ms)
        Valori piu negativi: immagine piu scura, meno banding.
        Compensare con Gain/ISO se si scurisce troppo.
        """
        app.webcam_shutter = int(float(v))
        ms = round(1000 * (2 ** app.webcam_shutter), 2)
        with app.cam_lock:
            if app.cap and app.cap.isOpened():
                app.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
                app.cap.set(cv2.CAP_PROP_EXPOSURE, app.webcam_shutter)
        self._log(f"[CAM] Shutter: 2^{app.webcam_shutter} = {ms} ms")

    def _on_gain(self, v):
        """Gain analogico = equivalente ISO.
        C920: range 0-255. Valori alti = piu luminoso ma piu rumore.
        Utile per compensare uno shutter speed corto.
        """
        app.webcam_gain = int(float(v))
        with app.cam_lock:
            if app.cap and app.cap.isOpened():
                app.cap.set(cv2.CAP_PROP_GAIN, app.webcam_gain)

    def _on_camera_change(self, event):
        app.selected_camera = int(self.cam_var.get().split()[-1])
        release_webcam()
        self._log(f"Camera cambiata → {self.cam_var.get()}")

    def _on_resolution_change(self, event):
        app.selected_resolution = self.res_var.get()
        release_webcam()
        self._log(f"Risoluzione cambiata → {app.selected_resolution}")

    # ─────────────────────────────────────────
    #  Selezione area
    # ─────────────────────────────────────────
    def _select_area(self):
        # Assicurati che la webcam sia aperta e il Live View attivo
        if not (app.cap and app.cap.isOpened()):
            if not initialize_webcam():
                self._log("[ERRORE] Webcam non disponibile")
                return

        if not self._live_running:
            # Avvia automaticamente il Live View se non è attivo
            self._toggle_live_view()

        # Attiva la modalità selezione
        self._selecting_area = True
        self._sel_start      = None
        self._sel_current    = None

        # Cambia il cursore per indicare la modalità disegno
        self.preview_panel.config(cursor="crosshair")

        # Calcola il prossimo ID disponibile
        next_id = 1
        while next_id in app.rois:
            next_id += 1
        self._next_area_id = next_id

        self._log(f"[INFO] Disegna l'area {next_id} direttamente sull'anteprima."
                  "  Click + trascina → rilascia per confermare.  Tasto destro = annulla.")

    def _update_area_listbox(self):
        self.area_listbox.delete(0, tk.END)
        if not app.rois:
            self.area_listbox.insert(tk.END, "  (nessuna area definita)")
        else:
            for aid, (x1, y1, x2, y2, rotation) in sorted(app.rois.items()):
                rot_str = f"  rot:{rotation}°" if rotation != 0 else ""
                self.area_listbox.insert(
                    tk.END,
                    f"  Area {aid}:  ({x1},{y1})-({x2},{y2})  {x2-x1}x{y2-y1}px{rot_str}"
                )

    def _remove_selected_area(self):
        sel = self.area_listbox.curselection()
        if not sel:
            self._log("[WARN] Seleziona un'area dalla lista per rimuoverla")
            return
        idx  = sel[0]
        keys = sorted(app.rois.keys())
        if idx < len(keys):
            area_id = keys[idx]
            del app.rois[area_id]
            self._log(f"[INFO] Area {area_id} rimossa")
            self._update_area_listbox()

    def _clear_all_areas(self):
        app.rois.clear()
        self._log("[INFO] Tutte le aree rimosse")
        self._update_area_listbox()

    # ─────────────────────────────────────────
    #  Correzione prospettica
    # ─────────────────────────────────────────
    _PERSP_LABELS = ["1-TopLeft", "2-TopRight", "3-BotRight", "4-BotLeft"]
    _PERSP_COLORS = [(80,  80,  255),   # blu    → 1 Top-Left
                     (80,  200, 80),    # verde  → 2 Top-Right
                     (255, 80,  80),    # rosso  → 3 Bot-Right
                     (200, 200, 0  )]   # giallo → 4 Bot-Left

    def _start_perspective_selection(self):
        if not self._live_running:
            if not (app.cap and app.cap.isOpened()):
                if not initialize_webcam():
                    self._log("[ERRORE] Webcam non disponibile")
                    return
            self._toggle_live_view()

        # Reset
        app.perspective_points     = []
        app.perspective_matrix     = None
        self._persp_points_display = []
        self._selecting_perspective = True

        self.preview_panel.config(cursor="crosshair")
        self.persp_btn.config(text="Annulla selezione", bg="#ffcccc")
        self._update_persp_status()
        self._log("[INFO] Clicca i 4 angoli in senso orario:  1-TopLeft  2-TopRight  3-BotRight  4-BotLeft")

    def _add_perspective_point(self, dx, dy):
        """Aggiunge un angolo cliccato sull'anteprima."""
        labels = self._PERSP_LABELS
        n = len(app.perspective_points)
        if n >= 4:
            return

        # Converti in coordinate frame reale
        fx, fy = self._display_to_frame(dx, dy)
        app.perspective_points.append((fx, fy))
        self._persp_points_display.append((dx, dy))

        self._log(f"[INFO] Punto {n+1}/4 ({labels[n]}): frame=({fx},{fy})")
        self._update_persp_status()

        if len(app.perspective_points) == 4:
            self._selecting_perspective = False
            self.preview_panel.config(cursor="")
            self.persp_btn.config(text="Seleziona 4 angoli", bg="#c8e6ff")

            if compute_perspective_matrix():
                # Rimuovi i pallini dall'anteprima — la correzione è attiva
                self._persp_points_display = []
                self._update_persp_status()
            else:
                self._log("[ERRORE] Impossibile calcolare la correzione — riprova")
                self._clear_perspective()

    def _clear_perspective(self):
        self._selecting_perspective     = False
        app.perspective_points          = []
        app.perspective_matrix          = None
        app.perspective_dst_w           = 0
        app.perspective_dst_h           = 0
        self._persp_points_display      = []
        self.preview_panel.config(cursor="")
        self.persp_btn.config(text="⊹  Seleziona 4 angoli", bg="#c8e6ff")
        self._update_persp_status()
        self._log("[INFO] Correzione prospettica rimossa")

    def _update_persp_status(self):
        n = len(app.perspective_points)
        if app.perspective_matrix is not None:
            self.persp_status.config(
                text=f"Attiva  →  output {app.perspective_dst_w}x{app.perspective_dst_h}px",
                fg="green")
        elif n > 0 and n < 4:
            labels = self._PERSP_LABELS
            self.persp_status.config(
                text=f"{n}/4  →  clicca {labels[n]}",
                fg="orange")
        elif n == 0:
            self.persp_status.config(text="Non attiva", fg="gray")

    # ─────────────────────────────────────────
    #  Mouse handlers per selezione su anteprima
    # ─────────────────────────────────────────
    def _display_to_frame(self, dx, dy):
        """Converte coordinate del pannello display → coordinate frame reale."""
        fx = (dx - self._disp_x_off) / self._disp_scale
        fy = (dy - self._disp_y_off) / self._disp_scale
        return int(fx), int(fy)

    def _on_preview_press(self, event):
        # Modalità selezione angoli prospettica
        if self._selecting_perspective:
            self._add_perspective_point(event.x, event.y)
            return
        # Modalità selezione area
        if not self._selecting_area:
            return
        self._sel_start   = (event.x, event.y)
        self._sel_current = (event.x, event.y)

    def _on_preview_drag(self, event):
        if not self._selecting_area or self._sel_start is None:
            return
        self._sel_current = (event.x, event.y)

    def _on_preview_release(self, event):
        if not self._selecting_area or self._sel_start is None:
            return

        self._sel_current = (event.x, event.y)
        self._selecting_area = False
        self.preview_panel.config(cursor="")

        x1d, y1d = self._sel_start
        x2d, y2d = self._sel_current
        x1, y1 = self._display_to_frame(x1d, y1d)
        x2, y2 = self._display_to_frame(x2d, y2d)

        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        if x2 - x1 > 5 and y2 - y1 > 5:
            area_id  = self._next_area_id
            rotation = int(self.rotation_var.get().replace("°", ""))
            app.rois[area_id] = (x1, y1, x2, y2, rotation)
            self._log(f"[OK] Area {area_id}: ({x1},{y1})-({x2},{y2})  {x2-x1}x{y2-y1}px  rot={rotation}°")
        else:
            self._log("[WARN] Area troppo piccola, ignorata")

        self._sel_start   = None
        self._sel_current = None
        self._update_area_listbox()

    def _clear_roi(self):
        app.roi = None
        self._update_roi_label()
        self._log("[INFO] Area rimossa: verrà catturato l'intero frame")

    # ─────────────────────────────────────────
    #  Test acquisizione
    # ─────────────────────────────────────────
    def _test_capture(self):
        filename = self.test_name_var.get().strip() or "test_capture.jpg"
        app.save_directory = self.dir_var.get().strip()

        if not app.rois:
            self._log("[WARN] Nessuna area definita. Prima aggiungi almeno un'area.")
            return

        # Cattura tutte le aree definite aggiungendo il numero area al nome file
        def _run():
            base, ext = os.path.splitext(filename)
            for aid in sorted(app.rois.keys()):
                fname    = f"{base}_area{aid}{ext}"
                response = _process_command(f"CAPTURE:{aid}:{fname}", self._log)
                self._log(f"[TEST] Area {aid} → {response}")
        threading.Thread(target=_run, daemon=True).start()

    # ─────────────────────────────────────────
    #  Server
    # ─────────────────────────────────────────
    # ─────────────────────────────────────────
    #  Pannello CAN
    # ─────────────────────────────────────────
    def _build_can_panel(self, p, opt):
        """Costruisce la sezione CAN Alarm nella barra sinistra."""
        from tkinter import filedialog
        frm_can = tk.LabelFrame(p, text="CAN Alarm Sender", font=("Arial", 9, "bold"))
        frm_can.pack(**opt)

        # Riga file DBC
        tk.Label(frm_can, text="File DBC:", font=("Arial", 8)).pack(anchor="w", padx=5, pady=(4, 0))
        dbc_row = tk.Frame(frm_can)
        dbc_row.pack(fill="x", padx=5, pady=2)

        self.can_dbc_var = tk.StringVar(value="")
        tk.Entry(dbc_row, textvariable=self.can_dbc_var,
                 font=("Arial", 8)).pack(side="left", fill="x", expand=True)
        tk.Button(dbc_row, text="...",
                  command=self._browse_dbc,
                  font=("Arial", 8), width=3).pack(side="left", padx=(3, 0))

        # Riga canale
        ch_row = tk.Frame(frm_can)
        ch_row.pack(fill="x", padx=5, pady=2)
        tk.Label(ch_row, text="Canale (0=CH1):", font=("Arial", 8)).pack(side="left")
        self.can_ch_var = tk.StringVar(value="0")
        tk.Spinbox(ch_row, from_=0, to=7, textvariable=self.can_ch_var,
                   width=4, font=("Arial", 8)).pack(side="left", padx=6)

        # Riga bitrate
        br_row = tk.Frame(frm_can)
        br_row.pack(fill="x", padx=5, pady=2)
        tk.Label(br_row, text="Bitrate:", font=("Arial", 8)).pack(side="left")
        self.can_bitrate_var = tk.StringVar(value="250000")
        ttk.Combobox(br_row, textvariable=self.can_bitrate_var,
                     values=["125000", "250000", "500000", "1000000"],
                     state="readonly", width=10,
                     ).pack(side="left", padx=6)

        # Pulsante connetti
        self.can_btn = tk.Button(frm_can, text="⚡  Connetti CAN",
                                 command=self._toggle_can,
                                 bg="#c8e6ff", font=("Arial", 9, "bold"), height=1)
        self.can_btn.pack(fill="x", padx=5, pady=4)

        self.can_status = tk.Label(frm_can, text="● Offline",
                                   fg="red", font=("Arial", 9, "bold"))
        self.can_status.pack(padx=5, pady=(0, 5))

    def _browse_dbc(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Seleziona file DBC",
            filetypes=[("DBC files", "*.dbc"), ("All files", "*.*")]
        )
        if path:
            self.can_dbc_var.set(path)

    def _toggle_can(self):
        global _alarm_sender
        if _alarm_sender is not None:
            # Disconnetti
            _alarm_sender.shutdown()
            _alarm_sender = None
            self.can_btn.config(text="⚡  Connetti CAN", bg="#c8e6ff")
            self.can_status.config(text="● Offline", fg="red")
            self._log("[CAN] Bus disconnesso")
        else:
            # Connetti
            dbc = self.can_dbc_var.get().strip()
            if not dbc:
                self._log("[CAN] Seleziona prima il file DBC")
                return
            try:
                ch = int(self.can_ch_var.get())
            except ValueError:
                self._log("[CAN] Canale non valido")
                return
            try:
                bitrate = int(self.can_bitrate_var.get())
            except ValueError:
                self._log('[CAN] Bitrate non valido')
                return
            try:
                _alarm_sender = AlarmCanSender(
                    dbc_path=dbc,
                    channel=ch,
                    bitrate=bitrate,
                )
                self.can_btn.config(text='■  Disconnetti CAN', bg='#ff8c8c')
                self.can_status.config(
                    text=f'● Connesso  CH{ch}  {bitrate//1000}k  ({len(AlarmCanSender.list_alarms())} allarmi)',
                    fg='green'
                )
                self._log(f'[CAN] Bus aperto — DBC:{dbc}  CH:{ch}  {bitrate}bps')
            except Exception as e:
                import traceback
                self._log(f'[CAN] Errore connessione: {e}')
                self._log(f'[CAN] Dettaglio: {traceback.format_exc().splitlines()[-2]}')
                self.can_status.config(text='● Errore', fg='orange')
    def _toggle_server(self):
        if app.server_running:
            app.server_running = False
            if app.server_socket:
                try:
                    app.server_socket.close()
                except Exception:
                    pass
            self.server_btn.config(text="▶  Start Server", bg="#8cff8c")
            self.server_status.config(text="● Offline", fg="red")
            self._log("[SERVER] Fermato dall'utente")
        else:
            try:
                port = int(self.port_var.get())
            except ValueError:
                self._log("[ERRORE] Porta non valida")
                return

            app.server_port    = port
            app.save_directory = self.dir_var.get().strip()

            if not (app.cap and app.cap.isOpened()):
                if not initialize_webcam():
                    self._log("[ERRORE] Webcam non disponibile, server non avviato")
                    return

            threading.Thread(
                target=start_socket_server,
                args=(port, self._log),
                daemon=True
            ).start()

            self.root.after(600, self._check_server_started)

    def _check_server_started(self):
        if app.server_running:
            self.server_btn.config(text="■  Stop Server", bg="#ff8c8c")
            self.server_status.config(
                text=f"● Online  (porta {app.server_port})", fg="green")
        else:
            self._log("[ERRORE] Server non avviato (porta già occupata?)")

    # ─────────────────────────────────────────
    #  Live View  (compatibile con server attivo)
    # ─────────────────────────────────────────
    def _toggle_live_view(self):
        if self._live_running:
            self._live_running = False
            self.live_btn.config(text="▶  Start Live View", bg="#8cff8c")
            self.live_status.config(text="● Inattivo", fg="gray")
        else:
            if not (app.cap and app.cap.isOpened()):
                if not initialize_webcam():
                    self._log("[ERRORE] Webcam non disponibile")
                    return
            self._live_running = True
            self.live_btn.config(text="■  Stop Live View", bg="#ff8c8c")
            self.live_status.config(text="● Attivo", fg="green")
            self._live_loop()

    def _live_loop(self):
        """
        Loop Live View: usa grab_color_frame() che include il cam_lock.
        Se il server sta acquisendo in quel momento, aspetta il suo turno
        (qualche millisecondo) e poi aggiorna la preview normalmente.
        """
        if not self._live_running:
            return

        frame = grab_color_frame()   # thread-safe grazie al cam_lock
        if frame is not None:
            # Applica correzione prospettica all'anteprima (se attiva)
            display = apply_perspective_correction(frame)

            # Disegna tutte le aree confermate con il loro ID
            for aid, (x1, y1, x2, y2, rotation) in app.rois.items():
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                rot_str = f"  {rotation}deg" if rotation != 0 else ""
                cv2.putText(display, f"Area {aid}{rot_str}  {x2-x1}x{y2-y1}",
                            (x1, max(y1 - 8, 15)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Indicatore server attivo nell'anteprima
            if app.server_running:
                cv2.putText(display, "[SERVER ONLINE]",
                            (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 200, 0), 2)

            # Scala per adattarsi al pannello
            pw = max(self.preview_panel.winfo_width(),  300)
            ph = max(self.preview_panel.winfo_height(), 200)
            h, w  = display.shape[:2]
            scale = min(pw / w, ph / h)
            nw, nh = int(w * scale), int(h * scale)

            # Calcola offset di centratura (Tkinter Label centra l'immagine)
            x_off = (pw - nw) // 2
            y_off = (ph - nh) // 2

            # Salva i parametri di scala per la conversione coordinate mouse
            self._disp_scale = scale
            self._disp_x_off = x_off
            self._disp_y_off = y_off

            if nw > 0 and nh > 0:
                small = cv2.resize(display, (nw, nh), interpolation=cv2.INTER_AREA)

                # Disegna i punti prospettici già confermati
                colors = self._PERSP_COLORS
                labels = self._PERSP_LABELS
                for i, (pdx, pdy) in enumerate(self._persp_points_display):
                    rx = int((pdx - x_off))
                    ry = int((pdy - y_off))
                    col = colors[i]
                    cv2.circle(small, (rx, ry), 8, col, -1)
                    cv2.circle(small, (rx, ry), 8, (255, 255, 255), 2)
                    cv2.putText(small, labels[i], (rx + 12, ry + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)

                # Disegna il rettangolo di selezione area in corso
                if self._selecting_area and self._sel_start and self._sel_current:
                    x1d, y1d = self._sel_start
                    x2d, y2d = self._sel_current
                    rx1 = x1d - x_off
                    ry1 = y1d - y_off
                    rx2 = x2d - x_off
                    ry2 = y2d - y_off
                    cv2.rectangle(small, (rx1, ry1), (rx2, ry2), (0, 200, 255), 2)
                    cv2.putText(small, "Rilascia per confermare",
                                (min(rx1, rx2), max(min(ry1, ry2) - 8, 15)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)

                imgtk = ImageTk.PhotoImage(
                    image=Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
                self.preview_panel.imgtk = imgtk
                self.preview_panel.configure(image=imgtk, text="")

        self.root.after(50, self._live_loop)   # ~20 fps

    # ─────────────────────────────────────────
    #  Chiusura
    # ─────────────────────────────────────────
    def _on_close(self):
        self._live_running = False
        app.server_running = False
        if app.server_socket:
            try:
                app.server_socket.close()
            except Exception:
                pass
        if _alarm_sender is not None:
            _alarm_sender.shutdown()
        release_webcam()
        cv2.destroyAllWindows()
        self.root.destroy()


# ─────────────────────────────────────────────
#  Entrypoint
# ─────────────────────────────────────────────
def main():
    root = tk.Tk()
    WebcamCaptureGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
