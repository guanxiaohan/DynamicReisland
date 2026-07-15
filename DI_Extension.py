import Utils
import Widgets
import Island

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, final, TypeVar, Protocol, Any, Union, Optional, Iterable

from Utils import log, warning, error, classLog, classWarning, classError

@dataclass
class ExtensionInfo:
    name: str
    namespace: str
    version: str
    author: str

class RegisterObjectProtocol(Protocol):
    def __call__(self, subject: object, namespace_or_identifier: str, _id: str | None = None):
        ...

class CreateTaskProtocol(Protocol):
    def __call__(self, subject: object, target: Callable | Utils.TaskBus.TaskInstance, *args: Any, **kwargs: Any) -> Utils.TaskBus.Task:
        ...

class StartServiceProtocol(Protocol):
    def __call__(self, identifier: Union[Utils.Service, str, Utils.UUID], cascade: bool = True) -> Any:
        ...
    
class InitDataKeyProtocol(Protocol):
    def __call__(self, subject: object, key: str, 
                read_restriction: tuple[str, ...] | None = None, 
                write_restriction: tuple[str, ...] | None = None, 
                type_validation: type | None = None,
                send_signal: Any = None,
                send_signal_with_value: bool = False) -> None:
        ...

class SubscribeProtocol(Protocol):
    def __call__(self, receiver: object, slot: Any, namespace_or_identifier: str, _id: str | None = None) -> None:
        ...

class UnsubscribeProtocol(Protocol):
    def __call__(self, receiver: object, namespace_or_identifier: str, _id: str | None = None, /, ignore_warning: bool = False) -> None:
        ...

class RegisterEventSignal(Protocol):
    def __call__(self, sender: object, arg_types: Iterable[type], namespace_or_identifier: str, _id: str | None = None) -> "Utils.EventBus.DRI_Signal":
        ...

class RemoveEventProtocol(Protocol):
    def __call__(self, namespace_or_identifier: str, _id: str | None = None):
        ...

class Extension(ABC):
    @final
    def initInterface(self,
                      registerObject: RegisterObjectProtocol,
                      createTask: CreateTaskProtocol,
                      createReusableTask: CreateTaskProtocol,
                      registerService: Callable[[Utils.Service], None],
                      startService: StartServiceProtocol,
                      stopService: StartServiceProtocol,
                      initDataKey: InitDataKeyProtocol,
                      getData: Callable[[object, str], Any],
                      setData: Callable[[object, str, Any], None],
                      subscribe: SubscribeProtocol,
                      unsubscribe: UnsubscribeProtocol,
                      registerEvent: RegisterEventSignal,
                      removeEvent: RemoveEventProtocol,
                      removeSignal: Callable[[Utils.UUID | Utils.EventBus.DRI_Signal], None]):
        
        self.registerObject = registerObject
        self.createTask = createTask
        self.createReusableTask = createReusableTask
        self.registerService = registerService
        self.startService = startService
        self.stopService = stopService
        self.initDataKey = initDataKey
        self.getData = getData
        self.setData = setData
        self.subscribe = subscribe
        self.unsubscribe = unsubscribe
        self.registerEvent = registerEvent
        self.removeEvent = removeEvent
        self.removeSignal = removeSignal


    @abstractmethod
    def extensionInfo(self) -> ExtensionInfo:
        ...
    
    @abstractmethod
    def initExtension(self):
        ...

def extension_entry() -> Extension:
    ...

    