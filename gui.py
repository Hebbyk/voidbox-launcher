"""
mc_launcher.gui — the actual app window.

Requires: pip install customtkinter pillow

Single-window design: every dialog (Add Instance, Install from search) lives
INSIDE this one window as an overlay, rather than opening as a separate OS
window. The one deliberate exception is the Microsoft login flow, which
needs pywebview's own native window and can't be embedded here.
"""

# --- build metadata ---
try:
    from _canary import BUILD_TAG
except ImportError:
    BUILD_TAG = None
# --- end build metadata ---



import io
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import urllib.parse
import urllib.request
from pathlib import Path


# The Microsoft sign-in window runs in its own process: pywebview insists on owning a
# process's main thread, and this process's main thread belongs to the app window.
# msauth starts this same program with --ms-login-window; handle that and exit before
# any of the UI is loaded.
if len(sys.argv) >= 3 and sys.argv[1] == "--ms-login-window":
    import msauth
    msauth.run_login_window(sys.argv[2])
    sys.exit(0)

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

import core
import elyby
import export_curseforge
import export_mrpack
import export_packwiz
import instances
import mod_doctor
import mod_updater
import version_change
import worlds
import msauth
import packs
import search
import settings
from version import APP_VERSION
import i18n
from i18n import tr

i18n.init()  # pick the interface language before any text is built

# Where bundled resources (theme, icon) live: PyInstaller unpacks them to
# sys._MEIPASS; running from source they sit next to this file.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

# Packaged Windows build has no console. Without this, every java.exe the
# launcher starts (the game, Forge's installer processors) would pop open
# its own black console window. No-op when running from source.
if sys.platform == "win32" and getattr(sys, "frozen", False):
    _orig_popen_init = subprocess.Popen.__init__

    def _popen_no_console(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        kwargs.setdefault("stdout", subprocess.DEVNULL)  # callers that capture output pass PIPE explicitly
        kwargs.setdefault("stderr", subprocess.DEVNULL)
        _orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _popen_no_console

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme(str(BASE_DIR / "theme_violet_nebula.json"))

# Violet Nebula palette. The theme file above sets each WIDGET TYPE's
# default colors (so Play/Install/Rename/Search/etc. — anything with no
# explicit fg_color override — already render in the CTA magenta without
# touching every call site). These four are for the specific per-widget
# overrides below that bypass the theme file on purpose: secondary/neutral
# actions, destructive actions, the add-mode banner, and muted text.
COLOR_SECONDARY = "#2A2440"         # card/row background
COLOR_SECONDARY_HOVER = "#3D3358"   # hover for a card-like frame (e.g. Browse card hover)
COLOR_BUTTON_SECONDARY = "#4A3D68"       # secondary BUTTONS — lighter than the card they sit on
COLOR_BUTTON_SECONDARY_HOVER = "#5C4D80"
COLOR_DESTRUCTIVE = "#B4224C"
COLOR_DESTRUCTIVE_HOVER = "#8F1B3D"
COLOR_BANNER = "#3D1D66"
COLOR_TEXT_MUTED = "#B8A9CC"
# status chips (background, text) - the same four tones everywhere so they read as one system
CHIP_AMBER = ("#3A2A12", "#F5B85C")
CHIP_RED = ("#3B1423", "#FF8FAE")
CHIP_GREEN = ("#14301F", "#7FE0A0")
CHIP_VIOLET = ("#2E1F57", "#D3B5FF")
COLOR_ACCENT = "#A855F7"

DEFAULT_INSTANCES_DIR = core.get_shared_cache_dir().parent / "instances"

ICON_PATH = BASE_DIR / "icon.ico"
# Windows groups taskbar buttons (and picks their icon) by this ID. Without
# our own, a script run via python.exe shows up under Python's icon.
APP_USER_MODEL_ID = "Hebby.VoidboxLauncher.1"

# In-app update check: reads the latest GitHub Release of this repository ("owner/name").
# The repo's releases must be public and carry the installer (.msi) as an asset.
# While this is still the placeholder, the update check is simply switched off.
UPDATE_REPO = "Hebbyk/voidbox-launcher"
UPDATE_API = "https://api.github.com/repos/{repo}/releases/latest"


def _version_tuple(v: str) -> tuple:
    return tuple(int((re.match(r"\d*", chunk).group() or 0)) for chunk in str(v).strip().lstrip("vV").split("."))


def is_newer(candidate: str, current: str) -> bool:
    a, b = _version_tuple(candidate), _version_tuple(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))  # "1.2.0" is not newer than "1.2"


def _trusted_download_url(url: str) -> bool:
    """Only ever download an installer over https from GitHub itself."""
    p = urllib.parse.urlparse(url or "")
    host = p.hostname or ""
    return p.scheme == "https" and (host == "github.com" or host.endswith(".github.com")
                                    or host.endswith(".githubusercontent.com"))


def parse_release(data: dict) -> dict | None:
    """What we need from GitHub's 'latest release' JSON; None if there's no usable installer."""
    asset = next((a for a in data.get("assets") or []
                  if str(a.get("name", "")).lower().endswith(".msi")), None)
    if not asset or not _trusted_download_url(asset.get("browser_download_url", "")):
        return None
    digest = str(asset.get("digest") or "")
    return {"version": str(data.get("tag_name", "")).lstrip("vV"), "name": asset["name"],
            "url": asset["browser_download_url"], "size": asset.get("size"),
            "sha256": digest[len("sha256:"):] if digest.startswith("sha256:") else None,
            "page": data.get("html_url")}

# Fallback badge shown for an instance with no custom icon: (text, color) per loader.
LOADER_BADGES = {
    "vanilla": ("V", "#4C8C2B"),
    "fabric": ("Fb", "#8F7A52"),
    "forge": ("Fg", "#C2571A"),
    "neoforge": ("Nf", "#E8832B"),
    "quilt": ("Q", "#8B5CF6"),
}
_BADGE_UNKNOWN = ("?", "#4A3D68")


def _badge_font(px: int):
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(px)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def make_loader_badge(loader: str | None) -> Image.Image:
    """Rounded-square badge with the loader's short name — drawn in code,
    so there are no image assets to ship. Rendered at 128px and shown
    smaller, so it stays sharp on high-DPI displays."""
    text, color = LOADER_BADGES.get((loader or "").strip().lower(), _BADGE_UNKNOWN)
    size = 128
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=28, fill=color)
    font = _badge_font(64 if len(text) == 1 else 54)
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text(((size - (r - l)) / 2 - l, (size - (b - t)) / 2 - t), text, font=font, fill="white")
    return img


def make_chip(master, text: str, tone):
    """A small rounded status label, e.g. '29 duplicate mods'."""
    return ctk.CTkLabel(master, text=f"  {text}  ", fg_color=tone[0], text_color=tone[1], corner_radius=10,
                        height=22, font=ctk.CTkFont(size=11, weight="bold"))


def popup_menu(anchor_widget, items):
    """Dark popup menu under a widget. items: [(label, callback)], a (None, None) item is a separator."""
    m = tk.Menu(anchor_widget, tearoff=0, bg="#1D1730", fg="#EDE7F6", activebackground=COLOR_ACCENT,
                activeforeground="#120F1D", bd=0, relief="flat", font=("Segoe UI", 10))
    for label, cb in items:
        if label is None:
            m.add_separator()
        else:
            m.add_command(label=label, command=cb)
    try:
        m.tk_popup(anchor_widget.winfo_rootx(), anchor_widget.winfo_rooty() + anchor_widget.winfo_height())
    finally:
        m.grab_release()
    return m


class AccountCard(ctk.CTkFrame):
    """Who is signed in, and one place (the arrow) to sign in or switch - instead of two always-on login buttons."""

    def __init__(self, master, on_microsoft, on_elyby):
        super().__init__(master, fg_color=COLOR_SECONDARY, corner_radius=12)
        self._on_microsoft, self._on_elyby = on_microsoft, on_elyby
        self.avatar = ctk.CTkLabel(self, text="?", width=36, height=36, corner_radius=18,
                                   fg_color=COLOR_BUTTON_SECONDARY, font=ctk.CTkFont(weight="bold"))
        self.avatar.pack(side="left", padx=(10, 8), pady=10)
        self.arrow = ctk.CTkButton(self, text="\u25be", width=28, height=28, fg_color="transparent",
                                    hover_color=COLOR_SECONDARY_HOVER, command=self.open_menu)
        self.arrow.pack(side="right", padx=(0, 6))
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        self.name = ctk.CTkLabel(info, text=tr("Not logged in"), anchor="w", font=ctk.CTkFont(weight="bold"))
        self.name.pack(fill="x")
        self.sub = ctk.CTkLabel(info, text=tr("Choose how to sign in"), anchor="w", text_color=COLOR_TEXT_MUTED,
                                font=ctk.CTkFont(size=11))
        self.sub.pack(fill="x")
        for w in (self, self.avatar, info, self.name, self.sub):
            w.bind("<Button-1>", lambda e: self.open_menu())

    def set_account(self, username: str, kind: str):
        """kind: 'premium' (Microsoft) or 'elyby'."""
        self.avatar.configure(text=(username[:1] or "?").upper(), fg_color=COLOR_ACCENT, text_color="#120F1D")
        self.name.configure(text=username)
        self.sub.configure(text="Microsoft" if kind == "premium" else "ely.by")

    def open_menu(self):
        return popup_menu(self.arrow, [(tr("Login (Microsoft)"), self._on_microsoft),
                                       (tr("Login (ely.by)"), self._on_elyby)])


class ConsoleRedirector:
    """Duplicates writes to both a queue (for the GUI's live log panel) and
    the original stream (so the real terminal keeps working exactly as
    before). The queue is what makes this thread-safe — Tkinter widgets
    can't be touched from a background thread, so the writer thread just
    enqueues text and the main thread's polling loop drains it.

    Note: print() sends the message and its trailing newline as TWO separate
    write() calls — must not drop the newline-only one, or every line runs
    into the next in the log panel."""

    def __init__(self, q: queue.Queue, original_stream):
        self.q = q
        self.original_stream = original_stream
        # The terminal copy goes through its own thread. A classic Windows console freezes any program that
        # writes to it while the user has clicked inside the window (Quick Edit "Select" mode), and a direct
        # write here would freeze the launch thread with it. Now only this little thread waits.
        self._out: queue.Queue = queue.Queue()
        if original_stream:
            threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        while True:
            text = self._out.get()
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except Exception:
                pass

    def write(self, text: str):
        if text:
            self.q.put(text)
            if self.original_stream:
                self._out.put(text)

    def flush(self):
        pass


class CrashPanel(ctk.CTkFrame):
    """Shown under the instance list when Minecraft exits with an error: the last
    lines of latest.log plus Copy / Open-folder buttons, instead of leaving the
    person to dig through the instance folder by hand."""

    def __init__(self, master, info: dict, on_open_folder, on_dismiss):
        super().__init__(master, fg_color=COLOR_SECONDARY, corner_radius=12)
        self._info = info
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(head, text=tr("Minecraft closed with an error (exit code {0})", info["exit_code"]),
                     anchor="w", font=ctk.CTkFont(weight="bold"), text_color="#FF8FAE").pack(side="left")
        ctk.CTkButton(head, text="\u2715", width=28, height=28, fg_color="transparent",
                      hover_color=COLOR_SECONDARY_HOVER, command=on_dismiss).pack(side="right")
        ctk.CTkLabel(self, text=tr("It ran for {0} seconds.", info["seconds"]), anchor="w",
                     text_color=COLOR_TEXT_MUTED).pack(fill="x", padx=14)

        box = ctk.CTkTextbox(self, height=96, font=("Consolas", 11), wrap="word")
        box.pack(fill="x", padx=14, pady=8)
        if info["tail"]:
            box.insert("1.0", "\n".join(info.get("highlights") or info["tail"][-12:]))
        else:
            box.insert("1.0", tr("No new log was written, so Minecraft stopped before it could log "
                                 "anything. This usually means a Java or launch-argument problem."))
        box.configure(state="disabled")
        box.see("end")

        extra = info.get("crash_report") or info.get("hs_err")
        if extra:
            ctk.CTkLabel(self, text=tr("Crash report: {0}", Path(extra).name), anchor="w",
                         text_color=COLOR_TEXT_MUTED).pack(fill="x", padx=14)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(4, 12))
        self._copy_btn = ctk.CTkButton(row, text=tr("Copy log"), width=110, command=self._copy,
                                       fg_color=COLOR_BUTTON_SECONDARY,
                                       hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        self._copy_btn.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text=tr("Open log folder"), width=140, command=on_open_folder,
                      fg_color=COLOR_BUTTON_SECONDARY,
                      hover_color=COLOR_BUTTON_SECONDARY_HOVER).pack(side="left")

    def _copy(self):
        text = "\n".join(self._info["tail"]) or tr("(no log was written)")
        self.clipboard_clear()
        self.clipboard_append(text)
        self._copy_btn.configure(text=tr("Copied!"))
        self.after(1500, lambda: self._copy_btn.configure(text=tr("Copy log")))


