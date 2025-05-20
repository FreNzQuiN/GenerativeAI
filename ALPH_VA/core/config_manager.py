# core/config_manager.py

import configparser
import os
import logging

# --- Logging Check ---
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_DIR = os.path.dirname(CORE_DIR) 
LOG_DIR = os.path.join(PROJECT_ROOT_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

# --- Configuration File Setup ---
CONFIG_DIR = os.path.join(PROJECT_ROOT_DIR, "config")
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)
    logger.info(f"Created configuration directory: {CONFIG_DIR}")
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, "config.ini")
config = configparser.ConfigParser(interpolation=None)

def _get_default_config_structure():
    """Mengembalikan struktur dictionary untuk config default."""
    return {
        "general": {
            "language": "id",
            "audio_output_path": "data/audio/"
        },
        "tts_settings": {
            "default_engine": "pyttsx3",
            "pyttsx3_rate": "150",
            "pyttsx3_volume": "1.0",
            "voicevox_speaker_id": "3",
        },
        "api_keys": {
            "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
        },
        "translator_plugin": {
            "default_source_language": "id",
            "default_target_language": "en"
        }
    }
    
def _initialize_config():
    """Membuat file config.ini dengan struktur default jika belum ada."""
    global config
    if not os.path.exists(CONFIG_FILE_PATH):
        logger.info(f"Configuration file \"{CONFIG_FILE_PATH}\" not found. Creating with default structure.")
        default_structure = _get_default_config_structure()
        for section, options in default_structure.items():
            config.add_section(section)
            for key, value in options.items():
                config.set(section, str(key), str(value))
        try:
            with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as configfile:
                config.write(configfile)
            logger.info(f"Default configuration file created at \"{CONFIG_FILE_PATH}\".")
        except Exception as e:
            logger.error(f"Error creating default configuration file: {e}")
    else:
        try:
            config.clear() 
            read_files = config.read(CONFIG_FILE_PATH, encoding='utf-8')
            if not read_files:
                logger.warning(f"Configuration file \"{CONFIG_FILE_PATH}\" was empty or unreadable. Consider resetting or checking it.")
            else:
                logger.info(f"Successfully read configuration from \"{CONFIG_FILE_PATH}\".")
        except Exception as e:
            logger.error(f"Error reading existing configuration file \"{CONFIG_FILE_PATH}\": {e}")


# --- Core Functions ---
def get_config_value(section: str, key: str, default=None):
    """
    Mengambil nilai string dari file konfigurasi.
    Mengembalikan nilai default (atau None) jika section/key tidak ditemukan.
    """
    try:
        if config.has_option(section, key):
            value = config.get(section, key)
            return value
        else:
            return default
    except configparser.NoSectionError:
        return default
    except Exception as e:
        logger.error(f"Error reading config value [{section}].{key}: {e}")
        return default

def get_int(section: str, key: str, default: int = 0) -> int:
    """Mengambil nilai integer. Mengembalikan default jika tidak ada atau bukan integer."""
    value_str = get_config_value(section, key)
    if value_str is not None:
        try:
            return int(value_str)
        except ValueError:
            logger.warning(f"Value for [{section}].{key} ('{value_str}') is not a valid integer. Returning default: {default}.")
            return default
    return default

def get_float(section: str, key: str, default: float = 0.0) -> float:
    """Mengambil nilai float. Mengembalikan default jika tidak ada atau bukan float."""
    value_str = get_config_value(section, key)
    if value_str is not None:
        try:
            return float(value_str)
        except ValueError:
            logger.warning(f"Value for [{section}].{key} ('{value_str}') is not a valid float. Returning default: {default}.")
            return default
    return default

def get_bool(section: str, key: str, default: bool = False) -> bool:
    """
    Mengambil nilai boolean.
    Menerima 'true', 'yes', 'on', '1' sebagai True (case-insensitive).
    Menerima 'false', 'no', 'off', '0' sebagai False (case-insensitive).
    Mengembalikan default jika tidak ada atau tidak dikenali.
    """
    value_str = get_config_value(section, key)
    if value_str is not None:
        val_lower = value_str.lower()
        if val_lower in ['true', 'yes', 'on', '1']:
            return True
        elif val_lower in ['false', 'no', 'off', '0']:
            return False
        else:
            logger.warning(f"Value for [{section}].{key} ('{value_str}') is not a recognized boolean. Returning default: {default}.")
            return default
    return default

def set_config_value(section: str, key: str, value):
    """Menyetel nilai dalam file konfigurasi. Semua nilai dikonversi ke string."""
    global config
    try:
        if not config.has_section(section):
            config.add_section(section)
            logger.info(f"Added new section: \"{section}\"")
        
        str_value = str(value)
        config.set(section, key, str_value)
        with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as configfile:
            config.write(configfile)
        logger.info(f"Set [{section}].{key} = {str_value} and saved to config file.")
    except Exception as e:
        logger.error(f"Error writing config value [{section}].{key}: {e}")

def set_default_if_not_exists(section: str, key: str, default_value):
    """Menyetel nilai default ke file konfigurasi HANYA JIKA key tersebut belum ada."""
    if get_config_value(section, key) is None:
        logger.info(f"Key \"{key}\" not found in section \"{section}\". Setting default value: \"{default_value}\".")
        set_config_value(section, key, default_value)
        return True
    return False

