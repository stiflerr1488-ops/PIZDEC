"""GUI для запуска «быстрый» (поиск) и «подробный» (карты) парсера."""

from __future__ import annotations

import queue
import os
import platform
import random
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from urllib.parse import quote
from pathlib import Path

import customtkinter as ctk
import qrcode
from PIL import Image

from playwright.sync_api import sync_playwright

from app.excel_writer import ExcelWriter
from app.filters import passes_potential_filters
from main import REQUIREMENTS_FILE, _missing_modules, _parse_required_modules, ensure_dependencies
from app.notifications import notify_sound
from app.playwright_utils import (
    PLAYWRIGHT_LAUNCH_ARGS,
    PLAYWRIGHT_USER_AGENT,
    PLAYWRIGHT_VIEWPORT,
    chrome_not_found_message,
    is_chrome_missing_error,
    launch_chrome,
    setup_resource_blocking,
)
from app.settings_store import load_settings, save_settings
from app.utils import build_result_paths, configure_logging, split_query


RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
FAST_MODE_LABEL = "быстрый"
SLOW_MODE_LABEL = "подробный"
DONATION_URL = "https://www.sberbank.ru/ru/choise_bank?requisiteNumber=+79633181841&bankCode=100000000004"
DONATION_PHONE = "+7-963-318-18-41"
THANKS_MESSAGE = (
    "Спасибо, что пользуешься этим парсером.\n"
    "Я потратил на него много времени и сил и отдаю его полностью бесплатно.\n"
    "Если захочешь отблагодарить и поддержать развитие, буду очень признателен.\n"
    "Если вдруг хочешь отблагодарить, нажми на кнопку."
)
POST_PARSE_MESSAGE = (
    "Если парсер помог и сэкономил тебе время, можно сказать «Спасибо».\n"
    "Кофе, вкусняшки, обновления."
)

LOG_LEVEL_LABELS = {
    "Подробные (всё)": "debug",
    "Обычные (рекомендуется)": "info",
    "Только важное": "warning",
    "Только ошибки": "error",
}
LOG_LEVEL_LABELS_REVERSE = {value: key for key, value in LOG_LEVEL_LABELS.items()}
LOG_LEVEL_ORDER = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
}

CITIES = [
    "Москва Красносельский",
    "Москва Таганский",
    "Москва Арбат",
    "Москва Пресненский",
    "Москва Хамовники",
    "Москва Замоскворечье",
    "Москва Хорошёво-Мнёвники",
    "Москва Раменки",
    "Москва Кунцево",
    "Москва Фили-Давыдково",
    "Москва Тёплый Стан",
    "Москва Юго-Западный",
    "Москва Черёмушки",
    "Москва Нагатинский затон",
    "Москва Донской",
    "Москва Зябликово",
    "Москва Бутово",
    "Москва Савёловский",
    "Москва Левобережный",
    "Москва Алексеевский",
    "Москва Бибирево",
    "Москва Лианозово",
    "Москва Метрогородок",
    "Москва Вешняки",
    "Москва Никольская",
    "Санкт-Петербург Невский проспект",
    "Санкт-Петербург Площадь Восстания",
    "Санкт-Петербург Лиговский проспект",
    "Санкт-Петербург Петроградская сторона",
    "Санкт-Петербург Петропавловская крепость",
    "Санкт-Петербург Северная сторона",
    "Санкт-Петербург Васильевский остров",
    "Санкт-Петербург Приморский район",
    "Санкт-Петербург Юго-Западный",
    "Санкт-Петербург Шушары",
    "Санкт-Петербург Купчино",
    "Санкт-Петербург Московский проспект",
    "Санкт-Петербург Кировский завод",
    "Санкт-Петербург Старая деревня",
    "Санкт-Петербург Гражданский проспект",
    "Санкт-Петербург Пушкин",
    "Санкт-Петербург Павловск",
    "Санкт-Петербург Ломоносов",
    "Санкт-Петербург Сестрорецк",
    "Санкт-Петербург Красное Село",
    "Новосибирск Железнодорожный",
    "Новосибирск Октябрьский",
    "Новосибирск Заельцовский",
    "Новосибирск Заельцовский",
    "Новосибирск Новая Заря",
    "Новосибирск Ленинский",
    "Новосибирск Южный",
    "Новосибирск Привокзальный",
    "Новосибирск Новая Сибирь",
    "Екатеринбург Чкаловский",
    "Екатеринбург Татищева",
    "Екатеринбург Солнечный",
    "Екатеринбург Новый Сортировочный",
    "Екатеринбург Верх-Исетский",
    "Екатеринбург Полевой",
    "Екатеринбург Озёрный",
    "Екатеринбург Заводская",
    "Екатеринбург Южный посёлок",
    "Нижний Новгород Нижне-Волжская набережная",
    "Нижний Новгород Советская площадь",
    "Нижний Новгород Заводской",
    "Нижний Новгород Дзержинский",
    "Нижний Новгород Автозавод",
    "Нижний Новгород Кировский",
    "Казань Кремлёвская площадь",
    "Казань Старо-Татарская",
    "Казань Высокий рынок",
    "Казань Канавино",
    "Казань Ярмарка",
    "Казань Ленина",
    "Казань Энергетика",
    "Казань Северный",
    "Челябинск Проспект Ленина",
    "Челябинск Площадь Революции",
    "Челябинск Копейский",
    "Челябинск Чурилово",
    "Челябинск Челябинский тракт",
    "Челябинск Новоуральский",
    "Омск Площадь Ленина",
    "Омск Улица Красный путь",
    "Омск Набережная",
    "Омск Солнечный",
    "Омск Дзержинский",
    "Омск Старо-Киргизская",
    "Самара Набережная",
    "Самара Площадь Куйбышева",
    "Самара Дачный",
    "Самара Фрунзенский",
    "Самара Солнечный",
    "Ростов-на-Дону Дону",
    "Ростов-на-Дону Театральная площадь",
    "Ростов-на-Дону Ворошиловский",
    "Ростов-на-Дону Ульяновка",
    "Ростов-на-Дону Новый город",
    "Ростов-на-Дону Батайск",
]

