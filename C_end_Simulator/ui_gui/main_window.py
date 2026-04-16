# -*- coding: utf-8 -*-
import sys
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QApplication, QFrame, QGraphicsOpacityEffect)
from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, pyqtSignal, QRect, QPoint, QVariantAnimation
from PyQt6.QtGui import QFont, QCursor, QPixmap, QIcon, QColor, QPainter, QPen

# ==========================================
# 🌟 自定义组件：明日方舟风格汉堡折叠按钮
# 实现逻辑：三条杠，点击后上下旋转成X，中间缩短消失
# ==========================================
class ArknightsMenuButton(QWidget):
    clicked = pyqtSignal() # 定义点击信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40) # 固定按钮大小
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor)) # 鼠标变小手
        self.is_x = False # 状态标记：是三杠还是X
        self.anim_progress = 0.0 # 动画进度 0.0 -> 1.0
        
        # 属性动画：控制 progress 变量从 0 变到 1
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(300) # 动画耗时 0.3 秒
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic) # 平滑曲线
        self.animation.valueChanged.connect(self.update_progress)

    def update_progress(self, value):
        self.anim_progress = value # 更新进度值
        self.update() # 触发重绘 paintEvent

    def mousePressEvent(self, event): # 鼠标点击事件
        self.is_x = not self.is_x # 切换状态
        self.animation.setStartValue(1.0 if not self.is_x else 0.0)
        self.animation.setEndValue(0.0 if not self.is_x else 1.0)
        self.animation.start() # 开始变形动画
        self.clicked.emit() # 发出点击信号
        super().mousePressEvent(event)

    def paintEvent(self, event): # 核心：手动绘制三条杠
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing) # 抗锯齿
        pen = QPen(QColor("white"), 3) # 白色，线宽 3
        pen.setCapStyle(Qt.PenCapStyle.FlatCap) # 线条末端平整
        painter.setPen(pen)

        p = self.anim_progress # 简化进度变量
        cx, cy = self.width() / 2, self.height() / 2 # 中心点
        line_w = 24 / 2 # 半线宽

        # 🌟 计算逻辑：
        # 上杠：从 y= -8 旋转到 45度
        # 中杠：宽度从 100% 缩减到 0%
        # 下杠：从 y= +8 旋转到 -45度

        # 1. 中间那条杠 (渐隐缩短)
        mid_w = line_w * (1 - p)
        if mid_w > 0:
            painter.drawLine(QPoint(int(cx - mid_w), int(cy)), QPoint(int(cx + mid_w), int(cy)))

        # 2. 上面那条杠 (下移并旋转)
        painter.save()
        painter.translate(cx, cy - 8 + (8 * p)) # 向中心移动
        painter.rotate(45 * p) # 旋转 45 度
        painter.drawLine(QPoint(int(-line_w), 0), QPoint(int(line_w), 0))
        painter.restore()

        # 3. 下面那条杠 (上移并旋转)
        painter.save()
        painter.translate(cx, cy + 8 - (8 * p)) # 向中心移动
        painter.rotate(-45 * p) # 旋转 -45 度
        painter.drawLine(QPoint(int(-line_w), 0), QPoint(int(line_w), 0))
        painter.restore()