class LauncherApp(ctk.CTk):
    def __init__(self):
        if sys.platform == "win32":
            try:  # must happen before the first window exists
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
            except Exception:
                pass
        super().__init__()
        self.title(f"Voidbox Launcher {APP_VERSION}")
        # CustomTkinter re-applies its own default icon ~200ms after the
        # window appears (it would overwrite one set right here), so set
        # ours after that.
        self.after(300, self._apply_app_icon)
        self.geometry("900x680")
        self.minsize(800, 500)  # below this, three 80px action buttons + a
        # readable instance name genuinely don't fit — floor set alongside
        # the packing-order fix, not instead of it

        self.auth: dict | None = None
        self.extra_jvm_args: list[str] | None = None  # set for ely.by (skin injector)
        self._icon_cache: dict[str, ctk.CTkImage] = {}  # icon_url -> loaded thumbnail
        self._current_results: list[dict] = []  # last search results, for the details Back button
        self.add_target_instance: instances.Instance | None = None  # set while Browse is in "add mods to X" mode
        self._all_instances: list = []  # last list read from disk; the search box filters this
        self._instance_filter_job = None  # pending debounced redraw (after() id)
        self._badge_cache: dict[tuple, ctk.CTkImage] = {}  # (loader, size) -> fallback badge
        self._update_rel: dict | None = None  # newer release found by the update check
        self.adds_in_flight: set = set()  # (instance path, filename) being added right now — blocks double-adds

        self.log_queue = queue.Queue()
        sys.stdout = ConsoleRedirector(self.log_queue, sys.stdout)
        sys.stderr = ConsoleRedirector(self.log_queue, sys.stderr)

        # Background threads must NEVER call Tkinter methods (including
        # .after()) directly — that's not reliably safe. They put a callback
        # here instead, and only the main thread's own polling loop runs it.
        self.action_queue = queue.Queue()

        self._health_gen, self._health_cache, self._badge_targets = 0, {}, []
        self._build_sidebar()
        # Log panel BEFORE the main area, deliberately: pack hands out
        # space in build order. Built after the tab view, the log boxed
        # out its own ~160px column beside the sidebar and left the
        # content area only (window width - 380px) — the real reason
        # Delete/Install/etc. kept getting squeezed out of their rows.
        # Built first, it's a full-width strip under the content.
        self._build_log_panel()
        self._build_main_area()
        self.refresh_instances()
        self.after(150, self._drain_log_queue)
        self.after(100, self._drain_action_queue)
        self._try_restore_login()
        threading.Thread(target=self._check_for_update, daemon=True).start()

    # ----- updates ---------------------------------------------------------

    def _check_for_update(self):
        """Background thread. Silent on any failure — never bother the user about it."""
        if UPDATE_REPO.startswith("OWNER/") or not getattr(sys, "frozen", False):
            return  # not configured yet / running from source (the installer is for packaged builds)
        try:
            req = urllib.request.Request(UPDATE_API.format(repo=UPDATE_REPO), headers={
                "User-Agent": core.USER_AGENT, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"[update] couldn't check for updates ({type(e).__name__})")
            return
        rel = parse_release(data)
        if rel and is_newer(rel["version"], APP_VERSION):
            self.run_on_main_thread(lambda: self._show_update_banner(rel))

    def _show_update_banner(self, rel: dict):
        self._update_rel = rel
        self.update_banner = ctk.CTkFrame(self, fg_color="#3B2A63")
        self.update_label = ctk.CTkLabel(
            self.update_banner, text=tr('Voidbox Launcher {0} is available (you have {1}).', rel['version'], APP_VERSION))
        self.update_label.pack(side="left", padx=12, pady=8)
        self.update_btn = ctk.CTkButton(self.update_banner, text=tr("Update now"), width=110, command=self._start_update)
        self.update_btn.pack(side="right", padx=(4, 10), pady=6)
        self.update_later_btn = ctk.CTkButton(self.update_banner, text=tr("Later"), width=70, fg_color="transparent",
                                               border_width=1, command=lambda: self.update_banner.pack_forget())
        self.update_later_btn.pack(side="right", padx=4, pady=6)
        self.update_banner.pack(side="top", fill="x", padx=10, pady=(10, 0), before=self.tabview)

    def _start_update(self):
        rel = self._update_rel
        self.update_btn.configure(state="disabled", text=tr("Downloading..."))
        self.update_later_btn.configure(state="disabled")
        dest = Path(tempfile.gettempdir()) / "VoidboxLauncher-update" / rel["name"]

        def on_progress(done, total):
            if total > 0:
                self.run_on_main_thread(lambda: self.update_label.configure(
                    text=tr('Downloading {0}... {1}%', rel['version'], int(done * 100 / total))))

        def worker():
            try:
                core.download_file(rel["url"], dest, sha256=rel["sha256"], expected_size=rel["size"],
                                   on_progress=on_progress)
            except Exception as e:
                msg = str(e)
                self.run_on_main_thread(lambda: self._update_failed(msg))
                return
            self.run_on_main_thread(lambda: self._launch_installer(dest))

        threading.Thread(target=worker, daemon=True).start()

    def _launch_installer(self, msi: Path):
        try:
            os.startfile(str(msi))  # opens the installer wizard (Windows)
        except Exception as e:
            self._update_failed(tr("Couldn't start the installer: {0}", e))
            return
        self.update_label.configure(text=tr("Installer opened. Closing Voidbox Launcher so it can update..."))
        self.after(1500, self.destroy)  # the installer can't replace files that are in use

    def _update_failed(self, msg: str):
        self.update_btn.configure(state="normal", text=tr("Update now"))
        self.update_later_btn.configure(state="normal")
        self.update_label.configure(text=tr("Update failed."))
        page = (self._update_rel or {}).get("page")
        messagebox.showerror(tr("Update failed"), msg + (tr("\n\nYou can download it manually:\n{0}", page) if page else ""))

    def open_settings(self):
        SettingsDialog(self)

    def restart(self):
        """Start a fresh copy of the launcher and close this one (applies a language change)."""
        cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(sys.argv[0]).resolve())]
        try:
            subprocess.Popen(cmd)
        except OSError as e:
            messagebox.showerror(tr("Couldn't restart"), str(e))
            return
        self.destroy()

    def _apply_app_icon(self):
        try:
            if ICON_PATH.exists():
                self.iconbitmap(str(ICON_PATH))
        except Exception as e:  # e.g. non-Windows Tk can't read .ico
            print(f"[gui] couldn't set window icon: {type(e).__name__}: {e}")

    def run_on_main_thread(self, callback):
        """Call this from a background thread — never call Tkinter methods
        (including .after()) directly from one, that's not reliably safe."""
        self.action_queue.put(callback)

    def _drain_action_queue(self):
        try:
            while True:
                callback = self.action_queue.get_nowait()
                try:
                    callback()
                except Exception as e:
                    # A single bad callback (e.g. a deferred update to a
                    # widget the user has since navigated away from and
                    # destroyed) must never take the whole recurring drain
                    # loop down with it — that would silently freeze every
                    # future background-thread UI update (login, progress,
                    # dialogs, all of it) for the rest of the app's life.
                    print(f"[gui] queued UI callback raised {type(e).__name__}: {e}")
        except queue.Empty:
            pass
        self.after(100, self._drain_action_queue)

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        sidebar.pack(side="left", fill="y")

        ctk.CTkLabel(sidebar, text="Voidbox", anchor="w", font=ctk.CTkFont(size=18, weight="bold")).pack(
            fill="x", padx=20, pady=(18, 10))
        self.account_card = AccountCard(sidebar, self.login_premium, self.login_cracked)
        self.account_card.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(sidebar, text="").pack(pady=10)  # spacer
        ctk.CTkButton(sidebar, text=tr("+ Add Instance"), command=self.add_instance_dialog,
                      fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER).pack(
            pady=5, fill="x", padx=20)
        ctk.CTkButton(sidebar, text=tr("Refresh"), command=self.refresh_instances, fg_color="transparent",
                      hover_color=COLOR_SECONDARY_HOVER, text_color=COLOR_TEXT_MUTED).pack(pady=2, fill="x", padx=20)

        # created last on purpose: place()d widgets stack by creation order, and the title label above overlaps it
        ctk.CTkButton(sidebar, text="\u2699", width=32, height=32, font=ctk.CTkFont(size=18),
                      fg_color="transparent", hover_color=COLOR_SECONDARY_HOVER,
                      command=self.open_settings).place(relx=1.0, x=-8, y=8, anchor="ne")

        self.progress_bar = ctk.CTkProgressBar(sidebar, mode="indeterminate")
        self.status_label = ctk.CTkLabel(sidebar, text="", wraplength=180, text_color=COLOR_TEXT_MUTED)
        self.status_label.pack(side="bottom", pady=(0, 15), padx=10)
        self.progress_bar.pack(side="bottom", pady=(15, 5), padx=20, fill="x")
        self.progress_bar.set(0)

    def _build_main_area(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(side="right", fill="both", expand=True, padx=10, pady=(10, 0))
        self.tab_instances, self.tab_browse = tr("Instances"), tr("Browse")
        self.tabview.add(self.tab_instances)
        self.tabview.add(self.tab_browse)

        inst_tab = self.tabview.tab(self.tab_instances)
        self.instance_search = ctk.CTkEntry(
            inst_tab, placeholder_text=tr("Search instances (name, loader, version)..."))
        self.instance_search.pack(fill="x", pady=(0, 8))
        self.instance_search.bind("<KeyRelease>", self._on_instance_search_key)
        self.instance_search.bind("<Escape>", self._on_instance_search_key)

        self.main_frame = ctk.CTkScrollableFrame(inst_tab, label_text=tr("Your Instances"))
        self.main_frame.pack(fill="both", expand=True)

        self._build_browse_tab(self.tabview.tab(self.tab_browse))

    def _build_browse_tab(self, tab):
        self.add_mode_banner = ctk.CTkFrame(tab, fg_color=COLOR_BANNER)
        self.add_mode_label = ctk.CTkLabel(self.add_mode_banner, text="", anchor="w")
        self.add_mode_label.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        ctk.CTkButton(self.add_mode_banner, text=tr("Cancel"), width=80, fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                      command=self.cancel_add_mode).pack(side="right", padx=10, pady=8)
        # not packed here — shown/hidden by enter_add_mode()/cancel_add_mode()

        self.search_bar_frame = top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", pady=(0, 10))

        self.search_entry = ctk.CTkEntry(top, placeholder_text=tr("Search modpacks..."))
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        ctk.CTkButton(top, text=tr("Search"), width=90, command=self.do_search).pack(side="left")

        self.results_frame = ctk.CTkScrollableFrame(tab, label_text=tr("Results"))
        self.results_frame.pack(fill="both", expand=True)

    def _build_log_panel(self):
        ctk.CTkLabel(self, text=tr("Output"), anchor="w").pack(side="bottom", fill="x", padx=15)
        self.log_box = ctk.CTkTextbox(self, height=110, state="disabled",
                                       font=("Consolas", 11), wrap="word")
        self.log_box.pack(side="bottom", fill="x", padx=10, pady=(5, 5))
        self.crash_panel = None
        core.game_exit_callback = lambda info: self.run_on_main_thread(lambda: self.show_crash_panel(info))

    def show_crash_panel(self, info: dict):
        self.hide_crash_panel()
        self.crash_panel = CrashPanel(
            self, info,
            on_open_folder=lambda: self._open_log_folder(info["log_dir"]),
            on_dismiss=self.hide_crash_panel)
        # side="bottom" stacks upward, so "after" the log box puts the panel ABOVE it
        self.crash_panel.pack(side="bottom", fill="x", padx=10, pady=(0, 5), after=self.log_box)

    def hide_crash_panel(self):
        if self.crash_panel is not None:
            self.crash_panel.destroy()
            self.crash_panel = None

    def _open_log_folder(self, path: str):
        try:
            instances.open_folder(path)
        except Exception as e:
            messagebox.showerror(tr("Couldn't open folder"), str(e))

    def _drain_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", line)
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self._drain_log_queue)

    def _start_progress(self, message: str = "Working..."):
        self.status_label.configure(text=message)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()

    def _start_progress_determinate(self, message: str = "Working..."):
        """Use instead of _start_progress when real progress is known (a
        file count, not just 'something is happening') — a modpack
        install, for instance, where packs.install_pack can report
        (current, total) per file instead of leaving the bar spinning
        with no sense of how far along it is."""
        self.status_label.configure(text=message)
        self.progress_bar.stop()  # in case an indeterminate animation was mid-loop
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)

    def _set_progress_fraction(self, current: int, total: int, message: str | None = None):
        if total > 0:
            self.progress_bar.set(current / total)
        if message is not None:
            self.status_label.configure(text=message)

    def _stop_progress(self):
        self.status_label.configure(text="")
        self.progress_bar.stop()
        self.progress_bar.configure(mode="indeterminate")  # reset default for the next use
        self.progress_bar.set(0)

    # -----------------------------------------------------------------
    # Login persistence — silent-only at startup, never pops a browser
    # uninvited. Actual token storage lives in msauth.py's own keyring use
    # (Microsoft) and settings.py (ely.by); this just decides which to try.
    # -----------------------------------------------------------------

    def _try_restore_login(self):
        method = settings.get_last_login_method()
        if method == "premium":
            threading.Thread(target=self._silent_premium_check, daemon=True).start()
        elif method == "cracked":
            threading.Thread(target=self._silent_cracked_check, daemon=True).start()

    def _silent_premium_check(self):
        auth = msauth.try_silent_auth()
        if auth:
            self.extra_jvm_args = None
            self.auth = auth
            self.run_on_main_thread(lambda: self.account_card.set_account(auth['username'], 'premium'))

    def _silent_cracked_check(self):
        session = settings.get_elyby_session()
        if not session:
            return
        try:
            auth = elyby.refresh(session["access_token"], session["client_token"])
        except elyby.ElyByError:
            return
        settings.save_elyby_session(auth["access_token"], auth["client_token"])
        try:
            jar = elyby.ensure_injector_jar(core.get_shared_cache_dir() / "injector_cache")
            self.extra_jvm_args = elyby.get_extra_jvm_args(jar)
        except Exception:
            self.extra_jvm_args = None
        self.auth = auth
        self.run_on_main_thread(lambda: self.account_card.set_account(auth['username'], 'elyby'))

    # -----------------------------------------------------------------
    # Instance list
    # -----------------------------------------------------------------

    def refresh_instances(self):
        """Re-read instances from disk, then redraw (respecting the search box)."""
        self._all_instances = instances.list_instances()
        self._render_instances()

    def _on_instance_search_key(self, event=None):
        if event is not None and event.keysym == "Escape":
            self.instance_search.delete(0, "end")
        # Debounce: rebuilding rows decodes each instance's icon, so wait
        # for a short pause in typing instead of redrawing per keystroke.
        if self._instance_filter_job is not None:
            self.after_cancel(self._instance_filter_job)
        self._instance_filter_job = self.after(150, self._render_instances)

    def _render_instances(self):
        self._instance_filter_job = None
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        query = self.instance_search.get().strip().lower()
        insts = self._all_instances
        if query:
            insts = [i for i in insts
                     if query in " ".join(str(x or "") for x in (
                         i.name, i.loader, i.loader_version, i.minecraft_version)).lower()]
        if not self._all_instances:
            ctk.CTkLabel(self.main_frame, text=tr("No instances yet — click + Add Instance")).pack(pady=20)
        elif not insts:
            ctk.CTkLabel(self.main_frame, text=tr('No instances match "{0}"', query)).pack(pady=20)
        self._badge_targets = []
        for inst in insts:
            self._add_instance_row(inst)
        self._start_health_scan()

    LOADER_NAMES = {"neoforge": "NeoForge", "forge": "Forge", "fabric": "Fabric", "quilt": "Quilt", "vanilla": "Vanilla"}

    def _instance_meta(self, inst: instances.Instance) -> str:
        loader = self.LOADER_NAMES.get(inst.loader, inst.loader)
        ver = "" if inst.loader_version in ("", "latest", None) or inst.loader == "vanilla" else f" {inst.loader_version}"
        return f"{loader}{ver}  \u00b7  Minecraft {inst.minecraft_version}"

    def _instance_menu_items(self, inst: instances.Instance):
        return [(tr("Export"), lambda: self.export_instance_dialog(inst)),
                (tr("Duplicate"), lambda: DuplicateDialog(self, inst)),
                (None, None),
                (tr("Delete"), lambda: self.delete_instance(inst.name))]

    def _add_instance_row(self, inst: instances.Instance):
        row = ctk.CTkFrame(self.main_frame, fg_color=COLOR_SECONDARY, corner_radius=12)
        row.pack(fill="x", pady=5)
        # Right-hand buttons are packed BEFORE the text so they always keep their space (a greedy expanding label
        # packed first once squeezed a button out entirely). One loud button per row: Play. Everything else is quiet.
        ctk.CTkButton(row, text=tr("Play"), width=90,
                      command=lambda n=inst.name: self.play_instance(n)).pack(side="right", padx=(4, 12), pady=8)
        more = ctk.CTkButton(row, text="\u00b7\u00b7\u00b7", width=36, fg_color=COLOR_BUTTON_SECONDARY,
                              hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        more.configure(command=lambda: popup_menu(more, self._instance_menu_items(inst)))
        more.pack(side="right", padx=4, pady=8)
        gear = ctk.CTkButton(row, text="\u2699", width=36, fg_color=COLOR_BUTTON_SECONDARY,
                             hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                             command=lambda i=inst: self.manage_instance_dialog(i))
        gear.pack(side="right", padx=4, pady=8)
        icon_label = ctk.CTkLabel(row, text="", width=48, height=48,
                                   image=self._loader_fallback_image(inst.loader, 48))
        icon_label.pack(side="left", padx=(12, 6), pady=10)
        if inst.icon_path:
            threading.Thread(target=self._load_local_icon, args=(inst.icon_path, icon_label),
                              daemon=True).start()
        mid = ctk.CTkFrame(row, fg_color="transparent")
        mid.pack(side="left", fill="x", expand=True, padx=6, pady=8)
        ctk.CTkLabel(mid, text=inst.name, anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x")
        ctk.CTkLabel(mid, text=self._instance_meta(inst), anchor="w", text_color=COLOR_TEXT_MUTED,
                     font=ctk.CTkFont(size=12)).pack(fill="x")
        badges = ctk.CTkFrame(mid, fg_color="transparent", height=0)
        badges.pack(fill="x")
        badges._row, badges._gear, badges._fix = row, gear, None     # the Fix button joins the right-hand cluster later
        self._badge_targets.append((inst, badges))

    # ---- health badges: filled in by a background scan so the list itself appears instantly ----

    def _start_health_scan(self):
        self._health_gen += 1
        gen, targets, cache = self._health_gen, list(self._badge_targets), self._health_cache

        def work():
            for inst, holder in targets:
                if gen != self._health_gen:
                    return
                try:
                    mods = Path(inst.path) / "minecraft" / "mods"
                    jars = list(mods.glob("*.jar")) if mods.is_dir() else []
                    if not jars:
                        continue
                    stamp = (mods.stat().st_mtime_ns, len(jars), sum(p.stat().st_size for p in jars),
                             inst.minecraft_version, inst.loader_version)
                    hit = cache.get(inst.path)
                    if hit and hit[0] == stamp:
                        summary = hit[1]
                    else:
                        rep = mod_doctor.analyze(inst)
                        summary = (len(rep.plan.moves), len(rep.problems))
                        cache[inst.path] = (stamp, summary)
                except Exception:
                    continue
                self.run_on_main_thread(lambda h=holder, i=inst, s=summary, g=gen: self._show_badges(h, i, s, g))
        threading.Thread(target=work, daemon=True).start()

    def _show_badges(self, holder, inst, summary, gen):
        if gen != self._health_gen or not holder.winfo_exists():
            return
        for w in holder.winfo_children():
            w.destroy()
        if holder._fix is not None:
            holder._fix.destroy()
            holder._fix = None
        dups, problems = summary
        if not dups and not problems:
            make_chip(holder, tr("Healthy"), CHIP_GREEN).pack(side="left", pady=(4, 0))
            return
        if dups:
            make_chip(holder, tr("{0} duplicates", dups), CHIP_AMBER).pack(side="left", padx=(0, 6), pady=(4, 0))
        if problems:
            make_chip(holder, tr("Loader too old"), CHIP_RED).pack(side="left", padx=(0, 6), pady=(4, 0))
        holder._fix = ctk.CTkButton(holder._row, text=tr("Fix problems"), width=100,
                                    fg_color=CHIP_AMBER[0], text_color=CHIP_AMBER[1], hover_color="#4A3517",
                                    command=lambda i=inst: self.manage_instance_dialog(i))
        holder._fix.pack(side="right", padx=4, pady=8, after=holder._gear)

    # -----------------------------------------------------------------
    # Account login
    # -----------------------------------------------------------------

    def login_cracked(self):
        username = ctk.CTkInputDialog(text=tr("ely.by username:"), title=tr("Login (ely.by)")).get_input()
        if not username:
            return
        password = ctk.CTkInputDialog(text=tr("ely.by password:"), title=tr("Login (ely.by)")).get_input()
        if not password:
            return
        try:
            auth = elyby.authenticate(username, password)
            jar = elyby.ensure_injector_jar(core.get_shared_cache_dir() / "injector_cache")
            self.auth = auth
            self.extra_jvm_args = elyby.get_extra_jvm_args(jar)
            self.account_card.set_account(auth['username'], 'elyby')
            settings.save_elyby_session(auth["access_token"], auth["client_token"])
            settings.save_last_login_method("cracked")
        except Exception as e:
            messagebox.showerror(tr("Login failed"), str(e))

    def login_premium(self):
        self._start_progress(tr("Logging in with Microsoft..."))

        def worker():
            try:
                auth = msauth.get_auth()
                self.extra_jvm_args = None
                self.auth = auth
                settings.save_last_login_method("premium")
                self.run_on_main_thread(lambda: self.account_card.set_account(auth['username'], 'premium'))
                self.run_on_main_thread(self._stop_progress)
            except Exception as e:
                msg = str(e)
                self.run_on_main_thread(lambda: messagebox.showerror(tr("Login failed"), msg))
                self.run_on_main_thread(self._stop_progress)

        threading.Thread(target=worker, daemon=True).start()

    # -----------------------------------------------------------------
    # Search / Browse
    # -----------------------------------------------------------------

    def do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        api_key = settings.get_curseforge_api_key()
        adding_to = self.add_target_instance

        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self._start_progress(tr("Searching for '{0}'...", query))

        def worker():
            try:
                if adding_to:
                    results = search.search_all_mods(query, curseforge_api_key=api_key)
                else:
                    results = search.search_all(query, curseforge_api_key=api_key)
                self.run_on_main_thread(lambda: self._show_search_results(results))
            except Exception as e:
                msg = str(e)
                self.run_on_main_thread(lambda: messagebox.showerror(tr("Search failed"), msg))
            finally:
                self.run_on_main_thread(self._stop_progress)

        threading.Thread(target=worker, daemon=True).start()

    def enter_add_mode(self, inst: instances.Instance):
        """Switches Browse into 'add a mod to this instance' mode: search
        looks for individual mods instead of modpacks, and Install adds
        the chosen file to `inst` instead of creating a new instance."""
        self.add_target_instance = inst
        self.add_mode_label.configure(
            text=tr('Adding mods to: {0}  ({1} on Minecraft {2})', inst.name, inst.loader, inst.minecraft_version))
        self.add_mode_banner.pack(fill="x", pady=(0, 5), before=self.search_bar_frame)
        self.search_entry.configure(placeholder_text=tr("Search mods..."))
        self.tabview.set(self.tab_browse)
        for widget in self.results_frame.winfo_children():
            widget.destroy()

    def cancel_add_mode(self):
        self.add_target_instance = None
        self.add_mode_banner.pack_forget()
        self.search_entry.configure(placeholder_text=tr("Search modpacks..."))

    def _show_search_results(self, results: list[dict]):
        self._current_results = results
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        if not results:
            ctk.CTkLabel(self.results_frame, text=tr("No results.")).pack(pady=20)
            return
        for r in results:
            self._add_result_row(r)

    def _add_result_row(self, r: dict):
        row = ctk.CTkFrame(self.results_frame, cursor="hand2", fg_color=COLOR_SECONDARY)
        row.pack(fill="x", pady=6, padx=2)
        default_fg = row.cget("fg_color")
        hover_fg = "#3D3358"

        # Button packed BEFORE the expanding label — same fix as the
        # instance-list rows: an expand=True label packed first will
        # greedily claim the row's cavity and can leave a fixed-width
        # button with zero space (invisible, not just small) once the
        # window narrows. See _add_instance_row for the fuller writeup.
        ctk.CTkButton(row, text=tr("Install"), width=90,
                      command=lambda res=r: self.open_install_dialog(res)).pack(
            side="right", padx=10, pady=10)

        icon_label = ctk.CTkLabel(row, text="", width=64, height=64)
        icon_label.pack(side="left", padx=10, pady=10)

        badge = "CurseForge" if r["source"] == "curseforge" else "Modrinth"
        desc = r["description"] or tr("(no description)")
        downloads = r.get("downloads")
        meta = f"  •  {downloads:,} downloads" if downloads else ""
        text = f"[{badge}] {r['title']}{meta}\n{desc}"
        text_label = ctk.CTkLabel(row, text=text, anchor="w", justify="left", wraplength=460)
        text_label.pack(side="left", padx=(0, 10), pady=10, fill="x", expand=True)

        # The whole panel is clickable (not just the Install button) —
        # clicking anywhere opens a full detail view; Install stays a
        # direct shortcut for going straight to the version picker.
        def _click(_e=None, res=r):
            self.show_pack_details(res)

        def _hover_in(_e=None):
            row.configure(fg_color=hover_fg)

        def _hover_out(_e=None):
            row.configure(fg_color=default_fg)

        for widget in (row, icon_label, text_label):
            widget.bind("<Button-1>", _click)
            widget.bind("<Enter>", _hover_in)
            widget.bind("<Leave>", _hover_out)

        icon_url = r.get("icon_url")
        if icon_url:
            threading.Thread(target=self._load_result_icon, args=(icon_url, icon_label),
                              daemon=True).start()

    def _loader_fallback_image(self, loader: str | None, size: int = 48) -> "ctk.CTkImage":
        key = ((loader or "").strip().lower(), size)
        if key not in self._badge_cache:
            img = make_loader_badge(loader)
            self._badge_cache[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
        return self._badge_cache[key]

    def _load_local_icon(self, path: str, icon_label: "ctk.CTkLabel", size: tuple = (48, 48)):
        """Same idea as _load_result_icon but for a file already on disk
        (an instance's custom icon) — no network fetch, so no caching
        either: unlike a URL, the same PATH (icon.png) can get overwritten
        with different content when the icon is changed, and a path-keyed
        cache would silently keep showing the old image. Local reads are
        cheap enough that always reloading fresh isn't worth the risk."""
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail(size)
            loaded = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)

            def _set_icon():
                if icon_label.winfo_exists():
                    icon_label.configure(image=loaded, text="")
            self.run_on_main_thread(_set_icon)
        except Exception:
            pass

    def _load_result_icon(self, url: str, icon_label: "ctk.CTkLabel", size: tuple = (64, 64)):
        """Fetches and decodes a result's thumbnail in the background, then
        hands the finished CTkImage to the main thread. Never raises —
        a failed/slow icon just leaves the blank placeholder in place
        rather than breaking the row or the search. Cache key includes
        size so a card's small thumbnail and the detail view's larger
        icon (same URL) don't collide or reuse the wrong resolution."""
        try:
            cache_key = (url, size)
            cached = self._icon_cache.get(cache_key)
            if cached is None:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                img.thumbnail(size)
                cached = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self._icon_cache[cache_key] = cached
            def _set_icon():
                if icon_label.winfo_exists():
                    icon_label.configure(image=cached, text="")
            self.run_on_main_thread(_set_icon)
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Pack detail view — replaces the results list in place, CurseForge-
    # page-ish (icon, description, stats) but with no Versions section:
    # Install already goes through the version picker, no need to repeat it.
    # -----------------------------------------------------------------

    def show_pack_details(self, r: dict):
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        ctk.CTkButton(self.results_frame, text=tr("← Back to results"), width=140, fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                      command=lambda: self._show_search_results(self._current_results)).pack(
            anchor="w", padx=10, pady=(10, 0))
        ctk.CTkLabel(self.results_frame, text=tr("Loading details...")).pack(pady=30)

        def worker():
            full_desc, categories, error = r.get("description") or "", [], None
            gallery, changelog = [], None
            try:
                if r["source"] == "modrinth":
                    detail = search.get_modrinth_project(r["id"])
                    full_desc = detail.get("body") or full_desc
                    categories = detail.get("categories") or []
                    gallery = [g["url"] for g in (detail.get("gallery") or []) if g.get("url")]
                    versions = search.get_modrinth_versions(r["id"])
                    if versions:
                        changelog = versions[0].get("changelog")
                else:
                    api_key = settings.get_curseforge_api_key()
                    detail = search.get_curseforge_mod(r["id"], api_key)
                    full_desc = detail.get("summary") or full_desc
                    categories = [c.get("name") for c in detail.get("categories", []) if c.get("name")]
                    gallery = [s.get("thumbnailUrl") or s.get("url")
                               for s in (detail.get("screenshots") or [])
                               if s.get("thumbnailUrl") or s.get("url")]
                    # CurseForge's changelog is raw HTML from a separate
                    # per-file endpoint — not fetched, no HTML renderer here.
            except Exception as e:
                error = str(e)
            self.run_on_main_thread(
                lambda: self._render_pack_details(r, full_desc, categories, error, gallery, changelog))

        threading.Thread(target=worker, daemon=True).start()

    def _render_pack_details(self, r: dict, full_desc: str, categories: list, error: str | None,
                              gallery: list | None = None, changelog: str | None = None):
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        ctk.CTkButton(self.results_frame, text=tr("← Back to results"), width=140, fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                      command=lambda: self._show_search_results(self._current_results)).pack(
            anchor="w", padx=10, pady=(10, 5))

        header = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=5)
        icon_label = ctk.CTkLabel(header, text="", width=96, height=96)
        icon_label.pack(side="left", padx=(0, 15))
        if r.get("icon_url"):
            threading.Thread(target=self._load_result_icon, args=(r["icon_url"], icon_label, (96, 96)),
                              daemon=True).start()

        info = ctk.CTkFrame(header, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)
        badge = "CurseForge" if r["source"] == "curseforge" else "Modrinth"
        ctk.CTkLabel(info, text=f"[{badge}] {r['title']}", anchor="w",
                     font=("", 16, "bold"), justify="left").pack(fill="x")
        downloads = r.get("downloads")
        stats = f"{downloads:,} downloads" if downloads else ""
        if categories:
            stats = (stats + "  •  " if stats else "") + ", ".join(categories)
        if stats:
            ctk.CTkLabel(info, text=stats, anchor="w", text_color=COLOR_TEXT_MUTED).pack(fill="x", pady=(2, 0))
        ctk.CTkButton(info, text=tr("Install"), width=100,
                      command=lambda: self.open_install_dialog(r)).pack(anchor="w", pady=(10, 0))

        if error:
            ctk.CTkLabel(self.results_frame,
                         text=tr("Couldn't load full details ({0}) — showing what search already had.", error),
                         text_color="orange", wraplength=520, justify="left").pack(
                fill="x", padx=10, pady=(5, 0))

        if gallery:
            gallery_row = ctk.CTkFrame(self.results_frame, fg_color="transparent")
            gallery_row.pack(fill="x", padx=10, pady=(5, 0))
            for url in gallery[:6]:  # cap it — a wall of images isn't the point, a preview is
                thumb = ctk.CTkLabel(gallery_row, text="", width=100, height=70)
                thumb.pack(side="left", padx=(0, 8))
                threading.Thread(target=self._load_result_icon, args=(url, thumb, (100, 70)),
                                  daemon=True).start()

        desc_box = ctk.CTkTextbox(self.results_frame, wrap="word")
        desc_box.pack(fill="both", expand=True, padx=10, pady=10)
        desc_box.insert("1.0", full_desc or tr("(no description)"))
        desc_box.configure(state="disabled")

        if changelog:
            ctk.CTkLabel(self.results_frame, text=tr("Latest changelog:"), anchor="w",
                         font=("", 12, "bold")).pack(fill="x", padx=10)
            change_box = ctk.CTkTextbox(self.results_frame, wrap="word", height=100)
            change_box.pack(fill="x", padx=10, pady=(0, 10))
            change_box.insert("1.0", changelog)
            change_box.configure(state="disabled")

    def open_install_dialog(self, result: dict):
        api_key = settings.get_curseforge_api_key()
        if self.add_target_instance:
            AddModDialog(self, result, self.add_target_instance, api_key)
        else:
            InstallPackDialog(self, result, api_key, on_installed=self.refresh_instances)

    # -----------------------------------------------------------------
    # Instance actions
    # -----------------------------------------------------------------

    def play_instance(self, name: str):
        if not self.auth:
            messagebox.showwarning(tr("Not logged in"), tr("Log in (ely.by or Microsoft) first."))
            return

        self.hide_crash_panel()
        self._start_progress(tr('Launching {0}...', name))

        def worker():
            try:
                instances.launch(name, self.auth, extra_jvm_args=self.extra_jvm_args)
                self.run_on_main_thread(self._stop_progress)
            except Exception as e:
                msg = str(e)
                self.run_on_main_thread(lambda: messagebox.showerror(tr("Launch failed"), msg))
                self.run_on_main_thread(self._stop_progress)

        threading.Thread(target=worker, daemon=True).start()

    def delete_instance(self, name: str):
        if messagebox.askyesno(tr("Delete instance"),
                                tr("Delete '{0}'? This also deletes its files (mods, saves, etc.).", name)):
            failures = instances.remove(name, delete_files=True)
            self.refresh_instances()
            if failures:
                shown = "\n".join(failures[:10]) + ("\n..." if len(failures) > 10 else "")
                messagebox.showwarning(
                    tr("Some files couldn't be deleted"),
                    tr("'{0}' was removed from the list, but {1} file(s) couldn't be deleted — probably still in use (close Minecraft/Java first if it's running):\n\n{2}", name, len(failures), shown))

    def add_instance_dialog(self):
        AddInstanceDialog(self, on_created=self.refresh_instances)

    def export_instance_dialog(self, inst: instances.Instance):
        ExportInstanceDialog(self, inst)

    def manage_instance_dialog(self, inst: instances.Instance):
        ManageInstanceDialog(self, inst)


class ModalDialog(ctk.CTkFrame):
    """An in-window modal — lives inside the SAME app window rather than
    opening a separate OS window, so the app stays a single window. (The
    Microsoft login flow is the one exception: it needs pywebview's own
    native window and can't be embedded this way.)"""

    def __init__(self, app: LauncherApp, title: str, width: int = 420, height: int = 380):
        self.app = app
        self.overlay = ctk.CTkFrame(app, fg_color="#0A0812")
        self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        super().__init__(app, width=width, height=height, corner_radius=12,
                          border_width=2, border_color=COLOR_SECONDARY_HOVER)
        self.place(relx=0.5, rely=0.5, anchor="center")
        self.pack_propagate(False)
        self.lift()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 0))
        ctk.CTkLabel(header, text=title, font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="\u2715", width=28, height=28, fg_color="transparent",
                      hover_color=COLOR_SECONDARY_HOVER, command=self.close).pack(side="right")

    def close(self):
        if getattr(self, "_closed", False):
            return  # e.g. user hit X mid-operation, then the worker finished and closed again
        self._closed = True
        self.overlay.destroy()
        self.destroy()


