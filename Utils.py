from concurrent.futures import ThreadPoolExecutor
import dataclasses
import inspect
import logging
import pathlib
import threading
import weakref
import urllib.request
import urllib.error
import time
from enum import IntEnum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Union, overload
from uuid import UUID, uuid4

from PySide6.QtCore import (QEasingCurve, QObject, QParallelAnimationGroup,
                            QPoint, QPropertyAnimation, QRect,
                            QSequentialAnimationGroup, QVariantAnimation,
                            Signal, SignalInstance)
from PySide6.QtGui import QGuiApplication

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

def validateName(name: Any):
    if not isinstance(name, str):
        return False
    
    return all((x not in name for x in ", !%$.\"[]{}&*"))

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

def normalizeIdentifier(namespace_or_identifier: str, _id: str | None = None, max_fields: int = 2):
    if not _id:
        if "." not in namespace_or_identifier:
            raise ValueError(f"Identifier must contain a dot if implicit _id is not provided: {namespace_or_identifier}")
        parts = namespace_or_identifier.split(".", maxsplit=max_fields - 1)
        namespace, _id = parts[0], parts[1]
    else:
        namespace = namespace_or_identifier

    if not validateName(namespace) or not validateName(_id):
        raise ValueError("Invalid identifier: ", namespace_or_identifier, _id)
    
    return namespace, _id