# ==========================================
# 🌟 自定义组件：侧边栏导航项 (带蹦出动画)
# ==========================================
class NavItem(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(60) # 增加高度，显得更大气
        self.setCheckable(True) # 可选中
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #FFFFFF;
                border: none;
                padding-left: 50px;
                font-size: 20px; /* 更大的字体 */
                font-weight: bold;
                text-align: left;
                border-left: 5px solid transparent;
            }
            QPushButton:hover { background-color: rgba(235, 77, 75, 40); }
            QPushButton:checked {
                background-color: rgba(235, 77, 75, 80);
                border-left: 5px solid #eb4d4b;
            }
        """)

# ==========================================
# 🏠 主监控大屏
# ==========================================
class MainWindow(QWidget):
    logout_requested = pyqtSignal() # 注销信号

    def __init__(self):
        super().__init__()
        self.setFixedSize(1200, 800) # 主窗口尺寸
        self.is_nav_open = False
        self.nav_width = int(1200 * 0.6) # 🌟 设定导航栏宽度为 60%
        self.init_ui()

    def init_ui(self):
        # 1. 顶部黑条 (TopBar)
        self.top_bar = QFrame(self)
        self.top_bar.setGeometry(0, 0, 1200, 60)
        self.top_bar.setStyleSheet("background-color: #000000; border-bottom: 1px solid #333333;")
        
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)

        # Logo
        self.logo_label = QLabel()
        if os.path.exists(r"D:\软件设计\logo.png"):
            self.logo_label.setPixmap(QPixmap(r"D:\软件设计\logo.png").scaled(120, 40, Qt.AspectRatioMode.KeepAspectRatio))
        top_layout.addWidget(self.logo_label)
        top_layout.addStretch()

        # 用户头像按钮
        self.avatar_btn = QPushButton()
        self.avatar_btn.setFixedSize(40, 40)
        avatar_path = r"D:\软件设计\use's_basic_avatar.png"
        if os.path.exists(avatar_path):
            self.avatar_btn.setIcon(QIcon(QPixmap(avatar_path).scaled(40, 40)))
            self.avatar_btn.setIconSize(QSize(40, 40))
        self.avatar_btn.setStyleSheet("border: none; background: transparent;")
        self.avatar_btn.clicked.connect(self.logout_requested.emit) # 点击注销
        top_layout.addWidget(self.avatar_btn)
        top_layout.addSpacing(15)

        # 🌟 汉堡动效按钮
        self.menu_btn = ArknightsMenuButton(self.top_bar)
        self.menu_btn.clicked.connect(self.toggle_nav)
        top_layout.addWidget(self.menu_btn)

        # 2. 茄紫色主体内容区
        self.body_area = QWidget(self)
        self.body_area.setGeometry(0, 60, 1200, 740)
        self.body_area.setStyleSheet("background-color: #110b17;")
        
        body_layout = QVBoxLayout(self.body_area)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("马尔可夫链监控大屏 (开发中...)")
        title.setStyleSheet("color: #eb4d4b; font-size: 24px; font-weight: bold;")
        body_layout.addWidget(title)

        # 3. 🌟 黑色滤镜层 (点击导航时背景变暗)
        self.mask = QWidget(self)
        self.mask.setGeometry(0, 60, 1200, 740)
        self.mask.setStyleSheet("background-color: rgba(0, 0, 0, 200);") # 深黑透明
        self.mask.hide()

        # 4. 🌟 侧边导航栏 (60% 宽度)
        self.nav_drawer = QFrame(self)
        self.nav_drawer.setGeometry(1200, 60, self.nav_width, 740) # 初始在屏幕右侧外
        self.nav_drawer.setStyleSheet("background-color: rgba(17, 11, 23, 250); border-left: 1px solid #444444;")
        
        self.nav_layout = QVBoxLayout(self.nav_drawer)
        self.nav_layout.setContentsMargins(0, 100, 0, 0)
        self.nav_layout.setSpacing(10)
        self.nav_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 创建导航项
        self.menu_items = []
        texts = ["INDEX / 首页", "INFORMATION / 情报", "OPERATOR / 干员", "WORLD / 设定", "MEDIA / 泰拉万象"]
        for t in texts:
            item = NavItem(t)
            self.menu_items.append(item)
            self.nav_layout.addWidget(item)
            item.hide() # 初始隐藏，用于蹦出动画

    def toggle_nav(self):
        # 页面展开/收起的动画
        self.is_nav_open = not self.is_nav_open
        
        # 1. 侧边栏平移动画
        self.drawer_anim = QPropertyAnimation(self.nav_drawer, b"pos")
        self.drawer_anim.setDuration(400)
        self.drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        if self.is_nav_open:
            self.mask.show() # 显示背景黑色滤镜
            self.drawer_anim.setStartValue(QPoint(1200, 60))
            self.drawer_anim.setEndValue(QPoint(1200 - self.nav_width, 60))
            self.drawer_anim.start()
            # 🌟 触发导航项“一个一个蹦出来”
            self.start_staggered_animation()
        else:
            self.mask.hide() # 隐藏滤镜
            self.drawer_anim.setStartValue(QPoint(1200 - self.nav_width, 60))
            self.drawer_anim.setEndValue(QPoint(1200, 60))
            self.drawer_anim.start()
            for item in self.menu_items: item.hide() # 隐藏菜单项

    # 🌟 核心动画：导航项逐个蹦出
    def start_staggered_animation(self):
        for i, item in enumerate(self.menu_items):
            item.show()
            # 为每个按钮创建从右往左“蹦”的动画
            anim = QPropertyAnimation(item, b"pos")
            anim.setDuration(500)
            # 延迟触发：每个按钮比前一个晚 80 毫秒
            QTimer.singleShot(i * 80, anim.start)
            
            # 设置动画起始位置（在按钮正常位置的右边 100 像素）
            start_pos = QPoint(100, item.y()) # 这里的相对坐标
            end_pos = QPoint(0, item.y())
            
            anim.setStartValue(start_pos)
            anim.setEndValue(end_pos)
            anim.setEasingCurve(QEasingCurve.Type.OutBack) # 带一点回弹效果，更有“蹦”的感觉

from PyQt6.QtCore import QTimer # 导入定时器

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())