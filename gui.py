"""GUI для запуска «быстрый» (поиск) и «подробный» (карты) парсера."""

from __future__ import annotations

import io
import os
import platform
import queue
import random
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

import qrcode
from PIL import Image
from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from excel_writer import ExcelWriter
from filters import passes_potential_filters
from notifications import notify_sound
from pacser_maps import YandexMapsScraper
from parser_search import run_fast_parser
from settings_store import load_settings, save_settings
from utils import build_result_paths, configure_logging, split_query

RESULTS_DIR = Path(__file__).resolve().parent / "results"
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
    "Онлайн-курсы",
    "Школы программирования",
    "Языковые курсы",
    "Детские сады",
    "Школы",
    "Курсы подготовки к экзаменам",
    "Фрилансеры",
    "Маркетинговые агентства",
    "Рекламные агентства",
    "Службы доставки",
    "Пекарни",
    "Кондитерские",
    "Фермерские рынки",
    "Медицинские клиники",
    "Психологи",
    "Лаборатории",
    "Фармацевтические компании",
    "Поставщики оборудования",
    "Дизайнеры интерьеров",
    "Магазины мебели",
    "Свадебные салоны",
    "Фотостудии",
    "Видеостудии",
    "Диджеи",
    "Музыкальные группы",
    "Прокат звукового оборудования",
    "Разработка программного обеспечения",
    "IT-консалтинг",
    "Создание сайтов",
    "Кибербезопасность",
    "Разработка мобильных приложений",
    "Компьютерные сервисы",
    "Ремонт гаджетов",
    "Магазины электроники",
    "Прокат строительной техники",
    "Строительная техника",
    "Аренда строительных материалов",
    "Производство мебели",
    "Производство окон",
    "Изготовление дверей",
    "Магазины сантехники",
    "Ремонт одежды",
    "Ателье",
    "Пошив штор",
    "Магазины одежды",
    "Свадебные фотографы",
    "Услуги по организации мероприятий",
    "Музыкальные школы",
    "Спортивные секции",
    "Автошколы",
    "Курсы вождения",
    "Салоны оптики",
    "Салоны связи",
    "Студии тату",
    "Барбершопы",
    "Магазины цветов",
    "Доставка еды",
    "Продуктовые магазины",
    "Аптеки",
    "Магазины косметики",
    "Салон красоты",
    "Салоны маникюра",
    "Спортивные команды",
    "Игровые клубы",
    "Клубы настольных игр",
    "Квест-комнаты",
    "Кинотеатры",
    "Боулинг",
    "Бильярд",
    "Пункты выдачи заказов",
    "Сервисы доставки",
    "Такси",
    "Авиабилеты",
    "Железнодорожные билеты",
    "Страховые компании",
    "Брокерские фирмы",
    "Инвестиционные компании",
    "Банки",
    "Кредитные организации",
    "Займы",
    "Пункты обмена валюты",
    "Страхование имущества",
    "Оценка недвижимости",
    "Услуги юристов",
    "Нотариусы",
    "Риэлторы",
    "Ремонтники",
    "Службы охраны",
    "ЧОП",
    "Магазины спортивных товаров",
    "Магазины игрушек",
    "Детские товары",
    "Игровые площадки",
    "Сервисные центры",
    "Техническое обслуживание",
    "Прокат офисной техники",
    "Переводческие услуги",
    "Логистические компании",
    "Услуги по уборке",
    "Сады",
    "Тепличные хозяйства",
    "Продажа семян",
    "Оптовые базы",
    "Детские магазины",
    "Товары для животных",
    "Ветеринарные клиники",
    "Зоопарки",
    "Животноводческие фермы",
    "Молочные фермы",
    "Продажа мяса",
    "Рыбные магазины",
    "Производители молочной продукции",
    "Производители мясной продукции",
    "Производители рыбной продукции",
    "Пекарни",
    "Кондитерские",
    "Кафе",
    "Рестораны",
    "Магазины хлеба",
    "Мясные лавки",
    "Кофейни",
    "Кофейные лавки",
    "Суши-бары",
    "Пиццерии",
    "Рестораны быстрого питания",
    "Шаурма",
    "Фастфуды",
    "Магазины для ремонта",
    "Магазины для строительства",
    "Строительные материалы",
    "Садовые магазины",
    "Магазины сантехники",
    "Строительные компании",
    "Ремонтные услуги",
    "ЖКХ",
    "Теплоизоляция",
    "Инженерные системы",
    "Окна и двери",
    "Кровля",
    "Строительные инструменты",
    "Дома под ключ",
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


