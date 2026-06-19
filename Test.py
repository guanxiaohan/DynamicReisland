import sys
import random
from PySide6.QtCore import QRect, QTimer, QObject
from PySide6.QtWidgets import QWidget, QApplication, QPushButton, QVBoxLayout, QHBoxLayout, QFrame, QLabel
from Utils import AnimationBus  # 确保导入你的总线

class AutomationStressWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.animationBus = AnimationBus(self)
        self.setupUI()
        
        # 注册属性
        _, self.islandProp = self.animationBus.registerProperty(self.islandView, "geometry")
        _, self.contentProp = self.animationBus.registerProperty(self.contentView, "geometry")
        
        # 初始化定时器用于自动化轰炸
        self.jitterTimer = QTimer(self)
        self.jitterTimer.timeout.connect(self.doJitterTick)
        self.jitterState = False

    def setupUI(self):
        self.setWindowTitle("⚙️ AnimationBus 自动化极限压力测试")
        self.setGeometry(100, 100, 900, 600)
        
        mainLayout = QHBoxLayout(self)
        controlPanel = QVBoxLayout()
        
        # 测试按钮
        self.btnJitter = QPushButton("🔥 开启/关闭 50ms 高频生死抖动测试")
        self.btnJitter.setCheckable(True)
        self.btnWaterfall = QPushButton("🌊 注入 50 级混合策略级联瀑布流")
        self.btnDeadlock = QPushButton("🔒 触发 潜在死锁/空转边界测试")
        
        controlPanel.addWidget(QLabel("<b>自动化测试控制:</b>"))
        controlPanel.addWidget(self.btnJitter)
        controlPanel.addWidget(self.btnWaterfall)
        controlPanel.addWidget(self.btnDeadlock)
        controlPanel.addStretch()
        mainLayout.addLayout(controlPanel, stretch=1)
        
        # 模拟灵动岛舞台
        self.stage = QFrame()
        self.stage.setStyleSheet("background-color: #1a1a1a; border-radius: 8px;")
        mainLayout.addWidget(self.stage, stretch=3)
        
        # 顶层岛容器
        self.islandView = QFrame(self.stage)
        self.islandView.setGeometry(200, 40, 200, 40)
        self.islandView.setStyleSheet("background-color: #000000; border-radius: 20px;")
        
        # 岛内子组件
        self.contentView = QFrame(self.stage)
        self.contentView.setGeometry(250, 200, 100, 40)
        self.contentView.setStyleSheet("background-color: #333333; border-radius: 10px;")

        # 信号绑定
        self.btnJitter.clicked.connect(self.toggleJitterTest)
        self.btnWaterfall.clicked.connect(self.runWaterfallTest)
        self.btnDeadlock.clicked.connect(self.runDeadlockTest)

    # ==================== 测试 1：高频生死抖动 ====================
    def toggleJitterTest(self, checked):
        """模拟用户或系统通知在极短时间内疯狂反复切换状态"""
        if checked:
            print("🚀 启动 50ms 高频抖动轰炸...")
            self.jitterTimer.start(50)  # 每 50 毫秒强行打断一次
        else:
            print("🛑 停止抖动轰炸。")
            self.jitterTimer.stop()

    def doJitterTick(self):
        # 两个状态疯狂互掐，全部使用 forceStart() 强行插队
        if self.jitterState:
            anim = self.animationBus.createAnimation(self.islandProp, endValue=QRect(50, 40, 500, 300), duration=400)
        else:
            anim = self.animationBus.createAnimation(self.islandProp, endValue=QRect(200, 40, 200, 40), duration=400)
        
        anim.forceStart()
        self.jitterState = not self.jitterState

    # ==================== 测试 2：级联瀑布流 ====================
    def runWaterfallTest(self):
        """混合并发、排队、阻塞策略，一口气塞入 50 个动画"""
        print("🌊 正在向队列注入 50 个级联动画...")
        
        policies = [
            AnimationBus.Parallel,
            AnimationBus.WaitUntilCurrentFinish,
            AnimationBus.BlockSuccessorsUntilStart
        ]
        
        for i in range(50):
            # 随机选择属性、终点、时长和策略
            prop = random.choice([self.islandProp, self.contentProp])
            policy = random.choice(policies)
            
            # 为了防止组件飞出屏幕，限制一下随机范围
            w = random.randint(100, 400)
            h = random.randint(40, 150)
            anim = self.animationBus.createAnimation(
                prop, 
                endValue=QRect(random.randint(50, 300), random.randint(40, 300), w, h),
                duration=random.randint(100, 300)
            )
            anim.enqueue(policy)

    # ==================== 测试 3：死锁与空转边界 ====================
    def runDeadlockTest(self):
        """极其恶劣的边界条件：注入零时长的动画、空动画组，或者对已被释放的属性连续施加策略"""
        print("🔒 正在执行边界条件测试...")
        
        # 边界 1：时长为 0 的动画（部分框架在此处会因为无法触发 finished 而死锁）
        zeroAnim = self.animationBus.createAnimation(self.islandProp, endValue=QRect(200, 40, 200, 40), duration=0)
        zeroAnim.enqueue(AnimationBus.WaitUntilCurrentFinish)
        
        # 边界 2：在没有任何动画运行时，强行对一个空队列触发 checkQueue 逻辑
        self.animationBus.checkQueue()
        
        # 边界 3：连续使用 BlockSuccessorsUntilStart 叠加，测试掩码和 blocked 布尔值是否会锁死
        blockAnim1 = self.animationBus.createAnimation(self.contentProp, endValue=QRect(250, 200, 150, 60), duration=200)
        blockAnim2 = self.animationBus.createAnimation(self.contentProp, endValue=QRect(250, 200, 100, 40), duration=200)
        
        blockAnim1.enqueue(AnimationBus.BlockSuccessorsUntilStart)
        blockAnim2.enqueue(AnimationBus.BlockSuccessorsUntilStart)
        
        print("✅ 边界条件注入完毕，观察总线是否能平稳消化。")

if __name__ == "__main__":
    app = QApplication()
    widget = AutomationStressWidget()
    widget.show()
    sys.exit(app.exec())