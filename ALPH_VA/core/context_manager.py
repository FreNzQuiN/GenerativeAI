# core/context_manager.py
import json
import os
from datetime import datetime
from google.genai import types # type: ignore atau pastikan google-generativeai terinstal
from core import config_manager
import logging
import uuid

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        # Pastikan LOG_DIR ada sebelum mencoba menulis log
        if hasattr(config_manager, 'LOG_DIR') and config_manager.LOG_DIR:
            if not os.path.exists(config_manager.LOG_DIR):
                os.makedirs(config_manager.LOG_DIR)
            log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
        else:
            logger.warning("config_manager.LOG_DIR not found or not configured. Logging to current directory for context_manager.")
            log_file_path = f"{os.path.split(__file__)[1].split('.')[0]}.log" # Fallback
    except Exception as e:
        logger.error(f"Error setting up logger for context_manager: {e}. Logging to current directory.", exc_info=True)
        log_file_path = f"{os.path.split(__file__)[1].split('.')[0]}.log" # Fallback

    if log_file_path:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    else: # Fallback jika path log tidak bisa ditentukan
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logger.warning("Could not set up file handler for context_manager. Using basicConfig.")
    logger.setLevel(logging.INFO)


# --- Konstanta Path ---
DEFAULT_ARCHIVE_FILENAME = "chat_sessions.json"
# Pastikan PROJECT_ROOT_DIR ada di config_manager
try:
    PROJECT_ROOT = config_manager.PROJECT_ROOT_DIR
except AttributeError:
    logger.error("config_manager.PROJECT_ROOT_DIR is not defined. Using fallback relative path.")
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Fallback: .. dari core/

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MEMORY_DIR = os.path.join(DATA_DIR, "memory")

if not os.path.exists(MEMORY_DIR):
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True) # exist_ok=True aman jika direktori sudah ada
        logger.info(f"Created/Ensured memory directory: {MEMORY_DIR}")
    except OSError as e:
        logger.error(f"Failed to create memory directory {MEMORY_DIR}: {e}", exc_info=True)
        # Aplikasi mungkin tidak bisa menyimpan sesi jika ini gagal.

# Dapatkan nama file arsip dari config, dengan fallback yang lebih aman
archive_filename_from_config = DEFAULT_ARCHIVE_FILENAME
try:
    cfg_val = config_manager.get_config_value("general", "chat_archive_filename", DEFAULT_ARCHIVE_FILENAME)
    if isinstance(cfg_val, str) and cfg_val.strip():
        archive_filename_from_config = cfg_val.strip()
    else:
        logger.warning(f"Invalid chat_archive_filename from config ('{cfg_val}'). Using default.")
except AttributeError:
    logger.warning("config_manager.get_config_value not found. Using default archive filename.")
except Exception as e:
    logger.error(f"Error getting chat_archive_filename from config: {e}. Using default.", exc_info=True)

ARCHIVE_FILE_PATH = os.path.join(MEMORY_DIR, archive_filename_from_config)
logger.info(f"Context archive file path set to: {ARCHIVE_FILE_PATH}")


# --- Fungsi Serialisasi/Deserialisasi ---
def _serialize_content(content_obj: types.Content) -> dict:
    """Serialisasi objek types.Content ke dictionary."""
    parts_data = []
    # Pastikan content_obj dan parts tidak None sebelum iterasi
    if hasattr(content_obj, 'parts') and content_obj.parts:
        for part in content_obj.parts:
            if hasattr(part, 'text'):
                parts_data.append({"text": part.text})
            # Tambahkan penanganan untuk jenis part lain jika perlu (misalnya, blob)
            # elif hasattr(part, 'inline_data'): # Contoh
            #     parts_data.append({"inline_data": {"mime_type": part.inline_data.mime_type, "data": "..."}})
            else:
                parts_data.append({"text": str(part)}) # Fallback
    
    role = "user" # Default role
    if hasattr(content_obj, 'role') and content_obj.role:
        role = content_obj.role
        
    return {"role": role, "parts": parts_data}

def _deserialize_content(content_dict: dict) -> types.Content:
    """Deserialisasi dictionary kembali ke types.Content."""
    if not isinstance(content_dict, dict):
        logger.error(f"Cannot deserialize content, expected dict, got {type(content_dict)}")
        # Kembalikan Content default atau raise error
        return types.Content(role="user", parts=[types.Part(text="[Deserialization Error]")])

    parts_list = []
    for part_data in content_dict.get("parts", []):
        if isinstance(part_data, dict) and "text" in part_data:
            parts_list.append(types.Part(text=str(part_data.get("text", ""))))
        # Tambahkan penanganan untuk jenis part lain jika perlu
        else: # Jika format part tidak terduga
            parts_list.append(types.Part(text="[Malformed Part Data]"))
            
    return types.Content(
        role=str(content_dict.get("role", "user")),
        parts=parts_list
    )


