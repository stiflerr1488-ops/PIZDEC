# Как собрать .exe и .app с PyQtDeploy

Ниже — практичная шпаргалка, как собрать приложение на PyQt в самостоятельный
исполняемый файл для Windows (.exe) и в bundle для macOS (.app) с помощью
`pyqtdeploy`.

## 1) Установка

```bash
pip install PyQt5 pyqtdeploy
```

> Для сборки под конкретную платформу нужен toolchain этой платформы.
> Обычно сборка выполняется на целевой ОС (Windows собираем на Windows,
> macOS — на macOS). Кросс‑сборка возможна, но требует отдельной настройки.

## 2) Подготовка sysroot

`sysroot` — это набор собранных зависимостей (Python, Qt, PyQt), который
используется при финальной сборке.

Пример `sysroot.json` (минимальный набор для QtCore/QtGui/QtWidgets):

```json
{
  "linux#qt5": {
    "source": "qt-everywhere-src-5.12.2.tar.xz",
    "edition": "opensource",
    "configure_options": ["-no-dbus"],
    "skip": ["qt3d", "qtwebengine"]
  },
  "linux#python": {
    "build_host_from_source": false,
    "build_target_from_source": true,
    "source": "Python-3.7.2.tgz",
    "dynamic_loading": true
  },
  "linux#sip": {
    "module_name": "PyQt5.sip",
    "source": "sip-4.19.15.tar.gz"
  },
  "linux#pyqt5": {
    "modules": ["QtCore", "QtGui", "QtWidgets"],
    "source": "PyQt5_*-5.12.2.tar.gz"
  }
}
```

Скачать архивы зависимостей и собрать sysroot:

```bash
pyqtdeploy-sysroot sysroot.json
```

## 3) Создание файла проекта (.pdy)

Откройте GUI конфигуратор:

```bash
pyqtdeploy app.pdy
```

Ключевые настройки:

- **Main script file** — точка входа (`main.py`).
- **Target Python version** / **Target PyQt version** — версии Python/PyQt.
- **Application Package Directory** — папка с исходниками приложения.
- **PyQt Modules** — модули, которые используете (например, QtCore/QtGui/QtWidgets).
- **Standard Library** — модули stdlib, которые импортируются напрямую.
- **Other Packages** — сторонние пакеты (из venv/site-packages), если есть.
- **Application bundle** — включить для macOS (.app).

## 4) Сборка

```bash
pyqtdeploy-build app.pdy
cd build-<platform>
../sysroot-<platform>/host/bin/qmake
make   # на Windows: nmake
```

### Автоматизация сборки

Если хотите автоматизировать шаги сборки, используйте скрипт
`pyqtdeploy_build.sh`:

```bash
./pyqtdeploy_build.sh app.pdy sysroot.json
```

При необходимости можно явно указать платформу:

```bash
./pyqtdeploy_build.sh app.pdy sysroot.json win-64
```

### Результат

- **Windows**: получаете `.exe` в директории сборки.
- **macOS**: получаете `.app` (bundle), пригодный для распространения.

## Полезные заметки

- Для ресурсов (иконки, картинки) удобно использовать Qt Resource System
  и обращаться к ним через `:/path/to/resource`.
- Если используете C-расширения, может понадобиться отдельная статическая
  линковка и настройка в разделе **Other Extension Modules**.

---

Если нужно, могу подготовить пример `sysroot.json` под вашу версию Python/Qt
и помочь отладить сборку на конкретной платформе.
