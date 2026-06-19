import logging
import pathlib
import dataclasses
from uuid import uuid4, UUID
from enum import IntEnum

from PySide6.QtCore import (QEasingCurve, QObject, QParallelAnimationGroup,
                            QPoint, QPropertyAnimation, QRect,
                            QSequentialAnimationGroup, QVariantAnimation, Signal, SignalInstance)
from PySide6.QtGui import QGuiApplication

from typing import Any

RootDir = pathlib.Path(__file__).resolve().parent
LOG_FILE = RootDir / "DynamicReisland.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(asctime)s | %(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def _class_name(source) -> str:
    if isinstance(source, str):
        return source
    return source.__class__.__name__

def log(*message) -> None:
    logger.info(" ".join(map(str, message)))

def warning(*message) -> None:
    logger.warning(" ".join(map(str, message)))

def error(*message) -> None:
    logger.error(" ".join(map(str, message)))

def classLog(source, *message) -> None:
    name = _class_name(source)
    logger.info(f"[{name}] " + " ".join(map(str, message)))

def classWarning(source, *message) -> None:
    name = _class_name(source)
    logger.warning(f"[{name}] " + " ".join(map(str, message)))

def classError(source, *message) -> None:
    name = _class_name(source)
    logger.error(f"[{name}] " + " ".join(map(str, message)))

def newUUID():
    return uuid4()

def parseUUID(i: str):
    return UUID(i)

@dataclasses.dataclass
class screenState:
    geometry: QRect
    logicalDPI: float

def acquireScreenState():
    screen = QGuiApplication.primaryScreen()
    return screenState(
        screen.geometry(),
        screen.logicalDotsPerInch()
    )

def generateEasingCurve():
    import math

    def spring_ease(x, zeta=0.6, omega0=10.0):
        t = max(0.0, min(1.0, x))
        if zeta < 1.0:
            wd = omega0 * math.sqrt(1 - zeta*zeta)
            expo = math.exp(-zeta*omega0*t)
            return 1 - expo*(math.cos(wd*t) + (zeta/math.sqrt(1-zeta*zeta))*math.sin(wd*t))
        else:
            # 临界或过阻尼的数值近似（避免除零）
            expo = math.exp(-omega0*t)
            return 1 - expo*(1 + omega0*t)
        
    easingCurve = QEasingCurve()
    easingCurve.setCustomType(spring_ease)
    return easingCurve, spring_ease