class ContextManager:
    """
    Mengelola sesi chat individual dan menyimpannya ke/dari file arsip JSON.
    """
    ARCHIVE_FILE_PATH = ARCHIVE_FILE_PATH # Gunakan path yang sudah dikonfigurasi di atas

    def __init__(self, session_id: str | None = None, user: str | None = None):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.user: str = user or "anonymous"
        self.created_at: str = datetime.now().isoformat()
        self._chat_session_history: list[types.Content] = [] # Type hint untuk kejelasan
        logger.info(f"ContextManager initialized for session_id: {self.session_id}, user: {self.user}")

    def remember(self, role: str, text: str):
        """Menambahkan pesan ke histori sesi saat ini."""
        if not isinstance(role, str) or not isinstance(text, str):
            logger.warning(f"Invalid input for remember: role='{role}', text='{text}'. Skipping.")
            return

        valid_role = role.lower() if role.lower() in ["user", "model"] else "user"
        try:
            content = types.Content(role=valid_role, parts=[types.Part(text=text)])
            self._chat_session_history.append(content)
            logger.debug(f"Session {self.session_id}: Remembered '{valid_role}' message: '{text[:50]}...'")
        except Exception as e:
            logger.error(f"Error creating types.Content for remembering: {e}", exc_info=True)

    def retrieve(self) -> list[types.Content]:
        """Mengambil salinan histori chat untuk sesi saat ini."""
        logger.debug(f"Session {self.session_id}: Retrieved chat history with {len(self._chat_session_history)} messages.")
        return list(self._chat_session_history) # Kembalikan salinan untuk mencegah modifikasi eksternal

    def clear_memory(self):
        """Menghapus histori chat dari memori untuk sesi saat ini."""
        self._chat_session_history = []
        logger.info(f"Session {self.session_id}: In-memory history cleared.")

    def to_dict(self) -> dict:
        """Serialisasi data sesi saat ini ke dictionary."""
        return {
            "session_id": self.session_id, # Tambahkan session_id untuk konsistensi
            "created_at": self.created_at,
            "user": self.user,
            "history": [_serialize_content(msg) for msg in self._chat_session_history]
        }

    @classmethod
    def _load_all_sessions_from_file(cls) -> dict:
        """Memuat semua data sesi dari file arsip. Mengembalikan dict kosong jika gagal."""
        if not os.path.exists(cls.ARCHIVE_FILE_PATH):
            logger.info(f"Archive file {cls.ARCHIVE_FILE_PATH} not found. Returning empty sessions dict.")
            return {}
        
        try:
            with open(cls.ARCHIVE_FILE_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip(): # File kosong
                    logger.info(f"Archive file {cls.ARCHIVE_FILE_PATH} is empty. Returning empty sessions dict.")
                    return {}
                data = json.loads(content) # Menggunakan json.loads setelah membaca
            
            if isinstance(data, dict) and "sessions" in data and isinstance(data["sessions"], dict):
                return data["sessions"]
            else:
                logger.warning(f"Archive file {cls.ARCHIVE_FILE_PATH} has invalid structure. Expected {{'sessions': {{...}}}}. Returning empty.")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from archive {cls.ARCHIVE_FILE_PATH}: {e}. Returning empty sessions dict.", exc_info=True)
            return {}
        except Exception as e:
            logger.error(f"Unexpected error loading sessions from archive {cls.ARCHIVE_FILE_PATH}: {e}. Returning empty sessions dict.", exc_info=True)
            return {}

    @classmethod
    def _save_all_sessions_to_file(cls, sessions_dict: dict) -> bool:
        """Menyimpan semua data sesi ke file arsip. Mengembalikan True jika berhasil."""
        if not isinstance(sessions_dict, dict):
            logger.error("_save_all_sessions_to_file expects a dict. Aborting save.")
            return False
        try:
            # Pastikan direktori ada sebelum menulis
            os.makedirs(os.path.dirname(cls.ARCHIVE_FILE_PATH), exist_ok=True)
            with open(cls.ARCHIVE_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump({"sessions": sessions_dict}, f, indent=4, ensure_ascii=False)
            logger.info(f"All sessions successfully saved to {cls.ARCHIVE_FILE_PATH}")
            return True
        except Exception as e:
            logger.error(f"Error saving sessions to archive {cls.ARCHIVE_FILE_PATH}: {e}", exc_info=True)
            return False

    def save_to_archive(self) -> bool:
        """Menyimpan sesi saat ini ke file arsip."""
        all_sessions = self._load_all_sessions_from_file()
        all_sessions[self.session_id] = self.to_dict()
        if self._save_all_sessions_to_file(all_sessions):
            logger.info(f"Session {self.session_id} archived with {len(self._chat_session_history)} messages.")
            return True
        logger.error(f"Failed to archive session {self.session_id}.")
        return False

    @classmethod
    def load_from_archive(cls, session_id: str) -> 'ContextManager | None':
        """Memuat instance ContextManager dari arsip berdasarkan session_id."""
        if not isinstance(session_id, str) or not session_id.strip():
            logger.warning("Invalid session_id provided for loading. Must be a non-empty string.")
            return None

        all_sessions = cls._load_all_sessions_from_file()
        session_data = all_sessions.get(session_id)

        if not session_data or not isinstance(session_data, dict):
            logger.warning(f"Session {session_id} not found in archive or data is invalid.")
            return None
        
        try:
            # Gunakan session_id dari data jika ada, untuk konsistensi jika argumen berbeda (meski seharusnya sama)
            loaded_session_id = session_data.get("session_id", session_id)
            user = session_data.get("user", "anonymous")
            
            obj = cls(session_id=loaded_session_id, user=user) # Membuat instance baru
            obj.created_at = session_data.get("created_at", datetime.now().isoformat())
            
            history_data = session_data.get("history", [])
            if not isinstance(history_data, list):
                logger.warning(f"History data for session {loaded_session_id} is not a list. Defaulting to empty history.")
                history_data = []
                
            obj._chat_session_history = [_deserialize_content(msg_dict) for msg_dict in history_data]
            
            logger.info(f"Session {loaded_session_id} loaded from archive with {len(obj._chat_session_history)} messages.")
            return obj
        except Exception as e:
            logger.error(f"Error creating ContextManager instance from archived data for session {session_id}: {e}", exc_info=True)
            return None

    @classmethod
    def list_sessions(cls) -> list[dict]:
        """Mengembalikan daftar metadata untuk semua sesi yang tersimpan."""
        all_sessions = cls._load_all_sessions_from_file()
        session_list = []
        for sid, sdata in all_sessions.items():
            if not isinstance(sdata, dict): # Lewati data sesi yang tidak valid
                logger.warning(f"Skipping invalid session data for ID '{sid}' in list_sessions.")
                continue
            session_list.append({
                "session_id": sid, # Gunakan key dari dict sessions sebagai ID utama
                "created_at": sdata.get("created_at"),
                "user": sdata.get("user"),
                "message_count": len(sdata.get("history", [])) if isinstance(sdata.get("history"), list) else 0
            })
        
        # Urutkan berdasarkan created_at (descending, terbaru dulu) jika ada
        try:
            session_list.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        except TypeError: # Jika created_at ada yang None atau tipe tidak konsisten
            logger.warning("Could not sort sessions by created_at due to inconsistent data.")
            
        return session_list

    def delete_from_archive(self) -> bool:
        """Menghapus sesi saat ini dari file arsip."""
        all_sessions = self._load_all_sessions_from_file()
        if self.session_id in all_sessions:
            del all_sessions[self.session_id]
            if self._save_all_sessions_to_file(all_sessions):
                logger.info(f"Session {self.session_id} deleted from archive.")
                return True
            logger.error(f"Failed to save archive after deleting session {self.session_id}.")
            return False
        else:
            logger.warning(f"Session {self.session_id} not found in archive. Cannot delete.")
            return False
            
if __name__ == "__main__":
    logger.info("--- ContextManager Test ---")

    # Buat sesi baru atau gunakan yang sudah ada
    # Untuk testing, kita bisa membuat ID baru setiap kali atau mencoba memuat yang lama
    test_session_id = "test-session-for-main"
    
    # Coba muat sesi yang ada, jika tidak ada, buat baru
    cm = ContextManager.load_from_archive(test_session_id)
    if not cm:
        logger.info(f"Session '{test_session_id}' not found, creating new one.")
        cm = ContextManager(session_id=test_session_id, user="test_user_main")
    else:
        logger.info(f"Loaded existing session '{test_session_id}'.")

    # Tambah beberapa pesan
    cm.remember("user", "Hello, this is a test message from __main__.")
    cm.remember("model", "Hi there! I received your test message.")
    cm.remember("user", f"The time is {datetime.now()}")

    # Simpan sesi
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
            print(f"  ID: {session_meta['session_id']}, User: {session_meta.get('user', 'N/A')}, Created: {session_meta.get('created_at', 'N/A')}, Messages: {session_meta['message_count']}")
    
    # Muat sesi terakhir yang ada di daftar (jika ada)
    if list_of_sessions:
        last_session_id_to_load = list_of_sessions[0]['session_id'] # Karena sudah diurutkan terbaru dulu
        print(f"\n--- Loading session: {last_session_id_to_load} ---")
        loaded_cm = ContextManager.load_from_archive(last_session_id_to_load)
        if loaded_cm:
            print(f"Successfully loaded session '{loaded_cm.session_id}' for user '{loaded_cm.user}'.")
            history = loaded_cm.retrieve()
            print(f"  History has {len(history)} messages:")
            for i, msg in enumerate(history):
                print(f"    {i+1}. Role: {msg.role}, Text: {msg.parts[0].text[:60]}...") # Asumsi 1 part
            
            # Contoh menambahkan pesan lagi dan menyimpan
            # loaded_cm.remember("user", "Another message after loading.")
            # loaded_cm.save_to_archive()
        else:
            print(f"Failed to load session '{last_session_id_to_load}'.")
    else:
        print("\nNo sessions to load for detailed view.")
        
    # Contoh menghapus sesi (jika Anda mau)
    # if cm.delete_from_archive():
    #     print(f"\nSession '{cm.session_id}' deleted successfully.")
    # else:
    #     print(f"\nFailed to delete session '{cm.session_id}' or it was not found.")

    logger.info("--- ContextManager Test Finished ---")