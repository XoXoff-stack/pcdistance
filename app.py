import ctypes
import hmac
import ipaddress
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from datetime import timedelta
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

from flask import Flask, abort, jsonify, request, send_file, send_from_directory, session
from werkzeug.serving import make_server
from werkzeug.utils import secure_filename

try:
    import mss
    import psutil
    import pyautogui
    import pyperclip
    import qrcode
    from PIL import ImageTk, Image
except Exception:
    mss = None
    psutil = None
    pyautogui = None
    pyperclip = None
    qrcode = None
    ImageTk = None
    Image = None


def resource_path(relative_path):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


WEB_ROOT = resource_path("web")
ACCESS_PIN = ""
CONTROL_ENABLED = False
CONTROL_LOCK = threading.Lock()
SCREEN_LOCK = threading.Lock()
LOGIN_ATTEMPTS = {}
LOGIN_LOCK = threading.Lock()
APP_CACHE = {"time": 0, "items": []}

web_app = Flask(__name__, static_folder=None)
web_app.secret_key = secrets.token_urlsafe(32)
web_app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=26 * 1024 * 1024,
)


KEYS = {
    "ctrl", "alt", "shift", "win", "esc", "enter", "tab", "backspace", "delete",
    "space", "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    "insert", "capslock", "printscreen", "volumeup", "volumedown", "volumemute",
    "playpause", "stop", "nexttrack", "prevtrack", "pause", "f1", "f2", "f3", "f4",
    "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
}
KEYS.update(chr(code) for code in range(ord("a"), ord("z") + 1))
KEYS.update(str(number) for number in range(10))


def client_is_local():
    try:
        address = ipaddress.ip_address(request.remote_addr or "")
        return address.is_private or address.is_loopback or address.is_link_local
    except ValueError:
        return False


def signed_in():
    return bool(session.get("authenticated")) and client_is_local()


def require_auth(function):
    from functools import wraps

    @wraps(function)
    def wrapped(*args, **kwargs):
        if not signed_in():
            return jsonify({"error": "Connexion requise."}), 401
        return function(*args, **kwargs)

    return wrapped


def require_control(function):
    from functools import wraps

    @wraps(function)
    def wrapped(*args, **kwargs):
        if not signed_in():
            return jsonify({"error": "Connexion requise."}), 401
        with CONTROL_LOCK:
            enabled = CONTROL_ENABLED
        if not enabled:
            return jsonify({"error": "Le contrôle est en pause sur le PC."}), 423
        if pyautogui is None:
            return jsonify({"error": "Le module de contrôle est indisponible."}), 503
        return function(*args, **kwargs)

    return wrapped


def safe_user_path(relative_path):
    root = Path.home().resolve()
    requested = str(relative_path or ".")
    target = (root / requested).resolve()
    if target != root and root not in target.parents:
        abort(403)
    return root, target


