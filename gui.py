import logging
import queue
import threading
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from excel_writer import ExcelWriter
from main import open_file
from yandex_maps_scraper import YandexMapsScraper


class QueueHandler(logging.Handler):
    def __init__(self, log_queue: "queue.Queue[str]") -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.log_queue.put(message)


class ScraperApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("Yandex Maps Scraper")
        self.geometry("820x640")
        self.minsize(720, 560)

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self._build_ui()
        self.after(100, self._poll_logs)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        form_frame = ctk.CTkFrame(self)
        form_frame.grid(row=0, column=0, padx=16, pady=16, sticky="ew")
        form_frame.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(form_frame, text="Поисковый запрос").grid(
            row=row, column=0, sticky="w", padx=12, pady=6
        )
        self.query_entry = ctk.CTkEntry(form_frame, placeholder_text="например: кофейня в Казани")
        self.query_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=6)

        row += 1
        ctk.CTkLabel(form_frame, text="Ниша").grid(row=row, column=0, sticky="w", padx=12, pady=6)
        self.niche_entry = ctk.CTkEntry(form_frame, placeholder_text="например: кофейня")
        self.niche_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=6)

        row += 1
        ctk.CTkLabel(form_frame, text="Город").grid(row=row, column=0, sticky="w", padx=12, pady=6)
        self.city_entry = ctk.CTkEntry(form_frame, placeholder_text="например: Казань")
        self.city_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=6)

        row += 1
        ctk.CTkLabel(form_frame, text="Лимит организаций").grid(
            row=row, column=0, sticky="w", padx=12, pady=6
        )
        self.limit_entry = ctk.CTkEntry(form_frame, placeholder_text="оставьте пустым для без лимита")
        self.limit_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=6)

        row += 1
        ctk.CTkLabel(form_frame, text="Имя файла").grid(row=row, column=0, sticky="w", padx=12, pady=6)
        self.output_entry = ctk.CTkEntry(form_frame)
        self.output_entry.insert(0, "result.xlsx")
        self.output_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=6)

        row += 1
        ctk.CTkLabel(form_frame, text="Лог файл (опционально)").grid(
            row=row, column=0, sticky="w", padx=12, pady=6
        )
        self.log_entry = ctk.CTkEntry(form_frame, placeholder_text="например: scraper.log")
        self.log_entry.grid(row=row, column=1, sticky="ew", padx=12, pady=6)

        row += 1
        self.headless_var = ctk.BooleanVar(value=False)
        self.headless_switch = ctk.CTkSwitch(
            form_frame, text="Headless режим", variable=self.headless_var
        )
        self.headless_switch.grid(row=row, column=0, columnspan=2, sticky="w", padx=12, pady=6)

        row += 1
        button_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        button_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        self.run_button = ctk.CTkButton(button_frame, text="Запустить", command=self._start_scrape)
        self.run_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.clear_button = ctk.CTkButton(button_frame, text="Очистить лог", command=self._clear_logs)
        self.clear_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.status_label = ctk.CTkLabel(
            form_frame, text="Готово к запуску", anchor="w"
        )
        self.status_label.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 0))

        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_text = ctk.CTkTextbox(log_frame, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.log_text.configure(state="disabled")

    def _clear_logs(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _poll_logs(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(100, self._poll_logs)

    def _start_scrape(self) -> None:
        query = self.query_entry.get().strip()
        niche = self.niche_entry.get().strip()
        city = self.city_entry.get().strip()
        if not query and (niche or city):
            query = f"{niche} в {city}".strip()

        if not query:
            messagebox.showerror("Ошибка", "Введите поисковый запрос или заполните нишу и город.")
            return

        limit_value = self.limit_entry.get().strip()
        limit = None
        if limit_value:
            try:
                limit = int(limit_value)
                if limit <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Ошибка", "Лимит должен быть положительным числом.")
                return

        output_name = self.output_entry.get().strip() or "result.xlsx"
        log_path = self.log_entry.get().strip()
        headless = bool(self.headless_var.get())

        self.run_button.configure(state="disabled")
        self.status_label.configure(text="Запуск...")

        thread = threading.Thread(
            target=self._run_scraper,
            args=(query, limit, headless, output_name, log_path),
            daemon=True,
        )
        thread.start()

    def _configure_logging(self, log_path: str) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setFormatter(formatter)
        root_logger.addHandler(queue_handler)

        if log_path:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

    def _run_scraper(
        self,
        query: str,
        limit: int | None,
        headless: bool,
        output_name: str,
        log_path: str,
    ) -> None:
        self._configure_logging(log_path)
        logger = logging.getLogger(__name__)
        script_dir = Path(__file__).resolve().parent
        output_dir = script_dir / "результаты"
        output_path = output_dir / Path(output_name).name

        writer = ExcelWriter(output_path)
        scraper = YandexMapsScraper(query=query, limit=limit, headless=headless)
        success = False
        error_message = ""
        try:
            for organization in scraper.run():
                writer.append(organization)
            success = True
        except Exception as exc:
            logger.exception("Ошибка во время парсинга: %s", exc)
            error_message = str(exc)
        finally:
            writer.close()

        if success:
            logger.info("Готово. Файл сохранен: %s", output_path)
            open_file(output_path)
            self.after(0, self._finish_success, output_path)
        else:
            self.after(0, self._finish_error, error_message)

    def _finish_success(self, output_path: Path) -> None:
        self.status_label.configure(text=f"Готово. Файл: {output_path}")
        self.run_button.configure(state="normal")

    def _finish_error(self, error_message: str) -> None:
        self.status_label.configure(text="Ошибка во время парсинга.")
        self.run_button.configure(state="normal")
        if error_message:
            messagebox.showerror("Ошибка", error_message)


def main() -> None:
    app = ScraperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
