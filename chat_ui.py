from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
import speech_recognition as sr
from worker_threads import transcribe_audio, LocalSpeechUnderstoodError


class ChatProcessingThread(QThread):
    """Kullanıcının yazdığı metni asistan mantığına (LLM) gönderir."""
    resultReady = pyqtSignal(str, str)  # (tipo, resposta)
    errorOccurred = pyqtSignal(str)

    def __init__(self, process_func, user_text, parent=None):
        super().__init__(parent)
        self._process_func = process_func
        self._user_text = user_text

    def run(self):
        try:
            tipo, resposta = self._process_func(self._user_text)
            self.resultReady.emit(tipo, resposta)
        except Exception as e:
            self.errorOccurred.emit(str(e))


class MicRecordThread(QThread):
    """Mikrofondan tek seferlik bir cümle yakalayıp yerel olarak
    (faster-whisper ile, internete gitmeden) metne çevirir."""
    transcribed = pyqtSignal(str)
    errorOccurred = pyqtSignal(str)
    timedOut = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recognizer = sr.Recognizer()
        self._mic = sr.Microphone()

    def run(self):
        try:
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self._recognizer.listen(source, timeout=5, phrase_time_limit=10)
        except sr.WaitTimeoutError:
            self.timedOut.emit()
            return
        except Exception as e:
            self.errorOccurred.emit(str(e))
            return

        try:
            text = transcribe_audio(audio)
            self.transcribed.emit(text)
        except LocalSpeechUnderstoodError:
            self.errorOccurred.emit("Ses anlaşılamadı, tekrar deneyin.")
        except Exception as e:
            self.errorOccurred.emit(str(e))


class CommandExecutionThread(QThread):
    """Onaylanan bir PowerShell komutunu arka planda çalıştırır."""
    resultReady = pyqtSignal(str)
    errorOccurred = pyqtSignal(str)

    def __init__(self, execute_func, command, parent=None):
        super().__init__(parent)
        self._execute_func = execute_func
        self._command = command

    def run(self):
        try:
            result = self._execute_func(self._command)
            self.resultReady.emit(result)
        except Exception as e:
            self.errorOccurred.emit(str(e))


