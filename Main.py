import importlib.util
import os
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID, uuid4

import DI_Extension
from Constants import *
from Island import (Island, IslandUISettings, defaultIslandStyleSheet,
                    defaultIslandUISettings)
from PySide6.QtCore import (QEasingCurve, QEvent, QMargins, QObject, QPoint,
                            QPropertyAnimation, QRect, Qt, QThread,
                            QThreadPool, Signal)
from PySide6.QtGui import (QAction, QBrush, QCloseEvent, QColor, QCursor,
                           QDesktopServices, QDropEvent, QIcon, QKeyEvent,
                           QMouseEvent, QMovie, QPainter, QPainterPath, QPen,
                           QPixmap, QResizeEvent, QScreen)
from PySide6.QtMultimedia import QAudio, QSoundEffect
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                               QGraphicsOpacityEffect, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)
from Utils import (AnimationBus, DataBus, EventBus, ServiceBus, TaskBus,
                   acquireScreenState, classError, classLog, classWarning,
                   error, log, normalizeIdentifier, validateName, warning)
from Widgets import Panel


class ExtensionHost(QObject):
    ExtensionDir = "./Extensions"
    
    def __init__(self, parent: "DynamicReisland"):
        super().__init__()

        self._parent = parent
        self.eventBus = self._parent.EventBus
        self.dataBus = self._parent.DataBus
        self.taskBus = self._parent.TaskBus
        self.serviceBus = self._parent.ServiceBus

        self.extensions: dict[UUID, DI_Extension.Extension] = {}

    def loadExtensions(self):
        sys.modules['DI_Extension'] = DI_Extension
        files = os.listdir(self.ExtensionDir)
        extensionPaths: list[str] = []
        for x in files:
            if os.path.isfile(path := os.path.join(self.ExtensionDir, x)) and path.lower().endswith(".py"):
                extensionPaths.append(path)
            elif os.path.isdir(path) and os.path.exists(os.path.join(path, "Extension.py")):
                extensionPaths.append(path)
        
        classLog(self, f"Found {len(extensionPaths)} extensions")
        
        for x in extensionPaths:
            spec = importlib.util.spec_from_file_location(pathlib.Path(x).name.removesuffix(".py"), x)
            if not spec: continue
            module = importlib.util.module_from_spec(spec)
            if not (module and spec.loader): continue
            spec.loader.exec_module(module)

            try:
                entry = module.extension_entry
            except AttributeError:
                classError(self, "No entry found in extension", x)
                continue
            try:
                extension: DI_Extension.Extension = entry()
            except Exception as err:
                classError(self, f"Failed to initialize extension {x}: {err.__class__.__name__}: {err.args}")
                continue
            try:
                extensionInfo: DI_Extension.ExtensionInfo = extension.extensionInfo()
                if not isinstance(extensionInfo, DI_Extension.ExtensionInfo):
                    raise Exception
            except Exception as err:
                error(f"Failed to read extension metadata of", x)
                continue
            
            classLog(self, "Starting up extension:", extensionInfo.name)
            self._parent.registerObject(extension, extensionInfo.identifier)

            extension.initInterface(
                self._parent.registerObject,
                self.taskBus.createTask,
                self.taskBus.createReusableTask,
                self.serviceBus.registerService,
                self.serviceBus.startService,
                self.serviceBus.stopService,
                self.dataBus.initKey,
                self.dataBus.get,
                self.dataBus.set, 
                self.eventBus.subscribe,
                self.eventBus.unsubscribe,
                self.eventBus.register,
                self.eventBus.removeEvent,
                self.eventBus.removeSignal,
                self._parent.UIManager.registerPanel
            )

            self.extensions[uuid4()] = extension
            extension.initExtension()
            classLog(self, "Extension initialized:", extensionInfo.name, ", with identifier:", extensionInfo.identifier)


