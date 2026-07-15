# Main Logics of DynamicReisland
import DI_Extension
from DI_Extension import log, classLog
from winsdk.windows.system.power import PowerManager

class MainExtension(DI_Extension.Extension):

    class PowerMonitorService(DI_Extension.Utils.Service):
        def initService(self):
            self.batteryChangedSignal = self.eventBus.register(self, [int], "DynamicReisland.batteryLevelChanged")
            self.dataBus.initKey(self, "batteryLevel", write_restriction=("DynamicReisland", ), type_validation=int, send_signal=self.batteryChangedSignal, send_signal_with_value=True)
            self.dataBus.set(self, "DynamicReisland.batteryLevel", -2)

        def onStart(self):
            self.dataBus.set(self, "DynamicReisland.batteryLevel", -1)
            classLog(self, "PowerMonitorService started.")

        def tick(self):
            try:
                percent = PowerManager.remaining_charge_percent
                saver = PowerManager.energy_saver_status.name
                supply = PowerManager.power_supply_status.name
                battery_status = PowerManager.battery_status.name

                log(
                    f"[PowerMonitor] Battery={percent}%, "
                    f"Saver={saver}, Supply={supply}, Status={battery_status}"
                )

                self.dataBus.set(self, "DynamicReisland.batteryLevel", percent)

            except Exception as e:
                log(f"[PowerMonitor] Error: {e}")

        def onStop(self):
            log("PowerMonitorService stopped.")
            self.dataBus.set(self, "DynamicReisland.batteryLevel", -2)

    def extensionInfo(self) -> DI_Extension.ExtensionInfo:
        return DI_Extension.ExtensionInfo(
            "DynamicReisland Core",
            "DynamicReisland",
            "v0.0.1",
            "Perplexity"
        )
    
    def initExtension(self):
        self.batteryService = self.PowerMonitorService("DynamicReisland.BatteryService",
                                                       DI_Extension.Utils.Service.Policy(
                                                           dedicatedThread=False,     # 不需要独立线程
                                                           permanentTick=False,       # 不需要永久循环
                                                           timer=10,                  # 每 10 秒 tick 一次
                                                           autoStart=True,            # 自动启动
                                                           dependencies=()            # 无依赖
                                                       ))
        self.registerObject(self.batteryService, "DynamicReisland.BatteryService")
        self.registerService(self.batteryService)
        self.subscribe(self, self.onBatteryChanged, "DynamicReisland.batteryLevelChanged")

        self.batteryService.start()

    def onBatteryChanged(self, percent: int):
        classLog(self, "Received battery information:", percent)
    
def extension_entry():
    return MainExtension()