def get_start_menu_roots():
    roots = [
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    return [root.resolve() for root in roots if root.exists()]


def get_applications():
    now = time.time()
    if now - APP_CACHE["time"] < 45:
        return APP_CACHE["items"]
    items = []
    for root in get_start_menu_roots():
        for folder, _, filenames in os.walk(root):
            for filename in filenames:
                if Path(filename).suffix.lower() not in {".lnk", ".exe"}:
                    continue
                full_path = Path(folder) / filename
                items.append({"name": Path(filename).stem, "path": str(full_path)})
                if len(items) >= 250:
                    break
            if len(items) >= 250:
                break
    items.sort(key=lambda item: item["name"].casefold())
    APP_CACHE["time"] = now
    APP_CACHE["items"] = items
    return items


@web_app.get("/")
def home_page():
    return send_from_directory(WEB_ROOT, "index.html")


@web_app.post("/api/login")
def login():
    if not client_is_local():
        return jsonify({"error": "Accès réservé au réseau local."}), 403
    address = request.remote_addr or "unknown"
    now = time.time()
    with LOGIN_LOCK:
        attempts = LOGIN_ATTEMPTS.get(address, [])
        attempts = [stamp for stamp in attempts if now - stamp < 60]
        if len(attempts) >= 6:
            LOGIN_ATTEMPTS[address] = attempts
            return jsonify({"error": "Trop de tentatives. Réessaie dans une minute."}), 429
    supplied_pin = str((request.get_json(silent=True) or {}).get("pin", ""))
    if not hmac.compare_digest(supplied_pin, ACCESS_PIN):
        with LOGIN_LOCK:
            attempts.append(now)
            LOGIN_ATTEMPTS[address] = attempts
        return jsonify({"error": "Code incorrect."}), 401
    with LOGIN_LOCK:
        LOGIN_ATTEMPTS.pop(address, None)
    session.clear()
    session.permanent = True
    session["authenticated"] = True
    return jsonify({"ok": True})


@web_app.post("/api/logout")
@require_auth
def logout():
    session.clear()
    return jsonify({"ok": True})


@web_app.get("/api/status")
@require_auth
def status():
    with CONTROL_LOCK:
        control_enabled = CONTROL_ENABLED
    if psutil is None:
        return jsonify({"error": "Informations système indisponibles."}), 503
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home().anchor or Path.home()))
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    return jsonify({
        "computer": socket.gethostname(),
        "cpu": psutil.cpu_percent(interval=None),
        "memory": memory.percent,
        "memory_used": round(memory.used / (1024 ** 3), 1),
        "memory_total": round(memory.total / (1024 ** 3), 1),
        "disk": disk.percent,
        "disk_used": round(disk.used / (1024 ** 3), 1),
        "disk_total": round(disk.total / (1024 ** 3), 1),
        "battery": None if battery is None else battery.percent,
        "control_enabled": control_enabled,
    })


@web_app.get("/api/screen")
@require_auth
def screen():
    if mss is None or Image is None:
        return jsonify({"error": "Capture d'écran indisponible."}), 503
    try:
        with SCREEN_LOCK:
            with mss.mss() as capture:
                monitor = capture.monitors[1]
                grabbed = capture.grab(monitor)
                image = Image.frombytes("RGB", grabbed.size, grabbed.rgb)
                maximum_width = 1440
                if image.width > maximum_width:
                    height = round(image.height * maximum_width / image.width)
                    image = image.resize((maximum_width, height), Image.Resampling.LANCZOS)
                from io import BytesIO
                output = BytesIO()
                image.save(output, format="JPEG", quality=62, optimize=True)
                output.seek(0)
                return send_file(output, mimetype="image/jpeg", max_age=0)
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.post("/api/input/mouse")
@require_control
def mouse_input():
    data = request.get_json(silent=True) or {}
    action = str(data.get("action", ""))
    button = str(data.get("button", "left"))
    if button not in {"left", "right", "middle"}:
        return jsonify({"error": "Bouton invalide."}), 400
    try:
        if action in {"move", "down", "up", "click", "double"}:
            width, height = pyautogui.size()
            x = max(0, min(width - 1, int(float(data.get("x", 0)) * width)))
            y = max(0, min(height - 1, int(float(data.get("y", 0)) * height)))
            pyautogui.moveTo(x, y, duration=0)
            if action == "down":
                pyautogui.mouseDown(button=button)
            elif action == "up":
                pyautogui.mouseUp(button=button)
            elif action == "click":
                pyautogui.click(button=button)
            elif action == "double":
                pyautogui.doubleClick(button=button)
        else:
            return jsonify({"error": "Action invalide."}), 400
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.post("/api/input/relative")
@require_control
def relative_mouse():
    data = request.get_json(silent=True) or {}
    try:
        dx = max(-500, min(500, int(float(data.get("x", 0)))))
        dy = max(-500, min(500, int(float(data.get("y", 0)))))
        pyautogui.moveRel(dx, dy, duration=0)
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.post("/api/input/click")
@require_control
def relative_click():
    data = request.get_json(silent=True) or {}
    button = str(data.get("button", "left"))
    if button not in {"left", "right", "middle"}:
        return jsonify({"error": "Bouton invalide."}), 400
    try:
        pyautogui.click(button=button, clicks=2 if data.get("double") else 1)
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.post("/api/input/scroll")
@require_control
def scroll_input():
    data = request.get_json(silent=True) or {}
    amount = max(-20, min(20, int(data.get("amount", 0))))
    try:
        pyautogui.scroll(amount)
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.post("/api/input/key")
@require_control
def key_input():
    data = request.get_json(silent=True) or {}
    keys = data.get("keys", [])
    if isinstance(keys, str):
        keys = [keys]
    if not isinstance(keys, list) or not 1 <= len(keys) <= 4:
        return jsonify({"error": "Raccourci invalide."}), 400
    normalized = [str(key).lower() for key in keys]
    if any(key not in KEYS for key in normalized):
        return jsonify({"error": "Touche non autorisée."}), 400
    try:
        if len(normalized) == 1:
            pyautogui.press(normalized[0])
        else:
            pyautogui.hotkey(*normalized)
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.post("/api/input/text")
@require_control
def text_input():
    if pyperclip is None:
        return jsonify({"error": "Presse-papiers indisponible."}), 503
    content = str((request.get_json(silent=True) or {}).get("text", ""))[:4000]
    try:
        pyperclip.copy(content)
        pyautogui.hotkey("ctrl", "v")
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.get("/api/clipboard")
@require_auth
def get_clipboard():
    if pyperclip is None:
        return jsonify({"error": "Presse-papiers indisponible."}), 503
    try:
        return jsonify({"text": str(pyperclip.paste())[:50000]})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.post("/api/clipboard")
