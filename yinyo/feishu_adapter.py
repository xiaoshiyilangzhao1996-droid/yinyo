# feishu_adapter.py — 飞书适配层 v1.0
# Webhook 接收 + 消息路由 + 状态反馈 + 文件/媒体处理
# 对标 GA fsapp.py + Hermes feishu.py + OpenClaw deliver.ts
import json, os, time, re, hashlib, threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from feishu_card import build_card_messages, build_text_payload, is_card_invalid_error

try:
    import requests as http
except ImportError:
    http = None

# ── 常量 ─────────────────────────────────────────────────────────
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'temp', 'feishu_media')
BATCH_DELAY = 0.3
PROCESSING_REACTION = "THUMBSUP"
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

# @提及解析正则（飞书 <at user_id="ou_xxx">@Name</at> 格式）
_AT_MENTION_RE = re.compile(r'<at\s+user_id=["\']([^"\']+)["\'][^>]*>[^<]*</at>')

# 支持的媒体类型
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
AUDIO_EXTS = {".opus", ".mp3", ".wav", ".m4a", ".aac"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class FeishuAdapter:
    """飞书适配器。Webhook 接收 + API 发送。"""

    def __init__(self, agent, config: dict = None):
        self.agent = agent
        self.config = config or {}
        self.app_id = self.config.get("app_id", os.environ.get("FEISHU_APP_ID", ""))
        self.app_secret = self.config.get("app_secret", os.environ.get("FEISHU_APP_SECRET", ""))
        self.verify_token = self.config.get("verify_token", os.environ.get("FEISHU_VERIFY_TOKEN", ""))
        self._tenant_token = None
        self._token_expiry = 0
        self.server: HTTPServer | None = None
        os.makedirs(MEDIA_DIR, exist_ok=True)

    # ── Token 管理 ────────────────────────────────────────────────

    def _get_tenant_token(self) -> str:
        """获取 tenant_access_token（自动缓存）。"""
        now = time.time()
        if self._tenant_token and now < self._token_expiry - 60:
            return self._tenant_token

        if not http:
            raise RuntimeError("requests library required for Feishu API")

        resp = http.post(
            f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get tenant token: {data}")
        self._tenant_token = data["tenant_access_token"]
        self._token_expiry = now + data.get("expire", 7200)
        return self._tenant_token

    # ── 消息发送 ──────────────────────────────────────────────────

    def send_message(self, chat_id: str, text: str, reply_to: str = None,
                     files: list = None) -> dict:
        """发送消息到飞书。自动 Card 2.0 + 分段 + fallback。

        Args:
            chat_id: 飞书 chat_id (oc_xxx) 或 open_id (ou_xxx)
            text: Markdown 回复内容
            reply_to: 可选，回复某条消息的 message_id
            files: 可选，要发送的文件路径列表

        Returns:
            {"success": True/False, "message_ids": [...], "fallback": False/True}
        """
        results = []
        fallback = False

        # 先尝试 Card 2.0
        cards = build_card_messages(text)
        for i, card in enumerate(cards):
            result = self._send_card(chat_id, card, reply_to if i == 0 else None)
            if not result.get("success"):
                # Card 拒绝 → 降级为纯文本
                if is_card_invalid_error(result.get("error", "")):
                    fallback = True
                    text_result = self._send_text(chat_id, text, reply_to)
                    results.append(text_result)
                    break
                else:
                    results.append(result)
            else:
                results.append(result)
            # 分段延迟
            if i < len(cards) - 1:
                time.sleep(BATCH_DELAY)

        # 发送文件/媒体
        if files:
            for fp in files:
                if os.path.isfile(fp):
                    media_result = self._send_media(chat_id, fp, reply_to)
                    results.append(media_result)

        return {
            "success": all(r.get("success") for r in results),
            "message_ids": [r.get("message_id", "") for r in results],
            "fallback": fallback
        }

    def add_reaction(self, message_id: str, reaction: str = PROCESSING_REACTION) -> bool:
        """添加消息 reaction。"""
        try:
            token = self._get_tenant_token()
            resp = http.post(
                f"{FEISHU_API_BASE}/im/v1/messages/{message_id}/reactions",
                headers={"Authorization": f"Bearer {token}"},
                json={"reaction_type": {"emoji_type": reaction}},
                timeout=5
            )
            return resp.json().get("code") == 0
        except Exception:
            return False

    def remove_reaction(self, message_id: str, reaction: str = PROCESSING_REACTION) -> bool:
        """移除消息 reaction。"""
        try:
            token = self._get_tenant_token()
            resp = http.delete(
                f"{FEISHU_API_BASE}/im/v1/messages/{message_id}/reactions/{reaction}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5
            )
            return resp.json().get("code") == 0
        except Exception:
            return False

    # ── 内部发送方法 ──────────────────────────────────────────────

    def _send_card(self, chat_id: str, card: dict, reply_to: str = None) -> dict:
        """发送 Card 2.0 消息。"""
        try:
            token = self._get_tenant_token()
            body = {
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": card["content"]
            }
            if reply_to:
                resp = http.post(
                    f"{FEISHU_API_BASE}/im/v1/messages/{reply_to}/reply",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"content": card["content"], "msg_type": "interactive"},
                    timeout=10
                )
            else:
                resp = http.post(
                    f"{FEISHU_API_BASE}/im/v1/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": chat_id,
                        "msg_type": "interactive",
                        "content": card["content"]
                    },
                    timeout=10
                )
            data = resp.json()
            if data.get("code") != 0:
                return {"success": False, "error": data.get("msg", str(data))}
            return {"success": True, "message_id": data.get("data", {}).get("message_id", "")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _send_text(self, chat_id: str, text: str, reply_to: str = None) -> dict:
        """发送纯文本消息（Card 拒绝时降级）。"""
        try:
            token = self._get_tenant_token()
            content = build_text_payload(text)
            if reply_to:
                resp = http.post(
                    f"{FEISHU_API_BASE}/im/v1/messages/{reply_to}/reply",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"content": content, "msg_type": "text"},
                    timeout=10
                )
            else:
                resp = http.post(
                    f"{FEISHU_API_BASE}/im/v1/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"receive_id": chat_id, "msg_type": "text", "content": content},
                    timeout=10
                )
            data = resp.json()
            return {"success": data.get("code") == 0,
                    "message_id": data.get("data", {}).get("message_id", ""),
                    "fallback": True}
        except Exception as e:
            return {"success": False, "error": str(e), "fallback": True}

    def _send_media(self, chat_id: str, file_path: str, reply_to: str = None) -> dict:
        """发送文件/图片/视频/音频。"""
        ext = os.path.splitext(file_path)[1].lower()
        try:
            token = self._get_tenant_token()
            # 上传
            file_type = self._guess_file_type(ext)
            file_size = os.path.getsize(file_path)
            with open(file_path, 'rb') as f:
                upload_resp = http.post(
                    f"{FEISHU_API_BASE}/im/v1/files",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": (os.path.basename(file_path), f)},
                    data={"file_type": file_type, "file_name": os.path.basename(file_path)},
                    timeout=30
                )
            upload_data = upload_resp.json()
            if upload_data.get("code") != 0:
                return {"success": False, "error": upload_data.get("msg", "Upload failed")}

            file_key = upload_data["data"]["file_key"]
            # 根据类型选择 API
            if ext in IMAGE_EXTS:
                content = json.dumps({"image_key": file_key})
                msg_type = "image"
            elif ext in AUDIO_EXTS:
                content = json.dumps({"file_key": file_key})
                msg_type = "audio"
            elif ext in VIDEO_EXTS:
                content = json.dumps({"file_key": file_key})
                msg_type = "media"
            else:
                content = json.dumps({"file_key": file_key})
                msg_type = "file"

            if reply_to:
                resp = http.post(
                    f"{FEISHU_API_BASE}/im/v1/messages/{reply_to}/reply",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"content": content, "msg_type": msg_type},
                    timeout=10
                )
            else:
                resp = http.post(
                    f"{FEISHU_API_BASE}/im/v1/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"receive_id": chat_id, "msg_type": msg_type, "content": content},
                    timeout=10
                )
            return {"success": resp.json().get("code") == 0,
                    "message_id": resp.json().get("data", {}).get("message_id", "")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _guess_file_type(ext: str) -> str:
        if ext in IMAGE_EXTS: return "image"
        if ext in AUDIO_EXTS: return "opus" if ext == ".opus" else "mp3"
        if ext in VIDEO_EXTS: return "mp4"
        if ext == ".pdf": return "pdf"
        if ext in (".doc", ".docx"): return "doc"
        if ext in (".xls", ".xlsx"): return "xls"
        if ext in (".ppt", ".pptx"): return "ppt"
        return "stream"

    # ── Webhook Server ────────────────────────────────────────────

    def start_server(self, host: str = "0.0.0.0", port: int = 8080):
        """启动 Webhook 服务器（阻塞）。"""
        adapter = self

        class FeishuHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                try:
                    event = json.loads(body)
                except json.JSONDecodeError:
                    self._respond(400, {"error": "Invalid JSON"})
                    return

                # URL 验证（飞书首次配置时）
                if event.get("type") == "url_verification":
                    token = event.get("token", "")
                    if adapter.verify_token and token != adapter.verify_token:
                        self._respond(403, {})
                        return
                    self._respond(200, {"challenge": event.get("challenge", "")})
                    return

                # 消息事件
                if event.get("type") == "event_callback":
                    inner = event.get("event", {})
                    msg = inner.get("message", {})
                    msg_type = msg.get("message_type", "text")
                    if msg_type == "text":
                        threading.Thread(
                            target=adapter._handle_text_message,
                            args=(inner,),
                            daemon=True
                        ).start()
                    elif msg_type == "image":
                        # v8.0: 图片消息 → 下载 + 调用 do_vision
                        threading.Thread(
                            target=adapter._handle_image_message,
                            args=(inner,),
                            daemon=True
                        ).start()
                    self._respond(200, {})
                    return

                self._respond(200, {})

            def _respond(self, code: int, data: dict):
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def log_message(self, format, *args):
                pass  # 静默日志

        self.server = HTTPServer((host, port), FeishuHandler)
        print(f"[YINYO] Feishu webhook server started on {host}:{port}")
        self.server.serve_forever()

    # ── 消息处理 ──────────────────────────────────────────────────

    def _handle_text_message(self, event: dict):
        """处理文本消息。"""
        msg = event.get("message", {})
        text = json.loads(msg.get("content", "{}")).get("text", "")
        if not text:
            return

        # @提及标准化：<at user_id="ou_xxx">@Name</at> → @open_id:ou_xxx
        text = _AT_MENTION_RE.sub(r'@open_id:\1', text)

        chat_id = msg.get("chat_id", "")
        message_id = msg.get("message_id", "")
        user_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
        root_message_id = msg.get("root_id", "")

        if not self.agent:
            return

        # 去重
        if self.agent.session_manager.is_duplicate(text, user_id):
            return

        # Processing reaction
        if message_id:
            self.add_reaction(message_id)

        try:
            result = self.agent.handle_message(user_id, chat_id, text)
        except Exception as e:
            result = {"text": f"❌ 处理出错: {e}", "files": []}

        # 移除 processing reaction
        if message_id:
            self.remove_reaction(message_id)

        if result is None:
            return

        reply_text = result.get("text", "")
        reply_files = result.get("files", [])

        if reply_text or reply_files:
            self.send_message(
                chat_id,
                reply_text,
                reply_to=message_id or root_message_id,
                files=reply_files
            )

    def _handle_image_message(self, event: dict):
        """v8.0: 处理图片消息。下载图片 → 调用 do_vision → 文本注入 Agent。"""
        msg = event.get("message", {})
        image_key = msg.get("content", "")

        # 尝试解析 image_key（飞书格式：{\"image_key\":\"xxx\"}）
        if isinstance(image_key, str):
            try:
                image_key = json.loads(image_key).get("image_key", image_key)
            except json.JSONDecodeError:
                pass

        chat_id = msg.get("chat_id", "")
        message_id = msg.get("message_id", "")
        user_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
        root_message_id = msg.get("root_id", "")

        if not self.agent or not image_key:
            return

        # 下载图片
        image_path = self._download_image(image_key)
        if not image_path:
            # 尝试用 image_key 作为路径
            image_path = image_key

        # 调用 do_vision
        try:
            from vision_adapter import get_vision_adapter
            adapter = get_vision_adapter()
            vision_result = adapter.describe(image_path, "请详细描述这张图片的内容")
            description = vision_result.get("description", "")
            if vision_result.get("error"):
                description = f"[Image received but vision failed: {vision_result['error']}]"
        except Exception as e:
            description = f"[Image received but vision failed: {e}]"

        # 构建上下文文本
        text = f"[Image message received]\n{description}"

        # Processing reaction
        if message_id:
            self.add_reaction(message_id)

        try:
            result = self.agent.handle_message(user_id, chat_id, text)
        except Exception as e:
            result = {"text": f"\u274c 处理出错: {e}", "files": []}

        if message_id:
            self.remove_reaction(message_id)

        if result is None:
            return

        reply_text = result.get("text", "")
        reply_files = result.get("files", [])

        if reply_text or reply_files:
            self.send_message(
                chat_id, reply_text,
                reply_to=message_id or root_message_id,
                files=reply_files
            )

    def _download_image(self, image_key: str) -> str | None:
        """下载飞书图片到本地。"""
        try:
            token = self._get_tenant_token()
            resp = http.get(
                f"{FEISHU_API_BASE}/im/v1/images/{image_key}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if resp.status_code != 200:
                return None

            ext = ".png"
            content_type = resp.headers.get("Content-Type", "")
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "gif" in content_type:
                ext = ".gif"
            elif "webp" in content_type:
                ext = ".webp"

            path = os.path.join(MEDIA_DIR, f"img_{image_key[:12]}{ext}")
            with open(path, "wb") as f:
                f.write(resp.content)
            return path
        except Exception:
            return None
