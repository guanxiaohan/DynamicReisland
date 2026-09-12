import os
import json
import threading

import requests
from pydantic import BaseModel, Field

# 你的框架导入（保持不变）
from Utils import Service, UUID, classLog, classError, log, error, classWarning
from DI_Extension import Extension, ExtensionInfo

# ---------- Pydantic 模型 ----------
class TranslateRequest(BaseModel):
    content: str = Field(..., description="待翻译文本")
    source_lang: str = Field("auto", description="源语言代码")
    target_lang: str = Field("zh", description="目标语言代码")

class TranslateResponse(BaseModel):
    result: str
    usage: dict | None = None


class DeepSeekService(Service):
    """
    翻译中转服务（FastAPI 版）：启动 uvicorn 服务器，
    接收 POST 请求，调用 DeepSeek API，附加术语表，并广播 Token 用量。
    """

    def __init__(self):
        policy = Service.Policy(
            dedicatedThread=True,   # 启动 uvicorn 服务器需要独立线程
            permanentTick=True,    # 不需要定时 tick
            timer=-1,
            autoStart=True,
            dependencies=()
        )
        super().__init__("DeepSeek.DeepSeekService", policy)

        # 服务器配置
        self.host = "127.0.0.1"
        self.port = 45501

        # DeepSeek 配置
        self.api_key = None
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-v4-flash"   # 或 deepseek-chat

        # 中转鉴权密钥
        self.passkey = None

        # 术语表
        self.glossary = {}

        # uvicorn 服务器实例（用于关闭）
        self.uvicorn_server = None
        self.server_thread = None

    def initService(self):
        """初始化：读取 API Key、Passkey 和术语表"""
        # 1. 读取 DeepSeek API Key
        api_key_file = "./Extensions/deepseek_api_key.txt"
        if os.path.exists(api_key_file):
            with open(api_key_file, "r") as f:
                self.api_key = f.read().strip()
        else:
            self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            classError(self, "DeepSeek API key not found. Please put it in deepseek_api_key.txt or set DEEPSEEK_API_KEY env.")
        else:
            classLog(self, "DeepSeek API key loaded.")

        # 2. 读取中转鉴权 Passkey
        passkey_file = "translator_passkey.txt"
        if os.path.exists(passkey_file):
            with open(passkey_file, "r") as f:
                self.passkey = f.read().strip()
        else:
            self.passkey = "2ru982q3ur9py2r91pcabdskjwpIO"
            classWarning(self, f"No passkey file found, using default: {self.passkey}")
        classLog(self, "Passkey loaded.")

        # 3. 加载术语表
        glossary_file = "glossary.json"
        if os.path.exists(glossary_file):
            try:
                with open(glossary_file, "r", encoding="utf-8") as f:
                    self.glossary = json.load(f)
                classLog(self, f"Glossary loaded: {len(self.glossary)} entries.")
            except Exception as e:
                classError(self, f"Failed to load glossary: {e}")
                self.glossary = {}
        else:
            classLog(self, "No glossary file found, proceeding without glossary.")

    def onStart(self):
        import uvicorn
        """启动 FastAPI + uvicorn 服务器"""
        try:
            # 构建 FastAPI 应用（使用 self 作为闭包）
            app = self._build_app()
            # 配置 uvicorn
            config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
            self.uvicorn_server = uvicorn.Server(config)

            # 在独立线程中运行（因为 serve_forever 阻塞）
            self.server_thread = threading.Thread(
                target=self.uvicorn_server.run,
                name="DeepSeekFastAPI",
                daemon=True
            )
            self.server_thread.start()
            classLog(self, f"FastAPI server listening on {self.host}:{self.port}")
        except Exception as e:
            classError(self, f"Failed to start FastAPI server: {e}")
            self.stop()  # 启动失败则停止服务

    def _build_app(self):
        from fastapi import FastAPI, HTTPException, Depends, Header

        """构建 FastAPI 应用，并将服务实例绑定到路由"""
        service = self  # 闭包引用

        app = FastAPI(title="DeepSeek Translation Proxy", version="1.0")

        # 语言映射
        lang_map = {
            "zh": "中文",
            "en": "英文",
            "ja": "日语",
            "ko": "韩语",
            "fr": "法语",
            "de": "德语",
            "es": "西班牙语",
            "auto": "自动检测"
        }

        # ---------- 鉴权依赖 ----------
        def verify_passkey(authorization: str = Header(...)):
            if not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Invalid Authorization header")
            token = authorization.split(" ")[1]
            if token != service.passkey:
                raise HTTPException(status_code=401, detail="Invalid passkey")
            return token

        # ---------- 翻译端点 ----------
        @app.post("/", response_model=TranslateResponse)
        def translate(req: TranslateRequest, _=Depends(verify_passkey)):
            # 1. 构造系统提示
            system = "你是一个专业的翻译助手。"
            if service.glossary:
                glossary_items = [f"{k}: {v}" for k, v in service.glossary.items()]
                system += "请严格参考以下术语表进行翻译，术语表中的词汇必须按指定译法翻译：\n"
                system += "\n".join(glossary_items) + "\n"
            system += "只输出翻译结果，不要添加任何解释、备注或额外内容。"

            # 2. 用户消息
            src_name = lang_map.get(req.source_lang, req.source_lang)
            tgt_name = lang_map.get(req.target_lang, req.target_lang)
            user = f"请将以下{src_name}文本翻译成{tgt_name}，只输出翻译结果：\n\n{req.content}"

            # 3. 调用 DeepSeek API
            payload = {
                "model": service.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": 0.3,
                "stream": False,
                "extra_body": {"thinking": {"type": "disabled"}}
            }
            headers = {
                "Authorization": f"Bearer {service.api_key}",
                "Content-Type": "application/json"
            }

            try:
                resp = requests.post(service.base_url, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except requests.exceptions.RequestException as e:
                raise HTTPException(status_code=502, detail=f"DeepSeek API error: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

            # 4. 返回结果
            result = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage")

            # 广播用量事件（若需要）
            service._emit_usage_event(usage)

            return TranslateResponse(result=result, usage=usage)

        # 可选的健康检查
        @app.get("/health")
        def health():
            return {"status": "ok"}

        return app

    def translate(self, content, src, tgt):
        """
        保留原有 translate 方法以备直接调用（但本服务主要通过 HTTP 调用，
        此方法可保留用于内部测试或将来使用）
        """
        # 这里实现与之前相同的逻辑，但为了避免重复，你可以直接复用上面的代码。
        # 由于我们已用 FastAPI 处理，本方法可以留空或简单调用。
        # 但为了完整性，可以保留原实现，但建议弃用，因为现在所有请求走 HTTP。
        # 我选择保留空实现，或抛异常。
        raise NotImplementedError("Use HTTP endpoint instead.")

    def _emit_usage_event(self, usage):
        """通过事件总线广播 usage（目前注释掉，保留接口）"""
        # if usage and hasattr(self, 'eventBus') and self.eventBus:
        #     self.eventBus.emit(self, 'translation_usage', usage)
        pass

    def onStop(self):
        """停止 uvicorn 服务器"""
        if self.uvicorn_server:
            classLog(self, "Shutting down FastAPI server...")
            # uvicorn.Server 的 shutdown 方法
            self.uvicorn_server.should_exit = True
            # 等待线程结束
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=3)
            classLog(self, "FastAPI server stopped.")
        else:
            classLog(self, "No server running.")


# ==================== Extension 入口（保持不变）====================
class DeepSeekExtension(Extension):
    def extensionInfo(self):
        return ExtensionInfo(
            name="DeepSeek Translate Service",
            identifier="DeepSeek.CoreExtension",
            version="1.0",
            author="YourName"
        )

    def initExtension(self):
        service = DeepSeekService()
        self.registerService(service)
        classLog(self, "DeepSeek Translate Service registered.")


def extension_entry() -> Extension:
    return DeepSeekExtension()