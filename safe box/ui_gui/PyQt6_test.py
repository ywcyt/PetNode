import sys
from PyQt6.QtWidgets import QApplication, QLabel

if __name__ == "__main__":
    app = QApplication(sys.argv)
    label = QLabel('PyQt6 安装成功！')
    label.show()
    sys.exit(app.exec())