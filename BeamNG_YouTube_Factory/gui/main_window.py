import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Q_ARG, QMetaObject, Qt, QUrl, Signal, QObject, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QSlider, QSpinBox, QDoubleSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QScrollArea)

from ai_director.catalog import Catalog
from ai_director.director import Director
from core import deps, logger
from core.models import JobRequest
from core.pipeline import Pipeline
from core.stop import CancelToken
from gui.style import DARK_QSS
from gui.worker import PipelineWorker

EXAMPLE = ("Красный Lamborghini едет по горной дороге, разгоняется, перепрыгивает через автобус, "
           "теряет управление и врезается в стену.")
LEVEL_COLORS = {"ERROR": "#ff6b6b", "WARNING": "#ffc857", "INFO": "#cfd6dd", "DEBUG": "#7b8590"}


class LogBridge(QObject):
    line = Signal(str, str)


class MainWindow(QMainWindow):
    def __init__(self, settings, db):
        super().__init__()
        self.s, self.db = settings, db
        self.catalog = Catalog()
        self.cancel = CancelToken()
        self.worker = None
        self.setWindowTitle("BeamNG YouTube Factory")
        self.resize(1360, 860)
        self.bridge = LogBridge()
        self.bridge.line.connect(self._append_log)
        logger.add_listener(lambda lvl, msg: self.bridge.line.emit(lvl, msg))
        tabs = QTabWidget()
        tabs.addTab(self._build_create(), "🎬  Создать видео")
        tabs.addTab(self._build_history(), "🗂  История")
        tabs.addTab(self._build_settings(), "⚙  Настройки")
        tabs.addTab(self._build_check(), "🩺  Проверка системы")
        tabs.currentChanged.connect(lambda i: self._refresh_history() if i == 1 else None)
        self.setCentralWidget(tabs)
        self._refresh_history()

    # ===================================================================== СОЗДАНИЕ
    def _build_create(self):
        w = QWidget()
        root = QHBoxLayout(w)
        left = QVBoxLayout()
        g = QGroupBox("1. Сценарий")
        v = QVBoxLayout(g)
        self.script = QPlainTextEdit()
        self.script.setPlaceholderText("Опишите историю обычным языком. Например:\n" + EXAMPLE)
        self.script.setMinimumHeight(130)
        v.addWidget(self.script)
        row = QHBoxLayout()
        b = QPushButton("Вставить пример")
        b.clicked.connect(lambda: self.script.setPlainText(EXAMPLE))
        b2 = QPushButton("Предпросмотр плана")
        b2.setToolTip("Показать, как режиссёр понял сценарий — без запуска игры")
        b2.clicked.connect(self._preview_plan)
        row.addWidget(b); row.addWidget(b2); row.addStretch()
        v.addLayout(row)
        left.addWidget(g)

        g = QGroupBox("2. Параметры съёмки")
        f = QFormLayout(g)
        self.car = QComboBox(); self.car.addItem("Автоматически (по сценарию)", "auto")
        for c in self.catalog.cars:
            self.car.addItem(c["name"], c["model"])
        self.map = QComboBox(); self.map.addItem("Автоматически (по сценарию)", "auto")
        for m in self.catalog.maps:
            self.map.addItem(m["name"] + ("" if m.get("spawn") else "  (нет точки старта)"), m["level"])
        self.duration = QSpinBox(); self.duration.setRange(10, 180); self.duration.setValue(30); self.duration.setSuffix(" с")
        self.res = QComboBox(); self.res.addItems(["720p", "1080p", "1440p"]); self.res.setCurrentText("1080p")
        self.fps = QComboBox(); self.fps.addItems(["30", "60"]); self.fps.setCurrentText("60")
        self.cam = QComboBox()
        for label, key in (("Кинематографичная (смена ракурсов)", "cinematic"), ("Экшен (динамичные ракурсы)", "action"),
                           ("Только за машиной", "chase")):
            self.cam.addItem(label, key)
        self.takes = QSpinBox(); self.takes.setRange(1, 5); self.takes.setValue(1)
        self.takes.setToolTip("Сколько удачных дублей снять с разных ракурсов (повторы идут в монтаж как слоу-мо)")
        f.addRow("Автомобиль:", self.car); f.addRow("Карта:", self.map); f.addRow("Длительность ролика:", self.duration)
        f.addRow("Качество записи:", self.res); f.addRow("Кадров в секунду:", self.fps)
        f.addRow("Камера:", self.cam); f.addRow("Дублей на сцену:", self.takes)
        left.addWidget(g)

        g = QGroupBox("3. Результат")
        v = QVBoxLayout(g)
        self.chk_v = QCheckBox("Вертикальный Shorts 9:16 (до 60 с)"); self.chk_v.setChecked(True)
        self.chk_h = QCheckBox("Горизонтальное 16:9")
        self.crop = QComboBox(); self.crop.addItem("Умное кадрирование за машиной", "smart"); self.crop.addItem("Размытый фон (весь кадр)", "blur")
        self.chk_music = QCheckBox("Музыка"); self.chk_music.setChecked(True)
        self.chk_sfx = QCheckBox("Звуковые эффекты на событиях"); self.chk_sfx.setChecked(True)
        self.chk_up = QCheckBox("Сразу загрузить на YouTube (после авторизации)")
        for x in (self.chk_v, self.chk_h, self.crop, self.chk_music, self.chk_sfx, self.chk_up):
            v.addWidget(x)
        left.addWidget(g)
        row = QHBoxLayout()
        self.btn_gen = QPushButton("▶  GENERATE VIDEO"); self.btn_gen.setObjectName("generate")
        self.btn_gen.clicked.connect(self._generate)
        self.btn_stop = QPushButton("■  СТОП"); self.btn_stop.setObjectName("stop"); self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        row.addWidget(self.btn_gen, 3); row.addWidget(self.btn_stop, 1)
        left.addLayout(row)
        left.addStretch()
        lw = QWidget(); lw.setLayout(left); lw.setMaximumWidth(480)
        sc = QScrollArea(); sc.setWidget(lw); sc.setWidgetResizable(True); sc.setMaximumWidth(500)
        root.addWidget(sc)

        right = QVBoxLayout()
        pg = QGroupBox("Предпросмотр")
        pv = QVBoxLayout(pg)
        self.video = QVideoWidget(); self.video.setMinimumHeight(300)
        self.player = QMediaPlayer(); self.audio = QAudioOutput(); self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        pv.addWidget(self.video, 1)
        ctl = QHBoxLayout()
        pb = QPushButton("▶/⏸"); pb.clicked.connect(self._toggle_play)
        self.seek = QSlider(Qt.Horizontal); self.seek.sliderMoved.connect(self.player.setPosition)
        self.player.positionChanged.connect(lambda p: self.seek.setValue(p))
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        ctl.addWidget(pb); ctl.addWidget(self.seek)
        pv.addLayout(ctl)
        right.addWidget(pg, 3)
        self.stage = QLabel("Готов к работе"); self.stage.setObjectName("hint")
        self.bar = QProgressBar(); self.bar.setRange(0, 100)
        right.addWidget(self.stage); right.addWidget(self.bar)
        self.logbox = QPlainTextEdit(); self.logbox.setReadOnly(True); self.logbox.setMaximumBlockCount(5000)
        right.addWidget(QLabel("Журнал событий")); right.addWidget(self.logbox, 2)
        root.addLayout(right, 1)
        return w

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def play(self, path):
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()

    def _append_log(self, level, msg):
        fmt = QTextCharFormat(); fmt.setForeground(QColor(LEVEL_COLORS.get(level, "#cfd6dd")))
        cur = self.logbox.textCursor(); cur.movePosition(QTextCursor.End)
        cur.insertText(msg + "\n", fmt)
        self.logbox.setTextCursor(cur); self.logbox.ensureCursorVisible()

    def _request(self) -> JobRequest:
        return JobRequest(script=self.script.toPlainText().strip(), car=self.car.currentData(), map=self.map.currentData(),
                          duration=self.duration.value(), resolution=self.res.currentText(), fps=int(self.fps.currentText()),
                          camera_style=self.cam.currentData(), takes_per_scene=self.takes.value(), vertical=self.chk_v.isChecked(),
                          horizontal=self.chk_h.isChecked(), crop_mode=self.crop.currentData(), music=self.chk_music.isChecked(),
                          sfx=self.chk_sfx.isChecked(), upload=self.chk_up.isChecked())

    def _preview_plan(self):
        req = self._request()
        if not req.script:
            QMessageBox.information(self, "Сценарий", "Сначала напишите сценарий."); return
        try:
            pl = Pipeline(self.s, self.db, catalog=self.catalog)
            plan = pl.make_plan(req)
            text = Director(catalog=self.catalog).format_report(plan)
            QMessageBox.information(self, "План съёмки", text)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Ошибка", str(e))

    def _start(self, fn):
        self.cancel.reset()
        self.btn_gen.setEnabled(False); self.btn_stop.setEnabled(True)
        self.worker = PipelineWorker(fn)
        self.worker.done.connect(self._finished)
        self.worker.start()

    def _pipeline(self):
        return Pipeline(self.s, self.db, cancel=self.cancel, catalog=self.catalog,
                        progress=lambda pct, st, msg="": self.bridge_progress(pct, st, msg))

    def bridge_progress(self, pct, stage, msg):
        # вызывается из рабочего потока → передаём в GUI-поток через очередь событий Qt
        QMetaObject.invokeMethod(self, "_set_progress", Qt.QueuedConnection, Q_ARG(float, float(pct)), Q_ARG(str, f"{stage}: {msg}"))

    @Slot(float, str)
    def _set_progress(self, pct, text):
        self.bar.setValue(int(pct)); self.stage.setText(text)

    def _generate(self):
        req = self._request()
        if not req.script:
            QMessageBox.information(self, "Сценарий", "Сначала напишите сценарий."); return
        if not (req.vertical or req.horizontal):
            QMessageBox.information(self, "Формат", "Выберите хотя бы один формат видео."); return
        self.s.save()
        self._start(lambda: self._pipeline().run(req))

    def _stop(self):
        self.cancel.cancel()
        self.btn_stop.setEnabled(False)
        self._append_log("WARNING", "Остановка… записанные материалы будут сохранены.")

    def _finished(self, ok, res):
        self.btn_gen.setEnabled(True); self.btn_stop.setEnabled(False)
        if ok:
            self.bar.setValue(100); self.stage.setText("Готово!")
            f = res["files"][0]["path"]
            self._append_log("INFO", "Готово: " + "; ".join(x["path"] for x in res["files"]))
            self.play(f)
            self._refresh_history()
            QMessageBox.information(self, "Готово", "Видео создано:\n" + "\n".join(x["path"] for x in res["files"]) +
                                    "\n\nЗаголовок: " + res["metadata"]["title"])
        else:
            self.stage.setText("Остановлено / ошибка")
            QMessageBox.warning(self, "Процесс завершён без результата", str(res)[:1500])
            self._refresh_history()

    # ====================================================================== ИСТОРИЯ
    def _build_history(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Проект", "Статус", "Создан", "Видео", "Ошибка"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True); self.table.setColumnWidth(0, 380)
        v.addWidget(self.table)
        row = QHBoxLayout()
        for label, fn in (("▶ Смотреть", self._h_play), ("📂 Папка", self._h_open), ("↻ Продолжить", self._h_resume),
                          ("🎬 Переснять сцену", self._h_retry), ("✂ Пересобрать монтаж", self._h_edit),
                          ("⬆ Загрузить на YouTube", self._h_upload), ("✂ Смонтировать мой видеофайл…", self._h_edit_file)):
            b = QPushButton(label); b.clicked.connect(fn); row.addWidget(b)
        v.addLayout(row)
        return w

    def _refresh_history(self):
        import time
        rows = self.db.list_projects()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vids = self.db.list_videos(r["id"])
            vals = [r["title"] or r["id"], r["status"], time.strftime("%d.%m.%Y %H:%M", time.localtime(r["created"])),
                    str(len(vids)), r["error"] or ""]
            for j, val in enumerate(vals):
                it = QTableWidgetItem(val); it.setData(Qt.UserRole, r["id"]); self.table.setItem(i, j, it)

    def _sel(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.information(self, "История", "Выберите проект в списке."); return None
        return self.table.item(r, 0).data(Qt.UserRole)

    def _h_play(self):
        pid = self._sel()
        if pid:
            vids = self.db.list_videos(pid)
            if vids:
                self.play(vids[0]["path"])
                self.centralWidget().setCurrentIndex(0)
            else:
                QMessageBox.information(self, "Видео", "У проекта ещё нет готового видео.")

    def _h_open(self):
        pid = self._sel()
        if pid:
            p = self.db.get_project(pid)["folder"]
            if sys.platform.startswith("win"):
                os.startfile(p)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", p])

    def _h_resume(self):
        pid = self._sel()
        if pid:
            self.centralWidget().setCurrentIndex(0)
            self._start(lambda: self._pipeline().run(None, project_id=pid, resume=True))

    def _h_retry(self):
        pid = self._sel()
        if not pid:
            return
        n, ok = QInputDialog.getInt(self, "Переснять сцену", "Номер сцены:", 1, 1, 50)
        if ok:
            self.centralWidget().setCurrentIndex(0)
            self._start(lambda: self._pipeline().retry_scene(pid, n))

    def _h_edit(self):
        pid = self._sel()
        if pid:
            self.centralWidget().setCurrentIndex(0)
            self._start(lambda: self._pipeline().edit_only(pid))

    def _h_upload(self):
        pid = self._sel()
        if not pid:
            return
        vids = [v for v in self.db.list_videos(pid) if v["kind"] == "vertical"] or self.db.list_videos(pid)
        if not vids:
            QMessageBox.information(self, "YouTube", "Нет готового видео."); return
        v = vids[0]
        meta_path = Path(v["path"]).parent / "youtube_metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"title": Path(v["path"]).stem, "description": "", "hashtags": [], "tags": []}
        if QMessageBox.question(self, "YouTube", f"Загрузить «{meta['title']}» на YouTube?\nПриватность: {self.s.get('youtube.privacy')}\n"
                                "Откроется окно браузера для входа в аккаунт Google.") != QMessageBox.Yes:
            return

        def job():
            from youtube import uploader
            yt = uploader.upload(Path(v["path"]), meta, self.s)
            self.db.set_youtube_id(v["id"], yt)
            return {"files": [{"path": f"https://youtu.be/{yt}"}], "metadata": meta}
        self._start(job)

    def _h_edit_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Видео для монтажа", "", "Видео (*.mp4 *.mkv *.mov *.avi)")
        if not path:
            return
        req = self._request()

        def job():
            from core.models import Take
            from editor.editor import Editor
            out = self.s.output_dir / "edits" / Path(path).stem
            tk = Take(1, 0, path, [], ok=True)
            res = Editor(self.s, self.cancel).edit([tk], req, out, Path(path).stem)
            res["metadata"] = {"title": Path(path).stem}
            return res
        self._start(job)

    # ===================================================================== НАСТРОЙКИ
    def _build_settings(self):
        w = QWidget(); outer = QVBoxLayout(w)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        inner = QWidget(); v = QVBoxLayout(inner)
        self.fields = {}

        def add(group, rows):
            g = QGroupBox(group); f = QFormLayout(g)
            for label, key, kind, *extra in rows:
                val = self.s.get(key)
                if kind == "bool":
                    wd = QCheckBox(); wd.setChecked(bool(val))
                elif kind == "int":
                    wd = QSpinBox(); wd.setRange(0, 65535); wd.setValue(int(val or 0))
                elif kind == "float":
                    wd = QDoubleSpinBox(); wd.setRange(0, 5); wd.setSingleStep(0.05); wd.setValue(float(val or 0))
                elif kind == "choice":
                    wd = QComboBox(); wd.addItems(extra[0]); wd.setCurrentText(str(val))
                elif kind == "path":
                    wd = QLineEdit(str(val or ""))
                else:
                    wd = QLineEdit(str(val or ""))
                    if kind == "secret":
                        wd.setEchoMode(QLineEdit.Password)
                self.fields[key] = (wd, kind)
                if kind == "path":
                    h = QHBoxLayout(); h.addWidget(wd)
                    bb = QPushButton("…"); bb.setMaximumWidth(34)
                    bb.clicked.connect(lambda _=False, e=wd, folder=(extra[0] if extra else True): self._browse(e, folder))
                    h.addWidget(bb); f.addRow(label, h)
                else:
                    f.addRow(label, wd)
            v.addWidget(g)

        add("BeamNG.drive", [("Папка игры (где BeamNG.drive.exe)", "paths.beamng_home", "path", True),
                             ("Папка пользователя (необязательно)", "paths.beamng_user", "path", True),
                             ("Хост", "beamng.host", "text"), ("Порт", "beamng.port", "int"),
                             ("Запускать игру автоматически", "beamng.launch", "bool")])
        add("OBS Studio (WebSocket)", [("Использовать OBS", "obs.enabled", "bool"), ("Хост", "obs.host", "text"),
                                       ("Порт", "obs.port", "int"), ("Пароль", "obs.password", "secret"),
                                       ("Сцена OBS (необязательно)", "obs.scene_name", "text"),
                                       ("Менять разрешение/FPS OBS", "obs.set_video_settings", "bool")])
        add("FFmpeg", [("ffmpeg", "paths.ffmpeg", "path", False), ("ffprobe", "paths.ffprobe", "path", False),
                       ("Качество (CRF, меньше=лучше)", "editor.crf", "int"),
                       ("Громкость музыки", "editor.music_volume", "float")])
        add("ИИ (подключаемый провайдер)", [("Провайдер", "ai.provider", "choice", ["offline", "anthropic", "openai"]),
                                            ("Anthropic: ключ", "ai.anthropic.api_key", "secret"), ("Anthropic: модель", "ai.anthropic.model", "text"),
                                            ("OpenAI-совместимый: ключ", "ai.openai.api_key", "secret"),
                                            ("OpenAI-совместимый: адрес", "ai.openai.base_url", "text"),
                                            ("OpenAI-совместимый: модель", "ai.openai.model", "text")])
        add("YouTube", [("client_secret.json", "youtube.client_secret", "path", False),
                        ("Приватность загрузки", "youtube.privacy", "choice", ["private", "unlisted", "public"])])
        add("Производство", [("Макс. попыток на сцену", "production.max_scene_attempts", "int")])
        sc.setWidget(inner); outer.addWidget(sc)
        b = QPushButton("Сохранить настройки"); b.clicked.connect(self._save_settings); outer.addWidget(b)
        return w

    def _browse(self, edit, folder):
        p = QFileDialog.getExistingDirectory(self, "Папка") if folder else QFileDialog.getOpenFileName(self, "Файл")[0]
        if p:
            edit.setText(p)

    def _save_settings(self):
        for key, (wd, kind) in self.fields.items():
            if kind == "bool": val = wd.isChecked()
            elif kind in ("int", "float"): val = wd.value()
            elif kind == "choice": val = wd.currentText()
            else: val = wd.text().strip()
            self.s.set(key, val)
        self.s.save()
        QMessageBox.information(self, "Настройки", "Сохранено.")

    # ===================================================================== ПРОВЕРКА
    def _build_check(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.check_out = QPlainTextEdit(); self.check_out.setReadOnly(True)
        b = QPushButton("Проверить систему"); b.clicked.connect(self._run_check)
        v.addWidget(b); v.addWidget(self.check_out)
        return w

    def _run_check(self):
        self._save_settings_silent()
        checks = deps.check_all(self.s, deep=True)
        self.check_out.setPlainText("\n".join(str(c) for c in checks))

    def _save_settings_silent(self):
        for key, (wd, kind) in self.fields.items():
            if kind == "bool": val = wd.isChecked()
            elif kind in ("int", "float"): val = wd.value()
            elif kind == "choice": val = wd.currentText()
            else: val = wd.text().strip()
            self.s.set(key, val)


def run_gui(settings, db):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    win = MainWindow(settings, db)
    win.show()
    return app.exec()
