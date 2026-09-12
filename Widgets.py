from Constants import *
from PySide6.QtCore import (QEasingCurve, QEvent, QMargins, QObject, QPoint,
                            QPropertyAnimation, QRect, QSize, Qt, QThread,
                            QThreadPool, Signal)
from PySide6.QtGui import (QAction, QBrush, QCloseEvent, QColor, QCursor,
                           QDesktopServices, QDropEvent, QIcon, QImage,
                           QKeyEvent, QMouseEvent, QMovie, QPainter,
                           QPainterPath, QPen, QPixmap, QResizeEvent, QScreen)
from PySide6.QtMultimedia import QAudio, QSoundEffect
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                               QGraphicsOpacityEffect, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)
from Utils import DataBus, EventBus, IntEnum, dataclasses, validateName, Callable, ScreenState


class Container(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.mainLayout = QGridLayout()
        self.mainLayout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.mainLayout)

class IconOnlyContainer(Container):
    def __init__(self, pixmap: QPixmap | QImage | None = None):
        super().__init__()
        
        self.pixmap: QPixmap
        if isinstance(pixmap, QPixmap):
            self.pixmap = pixmap
        elif pixmap is None:
            self.pixmap = QPixmap(IconSize)
        else:
            self.pixmap = QPixmap(pixmap)

        self.label = QLabel()
        self.label.setFixedSize(IconSize)
        self.label.setPixmap(self.pixmap)
        self.mainLayout.addWidget(self.label)

class BarContainer(Container):
    def __init__(self, screenStateAPI: Callable[[], ScreenState], cameraDiameter: int) -> None:
        super().__init__()

        self.mainLayout.setParent(None)
        self.leftContainer = Container(self)
        self.rightContainer = Container(self)
        self.getScreenState = screenStateAPI
        self.cameraDiameter = cameraDiameter

    def placeContainers(self):
        screenSize = self.getScreenState().hCenter
        size = self.geometry().size()
        topLeft = self.mapToGlobal(self.geometry().topLeft())

    def resizeEvent(self, event: QResizeEvent) -> None:
        return super().resizeEvent(event)

class Panel:
    @dataclasses.dataclass
    class PanelProperties:
        enableFullForm: bool = True
        fullFormSizeHint: QSize | None = None
        enableSimpleForm: bool = True
        simpleFormSizeHint: QSize | None = None
        progressBarEnabled: bool = False
        icon: QPixmap | QImage | None = None
        priority: int = 0
        isInstant: bool = False
        forceStay: bool = False

    class FormState(IntEnum):
        FullForm = 0x01
        SimpleForm = 0x02
        MinimalForm = 0x04
        
    def __init__(self, identifier: str, properties: PanelProperties) -> None:
        if validateName(identifier):
            self.identifier = identifier
        else:
            raise ValueError("Invalid identifier:", identifier)
        
        self.fullFormEnabled = properties.enableFullForm
        self.fullFormSizeHint = properties.fullFormSizeHint
        self.simpleFormEnabled = properties.enableSimpleForm
        self.simpleFormSizeHint = properties.simpleFormSizeHint
        
        self.progressBarEnabled = properties.progressBarEnabled
        self.progressBarValue = 0  # set to -1 to start indeterminate progress bar
        self.progressBarMaximum = 100
        self.formState = self.FormState.FullForm

        self.defaultIcon = properties.icon
        self.fullForm: Container | None = None
        self.simpleForm: Container | None = None
        self.minimalForm = IconOnlyContainer(self.defaultIcon)

        self.priority = properties.priority
        self.isInstant = properties.isInstant

    def loadGlobalAssets(self, dataBus: DataBus, eventBus: EventBus):
        self.dataBus = dataBus
        self.eventBus = eventBus

        self.stateChangeSignal = self.eventBus.register(self, [Panel, self.FormState], self.identifier + ".formStateChanged")
        self.showSignal = self.eventBus.register(self, [Panel], self.identifier + ".showRequested")
        self.hideSignal = self.eventBus.register(self, [Panel], self.identifier + ".hideRequested")
        if self.progressBarEnabled:
            self.progressBarSignal = self.eventBus.register(self, [Panel, int, int], self.identifier + ".progressBarUpdated")
            self.dataBus.initKey(self, self.identifier+".progressBarValue")
            self.dataBus.set(self, self.identifier+".progressBarValue", self.progressBarValue)
            self.dataBus.initKey(self, self.identifier+".progressBarMaximum")
            self.dataBus.set(self, self.identifier+".progressBarMaximum", self.progressBarMaximum)

    def requestFormStateChange(self, newState: FormState):
        self.formState = newState
        self.stateChangeSignal(self, newState)

    def requestShow(self):
        self.showSignal(self)

    def requestHide(self):
        self.hideSignal(self)

    def requestProgressBarUpdate(self, value: int | None = None, maximum: int | None = None):
        require_update = False
        if value is not None and self.progressBarValue != value:
            self.progressBarValue = value
            self.dataBus.set(self, self.identifier+".progressBarValue", value)
            require_update = True
        if maximum is not None and self.progressBarMaximum != maximum:
            self.progressBarMaximum = maximum
            self.dataBus.set(self, self.identifier+".progressBarMaximum", maximum)
            require_update = True
        if require_update:
            self.progressBarSignal(self, self.progressBarValue, self.progressBarMaximum)
    
    def currentContainer(self) -> Container:
        if self.formState == self.FormState.FullForm:
            if not self.fullForm:
                raise RuntimeError("Panel doesn't have a Full Form container")
            return self.fullForm
        
        elif self.formState == self.FormState.SimpleForm:
            if not self.simpleForm:
                raise RuntimeError("Panel doesn't have a Full Form container")
            return self.simpleForm
        
        else:
            return self.minimalForm
        
    def currentSizeHint(self) -> QSize:
        if self.formState == self.FormState.FullForm and self.fullFormSizeHint:
            return self.fullFormSizeHint
        elif self.formState == self.FormState.SimpleForm and self.simpleFormSizeHint:
            return self.simpleFormSizeHint
        else:
            return IconSize

    def currentFormState(self):
        return self.formState