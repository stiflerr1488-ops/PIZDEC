from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import customtkinter as ctk


@dataclass
class WarmupDialogConfig:
    title: str = "Прогрев браузера"
    geometry: str = "460x300"
    topmost: bool = True


class WarmupDialog:
    def __init__(
        self,
        root: ctk.CTk,
        on_done: Callable[[], None],
        on_start: Optional[Callable[[], None]] = None,
        config: Optional[WarmupDialogConfig] = None,
    ) -> None:
        self._root = root
        self._on_done = on_done
        self._on_start = on_start
        self._cfg = config or WarmupDialogConfig()
        self._win: Optional[ctk.CTkToplevel] = None
        self._msg_label: Optional[ctk.CTkLabel] = None
        self._btn_start: Optional[ctk.CTkButton] = None
        self._btn_close: Optional[ctk.CTkButton] = None
        self._btn_done: Optional[ctk.CTkButton] = None
        self._mode: str = "prompt"

    def _ensure(self) -> ctk.CTkToplevel:
        if self._win is not None:
            return self._win

        win = ctk.CTkToplevel(self._root)
        win.title(self._cfg.title)
        win.geometry(self._cfg.geometry)
        win.resizable(False, False)
        try:
            win.attributes("-topmost", self._cfg.topmost)
        except Exception:
            pass
        win.protocol("WM_DELETE_WINDOW", self.hide)

        frame = ctk.CTkFrame(win, corner_radius=14)
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        title = ctk.CTkLabel(frame, text="Прогрев профиля", font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(anchor="w", padx=12, pady=(10, 6))

        msg = ctk.CTkLabel(
            frame,
            text="",
            justify="left",
            wraplength=420,
        )
        msg.pack(anchor="w", padx=12, pady=(0, 12))
        self._msg_label = msg

        self._btn_start = ctk.CTkButton(
            frame,
            text="🔥 Прогреть",
            height=42,
            fg_color="#d93025",
            hover_color="#b61f16",
            command=self._click_start,
        )
        self._btn_start.pack(fill="x", padx=12, pady=(0, 8))

        self._btn_close = ctk.CTkButton(
            frame,
            text="Закрыть",
            height=36,
            command=self.hide,
        )
        self._btn_close.pack(fill="x", padx=12, pady=(0, 8))

        self._btn_done = ctk.CTkButton(
            frame,
            text="✅ Завершить прогрев",
            height=42,
            command=self._click_done,
        )
        self._btn_done.pack(fill="x", padx=12, pady=(0, 8))

        win.withdraw()
        self._win = win
        self._set_mode(self._mode)
        return win

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        if not self._msg_label or not self._btn_start or not self._btn_close or not self._btn_done:
            return
        if mode == "progress":
            self._msg_label.configure(
                text=(
                    "Инструкции:\n"
                    "• принять cookies\n"
                    "• открыть 2–3 карточки\n"
                    "• покрутить карту\n"
                    "• сделать 1–2 поиска\n"
                    "• подождать 30–60 сек"
                )
            )
            self._btn_start.pack_forget()
            self._btn_close.pack_forget()
            self._btn_done.pack(fill="x", padx=12, pady=(0, 8))
        else:
            self._msg_label.configure(
                text=(
                    "Профиль браузера не найден или пуст.\n"
                    "Рекомендуется прогреть его перед работой."
                )
            )
            self._btn_done.pack_forget()
            self._btn_start.pack(fill="x", padx=12, pady=(0, 8))
            self._btn_close.pack(fill="x", padx=12, pady=(0, 8))

    def _click_done(self) -> None:
        self.hide()
        try:
            self._on_done()
        except Exception:
            pass

    def _click_start(self) -> None:
        try:
            if self._on_start:
                self._on_start()
        except Exception:
            pass
        self.show_progress()

    def set_on_start(self, on_start: Optional[Callable[[], None]]) -> None:
        self._on_start = on_start

    def show_prompt(self) -> None:
        win = self._ensure()
        self._set_mode("prompt")
        try:
            win.deiconify()
            win.lift()
            win.focus_force()
        except Exception:
            pass

    def show_progress(self) -> None:
        win = self._ensure()
        self._set_mode("progress")
        try:
            win.deiconify()
            win.lift()
            win.focus_force()
        except Exception:
            pass

    def show(self) -> None:
        self.show_progress()

    def hide(self) -> None:
        if self._win is None:
            return
        try:
            self._win.withdraw()
        except Exception:
            pass
