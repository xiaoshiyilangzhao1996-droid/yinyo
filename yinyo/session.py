# session.py — 会话管理 + 命令系统 v1.0
# 对标 GA chatapp_common.py + Hermes session management
import time, hashlib, json
from dataclasses import dataclass, field


COMMAND_HELP = """📖 可用命令：
/help — 显示帮助
/status — 查看当前会话状态
/stop — 停止当前任务
/new — 开启新对话（清空上下文）
/continue — 列出可恢复的会话"""


@dataclass
class Session:
    """单个用户会话。"""
    user_id: str
    chat_id: str
    messages: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    stopped: bool = False
    run_count: int = 0

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})
        self.last_active = time.time()

    def add_assistant_message(self, result: dict):
        content = result.get("final_response", "") or json.dumps(result, ensure_ascii=False)
        self.messages.append({"role": "assistant", "content": content[:2000]})
        self.run_count += 1
        self.last_active = time.time()

    def clear(self):
        self.messages = []
        self.stopped = False

    def stop(self):
        self.stopped = True

    def status_report(self) -> str:
        uptime = int(time.time() - self.created_at)
        idle = int(time.time() - self.last_active)
        return (
            f"📊 会话状态\n"
            f"• 消息数: {len(self.messages)}\n"
            f"• 运行次数: {self.run_count}\n"
            f"• 运行中: {'已停止' if self.stopped else '空闲'}\n"
            f"• 会话时长: {uptime}s\n"
            f"• 空闲: {idle}s"
        )


class SessionManager:
    """多用户/多对话 session 管理。"""

    def __init__(self, ttl: int = 3600, dedup_ttl: int = 60):
        self.sessions: dict[str, Session] = {}
        self.ttl = ttl
        self.dedup_ttl = dedup_ttl
        self.dedup_store: dict[str, float] = {}

    def get_or_create(self, user_id: str, chat_id: str) -> Session:
        self._cleanup_expired()
        sid = f"{user_id}:{chat_id}"
        if sid not in self.sessions:
            self.sessions[sid] = Session(user_id, chat_id)
        return self.sessions[sid]

    def handle_command(self, text: str, session: Session) -> dict | None:
        """处理命令。返回回复 dict 或 None（非命令）。"""
        if not text.startswith('/'):
            return None

        parts = text.strip().split()
        cmd = parts[0].lower()

        # v8.2: /continue [N] 必须在精确匹配 /continue 之前检查
        if cmd.startswith('/continue') and len(parts) > 1:
            try:
                n = int(parts[1])
                return {"text": self._restore_session(session.user_id, n)}
            except ValueError:
                return {"text": f"用法: /continue [编号]。输入 /continue 查看可用会话。"}

        if cmd == '/help':
            return {"text": COMMAND_HELP}

        elif cmd == '/new':
            session.clear()
            return {"text": "✅ 新对话已开始。上下文已清空。"}

        elif cmd == '/stop':
            session.stop()
            return {"text": "⏹ 任务已停止。"}

        elif cmd == '/status':
            return {"text": session.status_report()}

        elif cmd == '/continue':
            return {"text": self._list_sessions(session.user_id)}

        return {"text": f"未知命令: {cmd}。输入 /help 查看可用命令。"}

    def is_duplicate(self, text: str, user_id: str) -> bool:
        """消息去重（MD5 + TTL）。

        对标 GA _claim_message_once()：飞书重连会重复推送消息，
        同一个 user+text 在 dedup_ttl 秒内只处理一次。
        """
        h = hashlib.md5(f"{user_id}:{text.strip()}".encode()).hexdigest()
        now = time.time()
        # 清理过期
        expired = [k for k, ts in self.dedup_store.items() if now - ts > self.dedup_ttl]
        for k in expired:
            del self.dedup_store[k]
        if h in self.dedup_store:
            return True
        self.dedup_store[h] = now
        return False

    def _list_sessions(self, user_id: str) -> str:
        """列出用户的可恢复会话。"""
        user_sessions = [
            (sid, s) for sid, s in self.sessions.items()
            if s.user_id == user_id and len(s.messages) > 0
        ]
        if not user_sessions:
            return "📭 没有可恢复的会话。"
        lines = ["📋 可恢复的会话："]
        for i, (sid, s) in enumerate(user_sessions, 1):
            preview = s.messages[-1]["content"][:60] if s.messages else "(空)"
            lines.append(f"  {i}. {preview}... ({len(s.messages)} 条消息)")
        lines.append("\n输入 /continue [编号] 恢复。")
        return "\n".join(lines)

    def _restore_session(self, user_id: str, n: int) -> str:
        user_sessions = [
            s for sid, s in self.sessions.items()
            if s.user_id == user_id and len(s.messages) > 0
        ]
        if 1 <= n <= len(user_sessions):
            s = user_sessions[n - 1]
            return f"✅ 已恢复会话 #{n}（{len(s.messages)} 条消息）。发送消息继续对话。"
        return f"无效的编号: {n}。有效范围: 1-{len(user_sessions)}。"

    def _cleanup_expired(self):
        """清理过期 session。"""
        now = time.time()
        expired = [
            sid for sid, s in self.sessions.items()
            if now - s.last_active > self.ttl
        ]
        for sid in expired:
            del self.sessions[sid]
