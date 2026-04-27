# -*- coding: utf-8 -*-
import sys # 导入系统工具
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget # 核心框架
from PyQt6.QtCore import Qt # 常量
from login_window import LoginWindow # 导入登录页
from register_window import RegisterWindow # 导入注册页
from ForgetPassword_window import ForgetPasswordWindow # 导入找回页
from main_window import MainWindow # 导入监控主页

class PetNodeApp(QMainWindow): # 应用程序总指挥类
    def __init__(self): # 初始化
        super().__init__() # 父类初始化
        self.init_manager() # 执行管理器设置
    def init_manager(self): # 管理器逻辑配置
        self.setWindowTitle('PETNODE 客户端') # 设置总标题
        self.stacked_widget = QStackedWidget() # 🌟 创建卡牌切换盒子
        self.setCentralWidget(self.stacked_widget) # 设为主核心
        self.login_page = LoginWindow() # 实例化登录页
        self.register_page = RegisterWindow() # 实例化注册页
        self.forget_page = ForgetPasswordWindow() # 实例化忘记页
        self.main_window_page = MainWindow() # 实例化大屏主页
        self.stacked_widget.addWidget(self.login_page) # 加入盒子 Index 0
        self.stacked_widget.addWidget(self.register_page) # 加入盒子 Index 1
        self.stacked_widget.addWidget(self.forget_page) # 加入盒子 Index 2
        self.stacked_widget.addWidget(self.main_window_page) # 加入盒子 Index 3
        # --- 🌟 建立跳转连接网 ---
        self.login_page.register_btn.clicked.connect(self.go_to_register) # 登录 -> 注册
        self.register_page.back_btn.clicked.connect(self.go_to_login) # 注册 -> 登录
        self.login_page.forget_btn.clicked.connect(self.go_to_forget) # 登录 -> 找回
        self.forget_page.back_btn.clicked.connect(self.go_to_login) # 找回 -> 登录
        self.main_window_page.logout_requested.connect(self.go_to_login) # 🌟 主页点头像 -> 登录
        self.login_page.login_successful.connect(self.go_to_main) # 🌟 登录成功 -> 主页
        # --- 🌟 启动配置：直接进入主页 ---
        self.go_to_main() # 初始启动即执行进入大屏主页的动作
    def keyPressEvent(self, event): # 全局回车监听
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter: # 如果敲回车
            idx = self.stacked_widget.currentIndex() # 看现在是哪页
            if idx == 0: self.login_page.handle_login() # 登录逻辑
            elif idx == 1: self.register_page.handle_register() # 注册逻辑
            elif idx == 2: self.forget_page.handle_reset() # 重置逻辑
        super().keyPressEvent(event) # 传递原生事件
    def go_to_register(self): # 跳转至注册页
        self.setFixedSize(450, 550) # 尺寸还原为手机比例
        self.stacked_widget.setCurrentIndex(1) # 翻转到注册页
    def go_to_login(self): # 跳转/注销至登录页
        self.setFixedSize(450, 550) # 尺寸还原为手机比例
        self.setStyleSheet("background-color: #110b17;") # 恢复主体茄紫色背景
        self.stacked_widget.setCurrentIndex(0) # 翻转到登录页
    def go_to_forget(self): # 跳转至找回页
        self.setFixedSize(450, 550) # 手机比例
        self.stacked_widget.setCurrentIndex(2) # 翻转
    def go_to_main(self): # 🌟 进入大监控屏的核心方法
        self.setFixedSize(1200, 800) # 尺寸放大为监控大屏模式
        self.setStyleSheet("background-color: #000000;") # 让边框底漆变黑，防止切换闪白
        self.stacked_widget.setCurrentIndex(3) # 🌟 翻转到大屏监控页
if __name__ == '__main__': # 程序入口
    app = QApplication(sys.argv) # 开启 App 进程
    main_app = PetNodeApp() # 实例化总指挥
    main_app.show() # 显示窗口
    sys.exit(app.exec()) # 循环运行