class EventBus(QObject):
    @dataclasses.dataclass(slots=True)
    class Trigger:
        _id: UUID
        parent: "EventBus"
        sender: object
        namespace: str
        event_id: str
        arguments: tuple[type, ...] = tuple()
        connections: list[UUID] = dataclasses.field(default_factory=list)

        def involves(self, receiver: object) -> bool:
            return self.parent.triggerInvolves(self, receiver)

    @dataclasses.dataclass(slots=True)
    class Subscription:
        trigger_id: UUID
        subscription_id: UUID
        receiver: weakref.ReferenceType
        slot: Callable

    @dataclasses.dataclass(slots=True)
    class DRI_Signal:
        parent: "EventBus"
        signal_id: UUID
        trigger_id: UUID
        arguments: tuple[type, ...] = tuple()
        arg_count: int = -1

        def __call__(self, *args: Any) -> Any:
            if len(args) != self.arg_count:
                raise TypeError(f"Argument count mismatches: expecting {self.arg_count}, {len(args)} given")
            
            for i, x, y in zip(range(self.arg_count), self.arguments, args):
                if not isinstance(y, x):
                    raise TypeError(f"Argument {i} type mismatches: expecting {x}, {type(y)} detected")

            self.parent.DRI_emit(self.signal_id, self.trigger_id, *args)

    def __init__(self, parent = None) -> None:
        super().__init__()
        self._parent = parent
        self._lock = threading.RLock()

        self.triggers: dict[UUID, EventBus.Trigger] = {}
        self.subscriptions: dict[UUID, EventBus.Subscription] = {}
        self.events: dict[str, dict[str, UUID]] = {} # Namespace, ID -> Trigger object
        self.signals: dict[UUID, EventBus.DRI_Signal] = {}

    def triggerInvolves(self, trigger: "EventBus.Trigger", receiver: object) -> bool:
        with self._lock:
            for x in trigger.connections:
                sub = self.subscriptions.get(x)
                if sub and sub.receiver() is receiver:
                    return True
        return False

    def subscribe(self, receiver: object, slot: Any, namespace_or_identifier: str, _id: str | None = None) -> None:
        if not callable(slot):
            raise TypeError("Slot must be callable.")

        namespace, _id = normalizeIdentifier(namespace_or_identifier, _id)

        with self._lock:
            trigger = self.getTrigger(namespace, _id)
            if trigger is None:
                raise KeyError(f"Event not found: {namespace}.{_id}")
            
            if trigger.involves(receiver):
                classLog(self, f"{receiver} has already connected to {namespace}.{_id}")
                return

            subscription_id = uuid4()
            
            if inspect.ismethod(slot):
                wrapped_slot = weakref.WeakMethod(slot)
            else:
                wrapped_slot = weakref.ref(slot) if hasattr(slot, "__weakref__") else lambda s=slot: s

            self.subscriptions[subscription_id] = EventBus.Subscription(
                trigger._id, subscription_id, weakref.ref(receiver), wrapped_slot
            )
            trigger.connections.append(subscription_id)

    def unsubscribe(self, receiver: object, namespace_or_identifier: str, _id: str | None = None, /, ignore_warning: bool = False):
        namespace, _id = normalizeIdentifier(namespace_or_identifier, _id)
        
        with self._lock:
            trigger = self.getTrigger(namespace, _id)
            if not trigger:
                raise KeyError(f"Event not found: {namespace}.{_id}")
            
            for x in tuple(trigger.connections):
                sub = self.subscriptions.get(x)
                if sub and sub.receiver() is receiver:
                    trigger.connections.remove(x)
                    self.subscriptions.pop(x, None)
                    return
            
        if not ignore_warning:
            classWarning(self, "No subscription found when trying to unsubscribe")
    
    def getTrigger(self, namespace: str, _id: str) -> Trigger | None:
        namespace_events = self.events.get(namespace, None)
        if namespace_events:
            trigger_id = namespace_events.get(_id, None)
            if trigger_id:
                return self.triggers.get(trigger_id, None)
        return None

    def DRI_emit(self, signal_id: UUID, trigger_id: UUID, *args, **kwargs):
        to_call: list[Callable] = []
        to_remove: list[UUID] = []

        with self._lock:
            if signal_id not in self.signals or trigger_id not in self.triggers:
                raise KeyError("Signal or Trigger not found in EventBus. Perhaps it's already been deleted.")
            
            trigger = self.triggers[trigger_id]
            for x in tuple(trigger.connections):
                sub = self.subscriptions.get(x)
                if not sub:
                    to_remove.append(x)
                    continue
                
                func = sub.slot() if isinstance(sub.slot, (weakref.WeakMethod, weakref.ReferenceType)) else sub.slot()
                if func:
                    to_call.append(func)
                else:
                    to_remove.append(x)

            for x in to_remove:
                if x in trigger.connections:
                    trigger.connections.remove(x)
                self.subscriptions.pop(x, None)

        for func in to_call:
            func(*args, **kwargs)

    def removeSignal(self, signal_id_or_object: UUID | object):
        if isinstance(signal_id_or_object, EventBus.DRI_Signal):
            signal_id = signal_id_or_object.signal_id
        elif isinstance(signal_id_or_object, UUID):
            signal_id = signal_id_or_object
        else:
            raise TypeError("signal_id_or_object must be UUID or EventBus.DRI_Signal")

        with self._lock:
            if signal_id not in self.signals:
                raise KeyError("Signal not found in EventBus.")
            self.signals.pop(signal_id, None)

    def removeEvent(self, namespace_or_identifier: str, _id: str | None = None):
        namespace, _id = normalizeIdentifier(namespace_or_identifier, _id)

        with self._lock:
            trigger_id = self.events.get(namespace, {}).pop(_id, None)
            if trigger_id is None:
                raise KeyError(f"Event not found: {namespace}.{_id}")

            trigger = self.triggers.pop(trigger_id, None)
            if trigger is not None:
                for subscription_id in trigger.connections:
                    self.subscriptions.pop(subscription_id, None)

                if not self.events.get(namespace):
                    self.events.pop(namespace, None)

            # 清理关联的 Signal
            signal_ids = [sid for sid, sig in self.signals.items() if sig.trigger_id == trigger_id]
            for sid in signal_ids:
                self.signals.pop(sid, None)

    def register(self, sender: object, arg_types: Iterable[type], namespace_or_identifier: str, _id: str | None = None) -> "EventBus.DRI_Signal":
        namespace, _id = normalizeIdentifier(namespace_or_identifier, _id)

        with self._lock:
            namespace_map = self.events.setdefault(namespace, {})
            if _id in namespace_map:
                raise ValueError(f"Event already registered: {namespace}.{_id}")

            trigger_id = uuid4()
            arg_tuple = tuple(arg_types)
            self.triggers[trigger_id] = EventBus.Trigger(trigger_id, self, sender, namespace, _id, arg_tuple)
            namespace_map[_id] = trigger_id

            signal_id = uuid4()
            signal = EventBus.DRI_Signal(self, signal_id, trigger_id, arg_tuple, len(arg_tuple))
            self.signals[signal_id] = signal
        
        return signal
        