NICHES = [
    "Парикмахерские",
    "Студии красоты",
    "Стоматологии",
    "Массажные салоны",
    "Косметологические кабинеты",
    "Юридические услуги",
    "Автосервисы",
    "Ремонт бытовой техники",
    "Строительные компании",
    "Ремонт квартир",
    "Электрики",
    "Плотники",
    "Садоводы и ландшафтные дизайнеры",
    "Клининговые компании",
    "Прачечные и химчистки",
    "Туристические агентства",
    "Гостиницы и отели",
    "Хостелы",
    "Кампинги",
    "Рестораны",
    "Кафе",
    "Кулинарные школы",
    "Ремонт автомобилей",
    "Путеводители и экскурсии",
    "Авиакомпании",
    "Аренда автомобилей",
    "Фитнес-клубы",
    "Спортивные залы",
    "Йога-студии",
    "Танцевальные студии",
    "Лыжные курорты",
    "Велосипедные магазины",
    "Свадебные агентства",
    "Аренда жилья",
    "Агентства недвижимости",
    "Прокат автомобилей",
    "Репетиторы",
    "Школы танцев",
    "Спортивные клубы для детей",
    "Ремонт холодильников",
    "Ремонт мобильных телефонов",
    "Ремонт компьютеров",
    "Изготовление мебели на заказ",
    "Художественные мастерские",
    "Организация корпоративов",
    "Охранные агентства",
    "Массажные кабинеты",
    "Услуги для домашних животных",
    "Услуги по стрижке собак",
    "Услуги по выгулу собак",
    "Услуги по стерилизации животных",
    "Магазины для домашних животных",
    "Услуги по организации мероприятий",
    "Мебельные магазины",
    "Магазины спортивного питания",
    "Магазины косметики",
    "Магазины парфюмерии",
    "Книжные магазины",
    "Химчистки",
    "Кулинарии",
    "Услуги по декорированию интерьеров",
    "Магазины электроники",
    "Магазины игрушек",
    "Магазины одежды",
    "Магазины обуви",
    "Оптовые поставки товаров",
    "Магазины автомобильных запчастей",
    "Автозаправочные станции",
    "Аптеки",
    "Салоны красоты",
    "Компании по ремонту и установке кондиционеров",
    "Производители строительных материалов",
    "Флористы",
    "Фотоателье",
    "Видеографы",
    "Мебельщики",
    "Прокат строительного инструмента",
    "Курсы по финансовому планированию",
    "Агентства по трудоустройству",
    "Массажные кабинеты",
    "Услуги по организации путешествий",
    "Организация деловых поездок",
    "Консалтинг в области финансов",
    "Аренда офисных помещений",
    "Туристические агентства для активного отдыха",
    "Услуги по доставке еды",
    "Ремонт электроприборов",
    "Курсы по web-разработке",
    "Аренда свадебных платьев",
    "Салон автомобилей",
    "Студии звукозаписи",
    "Салоны мобильных телефонов",
    "Компании по ремонту и обслуживанию котлов",
    "Дизайн интерьеров",
    "Производители холодильников",
    "Компании по проектированию",
    "Студии массажа",
    "Сервисы для малых бизнесов",
    "Компании по безопасности для бизнеса",
    "Стоматологические клиники",
    "Студии йоги",
    "Магазины бытовой техники",
    "Аренда светового оборудования",
    "Ремонт мониторов",
    "Компании по прокату оборудования",
    "Ремонт ноутбуков",
    "Компании по производству упаковки",
    "Производители продуктов питания",
    "Компании по организации туров",
    "Организация музыкальных мероприятий",
    "Студии фото и видео",
    "Онлайн-магазины аксессуаров",
    "Магазины строительных инструментов",
    "Производители мебели",
    "Магазины сантехники",
    "Студии красоты для мужчин",
    "Прокат свадебных платьев",
    "Мелкие дизайнерские услуги",
    "Спортивные клубы для подростков",
    "Магазины автозапчастей",
    "Прокат автомобилей для бизнеса",
    "Прокат мебели",
    "Производители косметики",
    "Ремонт одежды",
    "Производители текстиля",
    "Поставщики IT-услуг",
    "Дизайнеры упаковки",
    "Транспортные компании",
    "Студии по обучению танцам",
    "Ремонт одежды и текстиля",
    "Студии маникюра",
    "Офисные услуги для стартапов",
    "Мобильные сервисы",
    "Услуги по организации бизнес-поездок",
    "Услуги по разработке логотипов",
    "Студии графического дизайна",
    "Производители сувениров",
    "Прокат одежды",
    "Магазины для дома и сада",
    "Студии по созданию логотипов",
    "Студии дизайна",
    "Онлайн-сервисы по прокату техники",
    "Ремонт инструментов",
    "Магазины автозапчастей",
    "Прокат строительного оборудования",
    "Агентства по недвижимости",
    "Ремонт компьютеров",
    "Студии по разработке видеоигр",
    "Ремонт мебели",
    "Производители верхней одежды",
    "Компании по предоставлению юридических услуг",
    "Сетевые пекарни",
    "Услуги по ремонту телевизоров",
    "Школы фотографии",
    "Прокат медиаоборудования",
    "Услуги по подбору оборудования",
    "Платформы для обмена информацией",
    "Мобильные магазины",
    "Магазины электротоваров",
    "Производители газового оборудования",
    "Прокат профессиональных инструментов",
    "Услуги по ремонту двигателей",
    "Компании по монтажу и ремонту окон",
    "Спортивные клиники",
    "Магазины автомобилей",
    "Компания по организации массовых мероприятий",
    "Производители спортивного оборудования",
    "Студии звукозаписи",
    "Магазины аксессуаров для автомобилей",
    "Услуги по организации туров по городам",
    "Организация поездок за границу",
    "Продажа и аренда автомобилей",
    "Ремонт спортивного инвентаря",
    "Магазины аксессуаров для телефонов",
    "Агентства для организаций мероприятий",
    "Студии кастомизации автомобилей",
    "Студии по ремонту спортивного инвентаря",
    "Продажа комплектующих для автомобилей",
    "Услуги по декорированию домов",
    "Компании по продаже запчастей",
    "Сервисы по предоставлению медицинских услуг",
    "Студии по обучению фотографии",
    "Прокат книг",
    "Услуги по организации поездок в регионы",
    "Магазины для школы",
    "Прокат автомобилей для крупного бизнеса",
    "Специалисты по организации карнавала",
    "Производители рюкзаков",
    "Магазины для ремонта автомобилей",
    "Прокат мелкого оборудования",
    "Студии для аренды для мероприятий",
    "Разработка образовательных приложений",
    "Студии по созданию фильмов",
    "Услуги по организации чемпионатов",
    "Магазины для подготовки к учебе",
    "Производители фермерской продукции",
]


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
        self.root.title("Парсер SERM 4.0")
        try:
            self.root.iconbitmap("resources/icon.ico")
        except Exception:
            pass
        self.root.geometry("680x600")
        self.root.minsize(660, 560)

        self._log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._settings = load_settings()
        self._settings_window: ctk.CTkToplevel | None = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._captcha_event = threading.Event()
        self._captcha_whitelist_event = threading.Event()
        self._running = False
        self._autosave_job: str | None = None
        self._progress_mode = "determinate"
        self._captcha_window: ctk.CTkToplevel | None = None
        self._captcha_message_label: ctk.CTkLabel | None = None
        self._thanks_window: ctk.CTkToplevel | None = None
        self._thanks_message_label: ctk.CTkLabel | None = None
        self._thanks_qr_image: ctk.CTkImage | None = None
        self._thanks_qr_label: ctk.CTkLabel | None = None
        self._reviews_window: ctk.CTkToplevel | None = None
        self._deps_ready = False
        self._deps_error: str | None = None

        self._limit = 0
        self._lr = "120590"
        self._max_clicks = 800
        self._delay_min_s = 0.05
        self._delay_max_s = 0.15

        self._build_ui()
        self.root.after(100, self._drain_queue)
        configure_logging(self._settings.program.log_level)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_dependency_check()

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
        header.grid_columnconfigure(4, minsize=40)
        header.grid_columnconfigure(5, minsize=40)
        header.grid_columnconfigure(6, minsize=40)

        logo = ctk.CTkFrame(header, width=22, height=22, corner_radius=6, fg_color="#1f6aa5")
        logo.grid(row=0, column=0, rowspan=2, padx=(10, 10), pady=10, sticky="w")
        logo.grid_propagate(False)

        title = ctk.CTkLabel(header, text="Парсер SERM 4.0", font=ctk.CTkFont(size=22, weight="bold"))
        title.grid(row=0, column=1, padx=10, pady=(12, 0), sticky="w")

        self.subtitle_label = ctk.CTkLabel(
            header,
            text=SLOW_MODE_LABEL,
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=13),
        )
        self.subtitle_label.grid(row=1, column=1, padx=10, pady=(0, 12), sticky="w")

        self.thanks_btn = ctk.CTkButton(
            header,
            text="Спасибо ❤️",
            height=34,
            fg_color="#3c8d0d",
            hover_color="#347909",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._open_thanks_popup,
        )
        self.thanks_btn.grid(row=0, column=2, rowspan=2, padx=(0, 8), pady=10, sticky="e")

        self.telegram_btn = ctk.CTkButton(
            header,
            text="🐺 Дядя Волк",
            height=34,
            fg_color="#2b2b2b",
            hover_color="#3a3a3a",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._open_telegram,
        )
        self.telegram_btn.grid(row=0, column=3, rowspan=2, padx=(0, 8), pady=10, sticky="e")

        self.support_btn = ctk.CTkButton(
            header,
            text="🔧",
            width=34,
            height=34,
            fg_color="#2b2b2b",
            hover_color="#3a3a3a",
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._open_support_telegram,
        )
        self.support_btn.grid(row=0, column=4, rowspan=2, padx=(0, 8), pady=10, sticky="e")

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
        self.settings_btn.grid(row=0, column=5, rowspan=2, padx=(0, 8), pady=10, sticky="e")

        self.restart_btn = ctk.CTkButton(
            header,
            text="↻",
            width=34,
            height=34,
            fg_color="#6b6b6b",
            hover_color="#5d5d5d",
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._restart_app,
        )
        self.restart_btn.grid(row=0, column=6, rowspan=2, padx=(0, 10), pady=10, sticky="e")

    def _open_telegram(self) -> None:
        webbrowser.open("https://t.me/+FTIjY5WVmZU5MzYy")

    def _open_support_telegram(self) -> None:
        message = "Привет, у меня парсер не работает, сейчас скину тебе лог"
        encoded_message = quote(message)
        webbrowser.open(f"https://t.me/siente_como_odias?text={encoded_message}")

    def _open_donation_link(self) -> None:
        webbrowser.open(DONATION_URL)

    def _build_qr_image(self, size: int = 180) -> ctk.CTkImage:
        qr = qrcode.QRCode(border=1, box_size=6)
        qr.add_data(DONATION_URL)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")
        if isinstance(qr_image, Image.Image):
            pil_image = qr_image.convert("RGB")
        elif hasattr(qr_image, "get_image"):
            pil_image = qr_image.get_image().convert("RGB")
        else:
            pil_image = Image.fromarray(qr_image)
        return ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(size, size))

    def _emit_thanks_prompt(self, message: str) -> None:
        self._log_queue.put(("thanks", {"message": message}))

    def _build_top_card(self, parent: ctk.CTkFrame) -> None:
        card = ctk.CTkFrame(parent, corner_radius=14)
        card.pack(fill="x", padx=10, pady=(10, 8))
        card.grid_columnconfigure(0, weight=1)

        niche_row = ctk.CTkFrame(card, fg_color="transparent")
        niche_row.pack(fill="x", padx=10, pady=(10, 6))
        niche_row.grid_columnconfigure(0, weight=1)

        self.niche_entry = ctk.CTkEntry(niche_row, placeholder_text="Введите нишу…", height=36)
        self.niche_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.niche_random_btn = ctk.CTkButton(
            niche_row,
            text="🎲",
            width=110,
            height=36,
            command=self._randomize_niche,
        )
        self.niche_random_btn.grid(row=0, column=1, sticky="e")

        city_row = ctk.CTkFrame(card, fg_color="transparent")
        city_row.pack(fill="x", padx=10, pady=(0, 10))
        city_row.grid_columnconfigure(0, weight=1)

        self.city_entry = ctk.CTkEntry(city_row, placeholder_text="Введите город…", height=36)
        self.city_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.city_random_btn = ctk.CTkButton(
            city_row,
            text="🎲",
            width=110,
            height=36,
            command=self._randomize_city,
        )
        self.city_random_btn.grid(row=0, column=1, sticky="e")

        self.mode_var = ctk.StringVar(value=SLOW_MODE_LABEL)
        mode_row = ctk.CTkFrame(card, fg_color="transparent")
        mode_row.pack(fill="x", padx=10, pady=(0, 4))
        mode_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(mode_row, text="Режим", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0,
            column=0,
            padx=(0, 10),
            sticky="w",
        )
        mode_switch = ctk.CTkSegmentedButton(
            mode_row,
            values=[SLOW_MODE_LABEL, FAST_MODE_LABEL],
            variable=self.mode_var,
            command=self._on_mode_change,
        )
        mode_switch.grid(row=0, column=1, sticky="ew")

        self._sync_mode_label()

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
            text="Запустить",
            height=40,
            fg_color="#4CAF50",
            hover_color="#43A047",
            command=self._on_start,
        )
        self.start_btn.grid(row=0, column=0, padx=(0, 8), pady=(0, 10), sticky="ew")

        self.stop_btn = ctk.CTkButton(
            btns,
            text="Стоп",
            height=40,
            fg_color="#ff5555",
            hover_color="#ff3b3b",
            command=self._on_stop,
        )
        self.stop_btn.grid(row=0, column=1, padx=(8, 0), pady=(0, 10), sticky="ew")

        self.pause_btn = ctk.CTkButton(
            btns,
            text="Пауза",
            height=40,
            fg_color="#3d3d3d",
            hover_color="#4a4a4a",
            command=self._on_pause,
        )
        self.pause_btn.grid(row=1, column=0, padx=(0, 8), pady=(0, 10), sticky="ew")

        self.resume_btn = ctk.CTkButton(
            btns,
            text="Пуск",
            height=40,
            fg_color="#3d3d3d",
            hover_color="#4a4a4a",
            command=self._on_resume,
        )
        self.resume_btn.grid(row=1, column=1, padx=(8, 0), pady=(0, 10), sticky="ew")

        self.reviews_btn = ctk.CTkButton(
            btns,
            text="Отзывы",
            height=40,
            fg_color="#3d3d3d",
            hover_color="#4a4a4a",
            command=self._open_reviews_prompt,
        )
        self.reviews_btn.grid(row=2, column=0, padx=(0, 8), sticky="ew")

        self.results_btn = ctk.CTkButton(
            btns,
            text="Результаты",
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
        self.mode_var.set(SLOW_MODE_LABEL)
        self._sync_mode_label()
        self._set_status("Ожидание", "#666666")
        self._set_progress_mode("determinate")
        self._set_progress(0.0)
        self._clear_log()

    def _on_mode_change(self, _value: str) -> None:
        self._sync_mode_label()

    def _sync_mode_label(self) -> None:
        if hasattr(self, "subtitle_label"):
            self.subtitle_label.configure(text=self.mode_var.get())

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _set_entry_value(self, entry: ctk.CTkEntry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)

    def _randomize_niche(self) -> None:
        if not NICHES:
            return
        self._set_entry_value(self.niche_entry, random.choice(NICHES))

    def _randomize_city(self) -> None:
        if not CITIES:
            return
        self._set_entry_value(self.city_entry, random.choice(CITIES))

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.configure(text=text)
        self.status_dot.configure(text_color=color)

    def _set_progress(self, value: float) -> None:
        self.progress.set(max(0.0, min(1.0, value)))

    def _set_progress_mode(self, mode: str) -> None:
        mode = mode if mode in ("determinate", "indeterminate") else "determinate"
        self._progress_mode = mode
        self.progress.configure(mode=mode)
        if mode == "indeterminate":
            self.progress.start()
        else:
            self.progress.stop()

    def _finish_progress(self) -> None:
        self.progress.stop()
        self.progress.set(1.0)

    def _append_log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _should_show_log(self, level: str) -> bool:
        level_name = (level or "info").lower()
        current_level = (self._settings.program.log_level or "info").lower()
        return LOG_LEVEL_ORDER.get(level_name, 20) >= LOG_LEVEL_ORDER.get(current_level, 20)

    def _log(self, message: str, level: str = "info") -> None:
        if not self._should_show_log(level):
            return
        self._log_queue.put(("log", (level, message)))

    def _emit_progress(self, payload: dict) -> None:
        self._log_queue.put(("progress", payload))

    def _emit_captcha_prompt(self, payload: dict) -> None:
        self._log_queue.put(("captcha", payload))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._log_queue.get_nowait()
                if kind == "log":
                    if isinstance(payload, tuple):
                        _, message = payload
                        self._append_log(str(message))
                    else:
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
                elif kind == "progress_done":
                    self._finish_progress()
                elif kind == "state":
                    self._set_running(bool(payload))
                elif kind == "deps_state":
                    if isinstance(payload, dict):
                        self._handle_dependencies_state(payload)
                elif kind == "captcha":
                    if isinstance(payload, dict):
                        self._handle_captcha_event(payload)
                elif kind == "thanks":
                    if isinstance(payload, dict):
                        self._open_thanks_popup(payload.get("message", THANKS_MESSAGE))
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

    def _handle_captcha_event(self, payload: dict) -> None:
        stage = str(payload.get("stage", ""))
        message = str(payload.get("message", ""))
        if stage == "cleared":
            self._close_captcha_prompt()
            return
        if stage in {"detected", "manual", "still"}:
            self._open_captcha_prompt(
                message
                or "Капча, реши руками и продолжим. Если зависла — нажми F5 или кнопку ниже."
            )

    def _open_captcha_prompt(self, message: str) -> None:
        if self._captcha_window and self._captcha_window.winfo_exists():
            if self._captcha_message_label:
                self._captcha_message_label.configure(text=message)
            return

        self._captcha_window = ctk.CTkToplevel(self.root)
        self._captcha_window.title("Капча")
        self._captcha_window.geometry("420x240")
        self._captcha_window.resizable(False, False)
        self._captcha_window.transient(self.root)
        self._captcha_window.grab_set()
        self._captcha_window.attributes("-topmost", True)
        try:
            self._captcha_window.lift()
            self._captcha_window.focus_force()
        except Exception:
            pass

        container = ctk.CTkFrame(self._captcha_window, corner_radius=14)
        container.pack(fill="both", expand=True, padx=16, pady=16)
        container.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            container,
            text="🧩 Капча",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", pady=(8, 6), padx=12)

        self._captcha_message_label = ctk.CTkLabel(
            container,
            text=message,
            font=ctk.CTkFont(size=13),
            justify="left",
            wraplength=360,
        )
        self._captcha_message_label.grid(row=1, column=0, sticky="w", padx=12)

        auto_label = ctk.CTkLabel(
            container,
            text="Мы автоматически проверяем, как только капча решена — продолжим.",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=12),
            justify="left",
            wraplength=360,
        )
        auto_label.grid(row=2, column=0, sticky="w", padx=12, pady=(12, 8))

        stuck_btn = ctk.CTkButton(
            container,
            text="Капча зависла",
            command=self._on_captcha_stuck,
        )
        stuck_btn.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))

        close_btn = ctk.CTkButton(
            container,
            text="Закрыть",
            command=self._abort_captcha,
            fg_color="#ff5555",
            hover_color="#ff3b3b",
        )
        close_btn.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

        self._captcha_window.protocol("WM_DELETE_WINDOW", lambda: None)

    def _abort_captcha(self) -> None:
        self._on_close()

    def _on_captcha_stuck(self) -> None:
        self._captcha_whitelist_event.set()
        self._log("🧩 Капча зависла: открываю доверенные ссылки Яндекса.")

    def _close_captcha_prompt(self) -> None:
        if self._captcha_window and self._captcha_window.winfo_exists():
            try:
                self._captcha_window.grab_release()
            except Exception:
                pass
            self._captcha_window.destroy()
        self._captcha_window = None
        self._captcha_message_label = None

    def _close_thanks_popup(self) -> None:
        if self._thanks_window and self._thanks_window.winfo_exists():
            self._thanks_window.destroy()
        self._thanks_window = None
        self._thanks_message_label = None
        self._thanks_qr_label = None

    def _open_thanks_popup(self, message: str | None = None) -> None:
        popup_message = message or THANKS_MESSAGE
        if self._thanks_window and self._thanks_window.winfo_exists():
            if self._thanks_message_label:
                self._thanks_message_label.configure(text=popup_message)
            return

        self._thanks_window = ctk.CTkToplevel(self.root)
        self._thanks_window.title("Спасибо ❤️")
        self._thanks_window.geometry("480x520")
        self._thanks_window.resizable(False, False)
        self._thanks_window.transient(self.root)
        self._thanks_window.grab_set()
        self._thanks_window.attributes("-topmost", True)
        self._thanks_window.protocol("WM_DELETE_WINDOW", self._close_thanks_popup)
        try:
            self._thanks_window.lift()
            self._thanks_window.focus_force()
        except Exception:
            pass

        container = ctk.CTkFrame(self._thanks_window, corner_radius=14)
        container.pack(fill="both", expand=True, padx=16, pady=16)
        container.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            container,
            text="Спасибо ❤️",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", pady=(8, 6), padx=12)

        self._thanks_message_label = ctk.CTkLabel(
            container,
            text=popup_message,
            font=ctk.CTkFont(size=15),
            justify="left",
            wraplength=420,
        )
        self._thanks_message_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))

        if self._thanks_qr_image is None:
            self._thanks_qr_image = self._build_qr_image()

        self._thanks_qr_label = ctk.CTkLabel(container, image=self._thanks_qr_image, text="")
        self._thanks_qr_label.grid(row=2, column=0, pady=(0, 8))

        phone_label = ctk.CTkLabel(
            container,
            text=f"Телефон: {DONATION_PHONE}",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        phone_label.grid(row=3, column=0, pady=(0, 18))

        thanks_btn = ctk.CTkButton(
            container,
            text="Спасибо",
            fg_color="#3c8d0d",
            hover_color="#347909",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
            command=self._open_donation_link,
        )
        thanks_btn.grid(row=4, column=0, sticky="ew", padx=12)

    def _output_paths(self, query: str) -> tuple[Path, Path]:
        niche = self.niche_entry.get().strip()
        city = self.city_entry.get().strip()
        if not niche and not city:
            niche, city = split_query(query)
        return build_result_paths(niche=niche, city=city, results_dir=RESULTS_DIR)

    def _start_dependency_check(self) -> None:
        self._deps_ready = False
        self._deps_error = None
        self._set_status("Проверяю зависимости…", "#fbc02d")
        self._set_progress_mode("indeterminate")
        self._set_progress(0.0)
        self.start_btn.configure(state="disabled")
        worker = threading.Thread(target=self._dependency_worker, daemon=True)
        worker.start()

    def _dependency_worker(self) -> None:
        try:
            modules = _parse_required_modules(REQUIREMENTS_FILE)
            missing = _missing_modules(modules)
            if missing:
                self._log_queue.put(("log", ("info", f"📦 Устанавливаю зависимости: {', '.join(missing)}")))
            else:
                self._log_queue.put(("log", ("info", "✅ Зависимости уже установлены.")))
            ensure_dependencies()
            self._log_queue.put(("deps_state", {"ready": True}))
        except Exception as exc:
            self._log_queue.put(("log", ("error", f"❌ Ошибка установки зависимостей: {exc}")))
            self._log_queue.put(("deps_state", {"ready": False, "error": str(exc)}))

    def _handle_dependencies_state(self, payload: dict) -> None:
        ready = bool(payload.get("ready", False))
        self._deps_ready = ready
        self._deps_error = payload.get("error") if not ready else None
        if ready:
            self._set_status("Ожидание", "#666666")
            self._set_progress_mode("determinate")
            self._set_progress(0.0)
            self._log("✅ Зависимости готовы.")
        else:
            self._set_status("Ошибка зависимостей", "#ff5555")
            self._set_progress_mode("determinate")
            self._set_progress(0.0)
        self._set_running(self._running)

    def _set_running(self, running: bool) -> None:
        self._running = running
        state = "disabled" if running else "normal"
        self.start_btn.configure(state="normal" if not running and self._deps_ready else "disabled")
        if hasattr(self, "reviews_btn"):
            review_state = "normal" if not running and self._deps_ready else "disabled"
            self.reviews_btn.configure(state=review_state)
        self.pause_btn.configure(state="normal" if running else "disabled")
        self.resume_btn.configure(state="normal" if running else "disabled")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.settings_btn.configure(state=state)
        self.restart_btn.configure(state=state)

    def _restart_app(self) -> None:
        if self._running:
            return
        self._set_status("Перезапуск...", "#3c8d0d")
        self._log("🔁 Перезапуск приложения...")
        self.root.after(100, self._perform_restart)

    def _perform_restart(self) -> None:
        python = sys.executable
        args = [python, *sys.argv]
        try:
            subprocess.Popen(args, close_fds=True)
        finally:
            self.root.destroy()
            os._exit(0)

    def _open_settings(self) -> None:
        if self._running:
            self._log("⚠️ Останови парсер перед настройками.", level="warning")
            return
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.focus()
            return

        window = ctk.CTkToplevel(self.root)
        window.title("Настройки")
        window.geometry("560x720")
        window.resizable(False, False)
        window.grab_set()

        self._settings_window = window

        def _on_close() -> None:
            self._apply_settings_from_vars(vars_map)
            if not self._settings.program.autosave_settings:
                self._save_settings(log_message="💾 Настройки сохранены.")
            window.grab_release()
            window.destroy()
            self._settings_window = None

        window.protocol("WM_DELETE_WINDOW", _on_close)

        body = ctk.CTkScrollableFrame(window, corner_radius=14)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.grid_columnconfigure(0, weight=1)

        filters = self._settings.potential_filters
        program = self._settings.program
        notifications = self._settings.notifications

        exclude_no_phone_var = ctk.BooleanVar(value=filters.exclude_no_phone)
        exclude_blue_checkmark_var = ctk.BooleanVar(value=filters.exclude_blue_checkmark)
        exclude_green_checkmark_var = ctk.BooleanVar(value=filters.exclude_green_checkmark)
        exclude_good_place_var = ctk.BooleanVar(value=filters.exclude_good_place)
        exclude_noncommercial_var = ctk.BooleanVar(value=filters.exclude_noncommercial)
        max_rating_default = "Без ограничений" if filters.max_rating is None else f"{filters.max_rating:.1f}"
        max_rating_var = ctk.StringVar(value=max_rating_default)
        stop_words_var = ctk.StringVar(value=filters.stop_words)
        white_list_var = ctk.StringVar(value=filters.white_list)

        headless_var = ctk.BooleanVar(value=program.headless)
        block_images_var = ctk.BooleanVar(value=program.block_images)
        open_result_var = ctk.BooleanVar(value=program.open_result)
        log_level_var = ctk.StringVar(
            value=LOG_LEVEL_LABELS_REVERSE.get(program.log_level, "Обычные (рекомендуется)")
        )
        autosave_var = ctk.BooleanVar(value=program.autosave_settings)

        finish_sound_var = ctk.BooleanVar(value=notifications.on_finish)
        captcha_sound_var = ctk.BooleanVar(value=notifications.on_captcha)
        error_sound_var = ctk.BooleanVar(value=notifications.on_error)
        autosave_sound_var = ctk.BooleanVar(value=notifications.on_autosave)

        vars_map = {
            "exclude_no_phone": exclude_no_phone_var,
            "exclude_blue_checkmark": exclude_blue_checkmark_var,
            "exclude_green_checkmark": exclude_green_checkmark_var,
            "exclude_good_place": exclude_good_place_var,
            "exclude_noncommercial": exclude_noncommercial_var,
            "max_rating": max_rating_var,
            "stop_words": stop_words_var,
            "white_list": white_list_var,
            "headless": headless_var,
            "block_images": block_images_var,
            "open_result": open_result_var,
            "log_level": log_level_var,
            "autosave_settings": autosave_var,
            "sound_finish": finish_sound_var,
            "sound_captcha": captcha_sound_var,
            "sound_error": error_sound_var,
            "sound_autosave": autosave_sound_var,
        }

        def _on_change(*_args) -> None:
            self._apply_settings_from_vars(vars_map)
            self._maybe_autosave()

        row = 0
        ctk.CTkLabel(body, text="Фильтры для POTENTIAL", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, sticky="w", padx=10, pady=(6, 2)
        )
        row += 1
        ctk.CTkLabel(
            body,
            text="FULL сохраняется всегда, фильтры применяются только к potential.",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=12),
        ).grid(row=row, column=0, sticky="w", padx=10, pady=(0, 6))
        row += 1

        ctk.CTkCheckBox(body, text="Не сохранять без телефона", variable=exclude_no_phone_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1
        ctk.CTkCheckBox(
            body, text="Не сохранять с синей галочкой", variable=exclude_blue_checkmark_var
        ).grid(row=row, column=0, sticky="w", padx=10, pady=4)
        row += 1
        ctk.CTkCheckBox(
            body, text="Не сохранять с зелёной галочкой", variable=exclude_green_checkmark_var
        ).grid(row=row, column=0, sticky="w", padx=10, pady=4)
        row += 1
        ctk.CTkCheckBox(body, text="Исключать «Хорошее место»", variable=exclude_good_place_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1
        ctk.CTkCheckBox(body, text="Исключать некоммерческие", variable=exclude_noncommercial_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1

        rating_values = ["Без ограничений", "5.0", "4.7", "4.4"]
        rating_row = ctk.CTkFrame(body, fg_color="transparent")
        rating_row.grid(row=row, column=0, sticky="ew", padx=10, pady=(6, 4))
        rating_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(rating_row, text="Максимальный рейтинг").grid(row=0, column=0, sticky="w")
        ctk.CTkOptionMenu(rating_row, variable=max_rating_var, values=rating_values).grid(
            row=0, column=1, sticky="e"
        )
        row += 1

        ctk.CTkLabel(body, text="Стоп-слова (через запятую)").grid(
            row=row, column=0, sticky="w", padx=10, pady=(8, 2)
        )
        row += 1
        ctk.CTkEntry(body, textvariable=stop_words_var).grid(
            row=row, column=0, sticky="ew", padx=10, pady=(0, 6)
        )
        row += 1

        ctk.CTkLabel(body, text="Белый список (если задан — пропускать только их)").grid(
            row=row, column=0, sticky="w", padx=10, pady=(6, 2)
        )
        row += 1
        ctk.CTkEntry(body, textvariable=white_list_var).grid(
            row=row, column=0, sticky="ew", padx=10, pady=(0, 10)
        )
        row += 1

        ctk.CTkLabel(body, text="Настройки программы", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, sticky="w", padx=10, pady=(10, 2)
        )
        row += 1

        ctk.CTkCheckBox(body, text="Запускать в фоне (без окна)", variable=headless_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1
        ctk.CTkCheckBox(body, text="Не загружать изображения", variable=block_images_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1
        ctk.CTkCheckBox(body, text="Открывать результат после завершения", variable=open_result_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1

        def _open_browser() -> None:
            def _run() -> None:
                try:
                    with sync_playwright() as p:
                        block_images = bool(block_images_var.get())
                        block_media = False
                        browser = launch_chrome(
                            p,
                            headless=False,
                            args=PLAYWRIGHT_LAUNCH_ARGS,
                        )
                        context = browser.new_context(
                            user_agent=PLAYWRIGHT_USER_AGENT,
                            viewport=PLAYWRIGHT_VIEWPORT,
                            is_mobile=False,
                            has_touch=False,
                            device_scale_factor=1,
                        )
                        setup_resource_blocking(context, block_images, block_media)
                        page = context.new_page()
                        page.goto("about:blank")
                        browser.wait_for_event("disconnected")
                except Exception as exc:
                    if is_chrome_missing_error(exc):
                        self._log(chrome_not_found_message(), level="warning")
                        return
                    self._log(
                        "⚠️ Не удалось открыть Playwright-браузер, открываю системный.",
                        level="warning",
                    )
                    webbrowser.open("about:blank")

            threading.Thread(target=_run, daemon=True).start()

        ctk.CTkButton(body, text="Открыть браузер", command=_open_browser).grid(
            row=row, column=0, sticky="w", padx=10, pady=(6, 10)
        )
        row += 1

        log_row = ctk.CTkFrame(body, fg_color="transparent")
        log_row.grid(row=row, column=0, sticky="ew", padx=10, pady=(6, 4))
        log_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(log_row, text="Какие логи показывать").grid(row=0, column=0, sticky="w")
        ctk.CTkOptionMenu(log_row, variable=log_level_var, values=list(LOG_LEVEL_LABELS.keys())).grid(
            row=0, column=1, sticky="e"
        )
        row += 1

        ctk.CTkCheckBox(body, text="Автосохранение настроек", variable=autosave_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=(6, 10)
        )
        row += 1

        ctk.CTkLabel(body, text="Уведомления", font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, sticky="w", padx=10, pady=(10, 2)
        )
        row += 1
        ctk.CTkLabel(
            body,
            text="Показывать звук при важных событиях.",
            text_color=("gray35", "gray70"),
            font=ctk.CTkFont(size=12),
        ).grid(row=row, column=0, sticky="w", padx=10, pady=(0, 6))
        row += 1

        ctk.CTkCheckBox(body, text="При завершении", variable=finish_sound_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1
        ctk.CTkCheckBox(body, text="При капче", variable=captcha_sound_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1
        ctk.CTkCheckBox(body, text="При ошибке", variable=error_sound_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1
        ctk.CTkCheckBox(body, text="При автосейве", variable=autosave_sound_var).grid(
            row=row, column=0, sticky="w", padx=10, pady=4
        )
        row += 1

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.grid(row=row, column=0, sticky="ew", padx=10, pady=(12, 12))
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)

        def _on_apply() -> None:
            self._apply_settings_from_vars(vars_map)
            self._save_settings(log_message="⚙️ Настройки сохранены.")
            _on_close()

        ctk.CTkButton(btns, text="Сохранить настройки", command=_on_apply).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ctk.CTkButton(btns, text="Закрыть", fg_color="#3d3d3d", hover_color="#4a4a4a", command=_on_close).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )

        for var in vars_map.values():
            var.trace_add("write", _on_change)

    def _apply_settings_from_vars(self, vars_map: dict) -> None:
        filters = self._settings.potential_filters
        program = self._settings.program
        notifications = self._settings.notifications

        filters.exclude_no_phone = bool(vars_map["exclude_no_phone"].get())
        filters.exclude_blue_checkmark = bool(vars_map["exclude_blue_checkmark"].get())
        filters.exclude_green_checkmark = bool(vars_map["exclude_green_checkmark"].get())
        filters.exclude_good_place = bool(vars_map["exclude_good_place"].get())
        filters.exclude_noncommercial = bool(vars_map["exclude_noncommercial"].get())
        rating_value = vars_map["max_rating"].get()
        if rating_value == "Без ограничений":
            filters.max_rating = None
        else:
            try:
                filters.max_rating = float(str(rating_value).replace(",", "."))
            except Exception:
                filters.max_rating = None
        filters.stop_words = str(vars_map["stop_words"].get() or "").strip()
        filters.white_list = str(vars_map["white_list"].get() or "").strip()

        program.headless = bool(vars_map["headless"].get())
        program.block_images = bool(vars_map["block_images"].get())
        program.block_media = False
        program.open_result = bool(vars_map["open_result"].get())
        log_label = str(vars_map["log_level"].get() or "Обычные (рекомендуется)")
        program.log_level = LOG_LEVEL_LABELS.get(log_label, "info")
        program.autosave_settings = bool(vars_map["autosave_settings"].get())

        notifications.on_finish = bool(vars_map["sound_finish"].get())
        notifications.on_captcha = bool(vars_map["sound_captcha"].get())
        notifications.on_error = bool(vars_map["sound_error"].get())
        notifications.on_autosave = bool(vars_map["sound_autosave"].get())

        configure_logging(program.log_level)

    def _maybe_autosave(self) -> None:
        if not self._settings.program.autosave_settings:
            if self._autosave_job is not None:
                self.root.after_cancel(self._autosave_job)
                self._autosave_job = None
            return
        if self._autosave_job is not None:
            self.root.after_cancel(self._autosave_job)
        self._autosave_job = self.root.after(300, self._autosave_settings)

    def _autosave_settings(self) -> None:
        self._autosave_job = None
        self._save_settings(log_message="💾 Настройки автосохранены.")
        notify_sound("autosave", self._settings)

    def _save_settings(self, log_message: str | None = None) -> None:
        save_settings(self._settings)
        if log_message:
            self._log(log_message)

    def _on_close(self) -> None:
        if self._running:
            self._on_stop()
            worker = self._worker
            if worker and worker.is_alive():
                self._log("⏳ Завершаю фоновые процессы...")
                worker.join(timeout=10)
                if worker.is_alive():
                    self._log("⚠️ Не удалось дождаться завершения фоновых процессов.", level="warning")
        if self._autosave_job is not None:
            self.root.after_cancel(self._autosave_job)
            self._autosave_job = None
            self._save_settings(log_message="💾 Настройки сохранены.")
        elif not self._settings.program.autosave_settings:
            self._save_settings(log_message="💾 Настройки сохранены.")
        self.root.destroy()

    def _on_start(self) -> None:
        if self._running:
            return
        if not self._deps_ready:
            message = "⏳ Дождись проверки зависимостей перед запуском."
            if self._deps_error:
                message = f"❌ Зависимости не установлены: {self._deps_error}"
            self._log(message, level="warning")
            return
        query = self._build_query()
        if not query:
            self._log("⚠️ Укажи нишу и/или город.", level="warning")
            return

        mode = self.mode_var.get()
        output_path, results_folder = self._output_paths(query)

        self._stop_event.clear()
        self._pause_event.clear()
        self._captcha_event.clear()
        self._captcha_whitelist_event.clear()
        self._set_running(True)
        self._set_status("Запуск…", "#4CAF50")
        if mode == FAST_MODE_LABEL:
            self._set_progress_mode("determinate")
            self._set_progress(0.0)
        else:
            self._set_progress_mode("indeterminate")
        configure_logging(self._settings.program.log_level, full_log_path=results_folder / "log.txt")

        worker = threading.Thread(
            target=self._run_worker,
            args=(mode, query, output_path, results_folder),
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
        self._close_captcha_prompt()
        self._log("▶ Продолжаю.")
        self._set_status("Работаю", "#4CAF50")

    def _on_stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        self._pause_event.clear()
        self._captcha_event.set()
        self._close_captcha_prompt()
        self._log("🛑 Остановлено пользователем.")
        self._set_status("Остановка…", "#ff5555")

    def _open_results_dir(self) -> None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        _safe_open_path(RESULTS_DIR)

    def _paste_from_clipboard(self, entry: ctk.CTkEntry) -> None:
        text = ""
        try:
            text = entry.clipboard_get()
        except Exception:
            try:
                text = self.root.clipboard_get()
            except Exception:
                text = ""
        if text:
            entry.insert("insert", text)

    def _bind_paste_shortcuts(self, entry: ctk.CTkEntry) -> None:
        entry.bind("<Control-v>", lambda _event: self._paste_from_clipboard(entry), add="+")
        entry.bind("<Control-V>", lambda _event: self._paste_from_clipboard(entry), add="+")
        entry.bind("<Command-v>", lambda _event: self._paste_from_clipboard(entry), add="+")
        entry.bind("<Command-V>", lambda _event: self._paste_from_clipboard(entry), add="+")

    def _open_reviews_prompt(self) -> None:
        if self._running:
            return
        if not self._deps_ready:
            message = "⏳ Дождись проверки зависимостей перед запуском."
            if self._deps_error:
                message = f"❌ Зависимости не установлены: {self._deps_error}"
            self._log(message, level="warning")
            return
        if self._reviews_window is not None and self._reviews_window.winfo_exists():
            self._reviews_window.focus()
            return

        window = ctk.CTkToplevel(self.root)
        window.title("Отзывы")
        window.geometry("520x200")
        window.resizable(False, False)
        window.grab_set()

        container = ctk.CTkFrame(window, corner_radius=12)
        container.pack(fill="both", expand=True, padx=16, pady=16)
        container.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(
            container,
            text="Вставь ссылку на организацию в Яндекс.Картах",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        label.grid(row=0, column=0, sticky="w", pady=(0, 8))

        entry = ctk.CTkEntry(
            container,
            placeholder_text="https://yandex.ru/maps/...",
            height=36,
        )
        entry.grid(row=1, column=0, sticky="ew")
        self._bind_paste_shortcuts(entry)
        entry.focus_set()

        paste_btn = ctk.CTkButton(
            container,
            text="Вставить",
            height=32,
            fg_color="#3d3d3d",
            hover_color="#4a4a4a",
            command=lambda: self._paste_from_clipboard(entry),
        )
        paste_btn.grid(row=2, column=0, pady=(8, 0), sticky="w")

        buttons = ctk.CTkFrame(container, fg_color="transparent")
        buttons.grid(row=3, column=0, pady=(12, 0), sticky="ew")
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        def handle_start() -> None:
            url = entry.get().strip()
            if not url:
                self._log("⚠️ Укажи ссылку на организацию.", level="warning")
                return
            self._close_reviews_prompt()
            self._start_reviews(url)

        start_btn = ctk.CTkButton(
            buttons,
            text="Запустить",
            height=36,
            fg_color="#4CAF50",
            hover_color="#43A047",
            command=handle_start,
        )
        start_btn.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        cancel_btn = ctk.CTkButton(
            buttons,
            text="Отмена",
            height=36,
            fg_color="#3d3d3d",
            hover_color="#4a4a4a",
            command=self._close_reviews_prompt,
        )
        cancel_btn.grid(row=0, column=1, padx=(8, 0), sticky="ew")

        entry.bind("<Return>", lambda _event: handle_start())
        window.protocol("WM_DELETE_WINDOW", self._close_reviews_prompt)
        self._reviews_window = window

    def _close_reviews_prompt(self) -> None:
        if self._reviews_window is None:
            return
        if self._reviews_window.winfo_exists():
            self._reviews_window.destroy()
        self._reviews_window = None

    def _run_worker(
        self,
        mode: str,
        query: str,
        output_path: Path,
        results_folder: Path,
    ) -> None:
        self._log_queue.put(("status", ("Работаю", "#4CAF50")))
        try:
            if mode == FAST_MODE_LABEL:
                self._run_fast(query, output_path, results_folder)
            else:
                self._run_slow(query, output_path, results_folder)
        except Exception as exc:
            self._log(f"❌ Ошибка: {exc}", level="error")
            notify_sound("error", self._settings)
        finally:
            self._log_queue.put(("status", ("Готово", "#666666")))
            self._log_queue.put(("progress_done", None))
            self._log_queue.put(("state", False))

    def _reviews_output_path(self) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder = RESULTS_DIR / "reviews"
        return folder / f"reviews_{timestamp}.xlsx"

    def _start_reviews(self, url: str) -> None:
        if self._running:
            return
        if not self._deps_ready:
            message = "⏳ Дождись проверки зависимостей перед запуском."
            if self._deps_error:
                message = f"❌ Зависимости не установлены: {self._deps_error}"
            self._log(message, level="warning")
            return
        if not url:
            self._log("⚠️ Укажи ссылку на организацию.", level="warning")
            return
        output_path = self._reviews_output_path()

        self._stop_event.clear()
        self._pause_event.clear()
        self._captcha_event.clear()
        self._set_running(True)
        self._set_status("Отзывы: запуск…", "#4CAF50")
        self._set_progress_mode("determinate")
        self._set_progress(0.0)
        configure_logging(self._settings.program.log_level, full_log_path=output_path.parent / "log_reviews.txt")

        worker = threading.Thread(
            target=self._run_reviews_worker,
            args=(url, output_path),
            daemon=True,
        )
        self._worker = worker
        worker.start()

    def _run_reviews_worker(self, url: str, output_path: Path) -> None:
        from app.reviews_excel_writer import ReviewsExcelWriter
        from app.reviews_parser import YandexReviewsParser

        self._log_queue.put(("status", ("Отзывы: работаю", "#4CAF50")))
        writer = ReviewsExcelWriter(output_path)
        count = 0
        total = 0
        try:
            def captcha_message(stage: str) -> str:
                if stage == "still":
                    return "⚠️ Капча всё ещё активна. Реши её, я продолжаю проверять."
                if stage == "manual":
                    return "🧩 Капча снова появилась. Реши её руками, я продолжу автоматически."
                return "🧩 Реши капчу, я сам проверю и продолжу."

            def captcha_hook(stage: str, _page: object) -> None:
                if stage == "cleared":
                    self._emit_captcha_prompt({"stage": stage})
                    return
                if stage == "detected" and self._settings.program.headless:
                    return
                if stage in {"detected", "manual", "still"}:
                    self._emit_captcha_prompt({"stage": stage, "message": captcha_message(stage)})

            parser = YandexReviewsParser(
                url=url,
                headless=self._settings.program.headless,
                block_images=self._settings.program.block_images,
                block_media=self._settings.program.block_media,
                stop_event=self._stop_event,
                pause_event=self._pause_event,
                captcha_resume_event=self._captcha_event,
                captcha_hook=captcha_hook,
                log=self._log,
            )
            for review in parser.run():
                if self._stop_event.is_set():
                    break
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.1)
                if parser.total_reviews and total == 0:
                    total = parser.total_reviews
                writer.append(review)
                count += 1
                if total:
                    self._emit_progress({"total": total, "index": count})
        except Exception as exc:
            self._log(f"❌ Ошибка: {exc}", level="error")
            notify_sound("error", self._settings)
        finally:
            writer.close()
            self._log_queue.put(("progress_done", None))
            self._log_queue.put(("state", False))
            self._log_queue.put(("status", ("Готово", "#666666")))

        if not self._stop_event.is_set():
            self._log(f"📄 Отзывы сохранены: {output_path.name}")
            notify_sound("finish", self._settings)
            _safe_open_path(output_path)

    def _run_slow(
        self,
        query: str,
        output_path: Path,
        results_folder: Path,
    ) -> None:
        from app.pacser_maps import YandexMapsScraper

        self._log("🐢 подробный: Яндекс Карты.")
        def captcha_message(stage: str) -> str:
            if stage == "still":
                return "⚠️ Капча всё ещё активна. Реши её, я продолжаю проверять."
            if stage == "manual":
                return "🧩 Капча снова появилась. Реши её руками, я продолжу автоматически."
            return "🧩 Реши капчу, я сам проверю и продолжу. Если зависла — нажми кнопку ниже."

        def captcha_hook(stage: str, _page: object) -> None:
            if stage == "cleared":
                self._emit_captcha_prompt({"stage": stage})
                return
            if stage == "detected" and self._settings.program.headless:
                return
            if stage in {"detected", "manual", "still"}:
                self._emit_captcha_prompt({"stage": stage, "message": captcha_message(stage)})

        scraper = YandexMapsScraper(
            query=query,
            limit=self._limit if self._limit > 0 else None,
            headless=self._settings.program.headless,
            block_images=self._settings.program.block_images,
            block_media=self._settings.program.block_media,
            stop_event=self._stop_event,
            pause_event=self._pause_event,
            captcha_resume_event=self._captcha_event,
            captcha_whitelist_event=self._captcha_whitelist_event,
            captcha_hook=captcha_hook,
            log=self._log,
        )
        writer = ExcelWriter(output_path)
        count = 0
        try:
            for org in scraper.run():
                if self._stop_event.is_set():
                    break
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.1)
                include = passes_potential_filters(org, self._settings)
                writer.append(org, include_in_potential=include)
                count += 1
                if count % 10 == 0:
                    self._log(f"✅ Сохранено организаций: {count}")
        finally:
            writer.close()

        if not self._stop_event.is_set():
            self._log(f"📄 Файл сохранён: {output_path.name}")
            notify_sound("finish", self._settings)
            if self._settings.program.open_result:
                _safe_open_path(results_folder)
            if count > 20:
                self._emit_thanks_prompt(POST_PARSE_MESSAGE)

    def _run_fast(
        self,
        query: str,
        output_path: Path,
        results_folder: Path,
    ) -> None:
        from app.parser_search import run_fast_parser

        def captcha_message(stage: str) -> str:
            if stage == "still":
                return "⚠️ Капча всё ещё активна. Реши её, я продолжаю проверять."
            if stage == "manual":
                return "🧩 Капча снова появилась. Реши её руками, я продолжу автоматически."
            return "🧩 Реши капчу, я сам проверю и продолжу. Если зависла — нажми кнопку ниже."

        def captcha_hook(stage: str, _page: object) -> None:
            if stage == "cleared":
                self._emit_captcha_prompt({"stage": stage})
                return
            if stage == "detected" and self._settings.program.headless:
                return
            if stage in {"detected", "manual", "still"}:
                self._emit_captcha_prompt({"stage": stage, "message": captcha_message(stage)})

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
            lr=self._lr,
            max_clicks=self._max_clicks,
            delay_min_s=self._delay_min_s,
            delay_max_s=self._delay_max_s,
            stop_event=self._stop_event,
            pause_event=self._pause_event,
            captcha_resume_event=self._captcha_event,
            captcha_whitelist_event=self._captcha_whitelist_event,
            log=self._log,
            progress=progress_cb,
            captcha_hook=captcha_hook,
            settings=self._settings,
        )

        if not self._stop_event.is_set():
            self._log(f"⚡ {FAST_MODE_LABEL} завершён. Записано: {count}")
            notify_sound("finish", self._settings)
            if self._settings.program.open_result:
                _safe_open_path(results_folder)
            if count > 20:
                self._emit_thanks_prompt(POST_PARSE_MESSAGE)

    def run(self) -> None:
        self._set_running(False)
        self.root.mainloop()


def main() -> None:
    app = ParserGUI()
    app.run()


if __name__ == "__main__":
    main()
