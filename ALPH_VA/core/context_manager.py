# core/context_manager.py

import json
import os
from datetime import datetime
from google.genai import types
from core import config_manager
import logging
import uuid

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

# --- Konstanta Path ---
DEFAULT_ARCHIVE_FILENAME = "chat_sessions.json"
DATA_DIR = os.path.join(config_manager.PROJECT_ROOT_DIR, "data")
MEMORY_DIR = os.path.join(DATA_DIR, "memory")
if not os.path.exists(MEMORY_DIR):
    os.makedirs(MEMORY_DIR)
    logger.info(f"Created memory directory: {MEMORY_DIR}")

archive_filename = config_manager.get_config_value("general", "chat_archive_filename", DEFAULT_ARCHIVE_FILENAME)
if not isinstance(archive_filename, str) or not archive_filename:
    archive_filename = DEFAULT_ARCHIVE_FILENAME
ARCHIVE_FILE_PATH = os.path.join(MEMORY_DIR, archive_filename)
logger.info(f"Context archive file path set to: {ARCHIVE_FILE_PATH}")

def _serialize_content(content_obj: types.Content) -> dict:
    parts_data = []
    if hasattr(content_obj, 'parts') and content_obj.parts:
        parts_data = [{"text": part.text if hasattr(part, 'text') else str(part)} for part in content_obj.parts]
    return {
        "role": content_obj.role if hasattr(content_obj, 'role') else "user",
        "parts": parts_data
    }

def _deserialize_content(content_dict: dict) -> types.Content:
    return types.Content(
        role=content_dict.get("role", "user"),
        parts=[types.Part(text=part_data.get("text", "")) for part_data in content_dict.get("parts", [])]
    )

class ContextManager:
    """
    Setiap instance ContextManager mewakili satu session.
    Semua session disimpan dalam satu file JSON dengan struktur:
    {
        "sessions": {
            "session_id_1": {...},
            "session_id_2": {...},
            ...
        }
    }
    """
    ARCHIVE_FILE_PATH = ARCHIVE_FILE_PATH

    def __init__(self, session_id: str = None, user: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.user = user or "anonymous"
        self.created_at = datetime.now().isoformat()
        self._chat_session_history = []
        logger.info(f"ContextManager initialized for session_id: {self.session_id}")

    def remember(self, role: str, text: str):
        valid_role = role if role in ["user", "model"] else "user"
        self._chat_session_history.append(
            types.Content(
                role=valid_role,
                parts=[types.Part(text=text)]
            )
        )
        logger.debug(f"Remembered message: Role='{valid_role}', Text='{text[:50]}...'")

    def retrieve(self) -> list:
        logger.debug(f"Retrieved chat history with {len(self._chat_session_history)} messages.")
        return list(self._chat_session_history)

    def clear_memory(self):
        self._chat_session_history = []
        logger.info(f"Session history for session_id {self.session_id} cleared from memory.")

    def to_dict(self):
        return {
            "created_at": self.created_at,
            "user": self.user,
            "history": [_serialize_content(msg) for msg in self._chat_session_history]
        }

    @classmethod
    def _load_all_sessions(cls):
        if os.path.exists(cls.ARCHIVE_FILE_PATH):
            try:
                with open(cls.ARCHIVE_FILE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "sessions" in data and isinstance(data["sessions"], dict):
                        return data["sessions"]
            except Exception as e:
                logger.error(f"Error loading sessions from archive: {e}")
        return {}

    @classmethod
    def _save_all_sessions(cls, sessions_dict):
        try:
            with open(cls.ARCHIVE_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump({"sessions": sessions_dict}, f, indent=4, ensure_ascii=False)
            logger.info(f"All sessions saved to {cls.ARCHIVE_FILE_PATH}")
        except Exception as e:
            logger.error(f"Error saving sessions to archive: {e}")

    def save_to_archive(self):
        """Simpan session ini ke file archive (update jika sudah ada, tambah jika baru)."""
        sessions = self._load_all_sessions()
        sessions[self.session_id] = self.to_dict()
        self._save_all_sessions(sessions)
        logger.info(f"Session {self.session_id} archived with {len(self._chat_session_history)} messages.")

    @classmethod
    def load_from_archive(cls, session_id: str):
        """Load session dari archive berdasarkan session_id."""
        sessions = cls._load_all_sessions()
        if session_id not in sessions:
            logger.warning(f"Session {session_id} not found in archive.")
            return None
        session_data = sessions[session_id]
        obj = cls(session_id=session_id, user=session_data.get("user"))
        obj.created_at = session_data.get("created_at", datetime.now().isoformat())
        obj._chat_session_history = [
            _deserialize_content(msg_dict) for msg_dict in session_data.get("history", [])
        ]
        logger.info(f"Session {session_id} loaded from archive with {len(obj._chat_session_history)} messages.")
        return obj

    @classmethod
    def list_sessions(cls):
        """Return list of all session IDs and metadata."""
        sessions = cls._load_all_sessions()
        return [
            {
                "session_id": sid,
                "created_at": sdata.get("created_at"),
                "user": sdata.get("user"),
                "message_count": len(sdata.get("history", []))
            }
            for sid, sdata in sessions.items()
        ]

    def delete_from_archive(self):
        """Hapus session ini dari archive."""
        sessions = self._load_all_sessions()
        if self.session_id in sessions:
            del sessions[self.session_id]
            self._save_all_sessions(sessions)
            logger.info(f"Session {self.session_id} deleted from archive.")
        else:
            logger.warning(f"Session {self.session_id} not found in archive.")
            
if __name__ == "__main__":
    # Contoh penggunaan
    
    # cm = ContextManager(user="test_user")
    # cm.remember("user", "Hello, how are you?")
    # cm.remember("model", "I'm fine, thank you!")
    # cm.save_to_archive()
    
    
    list_of_sessions = ContextManager.list_sessions()
    # for session in list_of_sessions:
    #     print(f"Session ID: {session['session_id']}, Created At: {session['created_at']}, Messages: {session['message_count']}")
    
    # load last created session
    loaded_cm = ContextManager.load_from_archive(list_of_sessions[-1]['session_id'])
    if loaded_cm:
        print(f"Loaded session {loaded_cm.session_id} with {len(loaded_cm.retrieve())} messages.")
        
    # loaded_cm.remember("user", "New message after loading.")
    # loaded_cm.save_to_archive()
    
    # loaded_cm.delete_from_archive() # Hapus session dari archive