class DataBus:
    @dataclasses.dataclass(slots=True)
    class KeyMetadata:
        read_restriction: tuple[str, ...] | None = None
        write_restriction: tuple[str, ...] | None = None
        type_validation: type | None = None
        send_signal: EventBus.DRI_Signal | None = None
        send_signal_with_value: bool = False
    
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subjects: dict[int, str] = {}    # id(subject) -> "namespace"
        self._storage: dict[str, Any] = {}     # "namespace.key" -> value
        self._metadata: dict[str, DataBus.KeyMetadata] = {}   # "namespace.key" -> 权限、类型及绑定的信号元数据

    def _get_verified_ns(self, subject: object) -> str:
        """内部校验：确保主体已注册，返回其所属的 namespace"""
        with self._lock:
            ns = self._subjects.get(id(subject))
            if not ns:
                raise PermissionError("Access Denied: Subject is not registered to any namespace in DataBus.")
            return ns

    def registerObject(self, subject: object, namespace_or_identifier: str, _id: str | None = None) -> None:
        """
        向 DataBus 注册主体，锁定主权命名空间。
        """
        namespace, _ = normalizeIdentifier(namespace_or_identifier, _id)

        with self._lock:
            for sid, claimed_ns in self._subjects.items():
                if claimed_ns == namespace and sid != id(subject):
                    raise ValueError(f"Security Alert: Namespace '{namespace}' has already been claimed by another object.")
            self._subjects[id(subject)] = namespace

    def initKey(self, subject: object, key: str, 
                read_restriction: tuple[str, ...] | None = None, 
                write_restriction: tuple[str, ...] | None = None, 
                type_validation: type | None = None,
                send_signal: Any = None,
                send_signal_with_value: bool = False) -> None:
        """
        初始化键值，并可选地绑定一个 EventBus 的 Signal。
        
        :param send_signal: 传入 EventBus 实例化后的 Signal 对象。
                            若该信号要求参数 (arg_count > 0)，触发时会自动带上新写入的 value。
        """
        ns = self._get_verified_ns(subject)
        global_key = f"{ns}.{key}"

        with self._lock:
            if global_key in self._storage:
                raise KeyError(f"Property '{global_key}' is already initialized.")

            self._storage[global_key] = None
            self._metadata[global_key] = DataBus.KeyMetadata(
                read_restriction=read_restriction,
                write_restriction=write_restriction,
                type_validation=type_validation,
                send_signal=send_signal,
                send_signal_with_value=send_signal_with_value
            )

    def set(self, subject: object, key: str, value: Any) -> None:
        """
        设定属性值。若绑定的数据发生实质性变化 (value 改变)，将自动通过绑定的信号向外弹射。
        """
        ns = self._get_verified_ns(subject)
        global_key = key if "." in key else f"{ns}.{key}"

        signal_to_emit = None
        emit_with_value = False

        with self._lock:
            if global_key not in self._storage:
                raise KeyError(f"Property '{global_key}' has not been initialized via initKey.")

            meta = self._metadata[global_key]

            # 1. 校验写权限
            if meta.write_restriction is not None:
                if ns not in meta.write_restriction:
                    raise PermissionError(f"Write Access Denied: Namespace '{ns}' cannot write to '{global_key}'.")

            # 2. 运行时类型校验
            if meta.type_validation is not None:
                if not isinstance(value, meta.type_validation):
                    raise TypeError(f"Type Mismatch for '{global_key}': expected {meta.type_validation}, got {type(value)}.")

            # 3. 拦截无效冲刷（值未变则不触发后续逻辑和信号弹射）
            if self._storage[global_key] == value:
                return

            self._storage[global_key] = value

            # 4. 提取需要弹射的信号信息（在锁内安全提取，在锁外执行 emit，防止死锁）
            if meta.send_signal is not None:
                signal_to_emit = meta.send_signal
                emit_with_value = meta.send_signal_with_value

        # 5. 锁外弹射信号：保持低锁粒度，防止 EventBus 的回调阻塞 DataBus 状态机
        if signal_to_emit is not None:
            if emit_with_value:
                signal_to_emit(value)
            else:
                signal_to_emit()

    def get(self, subject: object, key: str) -> Any:
        """
        获取属性值，支持本地短 key 或跨命名空间长 key。
        带有主动容器沙箱防御，防止外部直接对返回的复杂对象进行恶意魔改。
        """
        ns = self._get_verified_ns(subject)
        global_key = key if "." in key else f"{ns}.{key}"

        with self._lock:
            if global_key not in self._storage:
                raise KeyError(f"Property '{global_key}' does not exist.")

            meta = self._metadata[global_key]

            # 1. 校验读权限
            if meta.read_restriction is not None:
                if ns not in meta.read_restriction:
                    raise PermissionError(f"Read Access Denied: Namespace '{ns}' cannot read '{global_key}'.")

            val = self._storage[global_key]

            # 2. 容器沙箱防御
            if isinstance(val, dict):
                return MappingProxyType(val)
            if isinstance(val, list):
                return tuple(val)
            
            return val
        
