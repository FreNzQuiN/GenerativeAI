# core/context_manager.py
import json
import os
import logging
import uuid
from datetime import datetime
from google.genai import types
from core.config_manager import ConfigManager

# --- Global Config Instance ---
try:
    _cfg = ConfigManager()
except Exception as e_cfg_init_cm:
    print(
        f"CRITICAL ERROR in context_manager.py: Failed to initialize ConfigManager: {e_cfg_init_cm}"
    )
    raise RuntimeError(
        f"ContextManager: ConfigManager initialization failed: {e_cfg_init_cm}"
    ) from e_cfg_init_cm

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        _log_dir_cm = _cfg.get_config_value(
            "general",
            "log_dir",
            os.path.join(
                _cfg.get_config_value(
                    "general",
                    "project_root_dir",
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ),
                "logs",
            ),
        )
        if not os.path.exists(_log_dir_cm):
            os.makedirs(_log_dir_cm, exist_ok=True)
        log_file_path = os.path.join(
            _log_dir_cm, f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
        )
    except Exception as e_log_path_cm:
        logger.error(
            "Error determining log_file_path for context_manager: %s. Using fallback.",
            e_log_path_cm,
            exc_info=False,
        )
        log_file_path = f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
    try:
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)
    except OSError as e_fh_cm:
        logger.error(
            "OSError setting up file handler for context_manager: %s. Using basicConfig.",
            e_fh_cm,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    except Exception as e_log_cm:
        logger.error(
            "Unexpected error setting up logger for context_manager: %s. Using basicConfig.",
            e_log_cm,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

DEFAULT_ARCHIVE_FILENAME = "chat_sessions.json"
PROJECT_ROOT = _cfg.get_config_value(
    "general",
    "project_root_dir",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MEMORY_DIR = os.path.join(DATA_DIR, "memory")

if not os.path.exists(MEMORY_DIR):
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
        logger.info("Created/Ensured memory directory: %s", MEMORY_DIR)
    except OSError as e:
        logger.error(
            "Failed to create memory directory %s: %s", MEMORY_DIR, e, exc_info=True
        )

archive_filename_from_config = DEFAULT_ARCHIVE_FILENAME
cfg_val = _cfg.get_config_value(
    "general", "chat_archive_filename", DEFAULT_ARCHIVE_FILENAME
)
if isinstance(cfg_val, str) and cfg_val.strip():
    archive_filename_from_config = cfg_val.strip()
else:
    logger.warning(
        "Invalid chat_archive_filename from config ('%s'). Using default: %s",
        cfg_val,
        DEFAULT_ARCHIVE_FILENAME,
    )

_ARCHIVE_FILE_PATH_MODULE_LEVEL = os.path.join(MEMORY_DIR, archive_filename_from_config)
logger.info("Context archive file path set to: %s", _ARCHIVE_FILE_PATH_MODULE_LEVEL)


def _serialize_content(content_obj: types.Content) -> dict:
    parts_data = []
    if hasattr(content_obj, "parts") and content_obj.parts:
        for part in content_obj.parts:
            if hasattr(part, "text"):
                parts_data.append({"text": part.text})
            else:
                parts_data.append({"text": str(part)})
    role = "user"
    if hasattr(content_obj, "role") and content_obj.role:
        role = content_obj.role
    return {"role": role, "parts": parts_data}


def _deserialize_content(content_dict: dict) -> types.Content:
    if not isinstance(content_dict, dict):
        logger.error(
            "Cannot deserialize content, expected dict, got %s", type(content_dict)
        )
        return types.Content(
            role="user", parts=[types.Part(text="[Deserialization Error]")]
        )
    parts_list = []
    for part_data in content_dict.get("parts", []):
        if isinstance(part_data, dict) and "text" in part_data:
            parts_list.append(types.Part(text=str(part_data.get("text", ""))))
        else:
            parts_list.append(types.Part(text="[Malformed Part Data]"))
    return types.Content(role=str(content_dict.get("role", "user")), parts=parts_list)


class ContextManager:
    _archive_file_path_class_level = _ARCHIVE_FILE_PATH_MODULE_LEVEL

    def __init__(self, session_id: str | None = None, user: str | None = None):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.user: str = user or "anonymous"
        self.created_at: str = datetime.now().isoformat()
        self._chat_session_history: list[types.Content] = []
        logger.info(
            "ContextManager initialized for session_id: %s, user: %s",
            self.session_id,
            self.user,
        )

    def remember(self, role: str, text: str):
        if not (isinstance(role, str) and isinstance(text, str)):
            logger.warning(
                "Invalid input for remember: role type %s, text type %s. Skipping.",
                type(role),
                type(text),
            )
            return
        valid_role = role.lower() if role.lower() in ["user", "model"] else "user"
        try:
            content = types.Content(role=valid_role, parts=[types.Part(text=text)])
            self._chat_session_history.append(content)
            logger.debug(
                "Session %s: Remembered '%s' message: '%s...'",
                self.session_id,
                valid_role,
                text[:50],
            )
        except Exception as e:
            logger.error(
                "Error creating types.Content for remembering: %s", e, exc_info=True
            )

    def retrieve(self) -> list[types.Content]:
        logger.debug(
            "Session %s: Retrieved chat history with %d messages.",
            self.session_id,
            len(self._chat_session_history),
        )
        return list(self._chat_session_history)

    def clear_memory(self):
        self._chat_session_history = []
        logger.info("Session %s: In-memory history cleared.", self.session_id)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "user": self.user,
            "history": [_serialize_content(msg) for msg in self._chat_session_history],
        }

    @classmethod
    def _load_all_sessions_from_file(cls) -> dict:
        archive_path = cls._archive_file_path_class_level
        if not os.path.exists(archive_path):
            logger.info(
                "Archive file %s not found. Returning empty sessions dict.",
                archive_path,
            )
            return {}
        try:
            with open(archive_path, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                logger.info(
                    "Archive file %s is empty. Returning empty sessions dict.",
                    archive_path,
                )
                return {}
            data = json.loads(content)
            if (
                isinstance(data, dict)
                and "sessions" in data
                and isinstance(data["sessions"], dict)
            ):
                return data["sessions"]
            else:
                logger.warning(
                    "Archive file %s has invalid structure. Expected {'sessions': {}}. Returning empty.",
                    archive_path,
                )
                return {}
        except json.JSONDecodeError as e:
            logger.error(
                "Error decoding JSON from archive %s: %s. Returning empty.",
                archive_path,
                e,
                exc_info=True,
            )
            return {}
        except OSError as e:
            logger.error(
                "OSError loading sessions from archive %s: %s. Returning empty.",
                archive_path,
                e,
                exc_info=True,
            )
            return {}
        except Exception as e:
            logger.error(
                "Unexpected error loading sessions from archive %s: %s. Returning empty.",
                archive_path,
                e,
                exc_info=True,
            )
            return {}

    @classmethod
    def _save_all_sessions_to_file(cls, sessions_dict: dict) -> bool:
        archive_path = cls._archive_file_path_class_level
        if not isinstance(sessions_dict, dict):
            logger.error("_save_all_sessions_to_file expects a dict. Aborting save.")
            return False
        try:
            os.makedirs(os.path.dirname(archive_path), exist_ok=True)
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump({"sessions": sessions_dict}, f, indent=4, ensure_ascii=False)
            logger.info("All sessions successfully saved to %s", archive_path)
            return True
        except OSError as e:
            logger.error(
                "OSError saving sessions to archive %s: %s",
                archive_path,
                e,
                exc_info=True,
            )
            return False
        except TypeError as e:
            logger.error(
                "TypeError during JSON serialization to %s: %s",
                archive_path,
                e,
                exc_info=True,
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error saving sessions to archive %s: %s",
                archive_path,
                e,
                exc_info=True,
            )
            return False

    def save_to_archive(self) -> bool:
        all_sessions = self._load_all_sessions_from_file()
        all_sessions[self.session_id] = self.to_dict()
        if self._save_all_sessions_to_file(all_sessions):
            logger.info(
                "Session %s archived with %d messages.",
                self.session_id,
                len(self._chat_session_history),
            )
            return True
        logger.error("Failed to archive session %s.", self.session_id)
        return False

    @classmethod
    def load_from_archive(cls, session_id: str) -> "ContextManager | None":
        if not (isinstance(session_id, str) and session_id.strip()):
            logger.warning(
                "Invalid session_id for loading: type %s, value '%s'. Must be non-empty string.",
                type(session_id),
                session_id,
            )
            return None
        all_sessions = cls._load_all_sessions_from_file()
        session_data = all_sessions.get(session_id)
        if not isinstance(session_data, dict):
            logger.warning(
                "Session %s not found in archive or data is invalid.", session_id
            )
            return None
        try:
            loaded_session_id = session_data.get("session_id", session_id)
            user = session_data.get("user", "anonymous")
            obj = cls(session_id=loaded_session_id, user=user)
            obj.created_at = session_data.get("created_at", datetime.now().isoformat())
            history_data = session_data.get("history", [])
            if not isinstance(history_data, list):
                logger.warning(
                    "History for session %s is not a list. Defaulting to empty.",
                    loaded_session_id,
                )
                history_data = []
            obj._chat_session_history = [
                _deserialize_content(msg_dict) for msg_dict in history_data
            ]
            logger.info(
                "Session %s loaded from archive with %d messages.",
                loaded_session_id,
                len(obj._chat_session_history),
            )
            return obj
        except (TypeError, ValueError) as e:
            logger.error(
                "Error creating ContextManager instance from archived data for session %s: %s",
                session_id,
                e,
                exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error creating ContextManager for session %s: %s",
                session_id,
                e,
                exc_info=True,
            )
            return None

    @classmethod
    def list_sessions(cls) -> list[dict]:
        all_sessions = cls._load_all_sessions_from_file()
        session_list = []
        for sid, sdata in all_sessions.items():
            if not isinstance(sdata, dict):
                logger.warning(
                    "Skipping invalid session data for ID '%s' in list_sessions.", sid
                )
                continue
            history = sdata.get("history", [])
            message_count = len(history) if isinstance(history, list) else 0
            session_list.append(
                {
                    "session_id": sid,
                    "created_at": sdata.get("created_at"),
                    "user": sdata.get("user"),
                    "message_count": message_count,
                }
            )
        try:
            session_list.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        except TypeError:
            logger.warning(
                "Could not sort sessions by created_at due to inconsistent data."
            )
        return session_list

    def delete_from_archive(self) -> bool:
        all_sessions = self._load_all_sessions_from_file()
        if self.session_id in all_sessions:
            del all_sessions[self.session_id]
            if self._save_all_sessions_to_file(all_sessions):
                logger.info("Session %s deleted from archive.", self.session_id)
                return True
            logger.error(
                "Failed to save archive after deleting session %s.", self.session_id
            )
            return False
        else:
            logger.warning(
                "Session %s not found in archive. Cannot delete.", self.session_id
            )
            return False


# --- ContextManager Test ---
if __name__ == "__main__":
    logger.info("--- ContextManager Test ---")
    test_session_id = "test-session-for-main-context"
    cm = ContextManager.load_from_archive(test_session_id)
    if not cm:
        logger.info("Session '%s' not found, creating new one.", test_session_id)
        cm = ContextManager(session_id=test_session_id, user="test_user_main_context")
    else:
        logger.info("Loaded existing session '%s'.", test_session_id)

    cm.remember("user", f"Test message at {datetime.now().isoformat()}")
    cm.remember("model", "Acknowledged.")
    if cm.save_to_archive():
        print(f"Session '{cm.session_id}' saved successfully.")
    else:
        print(f"Failed to save session '{cm.session_id}'.")

    print("\n--- Listing all sessions ---")
    list_of_sessions = ContextManager.list_sessions()
    if not list_of_sessions:
        print("No sessions found in archive.")
    else:
        print(f"Found {len(list_of_sessions)} session(s):")
        for session_meta in list_of_sessions:
            print(
                "  ID: %(session_id)s, User: %(user)s, Created: %(created_at)s, Messages: %(message_count)d"
                % session_meta
            )

    if list_of_sessions:
        last_session_id_to_load = list_of_sessions[0]["session_id"]
        print(f"\n--- Loading session: {last_session_id_to_load} ---")
        loaded_cm = ContextManager.load_from_archive(last_session_id_to_load)
        if loaded_cm:
            print(
                f"Successfully loaded session '{loaded_cm.session_id}' for user '{loaded_cm.user}'."
            )
            history = loaded_cm.retrieve()
            print(f"  History has {len(history)} messages:")
            for i, msg in enumerate(history):
                if msg.parts:
                    print(
                        f"    {i+1}. Role: {msg.role}, Text: {msg.parts[0].text[:60]}..."
                    )
                else:
                    print(f"    {i+1}. Role: {msg.role}, Text: [NO PARTS]")
        else:
            print(f"Failed to load session '{last_session_id_to_load}'.")
    else:
        print("\nNo sessions to load for detailed view.")
    logger.info("--- ContextManager Test Finished ---")