@require_control
def set_clipboard():
    if pyperclip is None:
        return jsonify({"error": "Presse-papiers indisponible."}), 503
    content = str((request.get_json(silent=True) or {}).get("text", ""))[:50000]
    try:
        pyperclip.copy(content)
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.get("/api/files")
@require_auth
def list_files():
    root, target = safe_user_path(request.args.get("path", "."))
    if not target.exists() or not target.is_dir():
        return jsonify({"error": "Dossier introuvable."}), 404
    entries = []
    try:
        for item in target.iterdir():
            if item.name.startswith("."):
                continue
            try:
                is_directory = item.is_dir()
                entries.append({
                    "name": item.name,
                    "path": item.relative_to(root).as_posix(),
                    "directory": is_directory,
                    "size": None if is_directory else item.stat().st_size,
                })
            except OSError:
                continue
    except PermissionError:
        return jsonify({"error": "Accès refusé à ce dossier."}), 403
    entries.sort(key=lambda entry: (not entry["directory"], entry["name"].casefold()))
    return jsonify({"path": target.relative_to(root).as_posix() or ".", "entries": entries[:500]})


@web_app.get("/api/files/download")
@require_auth
def download_file():
    root, target = safe_user_path(request.args.get("path", ""))
    if not target.exists() or not target.is_file():
        return jsonify({"error": "Fichier introuvable."}), 404
    return send_file(target, as_attachment=True, download_name=target.name)


@web_app.post("/api/files/upload")
@require_control
def upload_file():
    root, target = safe_user_path(request.form.get("path", "."))
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Aucun fichier sélectionné."}), 400
    if not target.exists() or not target.is_dir():
        return jsonify({"error": "Dossier de destination introuvable."}), 404
    filename = secure_filename(Path(uploaded.filename).name)
    if not filename:
        return jsonify({"error": "Nom de fichier invalide."}), 400
    destination = (target / filename).resolve()
    if destination != root and root not in destination.parents:
        return jsonify({"error": "Destination refusée."}), 403
    if destination.exists():
        return jsonify({"error": "Un fichier portant ce nom existe déjà dans ce dossier."}), 409
    try:
        uploaded.save(destination)
        return jsonify({"ok": True, "name": filename})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.get("/api/apps")
@require_auth
def applications():
    return jsonify({"items": get_applications()})


