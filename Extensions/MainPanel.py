# Main Logics of DynamicReisland
import DI_Extension

class MainExtension(DI_Extension.Extension):
    def extensionInfo(self) -> DI_Extension.ExtensionInfo:
        return DI_Extension.ExtensionInfo(
            "DynamicReisland Core",
            "DynamicReisland",
            "v0.0.1",
            "Perplexity"
        )
    
def extension_entry():
    return MainExtension()