class TaskBus:
    class TaskInstance:
        def __init__(self, *args, **kwargs) -> None:
            self.progress = 0
            self.progressMax = 100
            self.args = args
            self.kwargs = kwargs
            self.terminateFlag = False
            self.result = None

        def setProgress(self, current: int = -1, max: int = -1):
            self.progress = current
            self.progressMax = max

        def run(self) -> Any:
            ...

    @dataclasses.dataclass
    class Task:
        class State(IntEnum):
            Pending = 0x01
            Running = 0x02
            Terminating = 0x04
            Finished = 0x08
            Terminated = 0x10

        ID: UUID
        parent: "TaskBus"
        func: "Callable | TaskBus.TaskInstance"
        state: State = State.Pending
        onetime: bool = True
        args: tuple = ()
        kwargs: dict = dataclasses.field(default_factory=dict)
        result: Any = None

        _event: threading.Event | None = None

        def wait(self):
            self.parent.waitForTask(self)

        def terminate(self):
            self.parent.terminateTask(self)

        def start(self, immediate: bool = False):
            """
            启动任务。
            :param immediate: 若为 True，则避开线程池队列，立刻创建独立线程执行。
            """
            self.parent.runTask(self, immediate=immediate)
        
    Unsupported = -2

    def __init__(self, parent: object = None, use_pool: bool = True, max_workers: int = 4, overload_threshold: int = 5):
        """
        :param parent: 父级托管对象。
        :param use_pool: 是否启用线程池。
        :param max_workers: 线程池的核心常驻线程数。
        :param overload_threshold: 排队任务上限。当池中等待的任务超过此阈值时，新任务将自动走“弹性独立线程”执行。
        """
        self.parent = parent
        self._lock = threading.RLock()
        self._subjects: dict[int, str] = {}
        self._active_threads: dict[UUID, threading.Thread] = {}
        
        # 线程池相关配置
        self.use_pool = use_pool
        self.overload_threshold = overload_threshold
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Pool") if use_pool else None
        
        # 精确追踪池内正在排队（已被 submit 但尚未被 Worker 消费）的任务数量
        self._queued_in_pool = 0 

    def registerObject(self, subject: object, namespace_or_identifier: str, _id: str | None = None):
        namespace, _ = normalizeIdentifier(namespace_or_identifier, _id)
        with self._lock:
            for sid, claimed_ns in self._subjects.items():
                if claimed_ns == namespace and sid != id(subject):
                    raise ValueError(f"Security Alert: Namespace '{namespace}' has already been claimed.")
            self._subjects[id(subject)] = namespace

    def _verifySubject(self, subject: object):
        with self._lock:
            if id(subject) not in self._subjects:
                raise PermissionError("Access Denied: Subject is not registered to TaskBus.")

    def createTask(self, subject: object, func: Callable, *args, **kwargs) -> Task:
        self._verifySubject(subject)
        task_id = uuid4()
        return self.Task(
            ID=task_id,
            parent=self,
            func=func,
            state=self.Task.State.Pending,
            onetime=True,
            args=args,
            kwargs=kwargs
        )

    def createReusableTask(self, subject: object, target: "Callable | TaskBus.TaskInstance", *args, **kwargs) -> Task:
        self._verifySubject(subject)
        task_id = uuid4()
        return self.Task(
            ID=task_id,
            parent=self,
            func=target,
            state=self.Task.State.Pending,
            onetime=False,
            args=args,
            kwargs=kwargs
        )

    def runTask(self, task: "TaskBus.Task", 
                connectToSignal: EventBus.DRI_Signal | None = None, 
                connectToFunc: Callable | None = None, 
                immediate: bool = False) -> "TaskBus.Task.State":
        
        with self._lock:
            if task.state in (self.Task.State.Running, self.Task.State.Terminating):
                raise RuntimeError("Task is already running or terminating.")
            
            if task.onetime and task.state in (self.Task.State.Finished, self.Task.State.Terminated):
                raise RuntimeError("Cannot restart a one-time task.")

            task.state = self.Task.State.Running
            task.result = None
            task._event = threading.Event()

            if isinstance(task.func, self.TaskInstance):
                task.func.terminateFlag = False
                task.func.result = None

            # 核心调度决策逻辑：判定当前该任务是否采用独立的 extra 线程运行
            use_dedicated_thread = False
            
            if not self.use_pool or self._pool is None:
                use_dedicated_thread = True
            elif immediate:
                use_dedicated_thread = True
                log(f"[TaskBus] Priority Pass: Task {task.ID} bypasses pool.")
            elif self._queued_in_pool >= self.overload_threshold:
                use_dedicated_thread = True
                log(f"[TaskBus] Pool Overloaded ({self._queued_in_pool} waiting). Spawning dynamic extra thread for {task.ID}!")

        # 异步线程执行体
        def worker():
            # 进入 worker 意味着要么任务开始出队执行，要么是用独立线程
            if not use_dedicated_thread:
                with self._lock:
                    self._queued_in_pool = max(0, self._queued_in_pool - 1)

            # 在真正被 Worker 消费的那一刻，检查它是否在排队期间就被提前 terminate() 了
            with self._lock:
                was_canceled_early = (task.state == self.Task.State.Terminating)
            
            if was_canceled_early:
                with self._lock:
                    task.state = self.Task.State.Terminated
                if task._event:
                    task._event.set()
                return

            try:
                if isinstance(task.func, self.TaskInstance):
                    res = task.func.run()
                    task.result = task.func.result if task.func.result is not None else res
                else:
                    task.result = task.func(*task.args, **task.kwargs)
            except Exception as e:
                task.result = e
            finally:
                with self._lock:
                    if task.state == self.Task.State.Terminating or (isinstance(task.func, self.TaskInstance) and task.func.terminateFlag):
                        task.state = self.Task.State.Terminated
                    else:
                        task.state = self.Task.State.Finished
                    
                    self._active_threads.pop(task.ID, None)
                
                # 解锁 wait() 阻塞
                if task._event:
                    task._event.set()

                # 回调及信号发射
                if connectToSignal is not None:
                    arg_count = connectToSignal.arg_count
                    if arg_count > 0:
                        connectToSignal(task.result)
                    else:
                        connectToSignal()

                if connectToFunc is not None:
                    try:
                        connectToFunc(task.result)
                    except Exception:
                        pass

        # 根据决策分配底层硬件线索
        if use_dedicated_thread:
            t = threading.Thread(target=worker, daemon=True, name=f"Ex-{task.ID}")
            with self._lock:
                self._active_threads[task.ID] = t
                t.start()
        else:
            with self._lock:
                self._queued_in_pool += 1
            # 提交至线程池异步排队执行
            self._pool.submit(worker) # type: ignore

        return task.state
        
    def waitForTask(self, task: "TaskBus.Task"):
        if task._event:
            task._event.wait()

    def terminateTask(self, task: "TaskBus.Task"):
        with self._lock:
            if task.state == self.Task.State.Running:
                task.state = self.Task.State.Terminating
                if isinstance(task.func, self.TaskInstance):
                    task.func.terminateFlag = True
    
