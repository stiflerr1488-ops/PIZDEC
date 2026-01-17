from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from utils import find_yandex_browser_executable


YANDEX_REFERRAL_URL = (
    "https://redirect.appmetrica.yandex.com/serve/101728330012750979"
    "?partner_id=831050&appmetrica_js_redirect=0&full=0&clid=14512481&banerid=1314512477"
)


@dataclass
class SetupItem:
    key: str
    label: str


class SetupDialog:
    def __init__(self, root: ctk.CTk, items: List[SetupItem]) -> None:
        self._root = root
        self._items = items
        self._win = ctk.CTkToplevel(root)
        self._win.title("Подготовка к запуску")
        self._win.geometry("520x520")
        self._win.minsize(480, 480)
        self._win.resizable(False, False)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        frame = ctk.CTkFrame(self._win, corner_radius=14)
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        title = ctk.CTkLabel(frame, text="Установка зависимостей", font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(anchor="w", padx=12, pady=(12, 6))

        self._status_label = ctk.CTkLabel(frame, text="Проверяю окружение…")
        self._status_label.pack(anchor="w", padx=12, pady=(0, 10))

        items_frame = ctk.CTkFrame(frame, corner_radius=12)
        items_frame.pack(fill="both", expand=False, padx=12, pady=(0, 10))
        items_frame.grid_columnconfigure(0, weight=1)
        items_frame.grid_columnconfigure(1, minsize=140)

        self._rows: Dict[str, ctk.CTkLabel] = {}
        for idx, item in enumerate(self._items):
            lbl = ctk.CTkLabel(items_frame, text=item.label)
            lbl.grid(row=idx, column=0, padx=10, pady=6, sticky="w")
            status = ctk.CTkLabel(items_frame, text="⏳ ожидается", text_color=("gray55", "gray70"))
            status.grid(row=idx, column=1, padx=10, pady=6, sticky="e")
            self._rows[item.key] = status

        self._progress = ctk.DoubleVar(value=0.0)
        self._bar = ctk.CTkProgressBar(frame, variable=self._progress)
        self._bar.pack(fill="x", padx=12, pady=(6, 10))

        self._close_btn = ctk.CTkButton(frame, text="Закрыть", state="disabled", command=self._on_close)
        self._close_btn.pack(fill="x", padx=12, pady=(0, 8))

        self._on_close_cb: Optional[Callable[[], None]] = None

    def _on_close(self) -> None:
        if self._on_close_cb:
            self._on_close_cb()

    def set_on_close(self, cb: Callable[[], None]) -> None:
        self._on_close_cb = cb

    def set_status(self, text: str) -> None:
        self._status_label.configure(text=text)

    def set_item_status(self, key: str, text: str, color: Optional[str] = None) -> None:
        lbl = self._rows.get(key)
        if not lbl:
            return
        if color:
            lbl.configure(text=text, text_color=color)
        else:
            lbl.configure(text=text)

    def set_progress(self, value: float) -> None:
        self._progress.set(max(0.0, min(1.0, value)))

    def enable_close(self) -> None:
        self._close_btn.configure(state="normal")

    def show(self) -> None:
        try:
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()
        except Exception:
            pass

    def hide(self) -> None:
        try:
            self._win.withdraw()
        except Exception:
            pass


class YandexInstallDialog:
    def __init__(
        self,
        root: ctk.CTk,
        on_installed: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self._root = root
        self._on_installed = on_installed
        self._on_cancel = on_cancel
        self._win = ctk.CTkToplevel(root)
        self._win.title("Нужен Яндекс.Браузер")
        self._win.geometry("520x320")
        self._win.resizable(False, False)
        self._win.protocol("WM_DELETE_WINDOW", self._cancel)

        frame = ctk.CTkFrame(self._win, corner_radius=14)
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        title = ctk.CTkLabel(frame, text="Яндекс.Браузер обязателен", font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(anchor="w", padx=12, pady=(10, 6))

        msg = (
            "Мой парсер работает только на Яндекс.Браузере.\n"
            "Если у вас его нет, установите по кнопке ниже.\n"
            "После установки нажмите «Проверить»."
        )
        self._msg_label = ctk.CTkLabel(frame, text=msg, justify="left", wraplength=480)
        self._msg_label.pack(anchor="w", padx=12, pady=(0, 10))

        self._status_label = ctk.CTkLabel(frame, text="")
        self._status_label.pack(anchor="w", padx=12, pady=(0, 8))

        self._install_btn = ctk.CTkButton(
            frame,
            text="⬇️ Установить Яндекс.Браузер",
            height=42,
            fg_color="#e53935",
            hover_color="#c62828",
            command=self._install,
        )
        self._install_btn.pack(fill="x", padx=12, pady=(0, 8))

        self._check_btn = ctk.CTkButton(
            frame,
            text="🔍 Проверить",
            height=38,
            command=self._check,
        )
        self._check_btn.pack(fill="x", padx=12, pady=(0, 8))

        self._close_btn = ctk.CTkButton(
            frame,
            text="Закрыть приложение",
            height=36,
            command=self._cancel,
        )
        self._close_btn.pack(fill="x", padx=12, pady=(0, 8))

    def show(self) -> None:
        try:
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()
        except Exception:
            pass
        self._install()

    def _set_status(self, text: str) -> None:
        self._status_label.configure(text=text)

    def _check(self) -> None:
        if find_yandex_browser_executable():
            self._set_status("✅ Яндекс.Браузер найден.")
            try:
                self._win.destroy()
            except Exception:
                pass
            self._on_installed()
        else:
            self._set_status("❌ Яндекс.Браузер пока не найден.")

    def _install(self) -> None:
        self._set_status("⏳ Запускаю установщик…")
        thread = threading.Thread(target=self._install_worker, daemon=True)
        thread.start()

    def _install_worker(self) -> None:
        launched = _launch_yandex_installer(YANDEX_REFERRAL_URL)
        if launched:
            self._root.after(0, lambda: self._set_status("✅ Установщик запущен. Завершите установку."))
        else:
            self._root.after(0, lambda: self._set_status("ℹ️ Открыл ссылку для установки в браузере."))

    def _cancel(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass
        self._on_cancel()


def _launch_yandex_installer(url: str) -> bool:
    if os.name == "nt":
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                data = resp.read()
            if data:
                temp_dir = tempfile.gettempdir()
                installer_path = os.path.join(temp_dir, "yandex_browser_installer.exe")
                with open(installer_path, "wb") as file:
                    file.write(data)
                subprocess.Popen([installer_path], shell=True)
                return True
        except Exception:
            pass
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return False


def _pip_install(package: str) -> Tuple[bool, str]:
    cmd = [sys.executable, "-m", "pip", "install", package]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    ok = proc.returncode == 0
    output = (proc.stdout or "") + (proc.stderr or "")
    return ok, output.strip()


def _playwright_install() -> Tuple[bool, str]:
    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    ok = proc.returncode == 0
    output = (proc.stdout or "") + (proc.stderr or "")
    return ok, output.strip()


def _playwright_ready() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


class SetupFlow:
    def __init__(self, root: ctk.CTk) -> None:
        self._root = root
        self._log_lines: List[str] = []
        self._items = [
            SetupItem("customtkinter", "customtkinter"),
            SetupItem("pandas", "pandas"),
            SetupItem("playwright", "playwright"),
            SetupItem("pillow", "pillow"),
            SetupItem("openpyxl", "openpyxl"),
            SetupItem("playwright_stealth", "playwright-stealth"),
            SetupItem("playwright_browser", "Playwright Chromium"),
            SetupItem("yandex", "Яндекс.Браузер"),
        ]
        self._dialog = SetupDialog(self._root, self._items)

    def start(self, on_complete: Callable[[bool, List[str]], None]) -> None:
        self._dialog.set_on_close(lambda: self._finish(False, on_complete))
        self._dialog.show()
        thread = threading.Thread(target=self._run, args=(on_complete,), daemon=True)
        thread.start()

    def _update(self, fn: Callable[[], None]) -> None:
        self._root.after(0, fn)

    def _finish(self, ok: bool, on_complete: Callable[[bool, List[str]], None]) -> None:
        self._update(self._dialog.hide)
        self._update(lambda: on_complete(ok, self._log_lines))

    def _run(self, on_complete: Callable[[bool, List[str]], None]) -> None:
        total = len(self._items)
        completed = 0
        ok = True

        def step_done():
            nonlocal completed
            completed += 1
            self._update(lambda: self._dialog.set_progress(completed / total))

        self._update(lambda: self._dialog.set_status("Проверяю Python-библиотеки…"))

        packages = [
            ("customtkinter", "customtkinter"),
            ("pandas", "pandas"),
            ("playwright", "playwright"),
            ("PIL", "pillow"),
            ("openpyxl", "openpyxl"),
            ("playwright_stealth", "playwright-stealth"),
        ]
        for module_name, pip_name in packages:
            key = pip_name if pip_name != "pillow" else "pillow"
            if module_name == "PIL":
                key = "pillow"
            if module_name == "playwright_stealth":
                key = "playwright_stealth"

            try:
                importlib.import_module(module_name)
                self._log_lines.append(f"✅ {pip_name} уже установлен.")
                self._update(lambda k=key: self._dialog.set_item_status(k, "✅ установлено", "#7ad97a"))
            except Exception:
                self._log_lines.append(f"⏳ Устанавливаю {pip_name}…")
                self._update(lambda k=key: self._dialog.set_item_status(k, "⬇️ установка…", "#f5c542"))
                ok_install, output = _pip_install(pip_name)
                if ok_install:
                    self._log_lines.append(f"✅ {pip_name} установлен.")
                    self._update(lambda k=key: self._dialog.set_item_status(k, "✅ установлено", "#7ad97a"))
                else:
                    ok = False
                    self._log_lines.append(f"❌ Не удалось установить {pip_name}: {output}")
                    self._update(lambda k=key: self._dialog.set_item_status(k, "❌ ошибка", "#ff6b6b"))
            step_done()

        self._update(lambda: self._dialog.set_status("Проверяю Playwright Chromium…"))
        if _playwright_ready():
            self._log_lines.append("✅ Playwright Chromium готов.")
            self._update(lambda: self._dialog.set_item_status("playwright_browser", "✅ установлено", "#7ad97a"))
        else:
            self._log_lines.append("⏳ Устанавливаю Playwright Chromium…")
            self._update(lambda: self._dialog.set_item_status("playwright_browser", "⬇️ установка…", "#f5c542"))
            ok_install, output = _playwright_install()
            if ok_install and _playwright_ready():
                self._log_lines.append("✅ Playwright Chromium установлен.")
                self._update(lambda: self._dialog.set_item_status("playwright_browser", "✅ установлено", "#7ad97a"))
            else:
                ok = False
                self._log_lines.append(f"❌ Не удалось установить Playwright Chromium: {output}")
                self._update(lambda: self._dialog.set_item_status("playwright_browser", "❌ ошибка", "#ff6b6b"))
        step_done()

        self._update(lambda: self._dialog.set_status("Проверяю Яндекс.Браузер…"))
        if find_yandex_browser_executable():
            self._log_lines.append("✅ Яндекс.Браузер найден.")
            self._update(lambda: self._dialog.set_item_status("yandex", "✅ установлено", "#7ad97a"))
        else:
            self._log_lines.append("⚠️ Яндекс.Браузер не найден, запускаю установку.")
            self._update(lambda: self._dialog.set_item_status("yandex", "⚠️ требуется", "#f5c542"))
            installed = self._ensure_yandex()
            if installed:
                self._log_lines.append("✅ Яндекс.Браузер установлен.")
                self._update(lambda: self._dialog.set_item_status("yandex", "✅ установлено", "#7ad97a"))
            else:
                ok = False
                self._log_lines.append("❌ Яндекс.Браузер не установлен. Завершаю.")
                self._update(lambda: self._dialog.set_item_status("yandex", "❌ не установлен", "#ff6b6b"))
        step_done()

        self._update(lambda: self._dialog.set_status("Готово. Запускаю GUI…"))
        time.sleep(0.5)
        if not ok:
            self._update(lambda: self._dialog.enable_close())
            return
        self._finish(True, on_complete)

    def _ensure_yandex(self) -> bool:
        installed_event = threading.Event()
        cancel_event = threading.Event()

        def show_dialog():
            dialog = YandexInstallDialog(
                self._root,
                on_installed=installed_event.set,
                on_cancel=cancel_event.set,
            )
            dialog.show()

        self._update(show_dialog)
        while not installed_event.is_set() and not cancel_event.is_set():
            time.sleep(0.2)
        if cancel_event.is_set():
            self._update(lambda: self._root.destroy())
            return False
        return True
