import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt5.QtGui import QPixmap, QMovie, QIcon
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QCoreApplication


class AssistantUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WinVoice - Sesli Asistan & Sohbet")
        self.setWindowIcon(QIcon("app_icon.png"))
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(20, 20, 25, 220); border-radius: 15px; border: 1px solid rgba(255, 255, 255, 30);")

        self.setup_ui()
        self.hide()

        self.hide_timer = QTimer(self)
        self.hide_timer.timeout.connect(self.hide)

        self.position_window_bottom_right()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.icon_label = QLabel(self)
        pixmap = QPixmap("app_icon.png")
        if not pixmap.isNull():
            self.icon_label.setPixmap(pixmap.scaled(55, 55, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.icon_label.setFixedSize(60, 60)
            self.icon_label.setStyleSheet("""
                            QLabel {
                                background-color: #FFA500;
                                border-radius: 30px;
                                border: 2px solid white;
                            }
                        """)
            self.icon_label.setAlignment(Qt.AlignCenter)
        else:
            self.icon_label.setText("🎙️")
            self.icon_label.setStyleSheet("font-size: 32px; color: white;")

        header_layout.addWidget(self.icon_label)

        self.status_label = QLabel("Komut bekleniyor...", self)
        self.status_label.setStyleSheet("font-size: 18px; color: #FFFFFF; font-weight: bold;")
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.status_label.setMinimumWidth(260)

        header_layout.addWidget(self.status_label)
        main_layout.addLayout(header_layout)

        self.command_label = QLabel("", self)
        self.command_label.setStyleSheet("font-size: 15px; color: #A8D8FF; background-color: rgba(0,0,0,60); padding: 8px; border-radius: 8px;")
        self.command_label.setWordWrap(True)
        self.command_label.hide()
        main_layout.addWidget(self.command_label)

        self.setLayout(main_layout)

    def position_window_bottom_right(self, margin=40):
        try:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.adjustSize()
                x = max(geo.left(), geo.right() - self.width() - margin)
                y = max(geo.top(), geo.bottom() - self.height() - margin)
                self.move(x, y)
            else:
                self.adjustSize()
        except Exception:
            pass

    # Hotword dinleyicisi boştayken (hiçbir komut/sohbet aktif değilken) bu
    # mesajı sürekli yayınlıyor. Daha önce bu durumda da pencere ekranda
    # kalıyordu ve sağ alt köşeyi sürekli işgal ediyordu; artık boşta
    # durumunda pencere tamamen gizleniyor, yalnızca gerçek bir etkileşim
    # (hotword algılandı, komut/sohbet, hata) olduğunda görünür hale geliyor.
    IDLE_STATUS_PREFIX = "Etkinleştirmek için"

    def update_status_message(self, message):
        if message.startswith(self.IDLE_STATUS_PREFIX):
            self.hide_window()
            return
        self.status_label.setText(message)
        self.command_label.hide()
        self.command_label.setText("")
        self.adjustSize()
        self.position_window_bottom_right()
        self.show()
        # Bu genel durum güncellemesi (ör. mikrofon/internet hatası) bir
        # sonraki adımla güncellenmezse bile köşede kalıcı olarak asılı
        # kalmasın.
        self.hide_timer.start(6000)

    def show_command_and_status(self, status_message, command_text):
        self.status_label.setText(status_message)
        if command_text:
            self.command_label.setText(f"Komut: {command_text}")
            self.command_label.show()
        else:
            self.command_label.hide()
            self.command_label.setText("")
        self.adjustSize()
        self.position_window_bottom_right()
        self.show()
        self.hide_timer.stop()

    def show_chat_message(self, user_text, assistant_text):
        if user_text:
            self.status_label.setText(f"Siz: \"{user_text}\"")
        else:
            self.status_label.setText("Dinleniyor...")
        if assistant_text:
            self.command_label.setText(f"Asistan: {assistant_text}")
            self.command_label.show()
        else:
            self.command_label.hide()
            self.command_label.setText("")
        self.adjustSize()
        self.position_window_bottom_right()
        self.show()
        self.hide_timer.stop()

    def show_final_result(self, message, result_text):
        self.status_label.setText(message)
        if result_text:
            self.command_label.setText(f"Sonuç: {result_text[:200]}...")
            self.command_label.show()
        else:
            self.command_label.hide()
            self.command_label.setText("")
        self.adjustSize()
        self.position_window_bottom_right()
        self.show()
        self.hide_timer.start(3500)

    def hide_window(self):
        self.hide()
        self.hide_timer.stop()