class AddInstanceDialog(ModalDialog):
    def __init__(self, app: LauncherApp, on_created):
        super().__init__(app, title=tr("Add Instance"), width=420, height=400)
        self.on_created = on_created

        ctk.CTkLabel(self, text=tr("Instance name:")).pack(pady=(15, 0))
        self.name_entry = ctk.CTkEntry(self, width=300)
        self.name_entry.pack(pady=5)

        ctk.CTkLabel(self, text=tr("Minecraft version (e.g. 1.20.1):")).pack(pady=(10, 0))
        self.mc_entry = ctk.CTkEntry(self, width=300)
        self.mc_entry.pack(pady=5)

        ctk.CTkLabel(self, text=tr("Loader:")).pack(pady=(10, 0))
        self.loader_var = ctk.StringVar(value="vanilla")
        ctk.CTkOptionMenu(self, values=["vanilla", "fabric", "quilt", "forge", "neoforge"],
                           variable=self.loader_var).pack(pady=5)

        ctk.CTkButton(self, text=tr("Create Blank Instance"), command=self.create_blank).pack(pady=(15, 5))
        ctk.CTkButton(self, text=tr("Import from Pack File (.mrpack / .zip)"),
                      command=self.import_pack_file).pack(pady=5)

    def create_blank(self):
        name, mc = self.name_entry.get().strip(), self.mc_entry.get().strip()
        if not name or not mc:
            messagebox.showwarning(tr("Missing info"), tr("Enter a name and Minecraft version."))
            return
        loader = self.loader_var.get()
        if loader == "vanilla":
            instances.create_vanilla(name, mc, DEFAULT_INSTANCES_DIR)
        else:
            instances.create_modded(name, mc, loader, "recommended" if loader == "forge" else "latest",
                                     DEFAULT_INSTANCES_DIR)
        self.on_created()
        self.close()

    def import_pack_file(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning(tr("Missing info"), tr("Enter a name first."))
            return
        path = filedialog.askopenfilename(
            title=tr("Select a modpack file"),
            filetypes=[(tr("Modpack files"), "*.mrpack *.zip"), (tr("All files"), "*.*")])
        if not path:
            return

        api_key = None
        if instances.detect_pack_format(path) == "curseforge":
            api_key = settings.get_curseforge_api_key()
            if not api_key:
                api_key = ctk.CTkInputDialog(
                    text=tr("This looks like a CurseForge pack — paste your API key:"),
                    title=tr("CurseForge API Key")).get_input()
                if not api_key:
                    return
            settings.save_curseforge_api_key(api_key)

        # Close NOW, before the worker starts — this dialog's own full-
        # window dimming overlay sits on top of the sidebar, which is
        # where the progress bar actually lives. Left open (the old
        # behavior), the import's progress was completely invisible for
        # its entire duration no matter how accurate the numbers were.
        on_created = self.on_created
        self.close()
        self.app._start_progress_determinate(tr('Importing {0}...', name))

        def on_progress(i, total):
            self.app.run_on_main_thread(lambda: self.app._set_progress_fraction(
                i, total, tr('Importing {0}... ({1}/{2})', name, i, total)))

        def worker():
            try:
                instances.create_from_pack_file(name, path, DEFAULT_INSTANCES_DIR,
                                                 curseforge_api_key=api_key, on_progress=on_progress)
                self.app.run_on_main_thread(self.app._stop_progress)
                self.app.run_on_main_thread(lambda: messagebox.showinfo(
                    tr("Done"), tr("'{0}' imported successfully.", name)))
                self.app.run_on_main_thread(on_created)
            except Exception as e:
                msg = str(e)
                self.app.run_on_main_thread(self.app._stop_progress)
                self.app.run_on_main_thread(lambda: messagebox.showerror(tr("Import failed"), msg))

        threading.Thread(target=worker, daemon=True).start()


class InstallPackDialog(ModalDialog):
    """Shown after clicking Install on a search result: pick a version/file
    — with the loader it needs shown right in the list, so you know what
    you're getting before you commit — give it an instance name, then
    download + import through the same pipeline as manual file import."""

    def __init__(self, app: LauncherApp, result: dict, curseforge_api_key: str | None, on_installed):
        super().__init__(app, title=tr('Install: {0}', result['title']), width=440, height=380)
        self.result = result
        self.curseforge_api_key = curseforge_api_key
        self.on_installed = on_installed
        self.versions: list[dict] = []
        self.labels: list[str] = []

        ctk.CTkLabel(self, text=tr("Instance name:")).pack(pady=(10, 0))
        self.name_entry = ctk.CTkEntry(self, width=320)
        self.name_entry.insert(0, result["title"])
        self.name_entry.pack(pady=5)

        ctk.CTkLabel(self, text=tr("Version:")).pack(pady=(10, 0))
        self.version_var = ctk.StringVar(value=tr("Loading..."))
        self.version_menu = ctk.CTkOptionMenu(self, variable=self.version_var, values=[tr("Loading...")],
                                               width=320)
        self.version_menu.pack(pady=5)

        ctk.CTkButton(self, text=tr("Install"), command=self.do_install).pack(pady=(20, 5))

        threading.Thread(target=self._load_versions, daemon=True).start()

    @staticmethod
    def _format_label(v: dict) -> str:
        loader_part = f" \u2014 {', '.join(v['loaders'])}" if v.get("loaders") else ""
        versions_part = ", ".join(v["game_versions"][:2])
        return f"{v['name']} ({versions_part}){loader_part}"

    def _load_versions(self):
        try:
            if self.result["source"] == "modrinth":
                self.versions = search.get_modrinth_versions(self.result["id"])
            else:
                if not self.curseforge_api_key:
                    raise search.SearchError(tr("Need a CurseForge API key to list files for this pack."))
                self.versions = search.get_curseforge_files(self.result["id"], self.curseforge_api_key)

            self.labels = [self._format_label(v) for v in self.versions]

            def apply():
                if self.labels:
                    self.version_menu.configure(values=self.labels)
                    self.version_var.set(self.labels[0])
                else:
                    self.version_menu.configure(values=[tr("No versions found")])
                    self.version_var.set(tr("No versions found"))
            self.app.run_on_main_thread(apply)
        except Exception as e:
            msg = str(e)
            self.app.run_on_main_thread(lambda: messagebox.showerror(tr("Couldn't load versions"), msg))
            self.app.run_on_main_thread(self.close)

    def do_install(self):
        name = self.name_entry.get().strip()
        if not name or not self.versions:
            messagebox.showwarning(tr("Missing info"), tr("Enter a name and wait for versions to load."))
            return
        selected_label = self.version_var.get()
        try:
            index = self.labels.index(selected_label)
        except ValueError:
            messagebox.showwarning(tr("Pick a version"), tr("Select a version first."))
            return
        chosen = self.versions[index]

        # Same reasoning as AddInstanceDialog.import_pack_file: close now,
        # before the worker starts, so this dialog's dimming overlay isn't
        # sitting on top of the sidebar's progress bar for the whole install.
        on_installed = self.on_installed
        self.close()
        self.app._start_progress(tr('Downloading {0}...', name))

        def on_progress(i, total):
            self.app.run_on_main_thread(lambda: self.app._set_progress_fraction(
                i, total, tr('Installing {0}... ({1}/{2})', name, i, total)))

        def worker():
            try:
                download_dir = core.get_shared_cache_dir() / "downloaded_packs"
                download_dir.mkdir(parents=True, exist_ok=True)
                pack_path = search.download_pack_file(chosen["url"], chosen["filename"], download_dir)
                self.app.run_on_main_thread(lambda: self.app._start_progress_determinate(
                    tr('Installing {0}...', name)))
                instances.create_from_pack_file(name, str(pack_path), DEFAULT_INSTANCES_DIR,
                                                 curseforge_api_key=self.curseforge_api_key,
                                                 on_progress=on_progress)
                self.app.run_on_main_thread(self.app._stop_progress)
                self.app.run_on_main_thread(lambda: messagebox.showinfo(
                    tr("Done"), tr("'{0}' installed successfully.", name)))
                self.app.run_on_main_thread(on_installed)
            except Exception as e:
                msg = str(e)
                self.app.run_on_main_thread(self.app._stop_progress)
                self.app.run_on_main_thread(lambda: messagebox.showerror(tr("Install failed"), msg))

        threading.Thread(target=worker, daemon=True).start()


class ManageInstanceDialog(ModalDialog):
    """Edit an existing instance: rename, open its folder, and remove
    individual mods. The mod list is read from the instance's mods/ folder
    on disk, so hand-dropped jars show up too."""

    def __init__(self, app: LauncherApp, inst: instances.Instance):
        super().__init__(app, title=tr('Manage: {0}', inst.name), width=520, height=680)
        self.inst = inst

        self._rows = {}
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(14, 6))
        self.icon_preview = ctk.CTkLabel(head, text="", width=56, height=56,
                                          image=self.app._loader_fallback_image(inst.loader, 56))
        self.icon_preview.pack(side="left", padx=(0, 12))
        if inst.icon_path:
            threading.Thread(target=self.app._load_local_icon, args=(inst.icon_path, self.icon_preview),
                              daemon=True).start()
        right = ctk.CTkFrame(head, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True)
        name_row = ctk.CTkFrame(right, fg_color="transparent")
        name_row.pack(fill="x")
        self.name_entry = ctk.CTkEntry(name_row)
        self.name_entry.insert(0, inst.name)
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(name_row, text=tr("Rename"), width=80, command=self.do_rename, fg_color=COLOR_BUTTON_SECONDARY,
                      hover_color=COLOR_BUTTON_SECONDARY_HOVER).pack(side="right")
        chips = ctk.CTkFrame(right, fg_color="transparent")
        chips.pack(fill="x", pady=(6, 0))
        loader = "Vanilla" if inst.loader == "vanilla" else (
            f"{LauncherApp.LOADER_NAMES.get(inst.loader, inst.loader)}"
            + ("" if inst.loader_version in ("", "latest", None) else f" {inst.loader_version}"))
        make_chip(chips, loader, CHIP_VIOLET).pack(side="left", padx=(0, 6))
        make_chip(chips, f"Minecraft {inst.minecraft_version}", CHIP_VIOLET).pack(side="left")
        ctk.CTkButton(chips, text=tr("Change Icon..."), width=110, height=24, fg_color="transparent",
                      text_color=COLOR_TEXT_MUTED, hover_color=COLOR_SECONDARY_HOVER,
                      command=self.do_change_icon).pack(side="right")

        quiet = dict(fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=(2, 4))
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="b")
        buttons = [(tr("Add Mods..."), self.do_add_mods, {}),                       # the one accent: the main action here
                   (tr("Import World..."), self.do_import_world, quiet),
                   (tr("Check for updates"), self.do_check_updates, quiet),
                   (tr("Change version..."), self.do_change_version, quiet),
                   (tr("Duplicate..."), self.do_duplicate, quiet),
                   (tr("Open Instance Folder"), self.do_open_folder, quiet)]
        for i, (text, cmd, style) in enumerate(buttons):
            ctk.CTkButton(grid, text=text, command=cmd, **style).grid(
                row=i // 3, column=i % 3, sticky="ew", padx=3, pady=3)

        self.health_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.health_frame.pack(fill="x", padx=20, pady=(5, 0))
        self.refresh_health()

        self.mods_label = ctk.CTkLabel(self, text=tr("Mods"), anchor="w", font=ctk.CTkFont(weight="bold"))
        self.mods_label.pack(fill="x", padx=20, pady=(10, 0))
        self.mods_frame = ctk.CTkScrollableFrame(self)
        self.mods_frame.pack(fill="both", expand=True, padx=20, pady=(5, 15))
        self.refresh_mods()

    def refresh_mods(self):
        for w in self.mods_frame.winfo_children():
            w.destroy()
        self._rows = {}
        mods = instances.list_mods(self.inst.name)
        off = mod_doctor.list_disabled(self.inst.path)
        title = tr('Mods ({0})', len(mods)) + (("   \u00b7   " + tr("{0} off", len(off))) if off else "")
        self.mods_label.configure(text=title)
        if not mods and not off:
            ctk.CTkLabel(self.mods_frame, text=tr("No mods in this instance."),
                         text_color=COLOR_TEXT_MUTED).pack(pady=20)
            return
        # build the rows in small batches so the dialog opens at once, even with hundreds of mods
        self._rows_gen = getattr(self, "_rows_gen", 0) + 1
        items = [(f, True) for f in mods] + [(f, False) for f in off]
        self._build_rows(items, 0, self._rows_gen)

    ROW_BATCH = 20

    def _build_rows(self, items, start, gen):
        if gen != self._rows_gen or getattr(self, "_closed", False):
            return
        for filename, on in items[start:start + self.ROW_BATCH]:
            self._add_mod_row(filename, on)
        last = getattr(self, "_last_report", None)
        if last is not None:
            self._decorate_rows(last)
        if start + self.ROW_BATCH < len(items):
            self.after(5, lambda: self._build_rows(items, start + self.ROW_BATCH, gen))

    def _add_mod_row(self, filename: str, on: bool):
        row = ctk.CTkFrame(self.mods_frame, fg_color="transparent")
        row.pack(fill="x", pady=1)
        # right-hand pieces first (packing-order rule: a long name must never squeeze them out)
        ctk.CTkButton(row, text="\u2715", width=28, height=26, fg_color="transparent", text_color=COLOR_TEXT_MUTED,
                      hover_color=COLOR_DESTRUCTIVE,
                      command=lambda f=filename, o=on: self.do_remove_mod(f, o)).pack(side="right", padx=(2, 0))
        holder = ctk.CTkFrame(row, fg_color="transparent")
        holder.pack(side="right")
        sw = ctk.CTkSwitch(row, text="", width=44, switch_width=34, switch_height=16)
        sw.configure(command=lambda f=filename, s=sw: self.do_toggle_mod(f, bool(s.get())))
        if on:
            sw.select()
        sw.pack(side="left")
        stem = filename[:-4] if filename.lower().endswith(".jar") else filename
        ctk.CTkLabel(row, text=stem, anchor="w", text_color=None if on else COLOR_TEXT_MUTED).pack(
            side="left", fill="x", expand=True)
        self._rows[(filename, on)] = holder

    @staticmethod
    def _short_range(rng: str) -> str:
        m = re.fullmatch(r"\[\s*([\w.\-+]+)\s*,\s*\)", rng.strip())      # "[21.1.262,)" -> "21.1.262+"
        return f"{m.group(1)}+" if m else rng

    def _decorate_rows(self, report):
        """Adds the version and any problem chips to the rows once the background scan has finished."""
        old_names = {l.name for l, _w, _m in report.plan.moves}
        bad = {p.jar: p for p in report.problems}
        for j in report.scanned:
            holder = self._rows.get((j.name, True))
            if holder is None or not holder.winfo_exists():
                continue
            for w in holder.winfo_children():
                w.destroy()
            if j.name in old_names:
                make_chip(holder, tr("Older copy"), CHIP_AMBER).pack(side="left", padx=(0, 6))
            if j.name in bad:
                p = bad[j.name]
                name = LauncherApp.LOADER_NAMES.get(p.target, p.target)
                make_chip(holder, tr("Needs {0} {1}", name, self._short_range(p.wanted)), CHIP_RED).pack(
                    side="left", padx=(0, 6))
            version = next(iter(j.mods.values()), "")
            if version and version != "?":
                ctk.CTkLabel(holder, text=str(version)[:22], text_color=COLOR_TEXT_MUTED,
                             font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))

    def do_toggle_mod(self, filename: str, want_on: bool):
        try:
            (mod_doctor.enable_mod if want_on else mod_doctor.disable_mod)(self.inst.path, filename)
        except OSError as e:
            messagebox.showerror(tr("Couldn't change the mod"),
                                 tr('{0}\n\n(If Minecraft is running, close it and try again.)', e))
        self.refresh_mods()
        self.refresh_health()

    # ---- mod health: duplicates + "needs a newer loader" ----

    def refresh_health(self):
        for w in self.health_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.health_frame, text=tr("Checking mods..."), text_color=COLOR_TEXT_MUTED,
                     anchor="w").pack(fill="x")

        def work():
            try:
                report = mod_doctor.analyze(self.inst)
            except Exception as e:
                report = e
            self.app.run_on_main_thread(lambda: self._show_health(report))
        threading.Thread(target=work, daemon=True).start()

    def _show_health(self, report):
        if getattr(self, "_closed", False) or not self.health_frame.winfo_exists():
            return
        for w in self.health_frame.winfo_children():
            w.destroy()
        if isinstance(report, Exception):
            ctk.CTkLabel(self.health_frame, text=tr("Couldn't check mods: {0}", report),
                         text_color=COLOR_TEXT_MUTED, anchor="w").pack(fill="x")
            return
        self._last_report = report
        self._decorate_rows(report)
        bold = ctk.CTkFont(weight="bold")

        def card(title, body, color, button_text=None, command=None):
            c = ctk.CTkFrame(self.health_frame, fg_color=COLOR_SECONDARY, corner_radius=10)
            c.pack(fill="x", pady=(0, 4))
            top = ctk.CTkFrame(c, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(8, 0))
            if button_text:
                ctk.CTkButton(top, text=button_text, width=120, command=command, text_color=color,
                              fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER
                              ).pack(side="right", padx=(8, 0))
            ctk.CTkLabel(top, text=title, anchor="w", justify="left", wraplength=290, text_color=color,
                         font=bold).pack(side="left")
            if body:
                ctk.CTkLabel(c, text=body, anchor="w", justify="left", wraplength=440,
                             text_color=COLOR_TEXT_MUTED).pack(fill="x", padx=12, pady=(0, 8))
            else:
                ctk.CTkFrame(c, height=6, fg_color="transparent").pack()

        plan, shown = report.plan, False
        if plan.moves:
            shown = True
            card(tr("{0} mods have an old extra copy", len(plan.moves)),
                 tr("Keeps the newest of each and moves the rest to the disabled_mods folder. Nothing is deleted."),
                 "#F5B85C", tr("Fix duplicates"), lambda: self.do_fix_duplicates(plan))
        if plan.manual:
            shown = True
            card(tr("{0} need a manual look", len(plan.manual)),
                 tr("These also provide other mods, so they were left alone: {0}", ", ".join(plan.manual[:3])),
                 COLOR_TEXT_MUTED)
        if report.problems:
            shown = True
            lines = [tr("{0} needs {1} {2} (this instance has {3})", p.jar, p.target, p.wanted, p.actual)
                     for p in report.problems[:3]]
            if len(report.problems) > 3:
                lines.append(tr("...and {0} more", len(report.problems) - 3))
            card(tr("Needs a newer loader or game version"), "\n".join(lines), "#FF8FAE")
        if report.disabled:
            shown = True
            card(tr("{0} disabled mods", len(report.disabled)), None, COLOR_TEXT_MUTED,
                 tr("Restore all"), self.do_restore_disabled)
        if not shown:
            ctk.CTkLabel(self.health_frame, text=tr("No problems found."), text_color=COLOR_TEXT_MUTED,
                         anchor="w").pack(fill="x")

    def do_fix_duplicates(self, plan):
        lines = [tr("Keep {0} - disable {1}", w.name, l.name) for l, w, _ in plan.moves[:10]]
        text = tr("Move {0} old copies to the disabled_mods folder? Nothing is deleted.", len(plan.moves))
        text += "\n\n" + "\n".join(lines)
        if len(plan.moves) > 10:
            text += "\n" + tr("...and {0} more", len(plan.moves) - 10)
        if not messagebox.askyesno(tr("Fix duplicates"), text):
            return
        moved, failed = mod_doctor.fix_duplicates(self.inst.path, plan)
        if failed:
            messagebox.showerror(tr("Couldn't move some files"),
                                 tr("{0}\n\n(If Minecraft is running, close it and try again.)", "\n".join(failed)))
        self.refresh_mods()
        self.refresh_health()

    def do_restore_disabled(self):
        restored, skipped = mod_doctor.restore_all(self.inst.path)
        if skipped:
            messagebox.showinfo(tr("Restore all"), tr("Not restored (a mod with that name is already there):\n{0}",
                                                      "\n".join(skipped)))
        self.refresh_mods()
        self.refresh_health()

    def do_import_world(self):
        WorldImportDialog(self.app, self.inst)

    def _reload_inst(self):
        self.inst = instances.get(self.inst.name) or self.inst

    def do_change_version(self):
        ChangeVersionDialog(self.app, self.inst, on_changed=lambda: (
            self._reload_inst(), self.refresh_mods(), self.refresh_health(), self.app.refresh_instances()))

    def do_duplicate(self):
        DuplicateDialog(self.app, self.inst)

    def do_check_updates(self):
        UpdatesDialog(self.app, self.inst, on_changed=lambda: (self.refresh_mods(), self.refresh_health()))

    def do_rename(self):
        new_name = self.name_entry.get().strip()
        try:
            instances.rename(self.inst.name, new_name)
        except Exception as e:
            messagebox.showerror(tr("Rename failed"), str(e))
            return
        self.app.refresh_instances()
        self.close()

    def do_change_icon(self):
        path = filedialog.askopenfilename(
            title=tr("Choose an icon image"),
            filetypes=[(tr("Images"), "*.png *.jpg *.jpeg *.gif *.bmp *.ico"), (tr("All files"), "*.*")])
        if not path:
            return
        try:
            self.inst = instances.set_icon(self.inst.name, path)
        except Exception as e:
            messagebox.showerror(tr("Couldn't set icon"), str(e))
            return
        threading.Thread(target=self.app._load_local_icon,
                          args=(self.inst.icon_path, self.icon_preview), daemon=True).start()
        self.app.refresh_instances()

    def do_open_folder(self):
        try:
            instances.open_folder(self.inst.path)
        except Exception as e:
            messagebox.showerror(tr("Couldn't open folder"), str(e))

    def do_add_mods(self):
        self.app.enter_add_mode(self.inst)
        self.close()

    def do_remove_mod(self, filename: str, enabled: bool = True):
        if not messagebox.askyesno(tr("Remove mod"), tr("Delete '{0}' from {1}?", filename, self.inst.name)):
            return
        try:
            if enabled:
                instances.remove_mod(self.inst.name, filename)
            else:
                (mod_doctor.disabled_dir(self.inst.path) / filename).unlink()
        except Exception as e:
            messagebox.showerror(tr("Couldn't remove mod"),
                                 tr('{0}\n\n(If Minecraft is running, close it and try again.)', e))
        self.refresh_mods()
        self.refresh_health()