class NetworkTask:
        @dataclasses.dataclass
        class Response:
            status_code: int
            content: bytes
            headers: dict = dataclasses.field(default_factory=dict)

            @property
            def text(self) -> str:
                return self.content.decode('utf-8', errors='ignore')

        # 网络任务的具体执行实例
        class Instance(TaskBus.TaskInstance):
            def __init__(self, method: str, url: str, headers: dict | None = None, timeout: float = 15, retry: int = 0, data: bytes | None = None):
                super().__init__()
                self.method = method
                self.url = url
                self.headers = headers or {}
                self.timeout = timeout
                self.retry = retry
                self.data = data

            def run(self):
                attempts = self.retry + 1
                for attempt in range(attempts):
                    # 每次尝试前检测是否已被要求终止
                    if self.terminateFlag:
                        break
                    
                    try:
                        req = urllib.request.Request(
                            self.url, 
                            headers=self.headers, 
                            method=self.method, 
                            data=self.data
                        )
                        # 发起请求
                        with urllib.request.urlopen(req, timeout=self.timeout) as response:
                            if self.terminateFlag:
                                break
                            self.result = NetworkTask.Response(
                                status_code=response.status,
                                content=response.read(),
                                headers=dict(response.info())
                            )
                            return self.result
                    except urllib.error.HTTPError as e:
                        # 4xx / 5xx 错误视为“有响应结果”的请求
                        if attempt == attempts - 1 or self.terminateFlag:
                            self.result = NetworkTask.Response(
                                status_code=e.code,
                                content=e.read(),
                                headers=dict(e.headers)
                            )
                            return self.result
                    except Exception as e:
                        # 物理断网、DNS 失败或超时
                        if attempt == attempts - 1 or self.terminateFlag:
                            raise e
                        
                        # 重试等待期间优雅响应退出事件
                        log(f"[NetworkTask] Attempt {attempt + 1} failed. Retrying...")
                        for _ in range(20):  # 将 2 秒重试拆分为 20 次 0.1 秒的微等待
                            if self.terminateFlag:
                                break
                            time.sleep(0.1)

        # 静态便利工厂方法
        @classmethod
        def get(cls, bus: "TaskBus", subject: object, url: str, headers: dict | None = None, timeout: float = 15, retry: int = 0) -> "TaskBus.Task":
            task_instance = cls.Instance("GET", url, headers, timeout, retry)
            return bus.createReusableTask(subject, task_instance)

        @classmethod
        def post(cls, bus: "TaskBus", subject: object, url: str, headers: dict | None = None, data: bytes | None = None, timeout: float = 15, retry: int = 0) -> "TaskBus.Task":
            task_instance = cls.Instance("POST", url, headers, timeout, retry, data)
            return bus.createReusableTask(subject, task_instance)
        
