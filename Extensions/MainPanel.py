# Main Logics of DynamicReisland
import DI_Extension
from DI_Extension import *
from PySide6.QtCore import QSize
from winsdk.windows.system.power import PowerManager

class MainExtension(DI_Extension.Extension):

    class PowerService(DI_Extension.Utils.Service):
        def initService(self):
            self.batteryChangedSignal = self.eventBus.register(self, [int], "DynamicReisland.batteryLevelChanged")
            self.dataBus.initKey(self, "batteryLevel", write_restriction=("DynamicReisland", ), type_validation=int, send_signal=self.batteryChangedSignal, send_signal_with_value=True)
            self.dataBus.set(self, "DynamicReisland.batteryLevel", -2)
            
            # 用于保存 Windows 事件注销小票
            self._ev_token = None

        def onStart(self):
            classLog(self, "Initializing UWP hardware event listener...")
            initial_percent = PowerManager.remaining_charge_percent
            self.dataBus.set(self, "DynamicReisland.batteryLevel", initial_percent)
            
            handler_obj = self._on_windows_hardware_signal

            self._ev_token = PowerManager.add_remaining_charge_percent_changed(handler_obj)

        def _on_windows_hardware_signal(self, sender: object, args: object):
            try:
                percent = PowerManager.remaining_charge_percent
                classLog(self, f"Windows reported battery changed to {percent}%")
                
                # 同步去重写入 DataBus，DataBus 随后自动向 EventBus 广播
                self.dataBus.set(self, "DynamicReisland.batteryLevel", percent)
            except Exception as e:
                classLog(self, f"Callback Error: {e}")

        def tick(self):
            pass

        def onStop(self):
            if self._ev_token is not None:
                PowerManager.remove_remaining_charge_percent_changed(self._ev_token)
                self._ev_token = None
            self.dataBus.set(self, "DynamicReisland.batteryLevel", -2)

    class MainPanel(Widgets.Panel):
        def __init__(self) -> None:
            super().__init__("DynamicReisland.MainPanel", self.PanelProperties())

            self.fullForm = Widgets.Container)

    def extensionInfo(self) -> DI_Extension.ExtensionInfo:
        return DI_Extension.ExtensionInfo(
            "DynamicReisland Core",
            "DynamicReisland.CoreExtension",
            "v0.0.1",
            "Perplexity"
        )
    
    def initExtension(self):
        self.batteryService = self.PowerService("DynamicReisland.BatteryService",
                                                DI_Extension.Utils.Service.Policy(
                                                    dedicatedThread=False,     # 不需要独立线程
                                                    permanentTick=False,       # 不需要永久循环
                                                    timer=-1,                  # 每 10 秒 tick 一次
                                                    dependencies=()            # 无依赖
                                                ))
        self.registerObject(self.batteryService, "DynamicReisland.BatteryService")
        self.registerService(self.batteryService)
        self.subscribe(self, self.onBatteryChanged, "DynamicReisland.batteryLevelChanged")
        self.batteryService.start()

        self.mainPanel = self.MainPanel("DynamicReisland.MainPanel", self.MainPanel.PanelProperties(
            fullFormSizeHint=QSize(400, 30),
            enableFullForm=True,
            simpleFormSizeHint=QSize(200, 30),
            enableSimpleForm=True,
            progressBarEnabled=True,

        ))
        self.registerPanel(self, self.mainPanel)
        self.mainPanel.requestShow()

    def onBatteryChanged(self, percent: int):
        classLog(self, "Received battery information:", percent)
    
def extension_entry() -> Extension:
    return MainExtension()