class AnimationBus(QObject):
    Success = 0x00
    Failed = 0x01
    AlreadyExists = 0x02
    NotExisting = 0x04
    Termination = 0x08

    UseCurrentValue = UUID(int=0x1000)
    ValueWhenStart = UUID(int=0x1100)
    Automatic = UUID(int=0x1200)

    class Curve(IntEnum):
        OutCubic = 0x2000
        InCubic = 0x2100
        InOutCubic = 0x2200
        Spring = 0x2300

    OutCubic = Curve.OutCubic
    InCubic = Curve.InCubic
    InOutCubic = Curve.InOutCubic
    Spring = Curve.Spring

    springCurve, _springCurveFunc = generateEasingCurve()

    curveMap = {
        OutCubic: QEasingCurve.Type.OutCubic,
        InCubic: QEasingCurve.Type.InCubic,
        InOutCubic: QEasingCurve.Type.InOutCubic,
        Spring: springCurve
    }

    class ExecutionPolicy(IntEnum):
        Parallel = 0x00000
        WaitUntilCurrentFinish = 0x10000
        BlockSuccessorsUntilStart = 0x20000
        IgnoreQueueBlocking = 0x40000

    Parallel = ExecutionPolicy.Parallel
    WaitUntilCurrentFinish = ExecutionPolicy.WaitUntilCurrentFinish
    BlockSuccessorsUntilStart = ExecutionPolicy.BlockSuccessorsUntilStart
    IgnoreQueueBlocking = ExecutionPolicy.IgnoreQueueBlocking

    @dataclasses.dataclass
    class Animation:
        parent: "AnimationBus"
        propertyID: UUID
        startValue: Any
        endValue: Any
        determineStartValueWhenStart: bool
        duration: int
        autoDuration: bool
        easingCurve: "QEasingCurve | AnimationBus.Curve"

        def forceStart(self):
            self.parent.forceStart(self)

        def enqueue(self, executionPolicy: "AnimationBus.ExecutionPolicy | None" = None):
            if executionPolicy is None:
                executionPolicy = self.parent.Parallel
            self.parent.enqueue(self, executionPolicy)

        def involvedProperties(self) -> list[UUID]:
            return [self.propertyID]

    @dataclasses.dataclass
    class AnimationGroup:
        parallel: bool
        animations: list["AnimationBus.Animation"] = dataclasses.field(default_factory=list)

        def __contains__(self, item: "AnimationBus.Animation"):
            return item in self.animations
        
        def involves(self, propertyID: UUID) -> bool:
            return any((x.propertyID == propertyID for x in self.animations))
        
        def involvedProperties(self) -> list[UUID]:
            return [x.propertyID for x in self.animations]
        
    class AnimationInstance(QObject):
        finished = Signal()

        def __init__(self, parent: "AnimationBus", 
                     instanceID: UUID, QtAnimationIDs: list[UUID], 
                     animation: "AnimationBus.Animation | AnimationBus.AnimationGroup",
                     executionPolicy: "AnimationBus.ExecutionPolicy"):
            super().__init__()
            self.setParent(parent)
            self._parent = parent
            self.instanceID = instanceID
            # self.QtAnimationIDs = QtAnimationIDs
            self.animation = animation
            self.executionPolicy = executionPolicy
            self.isGroup = type(self.animation) == AnimationBus.AnimationGroup
            self.completed = False

        def setQtAnimations(self, qtAnimations: list[UUID]):
            self.QtAnimationIDs = qtAnimations
            self.remainingAnimationCount = len(self.QtAnimationIDs)
            for x in self.QtAnimationIDs:
                self._parent.QtAnimations[x].finished.connect(self.animationFinished)
        
        def involves(self, propertyID: UUID) -> bool:
            if type(self.animation) == AnimationBus.Animation:
                return self.animation.propertyID == propertyID
            elif type(self.animation) == AnimationBus.AnimationGroup:
                return self.animation.involves(propertyID)
            return False # For passing type checking
        
        def animationFinished(self):
            self.remainingAnimationCount -= 1
            if self.remainingAnimationCount == 0:
                self.finished.emit()
                self.completed = True
        
        def stop(self):
            self._parent.stopInstance(self)

    emptyAnimationGroup = AnimationGroup(False, [])

    def __init__(self, parent: QObject | None = None):
        super().__init__()
        self.setParent(parent)

        self.propertiesInCharge: dict[int, dict[bytes, UUID]] = {}
        self.properties: dict[UUID, tuple[QObject, bytes]] = {}
        self.QtAnimations: dict[UUID, QVariantAnimation] = {}
        self.animations: dict[UUID, AnimationBus.Animation] = {}
        self.animationGroups: dict[UUID, AnimationBus.AnimationGroup] = {}
        self.queuedAnimations: list[AnimationBus.AnimationInstance] = []
        self.ongoingAnimations: list[AnimationBus.AnimationInstance] = []

    def registerProperty(self, subject: QObject, _property: str | bytes) -> tuple[int, UUID]:
        if type(_property) == str:
            _property = _property.encode()

        if _property in self.propertiesInCharge.get(id(subject), {}):
            return AnimationBus.AlreadyExists, UUID(int=0)
        
        _old = self.propertiesInCharge.setdefault(id(subject), {})
        _uuid = uuid4()
        self.properties[_uuid] = (subject, _property) # type: ignore
        self.QtAnimations[_uuid] = QPropertyAnimation(subject, _property) # type: ignore
        _old[_property] = _uuid # type: ignore
        return AnimationBus.Success, _uuid
    
    def createAnimation(self, propertyID: UUID, startValue: Any = ValueWhenStart, endValue: Any = None, 
                        duration: int = 500, autoDuration: bool = True, easingCurve: QEasingCurve | Curve = OutCubic):
        if startValue == self.UseCurrentValue:
            subject, _property = self.properties[propertyID]
            startValue = subject.property(_property.decode())

        animation = self.Animation(
            self, propertyID, startValue if type(startValue) != UUID else None, endValue, 
            startValue == self.ValueWhenStart, duration, autoDuration, easingCurve
        )

        _uuid = uuid4()
        self.animations[_uuid] = animation
        return animation

    def getAnimation(self, _id: UUID) -> Animation | AnimationGroup | None:
        if _id in self.animations:
            return self.AnimationGroup(False, [self.animations[_id]])
        elif _id in self.animationGroups:
            return self.animationGroups[_id]
        else:
            return None

    def _parseAnimation(self, animation: Animation | UUID | AnimationGroup) -> tuple[int, Animation | AnimationGroup]:
        if type(animation) == AnimationBus.AnimationGroup:
            return self.Success, animation
        elif type(animation) == AnimationBus.Animation:
            return self.Success, self.AnimationGroup(False, [animation])
        elif type(animation) == UUID:
            if animation in self.animations:
                return self.Success, self.AnimationGroup(False, [self.animations[animation]])
            elif animation in self.animationGroups:
                return self.Success, self.animationGroups[animation]
        
        return self.Failed, self.emptyAnimationGroup
    
    def _parseEasingCurve(self, curve: Curve | QEasingCurve) -> QEasingCurve | QEasingCurve.Type:
        if type(curve) == AnimationBus.Curve:
            return AnimationBus.curveMap[curve]
        else:
            return curve # type: ignore
    
    def createInstance(self, animation: Animation | AnimationGroup, executionPolicy: ExecutionPolicy) -> AnimationInstance:
        instance = self.AnimationInstance(self, uuid4(), [], animation, executionPolicy)
        instance.finished.connect(lambda x=instance: self.instanceFinished(x))
        return instance

    def instanceFinished(self, instance: AnimationInstance):
        self.ongoingAnimations.remove(instance)
        for x in instance.QtAnimationIDs:
            self.QtAnimations[x].finished.disconnect(instance.animationFinished)
        log("Animation instance finished:", instance)
        self.checkQueue()

    def forceStart(self, animation: Animation | UUID | AnimationGroup):
        hex, animation = self._parseAnimation(animation)
        if hex == self.Failed:
            raise ValueError(f"Animation {animation} not found in AnimationBus {id(self)}")
        
        self.queuedAnimations.insert(0, self.createInstance(animation, self.Parallel))
        for x in animation.involvedProperties():
            self.freeProperty(x)
        self.checkQueue()

    def enqueue(self, animation: Animation | UUID | AnimationGroup, executionPolicy: ExecutionPolicy):
        hex, animation = self._parseAnimation(animation)
        if hex == self.Failed:
            raise ValueError(f"Animation {animation} not found in AnimationBus {id(self)}")
        
        self.queuedAnimations.append(self.createInstance(animation, executionPolicy))
        self.checkQueue()

    def stopAnimation(self, animation: Animation | UUID | AnimationGroup):
        hex, animation = self._parseAnimation(animation)
        if hex == self.Failed:
            raise ValueError(f"Animation {animation} not found in AnimationBus {id(self)}")
        
        for x in self.ongoingAnimations:
            if x.animation == animation:
                x.stop()

    def checkQueue(self):
        occupiedProperties = {y for x in self.ongoingAnimations for y in x.animation.involvedProperties()}
        blocked = False
        animationRunning = bool(occupiedProperties)
        indexesToStart: list[int] = []
        for i, x in enumerate(self.queuedAnimations):
            if (set(x.animation.involvedProperties()).intersection(occupiedProperties) or
                (x.executionPolicy & self.WaitUntilCurrentFinish and animationRunning)):
                if x.executionPolicy & self.BlockSuccessorsUntilStart:
                    blocked = True
                continue
            if (x.executionPolicy & self.IgnoreQueueBlocking) or (not blocked):
                indexesToStart.append(i)
                occupiedProperties |= set(x.animation.involvedProperties())
            if x.executionPolicy & self.BlockSuccessorsUntilStart:
                blocked = True

        animationsToStart: list[AnimationBus.AnimationInstance] = []
        for x in reversed(indexesToStart):
            animationsToStart.insert(0, self.queuedAnimations.pop(x))
        
        for x in animationsToStart:
            self.ongoingAnimations.append(x)
            self.startInstance(x)
    
    def startInstance(self, instance: AnimationInstance):
        animation = instance.animation
        if type(animation) == AnimationBus.Animation:
            animations = [animation]
        elif type(animation) == AnimationBus.AnimationGroup:
            animations = animation.animations
        else: 
            animations = [] # For passing type checking

        if not animations:
            raise RuntimeError("Empty animation instance")
        
        qtAnimationIDs: list[UUID] = []

        for x in animations:
            qtAnimation = self.QtAnimations[x.propertyID]
            if not x.determineStartValueWhenStart:
                qtAnimation.setStartValue(x.startValue)
            else:
                subject, _property = self.properties[x.propertyID]
                qtAnimation.setStartValue(subject.property(_property.decode()))
            qtAnimation.setEndValue(x.endValue)
            qtAnimation.setEasingCurve(self._parseEasingCurve(x.easingCurve))
            qtAnimation.setDuration(x.duration)
            qtAnimationIDs.append(x.propertyID)

        instance.setQtAnimations(qtAnimationIDs)

        for x in instance.QtAnimationIDs:
            self.QtAnimations[x].start()
            log("Animation instance started:", instance)

    def stopInstance(self, instance: AnimationInstance):
        if instance.completed:
            warning(f"{instance} already completed.")

        for x in instance.QtAnimationIDs:
            self.QtAnimations[x].stop()

        if not instance.completed:
            instance.finished.emit()

    def freeProperty(self, propertyID: UUID):
        for x in self.ongoingAnimations:
            if x.involves(propertyID):
                x.stop()