def _safe_open_path(path: Path) -> None:
    try:
        if not path.exists():
            return
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return
        if platform.system() == "Darwin":
            subprocess.run(["open", str(path)], check=False)
            return
        subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        return


def _hex_to_rgba(color: str) -> tuple[float, float, float, float]:
    color = color.lstrip("#")
    if len(color) != 6:
        return (1, 1, 1, 1)
    red = int(color[0:2], 16) / 255.0
    green = int(color[2:4], 16) / 255.0
    blue = int(color[4:6], 16) / 255.0
    return (red, green, blue, 1)


def _bind_text_wrap(label: Label) -> None:
    def _update(_instance, width: float) -> None:
        label.text_size = (width, None)

    label.bind(width=_update)
    _update(label, label.width)


class ParserGUIApp(App):
    def __init__(self) -> None:
        super().__init__()
        self._log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._settings = load_settings()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._captcha_event = threading.Event()
        self._running = False
        self._autosave_event: Clock | None = None
        self._progress_mode = "determinate"
        self._progress_event = None
        self._captcha_popup: Popup | None = None
        self._captcha_message_label: Label | None = None
        self._thanks_popup: Popup | None = None
        self._thanks_message_label: Label | None = None
        self._thanks_qr_texture = None
        self._settings_popup: Popup | None = None
        self._closing = False

        self._limit = 0
        self._lr = "120590"
        self._max_clicks = 800
        self._delay_min_s = 0.05
        self._delay_max_s = 0.15

        self.mode_var = SLOW_MODE_LABEL

        self.subtitle_label: Label | None = None
        self.niche_entry: TextInput | None = None
        self.city_entry: TextInput | None = None
        self.status_dot: Label | None = None
        self.status_label: Label | None = None
        self.progress: ProgressBar | None = None
        self.log_box: TextInput | None = None
        self.start_btn: Button | None = None
        self.pause_btn: Button | None = None
        self.resume_btn: Button | None = None
        self.stop_btn: Button | None = None
        self.settings_btn: Button | None = None
        self.restart_btn: Button | None = None

    def build(self) -> BoxLayout:
        Window.title = "Парсер SERM 4.0"
        Window.size = (680, 600)
        Window.minimum_width = 660
        Window.minimum_height = 560
        Window.bind(on_request_close=self._on_request_close)

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)
        root.add_widget(self._build_header())
        root.add_widget(self._build_body())

        Clock.schedule_interval(self._drain_queue, 0.1)
        configure_logging(self._settings.program.log_level)
        self._set_running(False)
        return root

    def _build_header(self) -> BoxLayout:
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=68, spacing=8)

        logo = BoxLayout(size_hint=(None, None), size=(22, 22))
        header.add_widget(logo)

        title_box = BoxLayout(orientation="vertical")
        title_label = Label(text="Парсер SERM 4.0", halign="left", valign="middle", font_size=22)
        _bind_text_wrap(title_label)
        title_box.add_widget(title_label)

        self.subtitle_label = Label(
            text=self.mode_var,
            color=(0.7, 0.7, 0.7, 1),
            halign="left",
            valign="middle",
            font_size=13,
        )
        _bind_text_wrap(self.subtitle_label)
        title_box.add_widget(self.subtitle_label)
        header.add_widget(title_box)

        header.add_widget(self._build_header_button("Спасибо ❤️", self._open_thanks_popup))
        header.add_widget(self._build_header_button("🐺 Дядя Волк", self._open_telegram))
        header.add_widget(self._build_header_button("🔧", self._open_support_telegram))
        self.settings_btn = self._build_header_button("⚙", self._open_settings)
        header.add_widget(self.settings_btn)
        self.restart_btn = self._build_header_button("↻", self._restart_app)
        header.add_widget(self.restart_btn)
        return header

    def _build_header_button(self, text: str, callback) -> Button:
        button = Button(text=text, size_hint=(None, None), size=(120, 34))
        button.bind(on_release=lambda _instance: callback())
        return button

    def _build_body(self) -> BoxLayout:
        body = BoxLayout(orientation="vertical", spacing=10)
        body.add_widget(self._build_top_card())
        body.add_widget(self._build_bottom_card())
        return body

    def _build_top_card(self) -> BoxLayout:
        card = BoxLayout(orientation="vertical", spacing=8, size_hint_y=None, height=180)

        niche_row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=40)
        self.niche_entry = TextInput(hint_text="Введите нишу…", multiline=False)
        niche_row.add_widget(self.niche_entry)
        niche_random_btn = Button(text="🎲", size_hint=(None, 1), width=80)
        niche_random_btn.bind(on_release=lambda _instance: self._randomize_niche())
        niche_row.add_widget(niche_random_btn)
        card.add_widget(niche_row)

        city_row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=40)
        self.city_entry = TextInput(hint_text="Введите город…", multiline=False)
        city_row.add_widget(self.city_entry)
        city_random_btn = Button(text="🎲", size_hint=(None, 1), width=80)
        city_random_btn.bind(on_release=lambda _instance: self._randomize_city())
        city_row.add_widget(city_random_btn)
        card.add_widget(city_row)

        mode_row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=40)
        mode_row.add_widget(Label(text="Режим", size_hint=(None, 1), width=80))

        mode_buttons = BoxLayout(orientation="horizontal", spacing=6)
        slow_btn = ToggleButton(text=SLOW_MODE_LABEL, group="mode", state="down")
        fast_btn = ToggleButton(text=FAST_MODE_LABEL, group="mode")
        slow_btn.bind(on_release=lambda _instance: self._on_mode_change(SLOW_MODE_LABEL))
        fast_btn.bind(on_release=lambda _instance: self._on_mode_change(FAST_MODE_LABEL))
        mode_buttons.add_widget(slow_btn)
        mode_buttons.add_widget(fast_btn)
        mode_row.add_widget(mode_buttons)
        card.add_widget(mode_row)

        mode_hint = Label(
            text="быстрый — Search, подробный — Maps",
            color=(0.7, 0.7, 0.7, 1),
            font_size=12,
        )
        card.add_widget(mode_hint)
        return card

    def _build_bottom_card(self) -> BoxLayout:
        card = BoxLayout(orientation="vertical", spacing=8)

        status_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=28, spacing=8)
        self.status_dot = Label(text="●", color=_hex_to_rgba("#666666"), size_hint=(None, 1), width=16)
        status_row.add_widget(self.status_dot)
        self.status_label = Label(text="Ожидание", halign="left", valign="middle", font_size=14)
        _bind_text_wrap(self.status_label)
        status_row.add_widget(self.status_label)
        card.add_widget(status_row)

        self.progress = ProgressBar(max=1.0, value=0.0, size_hint_y=None, height=12)
        card.add_widget(self.progress)

        self.log_box = TextInput(readonly=True, multiline=True)
        card.add_widget(self.log_box)

        btns = GridLayout(cols=2, spacing=8, size_hint_y=None, height=180)
        self.start_btn = Button(text="🚀 Запустить")
        self.start_btn.bind(on_release=lambda _instance: self._on_start())
        btns.add_widget(self.start_btn)

        self.pause_btn = Button(text="⏸ Пауза")
        self.pause_btn.bind(on_release=lambda _instance: self._on_pause())
        btns.add_widget(self.pause_btn)

        self.resume_btn = Button(text="▶ Пуск")
        self.resume_btn.bind(on_release=lambda _instance: self._on_resume())
        btns.add_widget(self.resume_btn)

        self.stop_btn = Button(text="🛑 Стоп")
        self.stop_btn.bind(on_release=lambda _instance: self._on_stop())
        btns.add_widget(self.stop_btn)

        results_btn = Button(text="📂 Результаты")
        results_btn.bind(on_release=lambda _instance: self._open_results_dir())
        btns.add_widget(results_btn)

        card.add_widget(btns)
        return card

    def _build_query(self) -> str:
        niche = self.niche_entry.text.strip() if self.niche_entry else ""
        city = self.city_entry.text.strip() if self.city_entry else ""
        if niche and city:
            return f"{niche} в {city}"
        return niche or city

    def _set_entry_value(self, entry: TextInput | None, value: str) -> None:
        if entry is None:
            return
        entry.text = value

    def _randomize_niche(self) -> None:
        if NICHES:
            self._set_entry_value(self.niche_entry, random.choice(NICHES))

    def _randomize_city(self) -> None:
        if CITIES:
            self._set_entry_value(self.city_entry, random.choice(CITIES))

    def _sync_mode_label(self) -> None:
        if self.subtitle_label is not None:
            self.subtitle_label.text = self.mode_var

    def _on_mode_change(self, value: str) -> None:
        self.mode_var = value
        self._sync_mode_label()

    def _append_log(self, text: str) -> None:
        if self.log_box is None:
            return
        self.log_box.text += text + "\n"
        self.log_box.cursor = (0, len(self.log_box.text.splitlines()))
        self.log_box.scroll_y = 0

    def _clear_log(self) -> None:
        if self.log_box is not None:
            self.log_box.text = ""

    def _set_status(self, text: str, color: str) -> None:
        if self.status_label is not None:
            self.status_label.text = text
        if self.status_dot is not None:
            self.status_dot.color = _hex_to_rgba(color)

    def _set_progress(self, value: float) -> None:
        if self.progress is None:
            return
        self.progress.value = max(0.0, min(1.0, value))

    def _animate_progress(self, _dt: float) -> None:
        if self.progress is None:
            return
        next_value = self.progress.value + 0.02
        if next_value > 1.0:
            next_value = 0.0
        self.progress.value = next_value

    def _set_progress_mode(self, mode: str) -> None:
        mode = mode if mode in ("determinate", "indeterminate") else "determinate"
        self._progress_mode = mode
        if self._progress_event is not None:
            self._progress_event.cancel()
            self._progress_event = None
        if mode == "indeterminate":
            self._progress_event = Clock.schedule_interval(self._animate_progress, 0.05)

    def _finish_progress(self) -> None:
        if self._progress_event is not None:
            self._progress_event.cancel()
            self._progress_event = None
        self._set_progress(1.0)

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

    def _emit_thanks_prompt(self, message: str) -> None:
        self._log_queue.put(("thanks", {"message": message}))

    def _drain_queue(self, _dt: float) -> None:
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
                elif kind == "captcha":
                    if isinstance(payload, dict):
                        self._handle_captcha_event(payload)
                elif kind == "thanks":
                    if isinstance(payload, dict):
                        self._open_thanks_popup(payload.get("message", THANKS_MESSAGE))
                self._log_queue.task_done()
        except queue.Empty:
            return

    def _set_running(self, running: bool) -> None:
        self._running = running
        state = running
        if self.start_btn is not None:
            self.start_btn.disabled = state
        if self.pause_btn is not None:
            self.pause_btn.disabled = not state
        if self.resume_btn is not None:
            self.resume_btn.disabled = not state
        if self.stop_btn is not None:
            self.stop_btn.disabled = not state
        if self.settings_btn is not None:
            self.settings_btn.disabled = state
        if self.restart_btn is not None:
            self.restart_btn.disabled = state

    def _on_start(self) -> None:
        if self._running:
            return
        query = self._build_query()
        if not query:
            self._log("⚠️ Укажи нишу и/или город.", level="warning")
            return

        mode = self.mode_var
        full_path, potential_path, results_folder = self._output_paths(query)

        self._stop_event.clear()
        self._pause_event.clear()
        self._captcha_event.clear()
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
            args=(mode, query, full_path, potential_path, results_folder),
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

    def _output_paths(self, query: str) -> tuple[Path, Path, Path]:
        niche = self.niche_entry.text.strip() if self.niche_entry else ""
        city = self.city_entry.text.strip() if self.city_entry else ""
        if not niche and not city:
            niche, city = split_query(query)
        return build_result_paths(niche=niche, city=city, results_dir=RESULTS_DIR)

    def _run_worker(
        self,
        mode: str,
        query: str,
        full_path: Path,
        potential_path: Path,
        results_folder: Path,
    ) -> None:
        self._log_queue.put(("status", ("Работаю", "#4CAF50")))
        try:
            if mode == FAST_MODE_LABEL:
                self._run_fast(query, full_path, potential_path, results_folder)
            else:
                self._run_slow(query, full_path, potential_path, results_folder)
        except Exception as exc:
            self._log(f"❌ Ошибка: {exc}", level="error")
            notify_sound("error", self._settings)
        finally:
            self._log_queue.put(("status", ("Готово", "#666666")))
            self._log_queue.put(("progress_done", None))
            self._log_queue.put(("state", False))

    def _run_slow(
        self,
        query: str,
        full_path: Path,
        potential_path: Path,
        results_folder: Path,
    ) -> None:
        self._log("🐢 подробный: Яндекс Карты.")

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

        scraper = YandexMapsScraper(
            query=query,
            limit=self._limit if self._limit > 0 else None,
            headless=self._settings.program.headless,
            block_images=self._settings.program.block_images,
            block_media=self._settings.program.block_media,
            stop_event=self._stop_event,
            pause_event=self._pause_event,
            captcha_resume_event=self._captcha_event,
            captcha_hook=captcha_hook,
            log=self._log,
        )
        writer = ExcelWriter(full_path, potential_path)
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
            self._log(f"📄 Файлы сохранены: {full_path.name}, {potential_path.name}")
            notify_sound("finish", self._settings)
            if self._settings.program.open_result:
                _safe_open_path(results_folder)
            if count > 20:
                self._emit_thanks_prompt(POST_PARSE_MESSAGE)

    def _run_fast(
        self,
        query: str,
        full_path: Path,
        potential_path: Path,
        results_folder: Path,
    ) -> None:
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
            full_output_path=full_path,
            potential_output_path=potential_path,
            lr=self._lr,
            max_clicks=self._max_clicks,
            delay_min_s=self._delay_min_s,
            delay_max_s=self._delay_max_s,
            stop_event=self._stop_event,
            pause_event=self._pause_event,
            captcha_resume_event=self._captcha_event,
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

    def _open_telegram(self) -> None:
        webbrowser.open("https://t.me/+FTIjY5WVmZU5MzYy")

    def _open_support_telegram(self) -> None:
        message = "Привет, у меня парсер не работает, сейчас скину тебе лог"
        encoded_message = quote(message)
        webbrowser.open(f"https://t.me/siente_como_odias?text={encoded_message}")

    def _open_donation_link(self) -> None:
        webbrowser.open(DONATION_URL)

    def _build_qr_texture(self, size: int = 180):
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
        pil_image = pil_image.resize((size, size))
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        buffer.seek(0)
        return CoreImage(buffer, ext="png").texture

    def _open_thanks_popup(self, message: str | None = None) -> None:
        popup_message = message or THANKS_MESSAGE
        if self._thanks_popup is not None:
            if self._thanks_message_label is not None:
                self._thanks_message_label.text = popup_message
            return

        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        title = Label(text="Спасибо ❤️", font_size=18, size_hint_y=None, height=30)
        content.add_widget(title)

        self._thanks_message_label = Label(text=popup_message, halign="left", valign="top")
        _bind_text_wrap(self._thanks_message_label)
        content.add_widget(self._thanks_message_label)

        if self._thanks_qr_texture is None:
            self._thanks_qr_texture = self._build_qr_texture()
        qr_image = KivyImage(texture=self._thanks_qr_texture, size_hint_y=None, height=200)
        content.add_widget(qr_image)

        phone_label = Label(text=f"Телефон: {DONATION_PHONE}", size_hint_y=None, height=24)
        content.add_widget(phone_label)

        thanks_btn = Button(text="Спасибо", size_hint_y=None, height=40)
        thanks_btn.bind(on_release=lambda _instance: self._open_donation_link())
        content.add_widget(thanks_btn)

        self._thanks_popup = Popup(title="Спасибо ❤️", content=content, size_hint=(None, None), size=(480, 520))
        self._thanks_popup.bind(on_dismiss=lambda _instance: self._close_thanks_popup())
        self._thanks_popup.open()

    def _close_thanks_popup(self) -> None:
        self._thanks_popup = None
        self._thanks_message_label = None

    def _handle_captcha_event(self, payload: dict) -> None:
        stage = str(payload.get("stage", ""))
        message = str(payload.get("message", ""))
        if stage == "cleared":
            self._close_captcha_prompt()
            return
        if stage in {"detected", "manual", "still"}:
            self._open_captcha_prompt(message or "Капча, реши руками и продолжим. Если зависла - обнови страницу F5")

    def _open_captcha_prompt(self, message: str) -> None:
        if self._captcha_popup is not None:
            if self._captcha_message_label is not None:
                self._captcha_message_label.text = message
            return

        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        title = Label(text="🧩 Капча", font_size=18, size_hint_y=None, height=30)
        content.add_widget(title)

        self._captcha_message_label = Label(text=message, halign="left", valign="top")
        _bind_text_wrap(self._captcha_message_label)
        content.add_widget(self._captcha_message_label)

        auto_label = Label(
            text="Мы автоматически проверяем, как только капча решена — продолжим.",
            color=(0.7, 0.7, 0.7, 1),
            size_hint_y=None,
            height=50,
            halign="left",
            valign="top",
        )
        _bind_text_wrap(auto_label)
        content.add_widget(auto_label)

        close_btn = Button(text="Закрыть", size_hint_y=None, height=40)
        close_btn.bind(on_release=lambda _instance: self._abort_captcha())
        content.add_widget(close_btn)

        self._captcha_popup = Popup(title="Капча", content=content, size_hint=(None, None), size=(420, 240))
        self._captcha_popup.open()

    def _close_captcha_prompt(self) -> None:
        if self._captcha_popup is not None:
            self._captcha_popup.dismiss()
        self._captcha_popup = None
        self._captcha_message_label = None

    def _abort_captcha(self) -> None:
        self._on_stop()

    def _open_settings(self) -> None:
        if self._running:
            self._log("⚠️ Останови парсер перед настройками.", level="warning")
            return
        if self._settings_popup is not None:
            return

        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        scroll = ScrollView()
        form = GridLayout(cols=1, spacing=8, size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))

        widgets = self._build_settings_form(form)
        scroll.add_widget(form)
        content.add_widget(scroll)

        btn_row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=40)
        save_btn = Button(text="Сохранить настройки")
        close_btn = Button(text="Закрыть")
        btn_row.add_widget(save_btn)
        btn_row.add_widget(close_btn)
        content.add_widget(btn_row)

        self._settings_popup = Popup(title="Настройки", content=content, size_hint=(None, None), size=(560, 720))

        def _on_dismiss(*_args) -> None:
            self._apply_settings_from_widgets(widgets)
            if not self._settings.program.autosave_settings:
                self._save_settings(log_message="💾 Настройки сохранены.")
            self._settings_popup = None

        def _on_apply(*_args) -> None:
            self._apply_settings_from_widgets(widgets)
            self._save_settings(log_message="⚙️ Настройки сохранены.")
            if self._settings_popup is not None:
                self._settings_popup.dismiss()

        def _on_change(*_args) -> None:
            self._apply_settings_from_widgets(widgets)
            self._maybe_autosave()

        self._bind_settings_widgets(widgets, _on_change)
        save_btn.bind(on_release=_on_apply)
        close_btn.bind(on_release=lambda _instance: self._settings_popup.dismiss())
        self._settings_popup.bind(on_dismiss=_on_dismiss)
        self._settings_popup.open()

    def _build_settings_form(self, form: GridLayout) -> dict:
        filters = self._settings.potential_filters
        program = self._settings.program
        notifications = self._settings.notifications

        form.add_widget(
            Label(text="[b]Фильтры для POTENTIAL[/b]", markup=True, size_hint_y=None, height=24)
        )
        form.add_widget(
            Label(
                text="FULL сохраняется всегда, фильтры применяются только к potential.",
                color=(0.7, 0.7, 0.7, 1),
                size_hint_y=None,
                height=24,
            )
        )

        exclude_no_phone = self._add_checkbox(form, "Не сохранять без телефона", filters.exclude_no_phone)
        require_checkmark = self._add_checkbox(
            form,
            "Только с галочкой (синяя/зелёная)",
            filters.require_checkmark,
        )
        exclude_good_place = self._add_checkbox(form, "Исключать «Хорошее место»", filters.exclude_good_place)
        exclude_noncommercial = self._add_checkbox(form, "Исключать некоммерческие", filters.exclude_noncommercial)

        rating_values = ["Без ограничений", "5.0", "4.7", "4.4"]
        max_rating_default = "Без ограничений" if filters.max_rating is None else f"{filters.max_rating:.1f}"
        max_rating = Spinner(text=max_rating_default, values=rating_values, size_hint_y=None, height=36)
        form.add_widget(self._wrap_labeled_widget("Максимальный рейтинг", max_rating))

        stop_words = TextInput(text=filters.stop_words, multiline=False)
        form.add_widget(self._wrap_labeled_widget("Стоп-слова (через запятую)", stop_words))

        white_list = TextInput(text=filters.white_list, multiline=False)
        form.add_widget(self._wrap_labeled_widget("Белый список (если задан — пропускать только их)", white_list))

        form.add_widget(Label(text="[b]Настройки программы[/b]", markup=True, size_hint_y=None, height=24))

        headless = self._add_checkbox(form, "Запускать в фоне (без окна)", program.headless)
        block_images = self._add_checkbox(form, "Не загружать изображения", program.block_images)
        block_media = self._add_checkbox(form, "Не загружать видео и аудио", program.block_media)
        open_result = self._add_checkbox(form, "Открывать результат после завершения", program.open_result)

        log_level = Spinner(
            text=LOG_LEVEL_LABELS_REVERSE.get(program.log_level, "Обычные (рекомендуется)"),
            values=list(LOG_LEVEL_LABELS.keys()),
            size_hint_y=None,
            height=36,
        )
        form.add_widget(self._wrap_labeled_widget("Какие логи показывать", log_level))

        autosave = self._add_checkbox(form, "Автосохранение настроек", program.autosave_settings)

        form.add_widget(Label(text="[b]Уведомления[/b]", markup=True, size_hint_y=None, height=24))
        form.add_widget(
            Label(
                text="Показывать звук при важных событиях.",
                color=(0.7, 0.7, 0.7, 1),
                size_hint_y=None,
                height=24,
            )
        )

        sound_finish = self._add_checkbox(form, "При завершении", notifications.on_finish)
        sound_captcha = self._add_checkbox(form, "При капче", notifications.on_captcha)
        sound_error = self._add_checkbox(form, "При ошибке", notifications.on_error)
        sound_autosave = self._add_checkbox(form, "При автосейве", notifications.on_autosave)

        return {
            "exclude_no_phone": exclude_no_phone,
            "require_checkmark": require_checkmark,
            "exclude_good_place": exclude_good_place,
            "exclude_noncommercial": exclude_noncommercial,
            "max_rating": max_rating,
            "stop_words": stop_words,
            "white_list": white_list,
            "headless": headless,
            "block_images": block_images,
            "block_media": block_media,
            "open_result": open_result,
            "log_level": log_level,
            "autosave_settings": autosave,
            "sound_finish": sound_finish,
            "sound_captcha": sound_captcha,
            "sound_error": sound_error,
            "sound_autosave": sound_autosave,
        }

    def _wrap_labeled_widget(self, label_text: str, widget) -> BoxLayout:
        layout = BoxLayout(orientation="vertical", spacing=4, size_hint_y=None, height=64)
        label = Label(text=label_text, size_hint_y=None, height=20, halign="left", valign="middle")
        _bind_text_wrap(label)
        layout.add_widget(label)
        layout.add_widget(widget)
        return layout

    def _add_checkbox(self, form: GridLayout, text: str, value: bool) -> CheckBox:
        row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=32)
        checkbox = CheckBox(active=value, size_hint=(None, None), size=(24, 24))
        label = Label(text=text, halign="left", valign="middle")
        _bind_text_wrap(label)
        row.add_widget(checkbox)
        row.add_widget(label)
        form.add_widget(row)
        return checkbox

    def _bind_settings_widgets(self, widgets: dict, callback) -> None:
        for key, widget in widgets.items():
            if isinstance(widget, CheckBox):
                widget.bind(active=callback)
            elif isinstance(widget, Spinner):
                widget.bind(text=callback)
            elif isinstance(widget, TextInput):
                widget.bind(text=callback)

    def _apply_settings_from_widgets(self, widgets: dict) -> None:
        filters = self._settings.potential_filters
        program = self._settings.program
        notifications = self._settings.notifications

        filters.exclude_no_phone = bool(widgets["exclude_no_phone"].active)
        filters.require_checkmark = bool(widgets["require_checkmark"].active)
        filters.exclude_good_place = bool(widgets["exclude_good_place"].active)
        filters.exclude_noncommercial = bool(widgets["exclude_noncommercial"].active)
        rating_value = widgets["max_rating"].text
        if rating_value == "Без ограничений":
            filters.max_rating = None
        else:
            try:
                filters.max_rating = float(str(rating_value).replace(",", "."))
            except Exception:
                filters.max_rating = None
        filters.stop_words = str(widgets["stop_words"].text or "").strip()
        filters.white_list = str(widgets["white_list"].text or "").strip()

        program.headless = bool(widgets["headless"].active)
        program.block_images = bool(widgets["block_images"].active)
        program.block_media = bool(widgets["block_media"].active)
        program.open_result = bool(widgets["open_result"].active)
        log_label = str(widgets["log_level"].text or "Обычные (рекомендуется)")
        program.log_level = LOG_LEVEL_LABELS.get(log_label, "info")
        program.autosave_settings = bool(widgets["autosave_settings"].active)

        notifications.on_finish = bool(widgets["sound_finish"].active)
        notifications.on_captcha = bool(widgets["sound_captcha"].active)
        notifications.on_error = bool(widgets["sound_error"].active)
        notifications.on_autosave = bool(widgets["sound_autosave"].active)

        configure_logging(program.log_level)

    def _maybe_autosave(self) -> None:
        if not self._settings.program.autosave_settings:
            if self._autosave_event is not None:
                self._autosave_event.cancel()
                self._autosave_event = None
            return
        if self._autosave_event is not None:
            self._autosave_event.cancel()
        self._autosave_event = Clock.schedule_once(self._autosave_settings, 0.3)

    def _autosave_settings(self, _dt: float) -> None:
        self._autosave_event = None
        self._save_settings(log_message="💾 Настройки автосохранены.")
        notify_sound("autosave", self._settings)

    def _save_settings(self, log_message: str | None = None) -> None:
        save_settings(self._settings)
        if log_message:
            self._log(log_message)

    def _restart_app(self) -> None:
        if self._running:
            return
        self._set_status("Перезапуск...", "#3c8d0d")
        self._log("🔁 Перезапуск приложения...")
        Clock.schedule_once(lambda _dt: self._perform_restart(), 0.1)

    def _perform_restart(self) -> None:
        python = sys.executable
        args = [python, *sys.argv]
        try:
            subprocess.Popen(args, close_fds=True)
        finally:
            self._closing = True
            self.stop()
            os._exit(0)

    def _on_request_close(self, *_args) -> bool:
        if self._closing:
            return False
        self._on_close()
        return False

    def _on_close(self) -> None:
        if not self._closing:
            self._closing = True
        if self._running:
            self._on_stop()
            worker = self._worker
            if worker and worker.is_alive():
                self._log("⏳ Завершаю фоновые процессы...")
                worker.join(timeout=10)
                if worker.is_alive():
                    self._log("⚠️ Не удалось дождаться завершения фоновых процессов.", level="warning")
        if self._autosave_event is not None:
            self._autosave_event.cancel()
            self._autosave_event = None
            self._save_settings(log_message="💾 Настройки сохранены.")
        elif not self._settings.program.autosave_settings:
            self._save_settings(log_message="💾 Настройки сохранены.")
        self.stop()


def main() -> None:
    ParserGUIApp().run()


if __name__ == "__main__":
    main()