class CommandBubble(QFrame):
    """Önerilen bir PowerShell komutunu gösterip çalıştır/iptal onayı isteyen balon."""
    runRequested = pyqtSignal()
    cancelRequested = pyqtSignal()

    def __init__(self, command_text, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background-color: #1E293B; border-radius: 12px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        label = QLabel("Önerilen komut:")
        label.setStyleSheet("font-size: 11px; color: #8592A6; background: transparent;")
        layout.addWidget(label)

        cmd_label = QLabel(command_text)
        cmd_label.setWordWrap(True)
        cmd_label.setStyleSheet(
            "font-size: 13px; color: #A8D8FF; background: transparent; font-family: Consolas, monospace;"
        )
        layout.addWidget(cmd_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton { background-color: #334155; color: #E5E7EB; border-radius: 8px; padding: 6px 16px; }
            QPushButton:hover { background-color: #475569; }
            QPushButton:disabled { background-color: #27303F; color: #64748B; }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)

        self.run_btn = QPushButton("Çalıştır")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.setStyleSheet("""
            QPushButton { background-color: #2563EB; color: white; border-radius: 8px;
                          padding: 6px 16px; font-weight: 600; }
            QPushButton:hover { background-color: #3B82F6; }
            QPushButton:disabled { background-color: #27303F; color: #64748B; }
        """)
        self.run_btn.clicked.connect(self._on_run)
        btn_row.addWidget(self.run_btn)

        layout.addLayout(btn_row)

    def _on_run(self):
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.run_btn.setText("Çalıştırılıyor...")
        self.runRequested.emit()

    def _on_cancel(self):
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("İptal edildi")
        self.cancelRequested.emit()

    def mark_done(self, text="Çalıştırıldı"):
        self.run_btn.setText(text)


class ChatPage(QWidget):
    """WinVoice asistanıyla yazarak konuşulabilen sohbet sayfası."""

    def __init__(self, process_input_func=None, execute_powershell_func=None,
                 pause_hotword_func=None, resume_hotword_func=None, parent=None):
        super().__init__(parent)
        self._process_input_func = process_input_func
        self._execute_powershell_func = execute_powershell_func
        self._pause_hotword_func = pause_hotword_func
        self._resume_hotword_func = resume_hotword_func
        self._active_thread = None
        self._exec_thread = None
        self._mic_thread = None
        self._thinking_label = None

        self.setStyleSheet("background-color: #0B0F19;")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel("Sesli Asistan")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #F8FAFC;")
        subtitle = QLabel("WinVoice ile yazışarak da konuşabilirsiniz.")
        subtitle.setStyleSheet("font-size: 13px; color: #8592A6;")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background-color: #121826; border-radius: 16px; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 4px; }
            QScrollBar::handle:vertical { background: #334155; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        self.messages_container = QWidget()
        self.messages_container.setStyleSheet("background-color: transparent;")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(16, 16, 16, 16)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch()
        self.scroll_area.setWidget(self.messages_container)
        root.addWidget(self.scroll_area, stretch=1)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Bir mesaj yazın...")
        self.input_box.setFixedHeight(44)
        self.input_box.setStyleSheet("""
            QLineEdit { background-color: #121826; border: 1px solid rgba(255,255,255,30);
                        border-radius: 10px; padding: 0 14px; color: #F1F5F9; font-size: 14px; }
            QLineEdit:focus { border: 1px solid #3B82F6; }
        """)
        self.input_box.returnPressed.connect(self._on_send_clicked)
        input_row.addWidget(self.input_box, stretch=1)

        self.mic_btn = QPushButton("🎙️")
        self.mic_btn.setFixedSize(44, 44)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setToolTip("Mikrofonla konuşarak mesaj gönder")
        self.mic_btn.setStyleSheet("""
            QPushButton { background-color: #1E293B; color: #F1F5F9; border-radius: 10px; font-size: 17px; }
            QPushButton:hover { background-color: #334155; }
            QPushButton:disabled { background-color: #27303F; color: #64748B; }
        """)
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        input_row.addWidget(self.mic_btn)

        self.send_btn = QPushButton("Gönder")
        self.send_btn.setFixedHeight(44)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton { background-color: #2563EB; color: white; border-radius: 10px;
                          padding: 0 22px; font-size: 14px; font-weight: 600; }
            QPushButton:hover { background-color: #3B82F6; }
            QPushButton:disabled { background-color: #27303F; color: #64748B; }
        """)
        self.send_btn.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self.send_btn)

        root.addLayout(input_row)

        self._add_system_note("WinVoice'a bir şeyler yazarak sohbet edebilir ya da komut isteyebilirsiniz.")

    # ------------------------------------------------------------------ #
    def _scroll_to_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _add_bubble(self, widget, align_right):
        widget.setMaximumWidth(420)
        row = QHBoxLayout()
        if align_right:
            row.addStretch()
            row.addWidget(widget)
        else:
            row.addWidget(widget)
            row.addStretch()
        self.messages_layout.insertLayout(self.messages_layout.count() - 1, row)
        self._scroll_to_bottom()

    def _add_user_message(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("""
            background-color: #2563EB; color: white; border-radius: 12px;
            padding: 10px 14px; font-size: 13px;
        """)
        self._add_bubble(label, align_right=True)

    def _add_assistant_message(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("""
            background-color: #1E293B; color: #E5E7EB; border-radius: 12px;
            padding: 10px 14px; font-size: 13px;
        """)
        self._add_bubble(label, align_right=False)
        return label

    def _add_system_note(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #64748B; font-size: 11px; background: transparent;")
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, label)
        self._scroll_to_bottom()

    def _add_command_bubble(self, command_text):
        bubble = CommandBubble(command_text)
        bubble.runRequested.connect(lambda: self._on_run_command(bubble, command_text))
        bubble.cancelRequested.connect(lambda: self._add_system_note("İşlem iptal edildi."))
        self._add_bubble(bubble, align_right=False)
        return bubble

    # ------------------------------------------------------------------ #
    def _on_send_clicked(self):
        text = self.input_box.text().strip()
        if not text:
            return
        if self._process_input_func is None:
            self._add_system_note("Asistan şu anda bağlı değil.")
            return

        self.input_box.clear()
        self._add_user_message(text)

        self.send_btn.setEnabled(False)
        self.mic_btn.setEnabled(False)
        self.input_box.setEnabled(False)
        self._thinking_label = self._add_assistant_message("Yazıyor...")

        self._active_thread = ChatProcessingThread(self._process_input_func, text)
        self._active_thread.resultReady.connect(self._on_result_ready)
        self._active_thread.errorOccurred.connect(self._on_processing_error)
        self._active_thread.start()

    def _on_result_ready(self, tipo, resposta):
        self.send_btn.setEnabled(True)
        self.mic_btn.setEnabled(True)
        self.input_box.setEnabled(True)
        self.input_box.setFocus()

        if tipo == "KOMUT":
            self._thinking_label.setText("Şunu çalıştırmamı ister misiniz?")
            self._add_command_bubble(resposta)
        else:
            self._thinking_label.setText(resposta)
            self._scroll_to_bottom()

    def _on_processing_error(self, error_message):
        self.send_btn.setEnabled(True)
        self.mic_btn.setEnabled(True)
        self.input_box.setEnabled(True)
        if self._thinking_label is not None:
            self._thinking_label.setText(f"Hata: {error_message}")

    # ------------------------------------------------------------------ #
    # Mikrofonla mesaj gönderme
    # ------------------------------------------------------------------ #
    def _on_mic_clicked(self):
        if self._pause_hotword_func:
            try:
                self._pause_hotword_func()
            except Exception:
                pass

        self.mic_btn.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.input_box.setEnabled(False)
        self.mic_btn.setText("🔴")
        self._add_system_note("Dinleniyor... (mikrofon)")

        self._mic_thread = MicRecordThread()
        self._mic_thread.transcribed.connect(self._on_mic_transcribed)
        self._mic_thread.errorOccurred.connect(self._on_mic_error)
        self._mic_thread.timedOut.connect(self._on_mic_timeout)
        self._mic_thread.finished.connect(self._reset_mic_button)
        self._mic_thread.start()

    def _reset_mic_button(self):
        self.mic_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_box.setEnabled(True)
        self.mic_btn.setText("🎙️")
        if self._resume_hotword_func:
            try:
                self._resume_hotword_func()
            except Exception:
                pass

    def _on_mic_transcribed(self, text):
        text = text.strip()
        if not text:
            self._add_system_note("Ses algılanamadı, tekrar deneyin.")
            return
        self.input_box.setText(text)
        self._on_send_clicked()

    def _on_mic_error(self, message):
        self._add_system_note(f"Mikrofon hatası: {message}")

    def _on_mic_timeout(self):
        self._add_system_note("Ses algılanamadı (zaman aşımı), tekrar deneyin.")

    def _on_run_command(self, bubble, command_text):
        if self._execute_powershell_func is None:
            self._add_system_note("Komut çalıştırma şu anda bağlı değil.")
            return
        self._exec_thread = CommandExecutionThread(self._execute_powershell_func, command_text)
        self._exec_thread.resultReady.connect(lambda result: self._on_command_result(bubble, result))
        self._exec_thread.errorOccurred.connect(lambda err: self._on_command_error(bubble, err))
        self._exec_thread.start()

    def _on_command_result(self, bubble, result):
        bubble.mark_done("Çalıştırıldı")
        text = result.strip() if result and result.strip() else "(çıktı yok)"
        self._add_assistant_message(f"Sonuç:\n{text[:800]}")

    def _on_command_error(self, bubble, error_message):
        bubble.mark_done("Hata oluştu")
        self._add_system_note(f"Hata: {error_message}")
