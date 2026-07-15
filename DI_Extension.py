import Utils
import Widgets
import Island

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, final

@dataclass
class ExtensionInfo:
    name: str
    namespace: str
    version: str
    author: str

class Extension(ABC):
    @final
    def initInterface(self,
                      registerObject: Callable[[object, str, str | None], None],
                      createTask: Callable[[object, Callable, ]],):
        self.registerObject = registerObject
        self.createTask = createTask

    @abstractmethod
    def extensionInfo(self) -> ExtensionInfo:
        ...
    
    @abstractmethod
    def initExtension(self):
        ...

def extension_entry() -> Extension:
    ...

    