class WorldImportDialog(ModalDialog):
    """Finds worlds on this PC (CurseForge app, official launcher, backups...) and COPIES the chosen one into
    the instance's saves folder. Nothing is moved or deleted, so the original stays where it was."""

    def __init__(self, app: LauncherApp, inst: instances.Instance):
        super().__init__(app, title=tr('Import world into {0}', inst.name), width=560, height=540)
        self.inst = inst
        self.saves = Path(inst.path) / "minecraft" / "saves"
        self.extra: list[str] = []
        self.found: list = []
        self.pick = ctk.IntVar(value=-1)
        self._busy = False

        self.status = ctk.CTkLabel(self, text=tr("Looking for worlds..."), text_color=COLOR_TEXT_MUTED, anchor="w")
        self.status.pack(fill="x", padx=20, pady=(10, 0))
        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=8)
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(0, 15), side="bottom")
        self.browse_btn = ctk.CTkButton(bottom, text=tr("Browse folder..."), command=self._browse,
                                         fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        self.browse_btn.pack(side="left")
        self.import_btn = ctk.CTkButton(bottom, text=tr("Import"), command=self.do_import, state="disabled")
        self.import_btn.pack(side="right")
        self.scan()

    def scan(self):
        self.status.configure(text=tr("Looking for worlds..."))
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.import_btn.configure(state="disabled")
        extra = list(self.extra)

        def work():
            try:
                found = worlds.find_worlds(self.saves, extra)
            except Exception:
                found = []
            self.app.run_on_main_thread(lambda: self._show(found))
        threading.Thread(target=work, daemon=True).start()

    def _show(self, found):
        if getattr(self, "_closed", False):
            return
        self.found = found
        self.pick.set(-1)
        if not found:
            self.status.configure(text=tr('No worlds found. Use "Browse folder..." to point at the folder that contains them.'))
            return
        self.status.configure(text=tr("{0} worlds found - pick one to copy:", len(found)))
        for i, w in enumerate(found):
            name = w.name if w.path.name == w.name else f"{w.name}  ({w.path.name})"
            saved = time.strftime("%Y-%m-%d %H:%M", time.localtime(w.saved))
            text = (f"{name}\n{tr('Minecraft {0}', w.mc_version)}  |  {w.size / 1e6:,.0f} MB  |  "
                    f"{tr('saved {0}', saved)}\n{w.source}")
            ctk.CTkRadioButton(self.list_frame, text=text, variable=self.pick, value=i,
                               command=lambda: self.import_btn.configure(state="normal")
                               ).pack(anchor="w", pady=(6, 0))
            if worlds.is_newer_than(w.mc_version, self.inst.minecraft_version):
                ctk.CTkLabel(self.list_frame, text=tr("Saved in a newer Minecraft version ({0}) - may not load", w.mc_version),
                             text_color="#FF8FAE", anchor="w").pack(anchor="w", padx=28)

    def _browse(self):
        folder = filedialog.askdirectory(title=tr("Choose a folder that contains worlds"))
        if folder:
            self.extra.append(folder)
            self.scan()

    def do_import(self):
        i = self.pick.get()
        if self._busy or not 0 <= i < len(self.found):
            return
        self._busy = True
        src = self.found[i].path
        self.import_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.progress.set(0)
        self.progress.pack(fill="x", padx=20, pady=(0, 8), side="bottom")
        self.status.configure(text=tr("Copying world... {0}%", 0))
        last = [-1]

        def on_progress(done, total):
            pct = int(done * 100 / total) if total else 100
            if pct != last[0]:
                last[0] = pct
                self.app.run_on_main_thread(lambda: self._progress(pct))

        def work():
            try:
                dest = worlds.copy_world(src, self.saves, on_progress)
                self.app.run_on_main_thread(lambda: self._done(dest))
            except Exception as e:
                self.app.run_on_main_thread(lambda: self._failed(e))
        threading.Thread(target=work, daemon=True).start()

    def _progress(self, pct):
        if getattr(self, "_closed", False):
            return
        self.progress.set(pct / 100)
        self.status.configure(text=tr("Copying world... {0}%", pct))

    def _done(self, dest):
        if not getattr(self, "_closed", False):
            self.close()
        messagebox.showinfo(tr("World imported"),
                            tr("'{0}' was copied into {1}. The original was not touched.", dest.name, self.inst.name))

    def _failed(self, e):
        self._busy = False
        if getattr(self, "_closed", False):
            return
        self.browse_btn.configure(state="normal")
        self.import_btn.configure(state="normal")
        self.progress.pack_forget()
        self.status.configure(text=tr("{0} worlds found - pick one to copy:", len(self.found)))
        messagebox.showerror(tr("Import failed"), str(e))


class UpdatesDialog(ModalDialog):
    """Looks every mod up by its file hash, lists newer builds for the same Minecraft version and loader, and
    installs the ticked ones. The old jar goes to previous_mods and the whole batch can be undone."""

    def __init__(self, app: LauncherApp, inst: instances.Instance, on_changed=None):
        super().__init__(app, title=tr('Mod updates: {0}', inst.name), width=560, height=560)
        self.inst = inst
        self.on_changed = on_changed
        self.updates: list = []
        self.checks: list = []
        self._busy = True

        self.status = ctk.CTkLabel(self, text=tr("Checking mods..."), text_color=COLOR_TEXT_MUTED, anchor="w",
                                   justify="left", wraplength=500)
        self.status.pack(fill="x", padx=20, pady=(10, 0))
        ctk.CTkLabel(self, anchor="w", justify="left", wraplength=500, text_color=COLOR_TEXT_MUTED,
                     text=tr("Mods are tested together in a pack. Update a few at a time and test the game. "
                             "Undo puts the previous versions back.")).pack(fill="x", padx=20)
        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=8)
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=20, pady=(0, 8), side="bottom")
        self.progress.start()
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(0, 6), side="bottom")
        self.undo_btn = ctk.CTkButton(bottom, text=tr("Undo last update"), command=self.do_undo,
                                       fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        if mod_updater.has_history(inst.path):
            self.undo_btn.pack(side="left")
        self.apply_btn = ctk.CTkButton(bottom, text=tr("Update selected"), command=self.do_apply, state="disabled")
        self.apply_btn.pack(side="right")
        self.sel_row = ctk.CTkFrame(self, fg_color="transparent")
        for label, stable_only in ((tr("Select all stable"), True), (tr("Select none"), False)):
            ctk.CTkButton(self.sel_row, text=label, width=130, height=26, fg_color=COLOR_BUTTON_SECONDARY,
                          hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                          command=lambda s=stable_only: self._select(s)).pack(side="left", padx=(0, 6))

        def work():
            try:
                report = mod_updater.check(inst, settings.get_curseforge_api_key(),
                                           progress=lambda t: self.app.run_on_main_thread(lambda: self._say(t)))
            except Exception as e:
                report = e
            self.app.run_on_main_thread(lambda: self._show(report))
        threading.Thread(target=work, daemon=True).start()

    def _say(self, text):
        # only the fixed phrases are translated; progress lines carry mod names (which may contain braces)
        if not getattr(self, "_closed", False):
            fixed = text in ("Reading mods...", "Asking Modrinth...", "Asking CurseForge...")
            self.status.configure(text=tr(text) if fixed else text)

    def _show(self, report):
        if getattr(self, "_closed", False):
            return
        self.progress.stop()
        self.progress.pack_forget()
        self._busy = False
        if isinstance(report, Exception):
            self.status.configure(text=tr("Couldn't check for updates: {0}", report), text_color="#FF8FAE")
            return
        self.updates = report.updates
        head = tr("{0} updates found, {1} up to date, {2} not recognized",
                  len(report.updates), report.up_to_date, len(report.unknown))
        if report.errors:
            head += "\n" + tr("Some lookups failed: {0}", "; ".join(report.errors))
        self.status.configure(text=head, text_color="#FF8FAE" if report.errors else COLOR_TEXT_MUTED)
        if not report.updates:
            ctk.CTkLabel(self.list_frame, text=tr("Everything recognized is up to date."),
                         text_color=COLOR_TEXT_MUTED).pack(pady=20)
            return
        self.sel_row.pack(fill="x", padx=20, pady=(0, 6), side="bottom")
        for u in report.updates:
            tag = "" if u.channel == "release" else f"  [{u.channel}]"
            if not u.url:
                tag += "  [" + tr("download it manually") + "]"
            var = ctk.BooleanVar(value=u.safe)
            cb = ctk.CTkCheckBox(self.list_frame, text=f"{u.title}   {u.old_version}  ->  {u.new_version}{tag}",
                                 variable=var, command=self._sync_btn)
            if not u.url:
                cb.configure(state="disabled")
            cb.pack(anchor="w", pady=3)
            self.checks.append(var)
        self._sync_btn()

    def _select(self, stable_only: bool):
        for u, v in zip(self.updates, self.checks):
            v.set(bool(stable_only and u.safe))
        self._sync_btn()

    def _sync_btn(self):
        n = sum(1 for v in self.checks if v.get())
        self.apply_btn.configure(state="normal" if n and not self._busy else "disabled",
                                 text=tr("Update selected") + (f" ({n})" if n else ""))

    def do_apply(self):
        chosen = [u for u, v in zip(self.updates, self.checks) if v.get() and u.url]
        if not chosen or self._busy:
            return
        self._busy = True
        self.apply_btn.configure(state="disabled")
        self.status.configure(text=tr("Updating..."), text_color=COLOR_TEXT_MUTED)
        self.progress.pack(fill="x", padx=20, pady=(0, 8), side="bottom")
        self.progress.start()

        def work():
            try:
                result = mod_updater.apply(self.inst, chosen,
                                           progress=lambda t: self.app.run_on_main_thread(lambda: self._say(t)))
            except Exception as e:
                result = e
            self.app.run_on_main_thread(lambda: self._applied(result))
        threading.Thread(target=work, daemon=True).start()

    def _applied(self, result):
        if self.on_changed:
            self.on_changed()
        if not getattr(self, "_closed", False):
            self.close()
        if isinstance(result, Exception):
            messagebox.showerror(tr("Update failed"), str(result))
            return
        done, failed = result
        text = tr("Updated {0} mods.", len(done))
        if failed:
            text += "\n\n" + tr("Not updated:") + "\n" + "\n".join(f"{j}: {why}" for j, why in failed[:8])
        messagebox.showinfo(tr("Updates"), text)

    def do_undo(self):
        if not messagebox.askyesno(tr("Undo last update"), tr("Put the previous versions of the last updated mods back?")):
            return
        restored, problems = mod_updater.undo_last(self.inst)
        if self.on_changed:
            self.on_changed()
        text = tr("Restored {0} mods.", len(restored))
        if problems:
            text += "\n\n" + "\n".join(problems[:8])
        if not getattr(self, "_closed", False):
            self.close()
        messagebox.showinfo(tr("Undo last update"), text)


class ChangeVersionDialog(ModalDialog):
    """Moves this instance to another Minecraft version IN PLACE (same worlds). A read-only check comes first;
    nothing changes until you press Change version, and a rollback snapshot is saved before anything does."""

    LOW_COVERAGE = 0.25      # this share of mods with no build for the target = "this pack can't really move"
    FIXED = ("Reading mods...", "Asking Modrinth...", "Asking CurseForge...", "Saving a rollback snapshot...",
             "Backing up worlds...", "Downloading new builds...", "Applying...")

    def __init__(self, app: LauncherApp, inst: instances.Instance, on_changed=None):
        super().__init__(app, title=tr('Change version: {0}', inst.name), width=580, height=620)
        self.inst, self.on_changed, self.plan, self._busy = inst, on_changed, None, True
        loader = "" if inst.loader == "vanilla" else f", {inst.loader} {inst.loader_version}"
        ctk.CTkLabel(self, text=tr("Now: Minecraft {0}{1}", inst.minecraft_version, loader), anchor="w").pack(
            fill="x", padx=20, pady=(10, 4))
        pick = ctk.CTkFrame(self, fg_color="transparent")
        pick.pack(fill="x", padx=20)
        ctk.CTkLabel(pick, text=tr("Move to Minecraft:")).pack(side="left")
        self.combo = ctk.CTkComboBox(pick, values=[tr("Loading versions...")], width=170, state="disabled")
        self.combo.pack(side="left", padx=8)
        self.check_btn = ctk.CTkButton(pick, text=tr("Check"), width=90, command=self.do_check, state="disabled",
                                        fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        self.check_btn.pack(side="left")
        self.status = ctk.CTkLabel(self, text=tr("Pick a version and press Check. Nothing is changed by checking."),
                                   text_color=COLOR_TEXT_MUTED, anchor="w", justify="left", wraplength=520)
        self.status.pack(fill="x", padx=20, pady=(8, 0))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(0, 12), side="bottom")
        self.undo_btn = ctk.CTkButton(bottom, text=tr("Undo last version change"), command=self.do_undo,
                                       fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        if version_change.latest_snapshot(inst):
            self.undo_btn.pack(side="left")
        self.apply_btn = ctk.CTkButton(bottom, text=tr("Change version"), command=self.do_apply, state="disabled")
        self.apply_btn.pack(side="right")
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate")
        self.ack_var, self.backup_var = ctk.BooleanVar(value=False), ctk.BooleanVar(value=True)
        self.ack_box = ctk.CTkCheckBox(self, text=tr("I understand this pack may not work, change it anyway"),
                                        variable=self.ack_var, command=self._sync_apply, text_color="#FF8FAE")
        self.backup_box = ctk.CTkCheckBox(self, text=tr("Back up my worlds first"), variable=self.backup_var)
        self.backup_box.pack(fill="x", padx=20, pady=(0, 6), side="bottom")
        self.keep_var = ctk.StringVar(value="move")
        self.keep_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.keep_frame, text=tr("Mods with no build for this version:"), anchor="w",
                     font=ctk.CTkFont(weight="bold")).pack(fill="x")
        ctk.CTkRadioButton(self.keep_frame, variable=self.keep_var, value="move", command=self._sync_apply,
                           text=tr("Move them out of the mods folder (recommended, Undo brings them back)")).pack(anchor="w", pady=2)
        ctk.CTkRadioButton(self.keep_frame, variable=self.keep_var, value="keep", command=self._sync_apply,
                           text=tr("Keep them in anyway (some still work, others can stop the game starting)")).pack(anchor="w", pady=2)
        self.result = ctk.CTkScrollableFrame(self)
        self.result.pack(fill="both", expand=True, padx=20, pady=8)

        def load():
            try:
                versions = version_change.release_versions()
            except Exception:
                versions = []
            try:
                size = version_change.tree_size(Path(inst.path) / "minecraft" / "saves")
            except Exception:
                size = 0
            self.app.run_on_main_thread(lambda: self._loaded(versions, size))
        threading.Thread(target=load, daemon=True).start()

    def _loaded(self, versions, size):
        if getattr(self, "_closed", False):
            return
        self._busy = False
        mb = f"{size / 1e6:,.0f} MB"
        self.backup_box.configure(text=tr("Back up my worlds first ({0})", mb) if size else tr("Back up my worlds first"))
        versions = [v for v in versions if v != self.inst.minecraft_version]
        if not versions:
            self.status.configure(text=tr("Couldn't load the version list. Check your connection."), text_color="#FF8FAE")
            return
        self.combo.configure(values=versions, state="readonly")
        self.combo.set(versions[0])
        self.check_btn.configure(state="normal")

    def _say(self, text):
        if not getattr(self, "_closed", False):
            self.status.configure(text=tr(text) if text in self.FIXED else text, text_color=COLOR_TEXT_MUTED)

    def _busy_on(self, on: bool):
        self._busy = on
        if on:
            self.progress.pack(fill="x", padx=20, pady=(0, 6), side="bottom")
            self.progress.start()
            self.check_btn.configure(state="disabled")
            self.apply_btn.configure(state="disabled")
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.check_btn.configure(state="normal")

    def do_check(self):
        target = self.combo.get().strip()
        if self._busy or not target:
            return
        self.plan = None
        for w in self.result.winfo_children():
            w.destroy()
        self.ack_box.pack_forget()
        self.keep_frame.pack_forget()
        self.keep_var.set("move")
        self._busy_on(True)

        def work():
            try:
                plan = version_change.plan_change(self.inst, target, settings.get_curseforge_api_key(),
                                                  progress=lambda t: self.app.run_on_main_thread(lambda: self._say(t)))
            except Exception as e:
                plan = e
            self.app.run_on_main_thread(lambda: self._show_plan(plan))
        threading.Thread(target=work, daemon=True).start()

    def _show_plan(self, plan):
        if getattr(self, "_closed", False):
            return
        self._busy_on(False)
        if isinstance(plan, Exception):
            self.status.configure(text=str(plan), text_color="#FF8FAE")
            return
        self.plan = plan
        total = len(plan.keep) + len(plan.replace) + len(plan.missing) + len(plan.unknown)
        self.status.configure(text=tr("{0} mods: {1} fit as they are, {2} will be replaced, {3} have no build for {4}, "
                                      "{5} not recognized", total, len(plan.keep), len(plan.replace),
                                      len(plan.missing), plan.target_mc, len(plan.unknown)), text_color=COLOR_TEXT_MUTED)

        def line(text, color=COLOR_TEXT_MUTED, bold=False):
            ctk.CTkLabel(self.result, text=text, anchor="w", justify="left", wraplength=500, text_color=color,
                         font=ctk.CTkFont(weight="bold") if bold else None).pack(fill="x", pady=(0, 3))

        loader = "" if plan.loader == "vanilla" else f"{plan.loader} {plan.loader_version}"
        if loader:
            line(tr("Loader will be: {0}", loader))
        self.low = bool(total) and len(plan.missing) / total >= self.LOW_COVERAGE
        if self.low:
            line(tr("This pack probably can't be moved: {0} of {1} mods have nothing for Minecraft {2}.",
                    len(plan.missing), total, plan.target_mc), "#FF8FAE", bold=True)
        if plan.missing:
            line(tr("No build for {0}:", plan.target_mc), "#F5B85C", bold=True)
            line(", ".join(plan.missing[:25]) + (" ..." if len(plan.missing) > 25 else ""))
        betas = [u.title for u in plan.replace if u.channel != "release"]
        if betas:
            line(tr("{0} replacements are beta builds:", len(betas)), "#F5B85C", bold=True)
            line(", ".join(betas))
        if plan.unknown:
            line(tr("Not recognized, left as they are (may not work):"), bold=True)
            line(", ".join(plan.unknown[:25]))
        for e in plan.errors:
            line(tr("Lookup problem: {0}", e), "#FF8FAE")
        if plan.missing:
            self.keep_frame.pack(fill="x", padx=20, pady=(0, 4), side="bottom")
        if self.low:
            self.ack_var.set(False)
            self.ack_box.pack(fill="x", padx=20, pady=(0, 4), side="bottom")
        self._sync_apply()

    def _sync_apply(self):
        ok = bool(self.plan) and not self._busy and (not getattr(self, "low", False) or self.ack_var.get())
        self.apply_btn.configure(state="normal" if ok else "disabled")

    def do_apply(self):
        plan = self.plan
        if not plan or self._busy:
            return
        keep = self.keep_var.get() == "keep"
        text = tr("Change {0} to Minecraft {1}?", self.inst.name, plan.target_mc) + "\n\n"
        if keep and plan.missing:
            text += tr("{0} mods replaced. {1} mods with no build stay in the mods folder - they may stop the game from "
                       "starting. You can undo this afterwards.", len(plan.replace), len(plan.missing))
        else:
            text += tr("{0} mods replaced, {1} moved out of the mods folder (nothing is deleted). You can undo this afterwards.",
                       len(plan.replace), len(plan.missing))
        if not messagebox.askyesno(tr("Change version"), text):
            return
        self._busy_on(True)
        backup = self.backup_var.get()          # read Tk variables HERE, on the main thread - never in work()
        keep_incompatible = self.keep_var.get() == "keep"
        last = [-1]

        def copy_progress(done, total):
            pct = int(done * 100 / total) if total else 100
            if pct != last[0]:
                last[0] = pct
                self.app.run_on_main_thread(lambda: self.status.configure(text=tr("Backing up worlds... {0}%", pct)))

        def work():
            try:
                res = version_change.apply(self.inst, plan, backup_worlds=backup, keep_incompatible=keep_incompatible,
                                           progress=lambda t: self.app.run_on_main_thread(lambda: self._say(t)),
                                           on_copy_progress=copy_progress)
            except Exception as e:
                res = e
            self.app.run_on_main_thread(lambda: self._applied(res, plan))
        threading.Thread(target=work, daemon=True).start()

    def _applied(self, res, plan):
        if self.on_changed:
            self.on_changed()
        if not getattr(self, "_closed", False):
            self.close()
        if isinstance(res, Exception):
            messagebox.showerror(tr("Change version"), str(res) + "\n\n" + tr("If something was half-changed, open Change version again and use Undo."))
            return
        text = tr("Now on Minecraft {0}. {1} mods replaced, {2} moved out.", plan.target_mc, len(res.replaced), len(res.removed))
        if res.kept:
            text += "\n" + tr("Kept in the mods folder anyway: {0}", len(res.kept))
        text += "\n\n" + tr("Rollback snapshot: {0}", str(res.snapshot))
        if res.worlds_backup:
            text += "\n" + tr("Worlds backup: {0}", str(res.worlds_backup))
        messagebox.showinfo(tr("Change version"), text)

    def do_undo(self):
        if not messagebox.askyesno(tr("Undo last version change"),
                                   tr("Put back the previous version, mods and configs? Worlds are not touched.")):
            return
        restored, problems, backup = version_change.undo(self.inst)
        if self.on_changed:
            self.on_changed()
        text = tr("Restored {0} mods.", len(restored))
        if problems:
            text += "\n\n" + "\n".join(problems[:8])
        if backup:
            text += "\n\n" + tr("A worlds backup from before the change is still at: {0}", str(backup))
        if not getattr(self, "_closed", False):
            self.close()
        messagebox.showinfo(tr("Undo last version change"), text)


class DuplicateDialog(ModalDialog):
    """Copies the whole instance (mods, configs, worlds) under a new name - for keeping the old version too."""

    def __init__(self, app: LauncherApp, inst: instances.Instance):
        super().__init__(app, title=tr('Duplicate: {0}', inst.name), width=480, height=300)
        self.inst, self._busy = inst, False
        ctk.CTkLabel(self, text=tr("Name of the copy:"), anchor="w").pack(fill="x", padx=20, pady=(14, 2))
        self.entry = ctk.CTkEntry(self)
        self.entry.insert(0, f"{inst.name} copy")
        self.entry.pack(fill="x", padx=20)
        self.info = ctk.CTkLabel(self, text=tr("Copies everything, worlds included. Calculating size..."),
                                  text_color=COLOR_TEXT_MUTED, anchor="w", justify="left", wraplength=420)
        self.info.pack(fill="x", padx=20, pady=10)
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.btn = ctk.CTkButton(self, text=tr("Duplicate"), command=self.do_duplicate)
        self.btn.pack(side="bottom", pady=15)

        def size():
            try:
                mb = version_change.tree_size(Path(inst.path), skip=version_change.SKIP_ON_DUPLICATE) / 1e6
            except Exception:
                mb = 0
            self.app.run_on_main_thread(lambda: self._sized(mb))
        threading.Thread(target=size, daemon=True).start()

    def _sized(self, mb):
        if not getattr(self, "_closed", False) and not self._busy:
            self.info.configure(text=tr("Copies everything, worlds included: about {0} MB.", f"{mb:,.0f}"))

    def do_duplicate(self):
        name = self.entry.get().strip()
        if self._busy or not name:
            return
        self._busy = True
        self.btn.configure(state="disabled")
        self.progress.pack(fill="x", padx=20, side="bottom", pady=(0, 6))
        last = [-1]

        def on_progress(done, total):
            pct = int(done * 100 / total) if total else 100
            if pct != last[0]:
                last[0] = pct
                self.app.run_on_main_thread(lambda: self._progress(pct))

        def work():
            try:
                res = version_change.duplicate_instance(self.inst, name, on_progress)
            except Exception as e:
                res = e
            self.app.run_on_main_thread(lambda: self._done(res))
        threading.Thread(target=work, daemon=True).start()

    def _progress(self, pct):
        if not getattr(self, "_closed", False):
            self.progress.set(pct / 100)
            self.info.configure(text=tr("Copying... {0}%", pct))

    def _done(self, res):
        self._busy = False
        if isinstance(res, Exception):
            if not getattr(self, "_closed", False):
                self.btn.configure(state="normal")
                self.progress.pack_forget()
            messagebox.showerror(tr("Duplicate"), str(res))
            return
        self.app.refresh_instances()
        if not getattr(self, "_closed", False):
            self.close()
        messagebox.showinfo(tr("Duplicate"), tr("'{0}' was created.", res.name))


class AddModDialog(ModalDialog):
    """Shown after clicking Install on a search result while Browse is in
    'add mods to X' mode. Unlike InstallPackDialog (which creates a brand
    new instance from any version you pick), this only ever offers builds
    that actually match the target instance's existing Minecraft version
    and loader — picking a mismatched build would just be a broken mod in
    the folder, not a working addition."""

    def __init__(self, app: LauncherApp, result: dict, target: instances.Instance,
                 curseforge_api_key: str | None):
        super().__init__(app, title=tr('Add to {0}: {1}', target.name, result['title']), width=440, height=330)
        self.result = result
        self.target = target
        self.curseforge_api_key = curseforge_api_key
        self.compatible: list[dict] = []
        self.labels: list[str] = []

        ctk.CTkLabel(self, text=tr('Compatible builds for {0} {1}:', target.loader, target.minecraft_version)).pack(pady=(15, 0))
        self.version_var = ctk.StringVar(value=tr("Loading..."))
        self.version_menu = ctk.CTkOptionMenu(self, variable=self.version_var, values=[tr("Loading...")],
                                               width=340)
        self.version_menu.pack(pady=10)
        self.install_btn = ctk.CTkButton(self, text=tr("Add to Instance"), command=self.do_add,
                                          state="disabled")
        self.install_btn.pack(pady=(15, 5))
        # In-dialog progress: this dialog's dimming overlay covers the
        # sidebar's bar, so progress shown there is invisible while it's open.
        self.progress = ctk.CTkProgressBar(self, width=340, mode="indeterminate")
        self.status = ctk.CTkLabel(self, text="", text_color=COLOR_TEXT_MUTED)

        threading.Thread(target=self._load_versions, daemon=True).start()

    def _load_versions(self):
        try:
            if self.result["source"] == "modrinth":
                all_versions = search.get_modrinth_versions(self.result["id"])
            else:
                if not self.curseforge_api_key:
                    raise search.SearchError(tr("Need a CurseForge API key to list files for this mod."))
                all_versions = search.get_curseforge_files(self.result["id"], self.curseforge_api_key)

            target_loader = self.target.loader.lower()
            self.compatible = [
                v for v in all_versions
                if self.target.minecraft_version in v.get("game_versions", [])
                and target_loader in [l.lower() for l in v.get("loaders", [])]
            ]
            self.labels = [InstallPackDialog._format_label(v) for v in self.compatible]

            def apply():
                if self.labels:
                    self.version_menu.configure(values=self.labels)
                    self.version_var.set(self.labels[0])
                    self.install_btn.configure(state="normal")
                else:
                    msg = tr("No build of '{0}' found for {1} {2}.", self.result['title'],
                             self.target.loader, self.target.minecraft_version)
                    self.version_menu.configure(values=[msg])
                    self.version_var.set(msg)
            self.app.run_on_main_thread(apply)
        except Exception as e:
            msg = str(e)
            self.app.run_on_main_thread(lambda: messagebox.showerror(tr("Couldn't load builds"), msg))
            self.app.run_on_main_thread(self.close)

    def do_add(self):
        if not self.compatible:
            return
        try:
            index = self.labels.index(self.version_var.get())
        except ValueError:
            messagebox.showwarning(tr("Pick a build"), tr("Select a build first."))
            return
        chosen = self.compatible[index]

        key = (str(self.target.path), chosen["filename"])
        if key in self.app.adds_in_flight:
            return  # same file already being added (e.g. double click)
        self.app.adds_in_flight.add(key)

        self.install_btn.configure(state="disabled", text=tr("Adding..."))
        self.version_menu.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.pack(pady=(10, 0))
        self.progress.start()
        self.status.configure(text=tr("Downloading..."))
        self.status.pack(pady=(4, 0))

        title, target_name = self.result["title"], self.target.name

        def unlock():
            if getattr(self, "_closed", False):
                return
            self.progress.stop()
            self.progress.pack_forget()
            self.status.pack_forget()
            self.install_btn.configure(state="normal", text=tr("Add to Instance"))
            self.version_menu.configure(state="normal")

        def set_fraction(done, total):
            if getattr(self, "_closed", False) or total <= 0:
                return
            if str(self.progress.cget("mode")) != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate")
            self.progress.set(done / total)
            self.status.configure(text=tr('Downloading... {0}%', int(done * 100 / total)))

        def on_progress(done, total):
            self.app.run_on_main_thread(lambda: set_fraction(done, total))

        def worker():
            try:
                dest = Path(self.target.path) / "minecraft" / "mods" / chosen["filename"]
                core.download_file(chosen["url"], dest, chosen.get("sha1"), on_progress=on_progress)

                resolved = packs.ResolvedFile(path=f"mods/{chosen['filename']}", url=chosen["url"],
                                               sha1=chosen.get("sha1"))
                if self.result["source"] == "curseforge":
                    resolved.curseforge_project_id = self.result["id"]
                    resolved.curseforge_file_id = chosen["id"]
                packs.add_file_to_manifest(
                    self.target.path, resolved, name=self.target.name,
                    minecraft_version=self.target.minecraft_version, loader=self.target.loader,
                    loader_version=self.target.loader_version)

                self.app.run_on_main_thread(lambda: messagebox.showinfo(
                    tr("Added"), tr("'{0}' added to {1}.", title, target_name)))
                self.app.run_on_main_thread(self.close)
            except Exception as e:
                msg = str(e)
                self.app.run_on_main_thread(unlock)
                self.app.run_on_main_thread(lambda: messagebox.showerror(tr("Add failed"), msg))
            finally:
                self.app.adds_in_flight.discard(key)

        threading.Thread(target=worker, daemon=True).start()


class ExportInstanceDialog(ModalDialog):
    """Pick a format and where to save, then export — reuses the same
    pack_manifest.json-driven export_*.py modules the CLI uses. packwiz
    exports to a folder (pack.toml/index.toml/mods/*.pw.toml side by side);
    mrpack and CurseForge each export to a single file."""

    FORMATS = {
        "packwiz": {"kind": "dir", "func": "_do_packwiz"},
        "Modrinth (.mrpack)": {"kind": "file", "ext": ".mrpack",
                                "filetypes": [("Modrinth pack", "*.mrpack")], "func": "_do_mrpack"},
        "CurseForge (.zip)": {"kind": "file", "ext": ".zip",
                               "filetypes": [("CurseForge pack", "*.zip")], "func": "_do_curseforge"},
    }

    def __init__(self, app: LauncherApp, inst: instances.Instance):
        super().__init__(app, title=tr('Export: {0}', inst.name), width=440, height=340)
        self.inst = inst
        self.output_path: str | None = None

        ctk.CTkLabel(self, text=tr("Format:")).pack(pady=(15, 0))
        self.format_var = ctk.StringVar(value="packwiz")
        ctk.CTkOptionMenu(self, values=list(self.FORMATS.keys()), variable=self.format_var,
                           command=self._on_format_changed, width=320).pack(pady=5)

        ctk.CTkLabel(self, text=tr("Save to:")).pack(pady=(10, 0))
        path_row = ctk.CTkFrame(self, fg_color="transparent")
        path_row.pack(pady=5, fill="x", padx=20)
        self.path_label = ctk.CTkLabel(path_row, text=tr("(not chosen)"), anchor="w",
                                        text_color=COLOR_TEXT_MUTED, wraplength=240)
        self.path_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(path_row, text=tr("Browse..."), width=90,
                      command=self._browse).pack(side="right")

        self.export_btn = ctk.CTkButton(self, text=tr("Export"), command=self.do_export)
        self.export_btn.pack(pady=(20, 5))
        self.progress = ctk.CTkProgressBar(self, width=340, mode="indeterminate")
        self.status = ctk.CTkLabel(self, text="", text_color=COLOR_TEXT_MUTED)

    def _on_format_changed(self, _choice):
        self.output_path = None
        self.path_label.configure(text=tr("(not chosen)"))

    def _browse(self):
        spec = self.FORMATS[self.format_var.get()]
        if spec["kind"] == "dir":
            path = filedialog.askdirectory(title=tr("Choose export folder"))
        else:
            path = filedialog.asksaveasfilename(
                title=tr("Choose export file"), defaultextension=spec["ext"],
                filetypes=spec["filetypes"] + [(tr("All files"), "*.*")],
                initialfile=f"{self.inst.name}{spec['ext']}")
        if path:
            self.output_path = path
            self.path_label.configure(text=path)

    def _meta(self) -> dict:
        """The instance's own details. Used when it has no pack_manifest.json (a blank
        instance nobody added a mod to through the launcher): it then exports as a pack
        made entirely of its files, instead of failing."""
        i = self.inst
        return {"name": i.name, "minecraft_version": i.minecraft_version,
                "loader": i.loader, "loader_version": i.loader_version}

    def _do_packwiz(self, on_progress=None):
        export_packwiz.export_to_packwiz(self.inst.path, self.output_path, pack_name=self.inst.name,
                                          fallback_meta=self._meta(), on_progress=on_progress)

    def _do_mrpack(self, on_progress=None):
        export_mrpack.export_to_mrpack(self.inst.path, self.output_path, pack_name=self.inst.name,
                                        fallback_meta=self._meta(), on_progress=on_progress)

    def _do_curseforge(self, on_progress=None):
        export_curseforge.export_to_curseforge(self.inst.path, self.output_path, pack_name=self.inst.name,
                                                fallback_meta=self._meta(), on_progress=on_progress)

    def do_export(self):
        if not self.output_path:
            messagebox.showwarning(tr("Missing info"), tr("Choose where to save first."))
            return
        spec = self.FORMATS[self.format_var.get()]
        run = getattr(self, spec["func"])

        if getattr(self, "_busy", False):
            return
        self._busy = True
        self.export_btn.configure(state="disabled", text=tr("Exporting..."))
        self.progress.configure(mode="indeterminate")
        self.progress.pack(pady=(10, 0))
        self.progress.start()
        self.status.configure(text=tr("Exporting..."))
        self.status.pack(pady=(4, 0))

        def unlock():
            self._busy = False
            if getattr(self, "_closed", False):
                return
            self.progress.stop()
            self.progress.pack_forget()
            self.status.pack_forget()
            self.export_btn.configure(state="normal", text=tr("Export"))

        def set_fraction(done, total):
            if getattr(self, "_closed", False) or total <= 0:
                return
            if str(self.progress.cget("mode")) != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate")
            self.progress.set(done / total)
            self.status.configure(text=tr('Exporting... {0}%', int(done * 100 / total)))

        last_pct = [-1]

        def on_progress(done, total):
            pct = int(done * 100 / total) if total else 0
            if pct == last_pct[0] and done != total:
                return  # one UI update per percent, not one per file
            last_pct[0] = pct
            self.app.run_on_main_thread(lambda: set_fraction(done, total))

        def worker():
            try:
                run(on_progress)
                self.app.run_on_main_thread(lambda: messagebox.showinfo(
                    tr("Done"), tr('Exported to:\n{0}', self.output_path)))
                self.app.run_on_main_thread(self.close)
            except Exception as e:
                msg = str(e)
                self.app.run_on_main_thread(unlock)
                self.app.run_on_main_thread(lambda: messagebox.showerror(tr("Export failed"), msg))

        threading.Thread(target=worker, daemon=True).start()


class SettingsDialog(ModalDialog):
    """Settings. For now: interface language. A language change is saved at once and
    takes effect after a restart (the whole window is built from translated text)."""

    def __init__(self, app: LauncherApp):
        super().__init__(app, title=tr("Settings"), width=420, height=320)
        ctk.CTkLabel(self, text=tr("Language:")).pack(pady=(25, 5))
        self.lang_var = ctk.StringVar(value=i18n.LANGUAGES[i18n.current_language()])
        ctk.CTkOptionMenu(self, values=list(i18n.LANGUAGES.values()), variable=self.lang_var,
                          command=self.on_language).pack()
        self.note = ctk.CTkLabel(self, text="", wraplength=360, text_color=COLOR_TEXT_MUTED)
        self.restart_btn = ctk.CTkButton(self, text="", command=app.restart)
        ctk.CTkLabel(self, text=tr("Version {0}", APP_VERSION),
                     text_color=COLOR_TEXT_MUTED).pack(side="bottom", pady=12)

    def on_language(self, label: str):
        code = next(c for c, name in i18n.LANGUAGES.items() if name == label)
        i18n.save_language(code)
        if code == i18n.current_language():  # switched back to what is already showing
            self.note.pack_forget()
            self.restart_btn.pack_forget()
            return
        # worded in the language just picked, since the rest of the window is still in the old one
        self.note.configure(text=i18n.tr_to(code, "Language changed. Restart Voidbox Launcher to apply it."))
        self.restart_btn.configure(text=i18n.tr_to(code, "Restart now"))
        self.note.pack(pady=(20, 8))
        self.restart_btn.pack()


if __name__ == "__main__":
    app = LauncherApp()
    app.mainloop()