class Service:
    class State(IntEnum):
        Stopped = 0x01
        Starting = 0x02
        Running = 0x04
        Stopping = 0x08

    @dataclasses.dataclass
    class Policy:
        dedicatedThread: bool = False
        permanentTick: bool = False
        timer: float = -1
        autoStart: bool = True
        dependencies: tuple[str, ...] = ()  # 核心升级：依赖标识符元组

    def __init__(self, serviceIdentifier: str, policy: Policy):
        self.ID: UUID = uuid4()
        self.identifier: str = serviceIdentifier
        self.policy: Service.Policy = policy
        self.state: Service.State = self.State.Stopped
        self.enabled: bool = True

        self.dataBus: DataBus | None = None
        self.eventBus: EventBus | None = None
        self.taskBus: TaskBus | None = None
        self._bus: "ServiceBus | None" = None  # 内部持有总线引用以执行拓扑查询

        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_tick_time: float = 0.0

    def loadGlobalAssets(self, dataBus: DataBus, eventBus: EventBus, taskBus: TaskBus, bus: "ServiceBus"):
        self.dataBus = dataBus
        self.eventBus = eventBus
        self.taskBus = taskBus
        self._bus = bus

    def onStart(self): pass
    def tick(self): pass
    def onStop(self): pass

    # --- 启停方法升级：支持连锁与发起者溯源 ---
    def start(self, cascade: bool = True, initiator: str | None = None, _visited: set[str] | None = None):
        with self._lock:
            if not self.enabled:
                log(f"Cannot start '{self.identifier}': Disabled.")
                return False
            if self.state != self.State.Stopped:
                return True # 已在运行或启动中，直接视作成功
            
            # 向总线申请依赖树的连锁启动
            if self._bus and not self._bus._ensure_dependencies_start(self, cascade, initiator, _visited):
                log(f"Start aborted for '{self.identifier}': Dependencies failed.")
                return False
            
            self.state = self.State.Starting
            self._stop_event.clear()
            self._needs_thread = self.policy.dedicatedThread or self.policy.permanentTick

            if self._needs_thread:
                self._thread = threading.Thread(target=self._run_loop, name=f"Svc-{self.identifier}", daemon=True)
                self._thread.start()
            else:
                try:
                    self.onStart()
                    self.state = self.State.Running
                    if self.policy.timer <= 0:
                        self.tick()
                        self._cleanup_after_run()
                    else:
                        self._last_tick_time = time.time()
                except Exception as e:
                    log(f"Failed to start '{self.identifier}': {e}")
                    self.state = self.State.Stopped
                    return False
            return True

    def _run_loop(self):
        try:
            self.onStart()
            with self._lock:
                if self.state != self.State.Starting:
                    return
                self.state = self.State.Running
            
            if self.policy.permanentTick:
                while self.state == self.State.Running and not self._stop_event.is_set():
                    self.tick()
            elif self.policy.timer > 0:
                while self.state == self.State.Running and not self._stop_event.is_set():
                    self.tick()
                    if self._stop_event.wait(timeout=self.policy.timer):
                        break
            else:
                self.tick()
        except Exception as e:
            log(f"Exception in '{self.identifier}': {e}")
        finally:
            self._cleanup_after_run()

    def _cleanup_after_run(self):
        with self._lock:
            if self.state in (self.State.Running, self.State.Stopping):
                self.state = self.State.Stopping
                try:
                    self.onStop()
                except Exception as e:
                    log(f"Error onStop for '{self.identifier}': {e}")
                self.state = self.State.Stopped
                self._thread = None

    def stop(self, cascade: bool = True, initiator: str | None = None, _visited: set[str] | None = None):
        with self._lock:
            if self.state in (self.State.Stopped, self.State.Stopping):
                return True
            
            # 向总线申请依赖树的连锁终止（先停掉依赖我的服务）
            if self._bus and not self._bus._ensure_dependencies_stop(self, cascade, initiator, _visited):
                log(f"Stop aborted for '{self.identifier}': Dependent services refused to stop.")
                return False
            
            self.state = self.State.Stopping
            self._stop_event.set()

            if not getattr(self, '_needs_thread', False):
                try:
                    self.onStop()
                except Exception as e:
                    log(f"Error onStop for '{self.identifier}': {e}")
                self.state = self.State.Stopped
            return True

    def restart(self, cascade: bool = True, initiator: str | None = None):
        log(f"Restarting service '{self.identifier}'...")
        if self.stop(cascade, initiator):
            if self._thread is not None:
                self._thread.join(timeout=3.0)
            self.start(cascade, initiator)


