"""Статический макет GUI (один файл).

По запросу: повторить внешний вид как на скриншоте и убрать весь функционал.
Все кнопки существуют только визуально (command=lambda: None).
"""

from __future__ import annotations

import customtkinter as ctk


def _setup_theme() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    # Сделаем интерфейс компактнее (помогает уместить всё в меньшем окне).
    try:
        ctk.set_widget_scaling(0.80)
    except Exception:
        pass


def _build_header(root: ctk.CTk) -> None:
    header = ctk.CTkFrame(root, corner_radius=14)
    header.pack(fill="x", padx=10, pady=(10, 8))
    header.grid_columnconfigure(1, weight=1)
    header.grid_columnconfigure(2, minsize=40)
    header.grid_columnconfigure(3, minsize=40)

    # Мини-"логотип" как на скрине (синяя плашка).
    logo = ctk.CTkFrame(header, width=22, height=22, corner_radius=6, fg_color="#1f6aa5")
    logo.grid(row=0, column=0, rowspan=2, padx=(10, 10), pady=10, sticky="w")
    logo.grid_propagate(False)

    title = ctk.CTkLabel(header, text="Парсер Яндекс", font=ctk.CTkFont(size=22, weight="bold"))
    title.grid(row=0, column=1, padx=10, pady=(12, 0), sticky="w")

    subtitle = ctk.CTkLabel(header, text="", text_color=("gray35", "gray70"), font=ctk.CTkFont(size=13))
    subtitle.grid(row=1, column=1, padx=10, pady=(0, 12), sticky="w")

    adv_btn = ctk.CTkButton(
        header,
        text="⚙",
        width=34,
        height=34,
        fg_color="#2b2b2b",
        hover_color="#3a3a3a",
        font=ctk.CTkFont(size=16, weight="bold"),
        command=lambda: None,
    )
    adv_btn.grid(row=0, column=2, rowspan=2, padx=(0, 8), pady=10, sticky="e")

    restart_btn = ctk.CTkButton(
        header,
        text="↻",
        width=34,
        height=34,
        fg_color="#3c8d0d",
        hover_color="#347909",
        font=ctk.CTkFont(size=16, weight="bold"),
        command=lambda: None,
    )
    restart_btn.grid(row=0, column=3, rowspan=2, padx=(0, 10), pady=10, sticky="e")


def _build_top_card(parent: ctk.CTkFrame) -> None:
    card = ctk.CTkFrame(parent, corner_radius=14)
    card.pack(fill="x", padx=10, pady=(10, 8))
    card.grid_columnconfigure(0, weight=1)

    def entry_row(placeholder: str) -> tuple[ctk.CTkEntry, ctk.CTkButton]:
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(10, 6))
        row.grid_columnconfigure(0, weight=1)

        e = ctk.CTkEntry(row, placeholder_text=placeholder, height=36)
        e.grid(row=0, column=0, sticky="ew")

        dice = ctk.CTkButton(
            row,
            text="🎲",
            width=40,
            height=36,
            fg_color="#2b2b2b",
            hover_color="#3a3a3a",
            font=ctk.CTkFont(size=16, weight="bold"),
            command=lambda: None,
        )
        dice.grid(row=0, column=1, padx=(10, 0))
        return e, dice

    entry_row("Введите нишу…")
    # Между строками — чуть меньше отступ как на скрине.
    row2 = ctk.CTkFrame(card, fg_color="transparent")
    row2.pack(fill="x", padx=10, pady=(0, 10))
    row2.grid_columnconfigure(0, weight=1)
    city_e = ctk.CTkEntry(row2, placeholder_text="Введите город…", height=36)
    city_e.grid(row=0, column=0, sticky="ew")
    city_dice = ctk.CTkButton(
        row2,
        text="🎲",
        width=40,
        height=36,
        fg_color="#2b2b2b",
        hover_color="#3a3a3a",
        font=ctk.CTkFont(size=16, weight="bold"),
        command=lambda: None,
    )
    city_dice.grid(row=0, column=1, padx=(10, 0))

    # Блок "Парсер" + сегментированная кнопка.
    mode_box = ctk.CTkFrame(card, corner_radius=12)
    mode_box.pack(fill="x", padx=10, pady=(0, 10))
    mode_box.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(mode_box, text="Парсер", text_color=("gray35", "gray70")) \
        .grid(row=0, column=0, padx=10, pady=(8, 0), sticky="w")

    parse_mode = ctk.StringVar(value="Карты (подробно)")
    seg = ctk.CTkSegmentedButton(
        mode_box,
        variable=parse_mode,
        values=["Карты (подробно)", "Поиск (быстро)"],
        command=lambda *_: None,
    )
    seg.grid(row=1, column=0, padx=10, pady=(6, 10), sticky="ew")

    # Выставим активную вкладку как на скрине.
    try:
        seg.set("Карты (подробно)")
    except Exception:
        pass


