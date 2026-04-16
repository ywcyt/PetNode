# -*- coding: utf-8 -*-
import sys # 导入系统模块
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QCheckBox, QApplication,
                             QGraphicsOpacityEffect, QMessageBox) # 导入常用的 PyQt6 窗口组件
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtSignal # 🌟 导入 pyqtSignal 用于自定义信号
from PyQt6.QtGui import QFont, QCursor # 导入字体和鼠标样式

class ToastNotification(QWidget): # 定义暗黑风 Toast 提示组件
    def __init__(self, parent, message, duration_ms=3000): # 初始化提示框
        super().__init__(parent) # 调用父类初始化
        self.duration_ms = duration_ms # 设置持续时间
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow) # 设置无边框子窗口
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) # 设置背景透明
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) # 设置鼠标点击穿透
        layout = QVBoxLayout() # 创建垂直布局
        layout.setContentsMargins(0, 0, 0, 0) # 清除布局边距
        self.setLayout(layout) # 应用布局
        label = QLabel(message) # 创建消息标签
        label.setAlignment(Qt.AlignmentFlag.AlignCenter) # 设置文字居中
        label.setStyleSheet("""
            QLabel {
                background-color: #333333; 
                color: #FFFFFF;
                border-radius: 12px; 
                padding: 12px 25px;
                font-size: 13px;
                border: 1px solid #444444; 
            }
        """) # 为提示框设置样式
        layout.addWidget(label) # 将标签加入布局
        self.opacity_effect = QGraphicsOpacityEffect(self) # 创建透明度特效
        self.setGraphicsEffect(self.opacity_effect) # 应用特效
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity") # 创建透明度动画
        self.animation.setDuration(1000) # 设置动画时间 1 秒
        self.animation.setStartValue(1.0) # 初始不透明
        self.animation.setEndValue(0.0) # 终点全透明
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic) # 设置平滑曲线
        self.animation.finished.connect(self.close) # 动画结束关闭提示
        self.timer = QTimer(self) # 创建定时器
        self.timer.setSingleShot(True) # 设置为单次触发
        self.timer.timeout.connect(self.fade_out) # 时间到触发淡出
    def show_fading(self): # 显示提示并开始倒计时
        self.adjustSize() # 调整大小
        parent_rect = self.parent().rect() # 获取父窗口大小
        toast_rect = self.rect() # 获取提示框大小
        x = (parent_rect.width() - toast_rect.width()) // 2 # 计算居中 X
        y = (parent_rect.height() - toast_rect.height()) // 2 # 计算居中 Y
        self.move(QPoint(x, y)) # 移动到中央
        self.show() # 显示窗口
        self.timer.start(self.duration_ms) # 开始计时
    def fade_out(self): # 开始淡出动画
        self.animation.start() # 执行动画