class ServiceBus:
    def __init__(self, dataBus: DataBus, eventBus: EventBus, taskBus: TaskBus, parent: object = None):
        self.parent = parent
        self.dataBus = dataBus
        self.eventBus = eventBus
        self.taskBus = taskBus
        self._lock = threading.RLock()
        self._services: dict[UUID, Service] = {}

        self._bus_stop_event = threading.Event()
        self._master_thread = threading.Thread(target=self._bus_master_loop, name="ServiceBus-Master", daemon=True)
        self._master_thread.start()

    # --- 🛡️ 安全验证策略 ---
    def _verify_cascade_permission(self, initiator: str | None, target: str) -> bool:
        """验证命名空间权限，支持未来基于规则表扩展"""
        if not initiator: 
            return True # 系统底层/总线直接发起的调用，视为最高权限

        init_ns = initiator.split('.')[0]
        target_ns = target.split('.')[0]

        # 核心规则：外部命名空间不能连锁启停 DynamicReisland 命名空间
        if target_ns == "DynamicReisland" and init_ns != "DynamicReisland":
            log(f"⚠️ Security Alert: '{initiator}' lacks permission to cascade '{target}'.")
            return False
            
        return True

    # --- 🕸️ 拓扑依赖解析与连锁流转 ---
    def _ensure_dependencies_start(self, service: Service, cascade: bool, initiator: str | None, visited: set[str] | None = None) -> bool:
        """确保要启动的服务的所有依赖项都已在运行"""
        visited = visited or set()
        if service.identifier in visited:
            raise RecursionError(f"Circular dependency detected at '{service.identifier}'")
        visited.add(service.identifier)

        with self._lock:
            for dep_id in service.policy.dependencies:
                dep_svc = self._resolveService(dep_id, safe=True)
                if not dep_svc:
                    log(f"Missing required dependency '{dep_id}' for '{service.identifier}'.")
                    return False

                if dep_svc.state != Service.State.Running:
                    if not cascade:
                        log(f"Dependency '{dep_id}' is not running and cascade is False.")
                        return False
                    
                    if not self._verify_cascade_permission(initiator or service.identifier, dep_svc.identifier):
                        return False
                    
                    # 连锁启动依赖
                    if not dep_svc.start(cascade=True, initiator=service.identifier, _visited=visited.copy()):
                        return False
            return True

    def _ensure_dependencies_stop(self, service: Service, cascade: bool, initiator: str | None, visited: set[str] | None = None) -> bool:
        """确保强依赖该服务的所有其他服务已停止"""
        visited = visited or set()
        if service.identifier in visited:
            raise RecursionError(f"Circular dependency detected at '{service.identifier}'")
        visited.add(service.identifier)

        with self._lock:
            # 查找哪些服务把当前服务当做了依赖
            for other_svc in self._services.values():
                if service.identifier in other_svc.policy.dependencies:
                    if other_svc.state not in (Service.State.Stopped, Service.State.Stopping):
                        if not cascade:
                            log(f"Service '{other_svc.identifier}' requires '{service.identifier}'. Cascade is False.")
                            return False
                        
                        if not self._verify_cascade_permission(initiator or service.identifier, other_svc.identifier):
                            return False
                        
                        # 连锁停止依赖于我的服务
                        if not other_svc.stop(cascade=True, initiator=service.identifier, _visited=visited.copy()):
                            return False
            return True

    def _bus_master_loop(self):
        while not self._bus_stop_event.is_set():
            with self._lock:
                services_snapshot = list(self._services.values())
            
            current_time = time.time()
            for svc in services_snapshot:
                if svc.state == Service.State.Running and svc.policy.timer > 0 and not (svc.policy.dedicatedThread or svc.policy.permanentTick):
                    if current_time - svc._last_tick_time >= svc.policy.timer:
                        try:
                            svc.tick()
                        except Exception as e:
                            log(f"Error in polled service '{svc.identifier}': {e}")
                        finally:
                            svc._last_tick_time = time.time()
            self._bus_stop_event.wait(0.01)

    def shutdown(self):
        self._bus_stop_event.set()
        with self._lock:
            for svc in self._services.values():
                svc.stop(cascade=False)

    def registerService(self, service: Service):
        with self._lock:
            if service.ID in self._services:
                raise ValueError(f"Service with ID {service.ID} already registered.")
            for registered_svc in self._services.values():
                if registered_svc.identifier == service.identifier:
                    raise ValueError(f"Identifier '{service.identifier}' has already been claimed.")

            # 注入总线引用
            service.loadGlobalAssets(self.dataBus, self.eventBus, self.taskBus, self)
            self._services[service.ID] = service
            log(f"Registered '{service.identifier}' (Dependencies: {service.policy.dependencies})")

            # 在注册阶段自动启动时，赋予系统级最高权限，允许无视命名空间安全规则的拓扑唤醒
            if service.policy.autoStart and service.enabled:
                service.start(cascade=True, initiator=None)

    def _resolveService(self, identifier_or_service: Union[Service, str, UUID], safe: bool = False) -> Service | None:
        with self._lock:
            if isinstance(identifier_or_service, Service):
                if identifier_or_service.ID in self._services:
                    return identifier_or_service
            elif isinstance(identifier_or_service, UUID):
                if identifier_or_service in self._services:
                    return self._services[identifier_or_service]
            elif isinstance(identifier_or_service, str):
                try:
                    parsed_uuid = UUID(identifier_or_service)
                    if parsed_uuid in self._services:
                        return self._services[parsed_uuid]
                except ValueError: pass
                for svc in self._services.values():
                    if svc.identifier == identifier_or_service:
                        return svc
            if safe:
                return None
            raise LookupError(f"Could not resolve service: '{identifier_or_service}'")

    # 对外暴露的极简 API
    def startService(self, identifier: Union[Service, str, UUID], cascade: bool = True):
        self._resolveService(identifier).start(cascade=cascade, initiator=None) # type: ignore
    
    def stopService(self, identifier: Union[Service, str, UUID], cascade: bool = True):
        self._resolveService(identifier).stop(cascade=cascade, initiator=None)  # type: ignore

