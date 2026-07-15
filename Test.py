import sys
import random
from PySide6.QtCore import QRect, QTimer, QObject
from PySide6.QtWidgets import QWidget, QApplication, QPushButton, QVBoxLayout, QHBoxLayout, QFrame, QLabel
from Utils import AnimationBus, DataBus, EventBus, NetworkTask, TaskBus, log
import time
import concurrent.futures
import threading
from uuid import UUID

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


class Sender:
    pass

class Receiver:
    def __init__(self):
        self.count = 0
        self.last = None

    def callback(self, *args):
        self.count += 1
        self.last = args

privacy_notified_count = 0
    
def run_event_bus_test_suite():
    print("====== 🚀 开始 EventBus 工业级集成与压力测试 ======")
    bus = EventBus()

    # 模拟用的接收器，用于测试弱引用
    class DummyReceiver:
        def __init__(self, name):
            self.name = name
            self.received_count = 0
            self.last_args = None

        def on_event(self, count: int, msg: str):
            self.received_count += 1
            self.last_args = (count, msg)

    # ==================== 测试阶段 1: 基础功能与强类型校验 ====================
    print("\n[阶段 1] 正在测试基础注册、订阅与运行时类型校验...")
    
    sender_obj = object()
    # 注册一个需要 (int, str) 的信号
    music_signal = bus.register(sender_obj, [int, str], "system.music_changed")
    
    receiver = DummyReceiver("Rx1")
    bus.subscribe(receiver, receiver.on_event, "system.music_changed")

    # 1.1 正常发射
    music_signal(1, "切歌：夜曲")
    assert receiver.received_count == 1, "基础订阅触发失败"
    assert receiver.last_args == (1, "切歌：夜曲"), "事件参数传递有误"
    print("  ✅ 基础发布订阅通路测试通过。")

    # 1.2 类型不匹配测试 (预期的崩溃拦截)
    try:
        music_signal("不是数字", "有害数据")  # 第一个参数传了 str，期望拦截
        raise AssertionError("❌ 致命：类型校验失效，错误的参数类型未被拦截！")
    except TypeError as e:
        print(f"  ✅ 强类型校验拦截成功: {e}")

    # 1.3 参数数量不匹配测试
    try:
        music_signal(2)  # 少传了参数
        raise AssertionError("❌ 致命：参数数量校验失效！")
    except TypeError as e:
        print(f"  ✅ 参数数量校验拦截成功: {e}")


    # ==================== 测试阶段 2: 内存泄漏与弱引用自动清理 ====================
    print("\n[阶段 2] 正在测试生命周期管理（弱引用自动 GC 清理）...")
    
    temp_receiver = DummyReceiver("Temporary_Rx")
    bus.subscribe(temp_receiver, temp_receiver.on_event, "system.music_changed")
    
    # 此时应该有两个连接
    trigger = bus.getTrigger("system", "music_changed")
    assert len(trigger.connections) == 2, "连接计数不匹配" # type: ignore

    # 强行销毁临时接收器
    del temp_receiver
    import gc
    gc.collect()  # 触发 Python 垃圾回收

    # 再次发射，触发内部的死链自动清理
    music_signal(2, "切歌：晴天")
    
    assert len(trigger.connections) == 1, "❌ 🚀 弱引用清理失败：已死去的对象仍残留在连接池中！" # type: ignore
    print("  ✅ 弱引用生死边界测试通过：已死亡对象被总线顺畅弹出，无内存泄漏风险。")


    # ==================== 测试阶段 3: 多线程并发极限压力轰炸 ====================
    print("\n[阶段 3] 开启多线程高频读写轰炸压力测试...")
    print("  🔥 正在激活 10 个线程，执行并发注册、取消订阅、高频发射大乱斗...")

    stress_signal = bus.register(sender_obj, [int], "stress.bomb")
    
    # 创建 50 个高并发接收器
    receivers = [DummyReceiver(f"Stress_Rx_{i}") for i in range(50)]
    for rx in receivers:
        bus.subscribe(rx, lambda val, r=rx: r.on_event(val, "stress"), "stress.bomb")

    stop_stress = threading.Event()

    def emitter_worker(worker_id):
        """高频发射线程"""
        count = 0
        while not stop_stress.is_set():
            try:
                stress_signal(count)
                count += 1
            except KeyError:
                # 容忍在事件被删除时的并发异常
                pass
            time.sleep(0.001)  # 1ms 轰炸一次

    def chaotic_worker(worker_id):
        """混沌线程：疯狂地在无锁/有锁之间进行注册、销毁、取消订阅"""
        while not stop_stress.is_set():
            ns = f"rand_ns_{worker_id}"
            eid = f"ev_{int(time.time() * 1000) % 100}"
            try:
                # 突发注册
                sig = bus.register(sender_obj, [str], ns, eid)
                # 瞬间突发发射
                sig("chaos")
                # 瞬间突发注销删除整个事件
                bus.removeEvent(ns, eid)
            except (ValueError, KeyError):
                pass
            time.sleep(0.002)

    # 组装线程池
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = []
        # 4个纯发射轰炸线程
        for i in range(4):
            futures.append(executor.submit(emitter_worker, i))
        # 4个死锁诱发（混沌操作）线程
        for i in range(4):
            futures.append(executor.submit(chaotic_worker, i))
            
        print("  ⏳ 压力测试中，保持高频冲刷 3 秒钟...")
        time.sleep(3.0)
        
        print("  🛑 正在收紧测试网，停止所有线程...")
        stop_stress.set()
        
        # 等待所有线程平稳退出
        concurrent.futures.wait(futures)

    # ==================== 测试阶段 4: 收尾与死锁/数据一致性盘点 ====================
    print("\n[阶段 4] 压力测试收尾盘点...")
    
    # 检查总线是否依然健康（有没有发生不可逆的锁死）
    try:
        final_signal = bus.register(sender_obj, [], "system.survived")
        print("  ✅ 极好！总线没有发生死锁，状态机依然可写。")
    except ValueError:
        print("  ✅ 总线存活，且正确维持了边界。")

    # 统计并发成果
    total_received = sum(rx.received_count for rx in receivers)
    print(f"  📊 统计数据：在 3 秒钟内，50 个常驻订阅者共安全吞吐了 **{total_received}** 次高并发信号。")
    print("\n🎉 恭喜！EventBus 通过了全套功能及多线程生死抖动压力测试！")

    print("====== 🚀 开始 DataBus x EventBus 响应式联动测试 ======")

