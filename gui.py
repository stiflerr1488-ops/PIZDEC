"""GUI для запуска медленного (карты) и быстрого (поиск) парсера."""

from __future__ import annotations

import queue
import os
import platform
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

from fast_parser import run_fast_parser
from yandex_maps_scraper import YandexMapsScraper
from excel_writer import ExcelWriter


RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class ParserSettings:
    headless: bool = False
    block_media: bool = False
    limit: int = 0
    lr: str = "120590"
    max_clicks: int = 800
    delay_min_s: float = 0.05
    delay_max_s: float = 0.15


def _setup_theme() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    try:
        ctk.set_widget_scaling(0.90)
    except Exception:
        pass


def _safe_open_path(path: Path) -> None:
    try:
        if not path.exists():
            return
        if path.is_file():
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
                return
            if platform.system() == "Darwin":
                subprocess.run(["open", str(path)], check=False)
                return
            subprocess.run(["xdg-open", str(path)], check=False)
        else:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
                return
            if platform.system() == "Darwin":
                subprocess.run(["open", str(path)], check=False)
                return
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        return


class ParserGUI:
    def __init__(self) -> None:
        _setup_theme()
        self.root = ctk.CTk()
        self.root.title("Парсер Яндекс")
        self.root.geometry("540x600")
        self.root.minsize(520, 560)

        self._log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._settings = ParserSettings()
        self._settings_window: ctk.CTkToplevel | None = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._captcha_event = threading.Event()
        self._running = False

        self._build_ui()
        self.root.after(100, self._drain_queue)

    def _build_ui(self) -> None:
        self._build_header()
        body = ctk.CTkFrame(self.root, corner_radius=14)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self._build_top_card(body)
        self._build_bottom_card(body)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.root, corner_radius=14)
        header.pack(fill="x", padx=10, pady=(10, 8))
        header.grid_columnconfigure(1, weight=1)
        header.grid_columnconfigure(2, minsize=40)
        header.grid_columnconfigure(3, minsize=40)

        logo = ctk.CTkFrame(header, width=22, height=22, corner_radius=6, fg_color="#1f6aa5")
        logo.grid(row=0, column=0, rowspan=2, padx=(10, 10), pady=10, sticky="w")
        logo.grid_propagate(False)

        title = ctk.CTkLabel(header, text="Парсер Яндекс", font=ctk.CTkFont(size=22, weight="bold"))
        title.grid(row=0, column=1, padx=10, pady=(12, 0), sticky="w")

        subtitle = ctk.CTkLabel(
            header,
            text="Медленный режим",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=13),
        )
        subtitle.grid(row=1, column=1, padx=10, pady=(0, 12), sticky="w")

        self.settings_btn = ctk.CTkButton(
            header,
            text="⚙",
            width=34,
            height=34,
            fg_color="#2b2b2b",
            hover_color="#3a3a3a",
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._open_settings,
        )
        self.settings_btn.grid(row=0, column=2, rowspan=2, padx=(0, 8), pady=10, sticky="e")

        self.restart_btn = ctk.CTkButton(
            header,
            text="↻",
            width=34,
            height=34,
            fg_color="#3c8d0d",
            hover_color="#347909",
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._restart_app,
        )
        self.restart_btn.grid(row=0, column=3, rowspan=2, padx=(0, 10), pady=10, sticky="e")

    def _build_top_card(self, parent: ctk.CTkFrame) -> None:
        card = ctk.CTkFrame(parent, corner_radius=14)
        card.pack(fill="x", padx=10, pady=(10, 8))
        card.grid_columnconfigure(0, weight=1)

        self.niche_entry = ctk.CTkEntry(card, placeholder_text="Введите нишу…", height=36)
        self.niche_entry.pack(fill="x", padx=10, pady=(10, 6))

        self.city_entry = ctk.CTkEntry(card, placeholder_text="Введите город…", height=36)
        self.city_entry.pack(fill="x", padx=10, pady=(0, 10))

        self.mode_var = ctk.StringVar(value="Медленный (скрапер)")

    def _build_bottom_card(self, parent: ctk.CTkFrame) -> None:
        card = ctk.CTkFrame(parent, corner_radius=14)
        card.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
        status_row.grid_columnconfigure(1, weight=1)

        self.status_dot = ctk.CTkLabel(status_row, text="●", text_color="#666666", font=ctk.CTkFont(size=14))
        self.status_dot.grid(row=0, column=0, sticky="w")
        self.status_label = ctk.CTkLabel(status_row, text="Ожидание", font=ctk.CTkFont(size=14, weight="bold"))
        self.status_label.grid(row=0, column=1, padx=(8, 0), sticky="w")

        self.progress = ctk.CTkProgressBar(card)
        self.progress.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        self.progress.set(0.0)

        self.log_box = ctk.CTkTextbox(card)
        self.log_box.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.log_box.configure(state="disabled")

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
        for c in range(2):
            btns.grid_columnconfigure(c, weight=1)

        self.start_btn = ctk.CTkButton(
            btns,
            text="🚀 Запустить",
            height=40,
            fg_color="#4CAF50",
            hover_color="#43A047",
            command=self._on_start,
        )
        self.start_btn.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="ew")

        self.pause_btn = ctk.CTkButton(
            btns,
            text="⏸ Пауза",
            height=40,
            fg_color="#3d3d3d",
            hover_color="#4a4a4a",
            command=self._on_pause,
        )
        self.pause_btn.grid(row=1, column=0, padx=(0, 8), pady=(0, 10), sticky="ew")

        self.resume_btn = ctk.CTkButton(
            btns,
            text="▶ Пуск",
            height=40,
            fg_color="#3d3d3d",
            hover_color="#4a4a4a",
            command=self._on_resume,
        )
        self.resume_btn.grid(row=1, column=1, padx=(8, 0), pady=(0, 10), sticky="ew")

        self.stop_btn = ctk.CTkButton(
            btns,
            text="🛑 Стоп",
            height=40,
            fg_color="#ff5555",
            hover_color="#ff3b3b",
            command=self._on_stop,
        )
        self.stop_btn.grid(row=2, column=0, padx=(0, 8), sticky="ew")

        self.results_btn = ctk.CTkButton(
            btns,
            text="📂 Результаты",
            height=40,
            fg_color="#3d3d3d",
            hover_color="#4a4a4a",
            command=self._open_results_dir,
        )
        self.results_btn.grid(row=2, column=1, padx=(8, 0), sticky="ew")

    def _reset_ui(self) -> None:
        if self._running:
            return
        self.niche_entry.delete(0, "end")
        self.city_entry.delete(0, "end")
        self.mode_var.set("Медленный (скрапер)")
        self._set_status("Ожидание", "#666666")
        self._set_progress(0.0)
        self._clear_log()

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.configure(text=text)
        self.status_dot.configure(text_color=color)

    def _set_progress(self, value: float) -> None:
        self.progress.set(max(0.0, min(1.0, value)))

    def _append_log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _log(self, message: str) -> None:
        self._log_queue.put(("log", message))

    def _emit_progress(self, payload: dict) -> None:
        self._log_queue.put(("progress", payload))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._log_queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    text, color = payload
                    self._set_status(str(text), str(color))
                elif kind == "progress":
                    data = payload
                    if isinstance(data, dict):
                        total = data.get("total")
                        index = data.get("index")
                        if isinstance(total, int) and total > 0 and isinstance(index, int):
                            self._set_progress(index / total)
                elif kind == "state":
                    self._set_running(bool(payload))
                self._log_queue.task_done()
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    def _build_query(self) -> str:
        niche = self.niche_entry.get().strip()
        city = self.city_entry.get().strip()
        if niche and city:
            return f"{niche} в {city}"
        return niche or city

    def _output_path(self, mode: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode_slug = "fast" if "Быстрый" in mode else "slow"
        return RESULTS_DIR / f"{mode_slug}_{stamp}.xlsx"

    def _set_running(self, running: bool) -> None:
        self._running = running
        state = "disabled" if running else "normal"
        self.start_btn.configure(state=state)
        self.pause_btn.configure(state="normal" if running else "disabled")
        self.resume_btn.configure(state="normal" if running else "disabled")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.settings_btn.configure(state=state)
        self.restart_btn.configure(state=state)

    def _restart_app(self) -> None:
        if self._running:
            return
        self._reset_ui()
        self._log("🔄 Интерфейс сброшен.")

    def _open_settings(self) -> None:
        if self._running:
            self._append_log("⚠️ Останови парсер перед настройками.")
            return
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.focus()
            return

        window = ctk.CTkToplevel(self.root)
        window.title("Настройки")
        window.geometry("420x420")
        window.resizable(False, False)
        window.grab_set()

        self._settings_window = window

        def _on_close() -> None:
            window.grab_release()
            window.destroy()
            self._settings_window = None

        window.protocol("WM_DELETE_WINDOW", _on_close)

        body = ctk.CTkFrame(window, corner_radius=14)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.grid_columnconfigure(1, weight=1)

        headless_var = ctk.BooleanVar(value=self._settings.headless)
        media_var = ctk.BooleanVar(value=self._settings.block_media)
        limit_var = ctk.StringVar(value=str(self._settings.limit))
        max_clicks_var = ctk.StringVar(value=str(self._settings.max_clicks))

        row = 0
        ctk.CTkLabel(body, text="Медленный режим", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 2)
        )
        row += 1

        ctk.CTkLabel(body, text="Лимит организаций (0 = без лимита)").grid(
            row=row, column=0, sticky="w", padx=10, pady=(4, 4)
        )
        ctk.CTkEntry(body, textvariable=limit_var).grid(row=row, column=1, sticky="ew", padx=10, pady=(4, 4))
        row += 1

        ctk.CTkCheckBox(body, text="Headless режим", variable=headless_var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 4)
        )
        row += 1

        ctk.CTkCheckBox(body, text="Блокировать медиа", variable=media_var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 8)
        )
        row += 1

        ctk.CTkLabel(body, text="Макс. кликов", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2)
        )
        row += 1

        ctk.CTkLabel(body, text="Количество").grid(row=row, column=0, sticky="w", padx=10, pady=(4, 4))
        ctk.CTkEntry(body, textvariable=max_clicks_var).grid(row=row, column=1, sticky="ew", padx=10, pady=(4, 4))
        row += 1

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=(12, 6))
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)

        def _parse_int(value: str, fallback: int) -> int:
            try:
                return int(float(value))
            except Exception:
                return fallback

        def _on_apply() -> None:
            self._settings.limit = max(0, _parse_int(limit_var.get(), self._settings.limit))
            self._settings.headless = bool(headless_var.get())
            self._settings.block_media = bool(media_var.get())
            self._settings.max_clicks = max(1, _parse_int(max_clicks_var.get(), self._settings.max_clicks))
            self._log("⚙️ Настройки сохранены.")
            _on_close()

        ctk.CTkButton(btns, text="Сохранить", command=_on_apply).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btns, text="Отмена", fg_color="#3d3d3d", hover_color="#4a4a4a", command=_on_close).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

    def _on_start(self) -> None:
        if self._running:
            return
        query = self._build_query()
        if not query:
            self._append_log("⚠️ Укажи нишу и/или город.")
            return

        mode = self.mode_var.get()
        output_path = self._output_path(mode)

        self._stop_event.clear()
        self._pause_event.clear()
        self._captcha_event.clear()
        self._set_running(True)
        self._set_status("Запуск…", "#4CAF50")
        self._set_progress(0.0)

        worker = threading.Thread(
            target=self._run_worker,
            args=(mode, query, output_path),
            daemon=True,
        )
        self._worker = worker
        worker.start()

    def _on_pause(self) -> None:
        if not self._running:
            return
        self._pause_event.set()
        self._log("⏸ Пауза включена.")
        self._set_status("Пауза", "#fbc02d")

    def _on_resume(self) -> None:
        if not self._running:
            return
        self._pause_event.clear()
        self._captcha_event.set()
        self._log("▶ Продолжаю.")
        self._set_status("Работаю", "#4CAF50")

    def _on_stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        self._pause_event.clear()
        self._captcha_event.set()
        self._log("🛑 Остановлено пользователем.")
        self._set_status("Остановка…", "#ff5555")

    def _open_results_dir(self) -> None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        _safe_open_path(RESULTS_DIR)

    def _run_worker(self, mode: str, query: str, output_path: Path) -> None:
        self._log_queue.put(("status", ("Работаю", "#4CAF50")))
        try:
            if "Быстрый" in mode:
                self._run_fast(query, output_path)
            else:
                self._run_slow(query, output_path)
        except Exception as exc:
            self._log(f"❌ Ошибка: {exc}")
        finally:
            self._log_queue.put(("status", ("Готово", "#666666")))
            self._log_queue.put(("state", False))

    def _run_slow(self, query: str, output_path: Path) -> None:
        self._log("🐢 Медленный режим: Яндекс Карты.")
        scraper = YandexMapsScraper(
            query=query,
            limit=self._settings.limit if self._settings.limit > 0 else None,
            headless=self._settings.headless,
            block_media=self._settings.block_media,
        )
        writer = ExcelWriter(output_path)
        count = 0
        try:
            for org in scraper.run():
                if self._stop_event.is_set():
                    break
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.1)
                writer.append(org)
                count += 1
                if count % 10 == 0:
                    self._log(f"✅ Сохранено организаций: {count}")
        finally:
            writer.close()

        if not self._stop_event.is_set():
            self._log(f"📄 Файл сохранён: {output_path.name}")
            _safe_open_path(output_path)

    def _run_fast(self, query: str, output_path: Path) -> None:
        def progress_cb(payload: dict) -> None:
            if payload.get("phase") == "serp_parse":
                self._emit_progress(
                    {
                        "index": payload.get("index", 0),
                        "total": payload.get("total", 0),
                    }
                )

        count = run_fast_parser(
            query=query,
            output_path=output_path,
            lr=self._settings.lr,
            max_clicks=self._settings.max_clicks,
            delay_min_s=self._settings.delay_min_s,
            delay_max_s=self._settings.delay_max_s,
            stop_event=self._stop_event,
            pause_event=self._pause_event,
            captcha_resume_event=self._captcha_event,
            log=self._log,
            progress=progress_cb,
        )

        if not self._stop_event.is_set():
            self._log(f"⚡ Быстрый режим завершён. Записано: {count}")
            _safe_open_path(output_path)

    def run(self) -> None:
        self._set_running(False)
        self.root.mainloop()


def main() -> None:
    app = ParserGUI()
    app.run()


if __name__ == "__main__":
    main()
