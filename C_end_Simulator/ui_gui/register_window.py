import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QCheckBox, QApplication,
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
# 🏠 注册界面核心类
# ==========================================
class RegisterWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.countdown = 60 # 验证码倒计时初始值
        self.init_ui()

    def init_ui(self):
        # 👉 终极美化 CSS (包含绝对防弹的白色对勾)
        self.setStyleSheet("""
            QWidget { background-color: #110b17; color: #FFFFFF; font-family: 'Montserrat', 'Microsoft YaHei'; }
            QLabel#titleLabel { font-size: 26px; font-weight: bold; letter-spacing: 2px; margin-top: 15px; margin-bottom: 15px; }
            QLineEdit { background-color: #333333; color: #FFFFFF; border: 2px solid #555555; border-radius: 8px; padding: 10px; font-size: 13px; }
            QLineEdit:focus { border: 2px solid #aaaaaa; }
            
            /* 胶囊主按钮 */
            QPushButton#primaryBtn { background-color: #eb4d4b; color: #FFFFFF; border-radius: 20px; font-size: 15px; font-weight: bold; height: 40px; margin-top: 10px; }
            QPushButton#primaryBtn:hover { background-color: #c0392b; }
            
            /* 返回登录文字按钮 */
            QPushButton#textBtn { background-color: transparent; color: gray; border: none; font-size: 13px; }
            QPushButton#textBtn:hover { color: white; }
            
            /* 获取验证码按钮 */
            QPushButton#codeBtn { background-color: #444444; color: white; border-radius: 8px; font-size: 12px; font-weight: bold; padding: 0 15px; }
            QPushButton#codeBtn:hover { background-color: #555555; }
            QPushButton#codeBtn:disabled { background-color: #222222; color: #777777; }
            
            /* 复选框和对勾 */
            QCheckBox { color: gray; font-size: 12px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px; border: 1px solid gray; }
            QCheckBox::indicator:unchecked { background-color: transparent; }
            QCheckBox::indicator:checked {
                background-color: #eb4d4b; border: 1px solid #eb4d4b;
                image: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAAsTAAALEwEAmpwYAAABOElEQVQ4y2P4//8/AyUYIxHGE8fHx9mR5Ojo6Bh4eHhcDAwM7AyEQI74+Hh9NjbG9vb2ZpSUlKRLS0urMjIy8pKSkq7MzMz89PT0pujo6G55efme3NzcI5KSks4U45mZmU5KSkreU4xHRUVlcXJyisTExGRzcXGxJyUlWRsbG8vExMTIQUlJSURFRUUMiYmJ2ZKSkiWjo6Nzk5KSjox44vHx8fpSUlL84uLipEJCQnIJCQnGZmZmkpaWlubk5OToS0lJiUZGRvIxMjJyER4A4uPj9ampqXFycXGRAXkEQHwKAGW4o6OjA8V4bGxskKSkJBMYMDExMcE4QEAwAAkECAgGIIEIAcGAGQj4+PiM5OTkGElKSppKSUl5SkpKWkpKSrgy4onGxsbyUlJSvOLi4phC4hEB5E8AZmH4X8w4C0wAAAAASUVORK5CYII=);
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 10, 40, 10) 
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- 标题 ---
        title_label = QLabel("PETNODE 注册")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # --- 1. 手机号输入框 ---
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("👤 请输入手机号")
        main_layout.addWidget(self.phone_input)
        main_layout.addSpacing(10)

        # --- 2. 验证码横向布局 ---
        code_layout = QHBoxLayout()
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("✉️ 请输入验证码")
        code_layout.addWidget(self.code_input)

        self.code_btn = QPushButton("获取验证码")
        self.code_btn.setObjectName("codeBtn")
        self.code_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.code_btn.setFixedHeight(40)
        self.code_btn.clicked.connect(self.handle_get_code) # 绑定获取验证码逻辑
        code_layout.addWidget(self.code_btn)
        
        main_layout.addLayout(code_layout)
        main_layout.addSpacing(10)

        # --- 3. 设置密码 ---
        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("🔒 请设置密码 (至少6位)")
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password) 
        main_layout.addWidget(self.pwd_input)
        main_layout.addSpacing(10)

        # --- 4. 确认密码 ---
        self.confirm_pwd_input = QLineEdit()
        self.confirm_pwd_input.setPlaceholderText("🔒 请再次输入密码")
        self.confirm_pwd_input.setEchoMode(QLineEdit.EchoMode.Password) 
        main_layout.addWidget(self.confirm_pwd_input)
        main_layout.addSpacing(15)

        # --- 协议勾选 ---
        self.agree_cb = QCheckBox("已同意《用户注册协议》和《隐私保护政策》")
        self.agree_cb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        main_layout.addWidget(self.agree_cb)

        # --- 注册主按钮 ---
        self.register_btn = QPushButton("立即注册")
        self.register_btn.setObjectName("primaryBtn")
        self.register_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) 
        self.register_btn.clicked.connect(self.handle_register) # 绑定注册逻辑
        main_layout.addWidget(self.register_btn)

        # --- 底部返回登录链接 ---
        bottom_layout = QHBoxLayout()
        self.back_btn = QPushButton("⬅ 返回登录") # 这个按钮在 app.py 里被监控着！
        self.back_btn.setObjectName("textBtn")
        self.back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        bottom_layout.addStretch() 
        bottom_layout.addWidget(self.back_btn)
        bottom_layout.addStretch() 
        main_layout.addLayout(bottom_layout)
        # --- 注册主按钮 ---
        self.register_btn = QPushButton("立即注册")
        self.register_btn.setObjectName("primaryBtn")
        self.register_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) 
        
        # 🌟 新增：设置回车键直接触发注册
        self.register_btn.setDefault(True) 
        
        self.register_btn.clicked.connect(self.handle_register)
        self.setLayout(main_layout)

        # 验证码倒计时定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)

    # 🌟 逻辑1：获取验证码倒计时
    def handle_get_code(self):
        phone = self.phone_input.text()
        if len(phone) != 11:
            self.toast = ToastNotification(self, "❌ 请输入正确的 11 位手机号")
            self.toast.show_fading()
            return
            
        # 启动倒计时
        self.code_btn.setEnabled(False)
        self.countdown = 60
        self.code_btn.setText(f"{self.countdown}s 后重发")
        self.timer.start(1000) # 每 1000 毫秒(1秒)执行一次 update_timer
        
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

    # 🌟 逻辑2：注册校验
    def handle_register(self):
        if not self.agree_cb.isChecked():
            self.toast = ToastNotification(self, "请勾选《用户注册协议》和《隐私保护政策》")
            self.toast.show_fading()
            return 

        phone = self.phone_input.text()
        code = self.code_input.text()
        pwd = self.pwd_input.text()
        confirm_pwd = self.confirm_pwd_input.text()

        # 简单判空校验
        if not phone or not code or not pwd:
            self.toast = ToastNotification(self, "❌ 请填写完整的注册信息")
            self.toast.show_fading()
            return

        # 密码一致性校验
        if pwd != confirm_pwd:
            self.toast = ToastNotification(self, "❌ 两次输入的密码不一致！")
            self.toast.show_fading()
            return

        # 校验全通过，模拟注册成功
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("系统提示")
        msg_box.setText("🎉 注册成功！即将返回登录页。")
        msg_box.setIcon(QMessageBox.Icon.NoIcon) 
        msg_box.setStyleSheet("""
            QMessageBox { background-color: #1a1025; }
            QMessageBox QLabel { color: white; font-size: 14px; }
            QMessageBox QPushButton { background-color: #eb4d4b; color: white; border-radius: 5px; padding: 5px 15px; min-width: 60px; }
            QMessageBox QPushButton:hover { background-color: #c0392b; }
        """)
        msg_box.exec()
        
        # 成功后自动清空输入框内容（方便下次打开）
        self.phone_input.clear()
        self.code_input.clear()
        self.pwd_input.clear()
        self.confirm_pwd_input.clear()
        self.agree_cb.setChecked(False)
        
        # 🌟 自动触发“返回登录”按钮的点击事件，实现注册完自动跳转回登录！
        self.back_btn.click()

# 仅供当前文件单独测试运行使用
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RegisterWindow()
    window.show()
    sys.exit(app.exec())