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
import importlib.util

from concurrent.futures import ThreadPoolExecutor
from Utils import *
from Island import *
import DI_Extension

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
        
        log(f"Found {len(extensionPaths)} extensions")
        
        for x in extensionPaths:
            spec = importlib.util.spec_from_file_location(pathlib.Path(x).name.removesuffix(".py"), x)
            if not spec: continue
            module = importlib.util.module_from_spec(spec)
            if not (module and spec.loader): continue
            spec.loader.exec_module(module)

            try:
                entry = module.extension_entry
            except AttributeError:
                error("No entry found in extension", x)
                continue
            try:
                extension: DI_Extension.Extension = entry()
            except Exception as err:
                error(f"Failed to initialize extension {x}: {err.__class__.__name__}: {err.args}")
                continue
            try:
                extensionInfo: DI_Extension.ExtensionInfo = extension.extensionInfo()
                if not isinstance(extensionInfo, DI_Extension.ExtensionInfo):
                    raise Exception
            except Exception as err:
                error(f"Failed to read extension metadata of", x)
                continue
            
            self._parent.registerObject(extension, extensionInfo.namespace + ".mainExtension")

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
                self.eventBus.removeSignal
            )

            self.extensions[uuid4()] = extension
            log("Starting up extension:", extensionInfo.name)
            extension.initExtension()
            log("Extension initialized:", extensionInfo)


class UIManager(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.islands: dict[str, Island] = {}
        self.animationBus = AnimationBus(self)

    def createIsland(self, islandID: str) -> bool:
        if islandID in self.islands:
            classWarning(self, "Trying to create Island " + islandID + ", but it already exists")
            return False
        
        island = Island(islandID, self.animationBus)
        self.islands[islandID] = island
        return True
        
class DynamicReisland:
    def __init__(self):
        log("Starting Dynamic Reisland")

        log("Initializing Managers...")
        self.DataBus = DataBus()
        self.EventBus = EventBus()
        self.TaskBus = TaskBus(self, max_workers=6, overload_threshold=16)
        self.ServiceBus = ServiceBus(self.DataBus, self.EventBus, self.TaskBus, self)
        self.UIManager = UIManager()
        
        log("Loading Extensions...")
        self.ExtensionHost = ExtensionHost(self)
        self.ExtensionHost.loadExtensions()

    def registerObject(self, subject: object, namespace_or_identifier: str, _id: str | None = None) -> None:
        self.DataBus.registerObject(subject, namespace_or_identifier, _id)
        self.TaskBus.registerObject(subject, namespace_or_identifier, _id)

    
if __name__ == "__main__":
    app = QApplication()
    mainClass = DynamicReisland()
    sys.exit(app.exec())