@web_app.post("/api/apps/launch")
@require_control
def launch_application():
    supplied_path = str((request.get_json(silent=True) or {}).get("path", ""))
    target = Path(supplied_path).resolve()
    allowed = any(target == root or root in target.parents for root in get_start_menu_roots())
    if not allowed or target.suffix.lower() not in {".lnk", ".exe"} or not target.is_file():
        return jsonify({"error": "Application non autorisée."}), 403
    try:
        os.startfile(str(target))
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@web_app.post("/api/system/action")
@require_control
def system_action():
    action = str((request.get_json(silent=True) or {}).get("action", ""))
    try:
        if action == "lock":
            if os.name != "nt":
                return jsonify({"error": "Action disponible sur Windows."}), 400
            ctypes.windll.user32.LockWorkStation()
        elif action == "show_desktop":
            pyautogui.hotkey("win", "d")
        elif action == "task_manager":
            pyautogui.hotkey("ctrl", "shift", "esc")
        elif action == "volume_up":
            pyautogui.press("volumeup")
        elif action == "volume_down":
            pyautogui.press("volumedown")
        elif action == "volume_mute":
            pyautogui.press("volumemute")
        else:
            return jsonify({"error": "Action inconnue."}), 400
        return jsonify({"ok": True})
    except Exception as error:
        return jsonify({"error": str(error)}), 500


class ServerThread(threading.Thread):
    def __init__(self, server):
        super().__init__(daemon=True)
        self.server = server

    def run(self):
        self.server.serve_forever()