class LoginWindow(QWidget): # 定义登录窗口类
    login_successful = pyqtSignal() # 🌟 核心：定义登录成功的自定义信号
    def __init__(self): # 构造函数
        super().__init__() # 调用父类构造
        self.init_ui() # 初始化界面
    def init_ui(self): # 界面初始化方法
        self.setWindowTitle('PETNODE 登录') # 设置标题
        self.setFixedSize(450, 550) # 设置固定大小
        self.setStyleSheet("""
            QWidget { background-color: #110b17; color: #FFFFFF; font-family: 'Montserrat', 'Microsoft YaHei'; }
            QLabel#titleLabel { font-size: 28px; font-weight: bold; letter-spacing: 2px; margin-top: 30px; margin-bottom: 30px; }
            QLineEdit { background-color: #333333; color: #FFFFFF; border: 2px solid #555555; border-radius: 8px; padding: 12px; font-size: 14px; }
            QLineEdit:focus { border: 2px solid #aaaaaa; }
            QPushButton#eyeBtn { background-color: #333333; color: gray; border: 2px solid #555555; border-radius: 8px; font-size: 16px; }
            QPushButton#eyeBtn:hover { background-color: #444444; color: white; border: 2px solid #aaaaaa; }
            QPushButton#primaryBtn { background-color: #eb4d4b; color: #FFFFFF; border-radius: 25px; font-size: 16px; font-weight: bold; letter-spacing: 2px; height: 50px; margin-top: 20px; }
            QPushButton#primaryBtn:hover { background-color: #c0392b; }
            QPushButton#textBtn { background-color: transparent; color: gray; border: none; font-size: 13px; }
            QPushButton#textBtn:hover { color: white; }
            QCheckBox { color: gray; font-size: 12px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px; border: 1px solid gray; }
            QCheckBox::indicator:unchecked { background-color: transparent; }
            QCheckBox::indicator:checked { background-color: #eb4d4b; border: 1px solid #eb4d4b; image: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAAsTAAALEwEAmpwYAAABOElEQVQ4y2P4//8/AyUYIxHGE8fHx9mR5Ojo6Bh4eHhcDAwM7AyEQI74+Hh9NjbG9vb2ZpSUlKRLS0urMjIy8pKSkq7MzMz89PT0pujo6G55efme3NzcI5KSks4U45mZmU5KSkreU4xHRUVlcXJyisTExGRzcXGxJyUlWRsbG8vExMTIQUlJSURFRUUMiYmJ2ZKSkiWjo6Nzk5KSjox44vHx8fpSUlL84uLipEJCQnIJCQnGZmZmkpaWlubk5OToS0lJiUZGRvIxMjJyER4A4uPj9ampqXFycXGRAXkEQHwKAGW4o6OjA8V4bGxskKSkJBMYMDExMcE4QEAwAAkECAgGIIEIAcGAGQj4+PiM5OTkGElKSppKSUl5SkpKWkpKSrgy4onGxsbyUlJSvOLi4phC4hEB5E8AZmH4X8w4C0wAAAAASUVORK5CYII=); }
        """) # 设置全局 CSS 样式
        main_layout = QVBoxLayout() # 创建主布局
        main_layout.setContentsMargins(40, 20, 40, 20) # 设置页边距
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # 顶部对齐
        title_label = QLabel("PETNODE 登录") # 创建标题标签
        title_label.setObjectName("titleLabel") # 设置 ID 供 CSS 调用
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # 居中对齐
        main_layout.addWidget(title_label) # 加入布局
        self.phone_input = QLineEdit() # 创建手机输入框
        self.phone_input.setPlaceholderText("👤 请输入手机号") # 设置提示语
        main_layout.addWidget(self.phone_input) # 加入布局
        main_layout.addSpacing(10) # 间距
        pwd_layout = QHBoxLayout() # 创建密码行水平布局
        self.pwd_input = QLineEdit() # 创建密码框
        self.pwd_input.setPlaceholderText("🔒 请输入密码") # 设置提示语
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password) # 默认密码模式
        pwd_layout.addWidget(self.pwd_input) # 加入布局
        self.pwd_eye_btn = QPushButton("🙈") # 创建小眼睛按钮
        self.pwd_eye_btn.setObjectName("eyeBtn") # 设置样式 ID
        self.pwd_eye_btn.setFixedSize(45, 45) # 固定大小
        self.pwd_eye_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) # 设置小手光标
        self.pwd_eye_btn.clicked.connect(self.toggle_pwd_visibility) # 绑定显示隐藏功能
        pwd_layout.addWidget(self.pwd_eye_btn) # 加入布局
        main_layout.addLayout(pwd_layout) # 将密码行加入主布局
        main_layout.addSpacing(15) # 间距
        self.agree_cb = QCheckBox("已同意《用户注册协议》和《隐私保护政策》") # 创建协议勾选框
        self.agree_cb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) # 设置光标
        main_layout.addWidget(self.agree_cb) # 加入布局
        self.login_btn = QPushButton("登 录") # 创建登录按钮
        self.login_btn.setObjectName("primaryBtn") # 设置样式 ID
        self.login_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) # 设置光标
        self.login_btn.clicked.connect(self.handle_login) # 绑定登录校验逻辑
        main_layout.addWidget(self.login_btn) # 加入布局
        bottom_layout = QHBoxLayout() # 创建底部链接布局
        self.register_btn = QPushButton("账号注册") # 创建注册链接
        self.register_btn.setObjectName("textBtn") # 文本按钮样式
        self.register_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) # 设置光标
        self.forget_btn = QPushButton("忘记密码？") # 创建忘记密码链接
        self.forget_btn.setObjectName("textBtn") # 文本按钮样式
        self.forget_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) # 设置光标
        bottom_layout.addWidget(self.register_btn) # 加入底部
        bottom_layout.addStretch() # 弹簧挤压
        bottom_layout.addWidget(self.forget_btn) # 加入底部
        main_layout.addLayout(bottom_layout) # 底部行加入主布局
        self.setLayout(main_layout) # 应用主布局
    def toggle_pwd_visibility(self): # 切换密码显示隐藏
        if self.pwd_input.echoMode() == QLineEdit.EchoMode.Password: # 如果是隐藏的
            self.pwd_input.setEchoMode(QLineEdit.EchoMode.Normal) # 改成可见
            self.pwd_eye_btn.setText("👁️") # 改成睁眼
        else: # 如果是可见的
            self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password) # 改成隐藏
            self.pwd_eye_btn.setText("🙈") # 改成闭眼
    def handle_login(self): # 处理登录校验
        if not self.agree_cb.isChecked(): # 如果没勾选协议
            self.toast = ToastNotification(self, "请勾选《用户注册协议》和《隐私保护政策》") # 创建提示
            self.toast.show_fading() # 显示提示
            return # 阻断运行
        phone = self.phone_input.text() # 获取输入的手机号
        pwd = self.pwd_input.text() # 获取输入的密码
        if phone == "13112345678" and pwd == "ABCabc123": # 🌟 匹配测试账号
            QMessageBox.information(self, "系统提示", "✅ 登录成功！") # 弹出成功对话框
            self.login_successful.emit() # 🌟 核心：发射成功信号，通知 app.py 切换页面
        else: # 账号密码错误
            msg_box = QMessageBox(self) # 创建消息框
            msg_box.setWindowTitle("登录失败") # 设置标题
            msg_box.setText("❌ 账号或密码输入错误，请重新输入") # 设置内容
            msg_box.setIcon(QMessageBox.Icon.NoIcon) # 无图标
            msg_box.setStyleSheet("QMessageBox { background-color: #1a1025; } QLabel { color: white; }") # 暗黑样式
            msg_box.exec() # 执行弹窗
            self.pwd_input.clear() # 清空密码框
            self.pwd_eye_btn.setText("🙈") # 重置眼睛
            self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password) # 重置隐藏
            self.pwd_input.setFocus() # 重新聚焦打字