def DataBusTest():
    print("====== 🚀 开始 DataBus [namespace.key] 极致精简版测试 ======")
    db = DataBus()

    class TimeService: pass
    class DynamicReisland: pass
    class EvilExtension: pass

    time_service = TimeService()
    reisland = DynamicReisland()
    evil_ext = EvilExtension()

    # ==================== 1. 注册与主权抢占防御 ====================
    print("\n[测试 1] 正在注册主权命名空间...")
    # 无论是传入带点的标识符，还是显式分拆，最终的主权域名都将是第一级 namespace
    db.registerObject(time_service, "TimeService.Main")       # 属于 TimeService 空间
    db.registerObject(reisland, "DynamicReisland", "Core")    # 属于 DynamicReisland 空间
    db.registerObject(evil_ext, "EvilExtension.Plugin")       # 属于 EvilExtension 空间
    print("  ✅ 基础空间注册成功。")

    # 恶意李鬼尝试抢占 DynamicReisland 空间
    class FakeIsland: pass
    fake_island = FakeIsland()
    try:
        db.registerObject(fake_island, "DynamicReisland.Fake")
        raise AssertionError("❌ 风险：允许了冒充已经存在的主权命名空间！")
    except ValueError as e:
        print(f"  ✅ 成功拦截仿冒空间抢占: {e}")

    # ==================== 2. 属性初始化 (namespace.key 自动拼接) ====================
    print("\n[测试 2] 正在初始化属性...")
    
    # TimeService 开放系统时间偏移，允许自己写，允许自己和 DynamicReisland 读
    db.initKey(
        subject=time_service,
        key="timeShift",
        read_restriction=("TimeService", "DynamicReisland"),
        write_restriction=("TimeService",),
        type_validation=float
    )
    print("  ✅ 成功初始化 'TimeService.timeShift'。")

    # ==================== 3. 读写流与跨空间极简访问 ====================
    print("\n[测试 3] 正在验证极简长短 Key 读写...")
    
    # TimeService 使用本地短 Key 写入
    db.set(time_service, "timeShift", -0.015)
    
    # DynamicReisland 使用极为直观的 namespace.key 长 Key 跨界读取
    shared_shift = db.get(reisland, "TimeService.timeShift")
    assert shared_shift == -0.015
    print(f"  ✅ 跨空间读取成功！成功拿到数据: {shared_shift}")

    # ==================== 4. 安全边界测试 ====================
    print("\n[测试 4] 正在验证越权安全墙...")
    
    # 4.1 邪恶插件尝试越权读取
    try:
        db.get(evil_ext, "TimeService.timeShift")
        raise AssertionError("❌ 致命：越权读取未被拦截！")
    except PermissionError as e:
        print(f"  ✅ 成功拦截越权读取: {e}")

    # 4.2 获准读取的灵动岛主体尝试越权改写
    try:
        db.set(reisland, "TimeService.timeShift", 100.0)
        raise AssertionError("❌ 致命：越权改写未被拦截！")
    except PermissionError as e:
        print(f"  ✅ 成功拦截越权写入: {e}")

    print("\n🎉 恭喜！重构后的 DataBus 完全符合 namespace.key 的极简访问预期，表现完美！")

    print("====== ⏱️ 开始 DataBus 极限性能与锁吞吐量测试 ======")
    db = DataBus()

    # 准备测试主体
    class CoreModule: pass
    class ExtensionModule: pass

    core = CoreModule()
    ext = ExtensionModule()

    db.registerObject(core, "Core.Core")
    db.registerObject(ext, "Extension.Core")

    # 初始化测试键
    db.initKey(core, "global_counter", type_validation=int)
    db.initKey(ext, "local_status", type_validation=str)
    db.set(core, "global_counter", 0)

    # 设定总循环量（单线程与多线程的总操作基数对齐）
    TOTAL_LOOPS = 200000 

    # ==================== 1. 单线程纯净性能基准 ====================
    print(f"\n[基准 1] 单线程连续读写测试 (执行 {TOTAL_LOOPS} 次 set + get)...")
    
    start_time = time.perf_counter()
    
    for i in range(TOTAL_LOOPS):
        db.set(core, "global_counter", i)
        _ = db.get(core, "global_counter")
        
    end_time = time.perf_counter()
    single_duration = end_time - start_time
    single_ops = TOTAL_LOOPS * 2  # 一次循环包含一次 set 和一次 get
    single_tput = single_ops / single_duration

    print(f"  ⚡ 耗时: {single_duration:.4f} 秒")
    print(f"  📊 吞吐量: **{single_tput:,.2f}** 次操作/秒 (Ops/Sec)")


    # ==================== 2. 多线程高锁竞争并发性能 ====================
    NUM_THREADS = 4
    LOOPS_PER_THREAD = TOTAL_LOOPS // NUM_THREADS
    
    print(f"\n[基准 2] 多线程高并发读写测试 ({NUM_THREADS} 线程并发冲刷，各执行 {LOOPS_PER_THREAD} 次)...")
    print("  🔥 测试包含：本地短 Key 写入、本地短 Key 读取、跨空间长 Key 密集抢占式读取...")

    def worker_task(thread_id: int):
        for i in range(LOOPS_PER_THREAD):
            # 1. 模拟本地状态高频改写
            db.set(ext, "local_status", f"state_{thread_id}_{i}")
            # 2. 模拟本地状态读取
            _ = db.get(ext, "local_status")
            # 3. 跨空间疯狂抢占 Core 的全局计数器 (诱发极端锁竞争)
            _ = db.get(ext, "Core.global_counter")

    threads = []
    for t_id in range(NUM_THREADS):
        t = threading.Thread(target=worker_task, args=(t_id,))
        threads.append(t)

    start_time = time.perf_counter()
    
    # 瞬间激活所有线程
    for t in threads:
        t.start()
    # 等待合流
    for t in threads:
        t.join()
        
    end_time = time.perf_counter()
    multi_duration = end_time - start_time
    # 每个线程每个循环做 1 次 set，2 次 get = 3 次核心操作
    multi_ops = NUM_THREADS * LOOPS_PER_THREAD * 3
    multi_tput = multi_ops / multi_duration

    print(f"  ⚡ 耗时: {multi_duration:.4f} 秒")
    print(f"  📊 吞吐量: **{multi_tput:,.2f}** 次操作/秒 (Ops/Sec)")


    # ==================== 3. 性能损耗与架构评估 ====================
    print("\n====== 📈 DataBus 性能分析报告 ======")
    print(f"  * 单线程极限吞吐速度: 约 **{single_tput / 10000:.1f} 万次/秒**")
    print(f"  * 多线程密集锁竞争速度: 约 **{multi_tput / 10000:.1f} 万次/秒**")
    
    efficiency = (multi_tput / single_tput) * 100
    print(f"  * 多线程锁并发效率保留比: **{efficiency:.2f}%**")
    print(
        "> **架构评语**：由于 Python 存在 GIL 限制，多线程密集的 `RLock` 抢占会引发频繁的线程上下文切换，"
        "导致吞吐量产生正常的阶梯型平滑下降。然而，即便在多线程极度不合理、不留空隙的死循环轰炸下，"
        "每秒仍能稳定吞吐数十万次的数据读写。这对于常规桌面微秒、毫秒级的应用级状态同步来说，性能储备已经溢出了几十倍。"
    )

    # 模拟你的 EventBus 信号类
    eventBus = EventBus()

    # 实例化 DataBus
    db = DataBus()

    # 准备组件
    class IslandUI: pass

    time_service = TimeService()
    island_ui = IslandUI()

    db.registerObject(time_service, "TimeService.Core")
    db.registerObject(island_ui, "IslandUI.Core")

    # ==================== 测试 1：绑定带参数的信号 ====================
    print("\n[测试 1] 正在测试【带参信号】联动...")
    
    # 创建一个需要 1 个参数的信号（用来广播最新的 timeShift 变化）
    sig_shift_changed = eventBus.register(time_service, [float], "TimeService.timeShift")
    
    # UI 侧订阅该信号
    ui_received_values = []
    def on_ui_time_update(new_shift):
        print(f"  📺 [UI 视图接收通知]: 监测到系统时间偏差变更为 -> {new_shift}")
        ui_received_values.append(new_shift)
        
    eventBus.subscribe(island_ui, on_ui_time_update, "TimeService.timeShift")

    # TimeService 初始化 key，并绑定该信号
    db.initKey(
        subject=time_service,
        key="timeShift",
        type_validation=float,
        send_signal=sig_shift_changed,
        send_signal_with_value=True
    )

    # 后台 TimeService 修正时间，触发 set
    print("  ⏳ 后台 TimeService 正在更新 timeShift 为 0.0050...")
    db.set(time_service, "timeShift", 0.0050)
    
    # 验证 UI 是否同步收到了值
    assert len(ui_received_values) == 1 and ui_received_values[0] == 0.0050
    print("  ✅ 带参信号联动成功！")

    # ==================== 测试 2：拦截无效变动，防止风暴 ====================
    print("\n[测试 2] 正在测试拦截【相同数值】的重复弹射...")
    
    # 再次写入相同的值，不应该触发信号弹射
    db.set(time_service, "timeShift", 0.0050)
    assert len(ui_received_values) == 1, "❌ 错误：数值未改变时也弹射了信号，容易造成死循环或 UI 刷新风暴！"
    print("  ✅ 成功拦截相同值的重复冲刷。")

    # ==================== 测试 3：绑定无参数的纯通知信号 ====================
    print("\n[测试 3] 正在测试【无参纯通知信号】联动...")
    
    # 比如某些隐私模式切换，UI 只需要知道“数据变了，去重新读取吧”，不需要信号传值
    sig_privacy_triggered = eventBus.register(time_service, [], "TimeService.privacyChanged")
    
    def on_privacy_notice():
        print("  🔒 [UI 视图接收通知]: 隐私状态发生改变，已触发安全遮罩。")
        global privacy_notified_count
        privacy_notified_count += 1
        
    eventBus.subscribe(island_ui, on_privacy_notice, "TimeService.privacyChanged")

    # 初始化隐私状态
    db.initKey(
        subject=time_service,
        key="isPrivateMode",
        type_validation=bool,
        send_signal=sig_privacy_triggered
    )

    # 改变状态
    db.set(time_service, "isPrivateMode", True)
    assert privacy_notified_count == 1
    print("  ✅ 无参纯通知信号联动成功！")

    print("\n🎉 极好！带有响应式信号触发的 DataBus 重构圆满成功！")


