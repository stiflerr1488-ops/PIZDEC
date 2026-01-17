from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import customtkinter as ctk


@dataclass
class CaptchaDialogConfig:
    title: str = "Капча"
    # NOTE: do not make this too small: on Windows with DPI scaling
    # the bottom "continue" button may get clipped.
    geometry: str = "420x270"
    topmost: bool = True


class CaptchaDialog:
    """Small modal-like window prompting the user to solve captcha manually.

    The dialog is UI-only. It should not interact with Playwright directly.
    """

    def __init__(
        self,
        root: ctk.CTk,
        on_done: Callable[[], None],
        on_reload: Optional[Callable[[], None]] = None,
        config: Optional[CaptchaDialogConfig] = None,
    ) -> None:
        self._root = root
        self._on_done = on_done
        self._on_reload = on_reload
        self._cfg = config or CaptchaDialogConfig()

        self._win: Optional[ctk.CTkToplevel] = None
        self._msg_label: Optional[ctk.CTkLabel] = None
        self._ack_var = ctk.BooleanVar(value=False)
        self._btn: Optional[ctk.CTkButton] = None
        self._reload_btn: Optional[ctk.CTkButton] = None

    def _ensure(self) -> ctk.CTkToplevel:
        if self._win is not None:
            return self._win

        w = ctk.CTkToplevel(self._root)
        w.title(self._cfg.title)
        w.geometry(self._cfg.geometry)
        w.resizable(False, False)
        try:
            w.attributes("-topmost", self._cfg.topmost)
        except Exception:
            pass

        # Hide instead of destroy: it can pop-up many times.
        w.protocol("WM_DELETE_WINDOW", self.hide)

        frame = ctk.CTkFrame(w, corner_radius=14)
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        title = ctk.CTkLabel(frame, text="Обнаружена капча", font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(anchor="w", padx=12, pady=(10, 4))

        msg = ctk.CTkLabel(
            frame,
            text="В окне браузера решите капчу, затем нажмите кнопку ниже.\nПосле этого сканирование/парсинг продолжится автоматически.",
            justify="left",
            wraplength=380,
        )
        msg.pack(anchor="w", padx=12, pady=(0, 10))
        self._msg_label = msg

        cb = ctk.CTkCheckBox(frame, text="Капча пройдена", variable=self._ack_var, command=self._update_btn_state)
        cb.pack(anchor="w", padx=12, pady=(0, 10))

        reload_btn = ctk.CTkButton(
            frame,
            text="🔄 Перезагрузить капчу",
            command=self._click_reload,
            height=36,
            state=("normal" if self._on_reload else "disabled"),
        )
        reload_btn.pack(fill="x", padx=12, pady=(0, 10))
        self._reload_btn = reload_btn

        btn = ctk.CTkButton(
            frame,
            text="✅ Продолжить парсинг",
            height=44,
            command=self._click_done,
            state="disabled",
        )
        btn.pack(fill="x", padx=12, pady=(0, 12))
        self._btn = btn

        w.withdraw()
        self._win = w
        return w

    def _update_btn_state(self) -> None:
        if self._btn is None:
            return
        self._btn.configure(state=("normal" if bool(self._ack_var.get()) else "disabled"))

    def _click_done(self) -> None:
        # Close quickly: if captcha still present, worker will re-open it.
        self.hide()
        try:
            self._on_done()
        except Exception:
            pass

    def _click_reload(self) -> None:
        try:
            if self._on_reload:
                self._on_reload()
        except Exception:
            pass

    def show(self, message: Optional[str] = None) -> None:
        w = self._ensure()
        self._ack_var.set(False)
        self._update_btn_state()

        if message and self._msg_label is not None:
            self._msg_label.configure(text=message)

        try:
            w.deiconify()
            w.lift()
            w.focus_force()
        except Exception:
            pass

    def hide(self) -> None:
        if self._win is None:
            return
        try:
            self._win.withdraw()
        except Exception:
            pass

    def is_visible(self) -> bool:
        if self._win is None:
            return False
        try:
            return bool(self._win.winfo_viewable())
        except Exception:
            return False