class PCDistanceApp:
    def __init__(self):
        global ACCESS_PIN
        self.root = tk.Tk()
        self.root.title("PC Distance")
        self.root.geometry("760x600")
        self.root.minsize(700, 560)
        self.root.configure(bg="#111318")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.server = None
        self.server_thread = None
        self.port = 8765
        self.pin = str(secrets.randbelow(90000000) + 10000000)
        ACCESS_PIN = self.pin
        self.control_enabled = False
        self.local_ip = self.find_local_ip()
        self.qr_photo = None
        self.setup_style()
        self.build_interface()
        self.start_server()

    def setup_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8), background="#292e39", foreground="#f3f4f6", borderwidth=0)
        style.map("TButton", background=[("active", "#3a4252"), ("disabled", "#222630")])
        style.configure("Accent.TButton", background="#6d5dfc", foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", "#8175ff")])
        style.configure("TLabel", background="#111318", foreground="#f3f4f6", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground="#9ba3b4", font=("Segoe UI", 9))
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"), foreground="#ffffff")
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"), foreground="#ffffff")

    def build_interface(self):
        outer = tk.Frame(self.root, bg="#111318", padx=28, pady=24)
        outer.pack(fill="both", expand=True)
        heading = tk.Frame(outer, bg="#111318")
        heading.pack(fill="x")
        ttk.Label(heading, text="PC DISTANCE", style="Title.TLabel").pack(anchor="w")
        ttk.Label(heading, text="Votre ordinateur, à portée de main.", style="Muted.TLabel").pack(anchor="w", pady=(4, 18))

        body = tk.Frame(outer, bg="#1a1e27", padx=22, pady=20, highlightthickness=1, highlightbackground="#2a3040")
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg="#1a1e27")
        left.pack(side="left", fill="both", expand=True, padx=(0, 24))
        ttk.Label(left, text="Connexion locale", style="Section.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(left, text="Adresse à ouvrir sur votre téléphone", style="Muted.TLabel").pack(anchor="w")
        self.url_value = tk.StringVar(value="Préparation du serveur…")
        url_box = tk.Entry(left, textvariable=self.url_value, readonlybackground="#111318", fg="#ffffff", insertbackground="#ffffff", relief="flat", font=("Consolas", 12), state="readonly")
        url_box.pack(fill="x", ipady=10, pady=(6, 7))
        ttk.Button(left, text="Copier l'adresse", command=self.copy_url).pack(anchor="w")

        ttk.Label(left, text="Code de connexion", style="Muted.TLabel").pack(anchor="w", pady=(22, 0))
        pin_row = tk.Frame(left, bg="#1a1e27")
        pin_row.pack(fill="x", pady=(5, 8))
        pin_label = tk.Label(pin_row, text=self.pin, bg="#111318", fg="#ffffff", font=("Consolas", 25, "bold"), padx=14, pady=8)
        pin_label.pack(side="left")
        ttk.Button(pin_row, text="Copier", command=self.copy_pin).pack(side="left", padx=(9, 0))

        self.server_state = tk.StringVar(value="Démarrage du serveur…")
        tk.Label(left, textvariable=self.server_state, bg="#1a1e27", fg="#79d69a", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(13, 0))
        ttk.Label(left, text="Les deux appareils doivent être connectés au même réseau Wi-Fi.", style="Muted.TLabel", wraplength=380).pack(anchor="w", pady=(5, 18))

        self.control_button = ttk.Button(left, text="Autoriser le contrôle", style="Accent.TButton", command=self.toggle_control)
        self.control_button.pack(anchor="w", pady=(3, 8))
        ttk.Button(left, text="Ouvrir sur cet ordinateur", command=self.open_local).pack(anchor="w")

        right = tk.Frame(body, bg="#1a1e27", width=210)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        ttk.Label(right, text="Scanner pour ouvrir", style="Section.TLabel").pack(anchor="center", pady=(0, 14))
        self.qr_label = tk.Label(right, bg="#ffffff", width=190, height=190)
        self.qr_label.pack(anchor="center", padx=7, pady=7)
        ttk.Label(right, text="Saisis ensuite le code affiché à gauche.", style="Muted.TLabel", wraplength=180, justify="center").pack(anchor="center", pady=(10, 0))

        footer = tk.Frame(outer, bg="#111318")
        footer.pack(fill="x", pady=(13, 0))
        ttk.Label(footer, text="Accès local uniquement • Code renouvelé à chaque lancement", style="Muted.TLabel").pack(side="left")
        ttk.Button(footer, text="Quitter", command=self.close).pack(side="right")

    def find_local_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                connection.connect(("192.0.2.1", 80))
                return connection.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def create_qr(self):
        if qrcode is None or ImageTk is None:
            return
        url = f"http://{self.local_ip}:{self.port}"
        image = qrcode.make(url).convert("RGB").resize((190, 190))
        self.qr_photo = ImageTk.PhotoImage(image)
        self.qr_label.configure(image=self.qr_photo)

    def start_server(self):
        global CONTROL_ENABLED
        with CONTROL_LOCK:
            CONTROL_ENABLED = False
        for candidate in range(8765, 8790):
            try:
                self.server = make_server("0.0.0.0", candidate, web_app, threaded=True)
                self.port = candidate
                break
            except OSError:
                self.server = None
        if self.server is None:
            self.server_state.set("Impossible de trouver un port disponible.")
            return
        self.server_thread = ServerThread(self.server)
        self.server_thread.start()
        self.local_ip = self.find_local_ip()
        self.url_value.set(f"http://{self.local_ip}:{self.port}")
        self.server_state.set("● Serveur actif — en attente de connexion")
        self.create_qr()
        self.root.after(700, self.open_local)

    def copy_url(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.url_value.get())
        self.server_state.set("Adresse copiée dans le presse-papiers.")

    def copy_pin(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.pin)
        self.server_state.set("Code copié dans le presse-papiers.")

    def open_local(self):
        if self.server is not None:
            webbrowser.open(f"http://127.0.0.1:{self.port}")

    def toggle_control(self):
        global CONTROL_ENABLED
        with CONTROL_LOCK:
            CONTROL_ENABLED = not CONTROL_ENABLED
            self.control_enabled = CONTROL_ENABLED
        if self.control_enabled:
            self.control_button.configure(text="Mettre le contrôle en pause")
            self.server_state.set("● Contrôle autorisé depuis la session connectée")
        else:
            self.control_button.configure(text="Autoriser le contrôle")
            self.server_state.set("● Serveur actif — commandes en pause")

    def close(self):
        global CONTROL_ENABLED
        with CONTROL_LOCK:
            CONTROL_ENABLED = False
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if os.name != "nt":
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("PC Distance", "Cette version est conçue pour Windows.")
        root.destroy()
        return
    PCDistanceApp().run()


if __name__ == "__main__":
    main()