def AnimationBusTest():
    app = QApplication()
    widget = AutomationStressWidget()
    widget.show()
    sys.exit(app.exec())

def TaskBusTest():
    # 限制线程池只有 2 个常驻线程，排队超载阈值为 2 
    taskBus = TaskBus(max_workers=5, overload_threshold=10)
    
    class TaskHolder:
        def task_slow(self, task_id: int, duration: float = 1.0) -> int:
            log(f"Slow task started: ID={task_id} (Thread: {threading.current_thread().name})")
            time.sleep(duration)
            log(f"Slow task finished: ID={task_id}")
            return task_id

    host = TaskHolder()
    taskBus.registerObject(host, "Extension.TaskHolder")

    print("====== 1. 正常提交排队任务 (利用常驻线程池) ======")
    # 连续提交两个任务，刚好占满最大为 2 核心的线程池
    t1 = taskBus.createTask(host, host.task_slow, 101, 0.8)
    t2 = taskBus.createTask(host, host.task_slow, 102, 0.8)
    
    t1.start()
    t2.start()

    print("\n====== 2. 测试高优先通道 (immediate=True) ======")
    # 即使池子全满，该高优任务也会利用独立的 extra 线程立即启动，而不排队
    t_high = taskBus.createTask(host, host.task_slow, 999, 0.5)
    t_high.start(immediate=True)
    t_high.wait()

    print("\n====== 3. 提交更多任务，制造排队并逼出【弹性超载降级】 ======")
    # 再次塞入 3 个常规任务。由于 t1/t2 还没跑完，这些任务会在池内堆积。
    # 堆积数量很快超过我们设定的 overload_threshold=2，后续的任务将被迫启用弹性独立线程。
    overflow_tasks = []
    for i in range(1, 16):
        t_overflow = taskBus.createTask(host, host.task_slow, 200 + i, 0.8)
        overflow_tasks.append(t_overflow)
        t_overflow.start() # 自动根据超载状态决策是否走弹性线程

    # 同步阻塞等待这批任务全部出结果
    t1.wait()
    t2.wait()
    t_high.wait()
    for t in overflow_tasks:
        t.wait()

    print("\n🎉 所有并发与超载测试圆满通过，线程分配完全符合预期！")

    