def _build_bottom_card(parent: ctk.CTkFrame) -> None:
    card = ctk.CTkFrame(parent, corner_radius=14)
    card.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    card.grid_columnconfigure(0, weight=1)
    # Лог-бокс должен растягиваться по высоте.
    card.grid_rowconfigure(2, weight=1)

    status_row = ctk.CTkFrame(card, fg_color="transparent")
    status_row.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
    status_row.grid_columnconfigure(1, weight=1)

    dot = ctk.CTkLabel(status_row, text="●", text_color="#666666", font=ctk.CTkFont(size=14))
    dot.grid(row=0, column=0, sticky="w")
    status = ctk.CTkLabel(status_row, text="Ожидание", font=ctk.CTkFont(size=14, weight="bold"))
    status.grid(row=0, column=1, padx=(8, 0), sticky="w")

    pb = ctk.CTkProgressBar(card)
    pb.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
    pb.set(0.0)

    log_box = ctk.CTkTextbox(card)
    log_box.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
    log_box.configure(state="normal")
    log_box.insert(
        "end",
        "☑ Playwright Chromium готов.\n"
        "☑ Яндекс.Браузер найден.\n",
    )
    log_box.configure(state="disabled")

    # Кнопки как на скрине: большая зеленая + сетка 2x2 ниже.
    btns = ctk.CTkFrame(card, fg_color="transparent")
    btns.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
    for c in range(2):
        btns.grid_columnconfigure(c, weight=1)

    start_btn = ctk.CTkButton(
        btns,
        text="🚀 Запустить",
        height=40,
        fg_color="#4CAF50",
        hover_color="#43A047",
        command=lambda: None,
    )
    start_btn.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="ew")

    pause_btn = ctk.CTkButton(
        btns,
        text="⏸ Пауза",
        height=40,
        fg_color="#3d3d3d",
        hover_color="#4a4a4a",
        command=lambda: None,
    )
    pause_btn.grid(row=1, column=0, padx=(0, 8), pady=(0, 10), sticky="ew")

    resume_btn = ctk.CTkButton(
        btns,
        text="▶ Пуск",
        height=40,
        fg_color="#3d3d3d",
        hover_color="#4a4a4a",
        command=lambda: None,
    )
    resume_btn.grid(row=1, column=1, padx=(8, 0), pady=(0, 10), sticky="ew")

    stop_btn = ctk.CTkButton(
        btns,
        text="🛑 Стоп",
        height=40,
        fg_color="#ff5555",
        hover_color="#ff3b3b",
        command=lambda: None,
    )
    stop_btn.grid(row=2, column=0, padx=(0, 8), sticky="ew")

    results_btn = ctk.CTkButton(
        btns,
        text="📂 Результаты",
        height=40,
        fg_color="#3d3d3d",
        hover_color="#4a4a4a",
        command=lambda: None,
    )
    results_btn.grid(row=2, column=1, padx=(8, 0), sticky="ew")


def main() -> None:
    _setup_theme()
    root = ctk.CTk()
    root.title("Парсер Яндекс")

    # Ещё меньше (примерно в 2 раза компактнее относительно первых версий).
    root.geometry("520x560")
    root.minsize(480, 520)

    _build_header(root)

    body = ctk.CTkFrame(root, corner_radius=14)
    body.pack(fill="both", expand=True, padx=10, pady=(0, 8))
    body.grid_columnconfigure(0, weight=1)
    body.grid_rowconfigure(1, weight=1)

    _build_top_card(body)
    _build_bottom_card(body)

    root.mainloop()


if __name__ == "__main__":
    main()
