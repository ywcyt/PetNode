import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QApplication,
                             QGraphicsOpacityEffect, QMessageBox) 
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint 
from PyQt6.QtGui import QFont, QCursor

# ==========================================
# 🌟 绝杀组件：明日方舟风暗黑 Toast 提示框
# ==========================================
class ToastNotification(QWidget):
    def __init__(self, parent, message, duration_ms=3000):
        super().__init__(parent)
        self.duration_ms = duration_ms
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"""
            QLabel {{
                background-color: #333333; 
                color: #FFFFFF;
                border-radius: 12px; 
                padding: 12px 25px;
                font-size: 13px;
                border: 1px solid #444444; 
            }}
        """)
        layout.addWidget(label)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(1000) 
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self.close) 

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fade_out)

    def show_fading(self):
        self.adjustSize()
        parent_rect = self.parent().rect()
        toast_rect = self.rect()
        x = (parent_rect.width() - toast_rect.width()) // 2
        y = (parent_rect.height() - toast_rect.height()) // 2
        self.move(QPoint(x, y))
        self.show()
        self.timer.start(self.duration_ms)

    def fade_out(self):
        self.animation.start()

# ==========================================
# 🏠 忘记密码界面核心类
# ==========================================
class ForgetPasswordWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.countdown = 60 
        self.init_ui()

    def init_ui(self):
        # 统一样式，包含小眼睛
        self.setStyleSheet("""
            QWidget { background-color: #110b17; color: #FFFFFF; font-family: 'Montserrat', 'Microsoft YaHei'; }
            QLabel#titleLabel { font-size: 26px; font-weight: bold; letter-spacing: 2px; margin-top: 15px; margin-bottom: 25px; }
            QLineEdit { background-color: #333333; color: #FFFFFF; border: 2px solid #555555; border-radius: 8px; padding: 10px; font-size: 13px; }
            QLineEdit:focus { border: 2px solid #aaaaaa; }
            
            QPushButton#eyeBtn { background-color: #333333; color: gray; border: 2px solid #555555; border-radius: 8px; font-size: 16px; }
            QPushButton#eyeBtn:hover { background-color: #444444; color: white; border: 2px solid #aaaaaa; }
            
            QPushButton#primaryBtn { background-color: #eb4d4b; color: #FFFFFF; border-radius: 20px; font-size: 15px; font-weight: bold; height: 40px; margin-top: 15px; }
            QPushButton#primaryBtn:hover { background-color: #c0392b; }
            
            QPushButton#textBtn { background-color: transparent; color: gray; border: none; font-size: 13px; }
            QPushButton#textBtn:hover { color: white; }
            
            QPushButton#codeBtn { background-color: #444444; color: white; border-radius: 8px; font-size: 12px; font-weight: bold; padding: 0 15px; }
            QPushButton#codeBtn:hover { background-color: #555555; }
            QPushButton#codeBtn:disabled { background-color: #222222; color: #777777; }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 20, 40, 20) 
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 标题
        title_label = QLabel("重置密码")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # 1. 手机号
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("👤 请输入绑定的手机号")
        main_layout.addWidget(self.phone_input)
        main_layout.addSpacing(10)

        # 2. 验证码
        code_layout = QHBoxLayout()
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("✉️ 请输入验证码")
        code_layout.addWidget(self.code_input)

        self.code_btn = QPushButton("获取验证码")
        self.code_btn.setObjectName("codeBtn")
        self.code_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.code_btn.setFixedHeight(40)
        self.code_btn.clicked.connect(self.handle_get_code) 
        code_layout.addWidget(self.code_btn)
        main_layout.addLayout(code_layout)
        main_layout.addSpacing(10)

        # 3. 新密码 (带小眼睛)
        pwd_layout = QHBoxLayout()
        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("🔒 请输入新密码")
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password) 
        pwd_layout.addWidget(self.pwd_input)

        self.pwd_eye_btn = QPushButton("🙈") 
        self.pwd_eye_btn.setObjectName("eyeBtn")
        self.pwd_eye_btn.setFixedSize(40, 40)
        self.pwd_eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.pwd_eye_btn.clicked.connect(self.toggle_pwd_visibility)
        pwd_layout.addWidget(self.pwd_eye_btn)
        
        main_layout.addLayout(pwd_layout)
        main_layout.addSpacing(10)

        # 4. 确认新密码 (带小眼睛)
        confirm_pwd_layout = QHBoxLayout()
        self.confirm_pwd_input = QLineEdit()
        self.confirm_pwd_input.setPlaceholderText("🔒 请确认新密码")
        self.confirm_pwd_input.setEchoMode(QLineEdit.EchoMode.Password) 
        confirm_pwd_layout.addWidget(self.confirm_pwd_input)

        self.confirm_pwd_eye_btn = QPushButton("🙈") 
        self.confirm_pwd_eye_btn.setObjectName("eyeBtn")
        self.confirm_pwd_eye_btn.setFixedSize(40, 40)
        self.confirm_pwd_eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.confirm_pwd_eye_btn.clicked.connect(self.toggle_confirm_pwd_visibility)
        confirm_pwd_layout.addWidget(self.confirm_pwd_eye_btn)

        main_layout.addLayout(confirm_pwd_layout)
        main_layout.addSpacing(20) # 取消了用户协议，这里间距稍微拉大一点

        # 重置按钮
        self.reset_btn = QPushButton("确认重置")
        self.reset_btn.setObjectName("primaryBtn")
        self.reset_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) 
        self.reset_btn.clicked.connect(self.handle_reset) 
        main_layout.addWidget(self.reset_btn)
        # 重置按钮
        self.reset_btn = QPushButton("确认重置")
        self.reset_btn.setObjectName("primaryBtn")
        self.reset_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) 
        
        # 🌟 新增：设置回车键直接触发重置
        self.reset_btn.setDefault(True) 
        
        self.reset_btn.clicked.connect(self.handle_reset)
        # 底部返回
        bottom_layout = QHBoxLayout()
        self.back_btn = QPushButton("⬅ 返回登录") 
        self.back_btn.setObjectName("textBtn")
        self.back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bottom_layout.addStretch() 
        bottom_layout.addWidget(self.back_btn)
        bottom_layout.addStretch() 
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)

    # 切换密码可见性
    def toggle_pwd_visibility(self):
        if self.pwd_input.echoMode() == QLineEdit.EchoMode.Password:
            self.pwd_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.pwd_eye_btn.setText("👁️")
        else:
            self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.pwd_eye_btn.setText("🙈")

    def toggle_confirm_pwd_visibility(self):
        if self.confirm_pwd_input.echoMode() == QLineEdit.EchoMode.Password:
            self.confirm_pwd_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.confirm_pwd_eye_btn.setText("👁️")
        else:
            self.confirm_pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_pwd_eye_btn.setText("🙈")

    # 验证码逻辑
    def handle_get_code(self):
        phone = self.phone_input.text()
        if len(phone) != 11:
            self.toast = ToastNotification(self, "❌ 请输入正确的 11 位手机号")
            self.toast.show_fading()
            return
        self.code_btn.setEnabled(False)
        self.countdown = 60
        self.code_btn.setText(f"{self.countdown}s 后重发")
        self.timer.start(1000) 
        self.toast = ToastNotification(self, "✅ 验证码已发送，请查收")
        self.toast.show_fading()

    def update_timer(self):
        self.countdown -= 1
        if self.countdown <= 0:
            self.timer.stop()
            self.code_btn.setEnabled(True)
            self.code_btn.setText("获取验证码")
        else:
            self.code_btn.setText(f"{self.countdown}s 后重发")

    # 重置逻辑
    def handle_reset(self):
        phone = self.phone_input.text()
        code = self.code_input.text()
        pwd = self.pwd_input.text()
        confirm_pwd = self.confirm_pwd_input.text()

        if not phone or not code or not pwd:
            self.toast = ToastNotification(self, "❌ 请填写完整的信息")
            self.toast.show_fading()
            return
        if pwd != confirm_pwd:
            self.toast = ToastNotification(self, "❌ 两次输入的新密码不一致！")
            self.toast.show_fading()
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("系统提示")
        msg_box.setText("🎉 密码重置成功！即将返回登录页。")
        msg_box.setIcon(QMessageBox.Icon.NoIcon) 
        msg_box.setStyleSheet("""
            QMessageBox { background-color: #1a1025; }
            QMessageBox QLabel { color: white; font-size: 14px; }
            QMessageBox QPushButton { background-color: #eb4d4b; color: white; border-radius: 5px; padding: 5px 15px; min-width: 60px; }
            QMessageBox QPushButton:hover { background-color: #c0392b; }
        """)
        msg_box.exec()
        
        self.phone_input.clear()
        self.code_input.clear()
        self.pwd_input.clear()
        self.confirm_pwd_input.clear()
        
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_eye_btn.setText("🙈")
        self.confirm_pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_pwd_eye_btn.setText("🙈")
        
        self.back_btn.click()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ForgetPasswordWindow()
    window.show()
    sys.exit(app.exec())