from PySide6.QtWidgets import (QWidget, QApplication, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QLineEdit, QDialog, QFrame, QGraphicsOpacityEffect)
from PySide6.QtCore import (Signal, QRect, QPoint, QPropertyAnimation, QEasingCurve, Qt, QObject, QThread, QThreadPool, QMargins, QEvent)
from PySide6.QtGui import (QPen, QPainter, QColor, QBrush, QPainterPath, QAction, QDesktopServices, QCursor, QIcon, QPixmap, QMovie, QScreen, QKeyEvent, QDropEvent, QResizeEvent, QMouseEvent, QCloseEvent)
from PySide6.QtMultimedia import (QSoundEffect, QAudio)

import uuid
import json
import requests
import re
import os
import pathlib
import sys

class Container(QWidget):
    def __init__(self) -> None:
        super().__init__()

class Panel(QWidget):
    def __init__(self) -> None:
        super().__init__()