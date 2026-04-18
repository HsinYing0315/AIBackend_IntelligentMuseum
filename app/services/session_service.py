"""
In-memory session and room manager for group chat.

Manages rooms, user sessions, and per-room conversation history.
"""
import uuid
import threading
from datetime import datetime


class SessionManager:
    """Thread-safe in-memory manager for chat rooms and conversation history."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern — one SessionManager per process."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # room_id -> room dict
        self.rooms: dict = {}
        # sid -> { user_name, room_id }
        self.users: dict = {}
        # Guards concurrent access
        self._data_lock = threading.Lock()

    # ─── Room Management ──────────────────────────────────────────────

    def create_room(self, room_id: str | None = None, npc_role: str = "博物館導覽員",
                    lang: str = "zh-TW", personality: str = "",
                    is_rag: bool = True) -> str:
        """Create a new room. Returns the room_id."""
        if room_id is None:
            room_id = str(uuid.uuid4())[:8]

        with self._data_lock:
            if room_id not in self.rooms:
                self.rooms[room_id] = {
                    "npc_role": npc_role,
                    "lang": lang,
                    "personality": personality,
                    "is_rag": is_rag,
                    "users": {},        # sid -> user_name
                    "history": [],      # list of message dicts
                    "created_at": datetime.now().isoformat(),
                }
        return room_id

    def delete_room(self, room_id: str):
        """Delete a room and disconnect all users in it."""
        with self._data_lock:
            room = self.rooms.pop(room_id, None)
            if room:
                for sid in list(room["users"].keys()):
                    self.users.pop(sid, None)

    def get_room(self, room_id: str) -> dict | None:
        """Return room info or None."""
        return self.rooms.get(room_id)

    def list_rooms(self) -> list[dict]:
        """Return a summary of all active rooms."""
        result = []
        for room_id, room in self.rooms.items():
            result.append({
                "room_id": room_id,
                "npc_role": room["npc_role"],
                "lang": room["lang"],
                "user_count": len(room["users"]),
                "message_count": len(room["history"]),
                "created_at": room["created_at"],
            })
        return result

    # ─── User Management ──────────────────────────────────────────────

    def join_room(self, sid: str, room_id: str, user_name: str) -> bool:
        """Add a user to a room. Returns True if successful."""
        with self._data_lock:
            room = self.rooms.get(room_id)
            if room is None:
                return False
            room["users"][sid] = user_name
            self.users[sid] = {
                "user_name": user_name,
                "room_id": room_id,
            }
        return True

    def leave_room(self, sid: str) -> tuple[str | None, str | None]:
        """Remove a user. Returns (room_id, user_name) or (None, None)."""
        with self._data_lock:
            user_info = self.users.pop(sid, None)
            if user_info is None:
                return None, None
            room_id = user_info["room_id"]
            user_name = user_info["user_name"]
            room = self.rooms.get(room_id)
            if room:
                room["users"].pop(sid, None)
                # If room is empty, keep it alive so history is preserved
            return room_id, user_name

    def get_user(self, sid: str) -> dict | None:
        """Get user info by socket id."""
        return self.users.get(sid)

    def get_room_users(self, room_id: str) -> list[str]:
        """Return list of user names in a room."""
        room = self.rooms.get(room_id)
        if room is None:
            return []
        return list(room["users"].values())

    # ─── Conversation History ─────────────────────────────────────────

    def append_message(self, room_id: str, role: str, name: str,
                       content: str, lang: str = ""):
        """Append a message to room history.
        
        Args:
            role: 'user' or 'npc'
            name: user_name or npc_role
            content: message text
            lang: language code of the message
        """
        with self._data_lock:
            room = self.rooms.get(room_id)
            if room is None:
                return
            room["history"].append({
                "role": role,
                "name": name,
                "content": content,
                "lang": lang,
                "timestamp": datetime.now().isoformat(),
            })

    def get_history(self, room_id: str, last_n: int = 20) -> list[dict]:
        """Return the last N messages from a room's history."""
        room = self.rooms.get(room_id)
        if room is None:
            return []
        return room["history"][-last_n:]

    def format_history_for_prompt(self, room_id: str, last_n: int = 20) -> str:
        """Format conversation history as a string for LLM prompt injection."""
        messages = self.get_history(room_id, last_n)
        if not messages:
            return ""

        lines = []
        for msg in messages:
            role_label = msg["name"]
            lines.append(f"{role_label}: {msg['content']}")
        return "\n".join(lines)
