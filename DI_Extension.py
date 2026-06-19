import Utils
import Widgets
import Island

from collections import abc
from dataclasses import dataclass

@dataclass
class ExtensionInfo:
    name: str
    namespace: str
    version: str
    author: str

class Extension:
    def extensionInfo(self) -> ExtensionInfo:
        ...

def extension_entry() -> Extension:
    ...

    