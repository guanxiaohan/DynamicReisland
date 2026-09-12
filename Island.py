import dataclasses
from enum import IntEnum, IntFlag
from typing import Callable
from uuid import UUID, uuid4

from Constants import *
from PySide6.QtCore import (QEasingCurve, QEvent, QMargins, QObject, QPoint,
                            QPropertyAnimation, QRect, QSize, Qt, QThread,
                            QThreadPool, Signal)
from PySide6.QtGui import (QAction, QBrush, QCloseEvent, QColor, QCursor,
                           QDesktopServices, QDropEvent, QIcon, QKeyEvent,
                           QMouseEvent, QMovie, QPainter, QPainterPath,
                           QPaintEvent, QPen, QPixmap, QResizeEvent, QScreen)
from PySide6.QtMultimedia import QAudio, QSoundEffect
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                               QGraphicsOpacityEffect, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)
from Utils import AnimationBus, ScreenState
from Widgets import Container, Panel

defaultIslandStyleSheet = """
.Island {
    background-color: transparent;
}
.Container {
    background-color: transparent;
}
"""


@dataclasses.dataclass
class IslandUISettings:
    BorderRadius: int = 15 # px
    Margins: QMargins = dataclasses.field(default_factory=lambda: QMargins(6, 3, 6, 3))
    ShowCamera: bool = True
    EnableProgressBar: bool = True
    StyleSheet: str = defaultIslandStyleSheet
    PanelTransitionDuration: int = 800 # ms
    MinimalSize: QSize = QSize(30, 30)

defaultIslandUISettings = IslandUISettings()

class Island(QWidget):
    class Flag(IntFlag):
        NoFlag = 0x00
        ToRecycle = 0x01

    def __init__(self, islandID: UUID, animationBus: AnimationBus, screenStateAPI: Callable[[], ScreenState], uiSettings: IslandUISettings = defaultIslandUISettings) -> None:
        super().__init__()
        self.islandID = islandID
        self.animationBus = animationBus
        self.UISettings = uiSettings
        self.getScreenState = screenStateAPI
        self.panel: Panel | None = None
        self.flags = self.Flag.NoFlag
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
        
        _, self.geometryPropertyID = self.animationBus.registerProperty(self, "geometry")
        self.container = Container()
        self.container.setObjectName("islandContainer")

        self.opacityEffect = ... # TODO

        self.setStyleSheet(self.UISettings.StyleSheet)

    def transitionToPanel(self, panel: Panel | None):
        self.container.mainLayout.takeAt(0)
        if not panel:
            # TODO
            ...

    def setPanel(self, panel: Panel | None):
        self.panel = panel
        if self.container.mainLayout.count() >= 0:
            self.container.mainLayout.takeAt(0)
        if panel:
            self.container.mainLayout.addWidget(panel.currentContainer())

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.container.setGeometry(QRect(0, 0, self.width(), self.height()).marginsRemoved(self.UISettings.Margins))
        return super().resizeEvent(event)
    
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        rect = self.rect()
        radius = self.UISettings.BorderRadius
        
        draw_rect = rect.adjusted(0, 0, 0, 0)
        path.addRoundedRect(draw_rect, radius, radius)
        
        painter.setPen(QPen(IslandBackgroundColor))
        painter.fillPath(path, QBrush(IslandBackgroundColor))
        
        if self.panel and self.panel.progressBarEnabled:
            self.drawProgress(painter, draw_rect, radius)

        if self.UISettings.ShowCamera:
            cameraRect = self.getScreenState().cameraRect
            painter.setBrush(QBrush(CameraColor))
            painter.drawEllipse(self.mapFromGlobal(cameraRect.center()), cameraRect.width() / 2, cameraRect.height() / 2)
            
        return super().paintEvent(event)

    def drawProgress(self, painter: QPainter, draw_rect: QRect, radius: int):
        ...

    def freeResources(self):
        self.hide()
        self.animationBus.freeProperty(self.geometryPropertyID)

    def currentSizeHint(self):
        if self.panel:
            return self.panel.currentSizeHint()
        else:
            return self.UISettings.MinimalSize