# --- Utility Functions ---
def list_config(section: str = None):
    """Mencetak semua section dan option ke logger (INFO)."""
    logger.info("Current configuration:")
    if not config.sections():
        logger.info("No sections found in the configuration file.")
        return
    if section:
        if config.has_section(section):
            logger.info(f"[{section}]")
            for key_val, value_val in config.items(section): 
                logger.info(f"  {key_val} = {value_val}")
        else:
            logger.warning(f"Section \"{section}\" does not exist in the configuration file.")
            return
    else:
        for section in config.sections():
            logger.info(f"[{section}]")
            for key_val, value_val in config.items(section): 
                logger.info(f"  {key_val} = {value_val}")

def section_exists(section: str) -> bool:
    return config.has_section(section)

def key_exists(section: str, key: str) -> bool:
    return config.has_option(section, key)

def remove_section_from_config(section: str): 
    global config
    try:
        if config.has_section(section):
            config.remove_section(section)
            with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as configfile:
                config.write(configfile)
            logger.info(f"Removed section \"{section}\" and saved config file.")
        else:
            logger.warning(f"Attempted to remove non-existent section: \"{section}\".")
    except Exception as e:
        logger.error(f"Error removing section \"{section}\": {e}")

def remove_key_from_config(section: str, key: str):
    global config
    try:
        if config.has_option(section, key):
            config.remove_option(section, key)
            with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as configfile:
                config.write(configfile)
            logger.info(f"Removed key \"{key}\" from section \"{section}\" and saved config file.")
        else:
            logger.warning(f"Attempted to remove non-existent key \"{key}\" from section \"{section}\".")
    except Exception as e:
        logger.error(f"Error removing key \"{key}\" from section \"{section}\": {e}")

def reset_config_to_defaults():
    """Mereset file konfigurasi ke struktur dan nilai default."""
    global config
    try:
        config.clear()
        default_structure = _get_default_config_structure()
        for section, options in default_structure.items():
            config.add_section(section)
            for key, value in options.items():
                config.set(section, str(key), str(value))
        
        with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as configfile:
            config.write(configfile)
        logger.info(f"Configuration file reset to defaults at \"{CONFIG_FILE_PATH}\".")
    except Exception as e:
        logger.error(f"Error resetting config: {e}")

def is_config_empty() -> bool:
    return not config.sections()

class ConfigManager():
    def __init__(self):
        _initialize_config()
        logger.info("Configuration Manager initialized and default config loaded.")
        self.config = config
    
    def get_config(self):
        """Mengembalikan objek configparser untuk akses lebih lanjut."""
        return self.config
    def set_config_value(self, section: str, key: str, value):
        """Menyetel nilai dalam file konfigurasi."""
        set_config_value(section, key, value)
    def get_config_value(self, section: str, key: str, default=None):
        """Mengambil nilai dari file konfigurasi."""
        return get_config_value(section, key, default)
    def get_int(self, section: str, key: str, default: int = 0) -> int:
        """Mengambil nilai integer dari file konfigurasi."""
        return get_int(section, key, default)
    def get_float(self, section: str, key: str, default: float = 0.0) -> float:
        """Mengambil nilai float dari file konfigurasi."""
        return get_float(section, key, default)
    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        """Mengambil nilai boolean dari file konfigurasi."""
        return get_bool(section, key, default)
    def set_default_if_not_exists(self, section: str, key: str, default_value):
        """Menyetel nilai default ke file konfigurasi jika key tersebut belum ada."""
        return set_default_if_not_exists(section, key, default_value)
    def list_config(self, section: str = None):
        """Mencetak semua section dan option ke logger (INFO)."""
        list_config(section)
    def section_exists(self, section: str) -> bool:
        """Memeriksa apakah section ada dalam file konfigurasi."""
        return section_exists(section)
    def key_exists(self, section: str, key: str) -> bool:
        """Memeriksa apakah key ada dalam section file konfigurasi."""
        return key_exists(section, key)
    def remove_section(self, section: str):
        """Menghapus section dari file konfigurasi."""
        remove_section_from_config(section)
    def remove_key(self, section: str, key: str):
        """Menghapus key dari section file konfigurasi."""
        remove_key_from_config(section, key)
    def reset_config(self):
        """Mereset file konfigurasi ke struktur dan nilai default."""
        reset_config_to_defaults()
    def is_config_empty(self) -> bool:
        """Memeriksa apakah file konfigurasi kosong (tidak ada section)."""
        return is_config_empty()
    
    
ConfigManager()

if __name__ == "__main__":
    logger.info("=== Configuration Manager - Example Usage ===")
    
    list_config("general")
    
    if is_config_empty():
        logger.info("Configuration is currently empty (no sections).")
    else:
        logger.info("Configuration is not empty.")

    gemini_key_config = get_config_value("api_keys", "gemini_api_key")
    if gemini_key_config == "YOUR_GEMINI_API_KEY_HERE" or gemini_key_config is None:
        logger.warning("GEMINI_API_KEY not set in config.ini or still default. Checking environment variable.")
        gemini_key_env = os.environ.get("GEMINI_API_KEY")
        if gemini_key_env:
            logger.info("Found GEMINI_API_KEY in environment. Consider setting it in config.ini for persistence.")
        else:
            logger.error("GEMINI_API_KEY not found in config.ini or environment variables. Application might fail.")