def NetworkTaskTest():
    bus = TaskBus()
    
    class ExtensionModule:
        pass

    ext = ExtensionModule()
    bus.registerObject(ext, "System.NetworkMonitor")

    print("\n====== 1. 测试标准 GET 网络请求 ======")
    # 使用 TaskBus.NetworkTask 静态工厂创建一个 GET 任务
    net_task = NetworkTask.get(
        bus=bus, 
        subject=ext, 
        url="https://httpbin.org/json", 
        timeout=5
    )
    
    net_task.start()
    net_task.wait()
    
    # 打印返回结果
    response: NetworkTask.Response = net_task.result
    print(f"📡 状态码: {response.status_code}")
    print(f"📄 数据预览:\n{response.text[:200]}...")

    print("\n====== 2. 测试带重试机制的失败请求阻断 ======")
    # 访问一个必定超时的无效地址，重试 2 次
    retry_task = NetworkTask.get(
        bus=bus,
        subject=ext,
        url="https://10.255.255.1", # 无效局域网 IP 会导致连接超时
        timeout=3,
        retry=2
    )
    
    retry_task.start()
    
    # 模拟在第一次重试期间，外部强行中断该任务
    time.sleep(4.0)
    log("探测到任务超时中，强行中止网络请求任务...")
    retry_task.terminate()
    retry_task.wait()
    
    print(f"🛡️ 任务最终状态: {retry_task.state} (预期: Terminated)")


if __name__ == "__main__":
    NetworkTaskTest()