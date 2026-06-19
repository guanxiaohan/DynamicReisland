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
from Utils import *
from Widgets import *

@dataclasses.dataclass
class IslandUISettings:
    BorderRadius: int = 15
    Margins: QMargins = dataclasses.field(default_factory=QMargins)
    ShowCamera: bool = True

defaultIslandUISettings = IslandUISettings(15, QMargins(3, 6, 3, 6), True)

class Island(QWidget):
    def __init__(self, islandID: str, animationBus: AnimationBus, uiSettings: IslandUISettings = defaultIslandUISettings) -> None:
        super().__init__()
        self.islandID = islandID
        self.animationBus = animationBus
        self.UISettings = uiSettings
        self.setupUI()

    def setupUI(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        
        self.container = Container()

        self.animationBus.registerProperty(self, "geometry")

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.container.setGeometry(QRect(0, 0, self.width(), self.height()).marginsRemoved(self.UISettings.Margins))
        return super().resizeEvent(event)