"""
Island Framework

class UIManager
class Island(QWidget)
class Container(QWidget)
class Panel
    @dataclasses.dataclass
    class PanelProperties
UIManager管控全局Island布局、坐标变化与Panel层级调控。
抽象层面，一个Island为一个“岛”（一个主控件）。
Island设计主题为深色模式。
而Island内使用的QWidget排版容器为Container，用于提供高级动画支持。
Island本身具有一定边距与圆角设定，以及鼠标悬浮时的微放大动画。
Island提供API，用于内部Panel向外显示进度条。该进度条逻辑较为复杂：
当Island宽度大于阈值时，进度条的位置是Island的下边缘（考虑圆角对显示区域的缩小作用）
当Island宽度小于阈值时，进度条展示为环绕Island的一个圈，从顶部中间开始顺时针旋转。
无论是以上哪种，抑或是二者的过渡区段，均需要平滑过渡。进度条颜色为白色，但可提供API自定义。
Island内部的显示内容由一个Panel决定。理论上来说，Panel定义了一个面板，但又不只是一个面板。
出于艺术设计目的，Panel内部控件在排版时需保证“摄像头”区域永远空出。
Panel内部一般需自写其完全形态与缩略形态，分别记为fullForm与simpleForm，分别放于两个Container中。
Panel的主要功能、完整视图均位于fullForm中，主要在聚焦于Island时使用。
而simpleForm是节省空间的形态，用于常驻挂在屏幕顶端使用。
通常来说，Panel提供方便的接口，可以快速地定义Panel的simpleForm（例如，“摄像头”左边一个图标，右边一个单词）。
当然，simpleForm也可以直接获取Container进行自定义。
Panel还需定义该面板中的其他必要排版信息，
如该面板的优先级，是否支持fullForm/simpleForm，是否使用进度条API，是否需要独立Island进行显示，是否允许折叠到侧Island中，等等。
Panel可与EventBus，DataBus等进行交流，用于UI更新。
原则上，Panel只应该关心UI显示层面的逻辑。底层更新逻辑由UIManager与自定义Service类控制。
在注册Panel时，ExtensionHost会为其赋予registerObject, registerEvent等API。
Panel具有的API有：
Panel.requestShow()
Panel.requestHide()
Panel.updateProgressBar(current: int = -1, max: int = -1)
Panel需实现的方法有：
Panel.initializeUI()
为方便开发，定义一个BarContainer，用于常见的条形岛。它将岛拆分成左右两块，分别为leftContainer与rightContainer，
自动计算并空出中间的摄像头区域（如有），并提供setLeftIcon与setRightIcon来设置Panel的左右图标。
为方便开发，定义一个NotificationContainer，用于常见的大型岛。它将顶部拆分成左右两块，而下边的区域则是一整块contentContainer，类似于手机通知。上边同样支持左右图标设置。
图标的设置需平滑过渡：图标从左/右侧平滑移入，连带内部Container内容移动，且更改图标时需交叉淡入淡出。
UIManager支持多岛并存，用于提升空间利用率，以及在一个Island占位时提供更多显示机会。
主逻辑为优先屏幕顶部中间的默认Island，如果其他高优先级或重要事件的Island请求，但无法空出中间的Island的话，
那么会新创建一个simpleForm的Island，显示在中间Island的右边，如果右边也被占，那么就是第三个Island，左边，根据实际宽度情况，以此类推。
主Island默认居中，但有时为了平衡视觉，在允许的情况下，可以适当偏移（需要Island当前的form继承了BarContainer）
Panel还允许设定defaultIcon，用于极简模式的折叠显示。（极简模式仅剩一个Icon）
此外，还提供一些预定义的控件，用于优雅设计。
class Label 继承了QLabel，可用于平滑过渡文本显示。
class PushButton 继承了QPushButton，定义了样式，流畅用于EventBus交互。
class AlternatingLabel 继承了Label，可用于自动淡入淡出轮换显示文本。
class LineEdit 继承了QLineEdit，一个输入控件。

以一个音乐播放器控件举例：
class MediaControlExtension(DI_Extension.Extension)
class MediaControlPanel(DI_Extension.Panel):
    def __init__(self, playPauseSignal: DRI_Signal):
        super().__init__()
        self.properties = self.PanelProperties(identifier = "DynamicReisland.MediaControlPanel", enableFullForm = True, enableSimpleForm = True)
        self.playPauseSignal = playPauseSignal
    
    def initializeUI(self):
        self.fullForm = NotificationContainer()
        self.simpleForm = IconLabelContainer()

        self.leftLabel = Label()
        self.rightLabel = Label()
        self.fullForm.leftContainer.mainlayout.addWidget(self.leftLabel)
        ...

        self.playPauseButton = PushButton()
        self.playPauseButton.whenClicked(self.playPauseSignal)
        self.fullForm.contentContainer.addWidget(self.playPauseButton)
        ...

    def updateInfo(self, info: dict):
        self.fullForm.leftContainer.setIcon(xxx)
        self.simpleForm.leftContainer.setIcon(xxx)
        self.playPauseButton.setIcon(xxx)
        ...

...
self.mediaPanel = self.MediaControlPanel()
self.registerObject(self.mediaPanel, "DynamicReisland.MediaControlPanel")
signal = self.eventBus.register(self.MediaService, [dict], "DynamicReisland.mediaInfoChanged")
self.eventBus.subscribe(self.mediaPanel, self.mediaPanel.updateInfo, "DynamicReisland.mediaInfoChanged")
self.registerPanel(self.mediaPanel)

"""

"""
等待实现的逻辑：
1，Island自动重排：rearrange在面对多个岛时，自动重排它们：
将所有panel为FullForm的Island置于中间，自上向下堆叠。
将所有panel为SimpleForm的Island置于FullForm两边，左右平均分布。
将所有panel为MinimalForm的Island置于SimpleForm左右两边，共同左右平均分布。
2，处理panelShowRequested与panelHideRequested
将所有Island上的Panel重排或者重新分配，尽可能不开新Island，重排时近距离优先。
3，处理Panel进度条显示
"""