class UIManager(QObject):
    def __init__(self, eventBus: EventBus, dataBus: DataBus, parent: "DynamicReisland") -> None:
        super().__init__()
        self._parent = parent
        self.islands: dict[UUID, Island] = {}
        self.islandObjects: list[Island] = []
        self.islandPanelQueue: dict[UUID, list[Panel]] = {}
        self.panels: dict[str, Panel] = {}
        self.animationBus = AnimationBus(self)
        self.eventBus = eventBus
        self.dataBus = dataBus
        self._subjects: dict[int, str] = {}
        self._namespace_members: dict[str, set[int]] = {}  # namespace -> {subject_ids}
        self._storage: dict[str, Any] = {}  # "namespace.key" -> value

        self.screenState = acquireScreenState()
        self.createIsland(defaultIslandUISettings, None)

    def registerObject(self, subject: object, namespace_or_identifier: str, _id: str | None = None) -> None:
        namespace, _ = normalizeIdentifier(namespace_or_identifier, _id)
        sid = id(subject)
        self._subjects[sid] = namespace

        if namespace not in self._namespace_members:
            self._namespace_members[namespace] = set()

        self._namespace_members[namespace].add(sid)

    def _get_verified_ns(self, subject: object) -> str:
        """内部校验：确保主体已注册，返回其所属的 namespace"""
        ns = self._subjects.get(id(subject))
        if not ns:
            raise PermissionError("Access Denied: Subject is not registered to any namespace in DataBus.")
        return ns

    def getScreenState(self):
        return self.screenState

    def createIsland(self, settings: IslandUISettings, withPanel: Panel | None = None) -> UUID:
        island = Island(uuid4(), self.animationBus, self.getScreenState, settings)

        if not self.islands:
            island.setGeometry(QRect(QPoint(int(self.screenState.hCenter - settings.MinimalSize.width() / 2), -settings.MinimalSize.height()), settings.MinimalSize))
        else:
            island.setGeometry(QRect(QPoint(int(self.screenState.hCenter - settings.MinimalSize.width() / 2), 0), settings.MinimalSize))

        self.islands[island.islandID] = island
        self.islandObjects.append(island)
        self.islandPanelQueue[island.islandID] = []

        if withPanel:
            island.panel = withPanel
        
        island.show()
        self.rearrange()
        return island.islandID
    
    def destroyIsland(self, ID: UUID):
        if ID not in self.islands:
            raise KeyError("No island found: {}")
        
        island = self.islands[ID]
        island.flags |= island.Flag.ToRecycle
        self.rearrange()

    def registerPanel(self, object: object, panel: Panel):
        self._get_verified_ns(object)
        identifier = panel.identifier
        if identifier in self.panels:
            raise RuntimeError("Panel already registered:", identifier)
        self.panels[identifier] = panel
        
        self._parent.registerObject(panel, panel.identifier)
        panel.loadGlobalAssets(self.dataBus, self.eventBus)
        self.eventBus.subscribe(self, self.panelShowRequested, identifier + ".showRequested")

    def destroyPanel(self, panelID: UUID):
        ...

    def islandCount(self) -> int:
        return len(self.islands)

    def rearrange(self):
        if not self.islands:
            return
        
        if self.islandCount() == 1:
            island = self.islandObjects[0]
            islandSize = island.currentSizeHint()
            newGeometry = QRect(int(self.screenState.hCenter - islandSize.width() / 2), 0, islandSize.width(), islandSize.height())
            self.animationBus.createAnimation(island.geometryPropertyID,
                                              AnimationBus.ValueWhenStart,
                                              newGeometry, 800, False, AnimationBus.Spring).enqueue()
            return
        
        originalGeometryList = {x: self.islands[x].geometry() for x in self.islands}
        newGeometryList: dict[UUID, QRect] = {}

        for x in self.islands:
            ...


    def panelShowRequested(self, panel: Panel):
        classLog(self, "Panel requested to show:", panel.identifier)
        # Allocate an island to the panel
        for i, x in self.islands.items():
            x.setPanel(panel)
            break

    def panelHideRequested(self, panel: Panel):
        ...

    def panelProgressBarUpdated(self, panel: Panel, value: int, maximum: int):
        ...

    def panelFormStateChanged(self, panel: Panel, formState: Panel.FormState):
        ...

    def screenChanged(self):
        self.screenState = acquireScreenState()
        self.rearrange()

    def recycleIsland(self, islandID: UUID):
        island = self.islands[islandID]
        island.freeResources()
        self.animationBus.freeProperty(island.geometryPropertyID)
        self.islands.pop(islandID)
        self.islandObjects.remove(island)
        self.islandPanelQueue.pop(islandID)

class DynamicReisland:
    def __init__(self):
        log("Starting DynamicReisland")

        log("Initializing Managers...")
        self.DataBus = DataBus()
        self.EventBus = EventBus()
        self.TaskBus = TaskBus(self, max_workers=6, overload_threshold=16)
        self.ServiceBus = ServiceBus(self.DataBus, self.EventBus, self.TaskBus, self)
        self.UIManager = UIManager(self.EventBus, self.DataBus, self)
        self.registerObject(self.UIManager, "DynamicReisland.UIManager")
        
        log("Loading Extensions...")
        self.ExtensionHost = ExtensionHost(self)
        self.ExtensionHost.loadExtensions()

    def registerObject(self, subject: object, namespace_or_identifier: str, _id: str | None = None) -> None:
        self.DataBus.registerObject(subject, namespace_or_identifier, _id)
        self.TaskBus.registerObject(subject, namespace_or_identifier, _id)
        self.UIManager.registerObject(subject, namespace_or_identifier, _id)

    
if __name__ == "__main__":
    app = QApplication()
    mainClass = DynamicReisland()
    app.primaryScreenChanged.connect(mainClass.UIManager.rearrange)
    sys.exit(app.exec())
