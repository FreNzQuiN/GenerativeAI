# core/config_manager.py

import configparser
import os
import logging
import threading  # Untuk thread-safe Singleton

# --- Global Constants (OK untuk konstanta konfigurasi dasar) ---
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_DIR = os.path.dirname(CORE_DIR)
LOG_DIR = os.path.join(PROJECT_ROOT_DIR, "logs")
CONFIG_DIR = os.path.join(PROJECT_ROOT_DIR, "config")
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, "config.ini")

# --- Logging Setup ---
# (Setup logger sama seperti sebelumnya, pastikan robust)
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError as e:
        print(
            f"CRITICAL: Failed to create log directory {LOG_DIR}: {e}. Logging might fail."
        )

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    try:
        log_file_path = os.path.join(
            LOG_DIR, f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
        )
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)
    except OSError as e:
        print(
            f"CRITICAL: Failed to setup file handler for config_manager: {e}. Using basicConfig."
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    except Exception as e:
        print(
            f"CRITICAL: Unexpected error setting up logger for config_manager: {e}. Using basicConfig."
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

# Pastikan CONFIG_DIR ada
if not os.path.exists(CONFIG_DIR):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        logger.info("Created configuration directory: %s", CONFIG_DIR)
    except OSError as e:
        logger.error(
            "Failed to create configuration directory %s: %s",
            CONFIG_DIR,
            e,
            exc_info=True,
        )


class ConfigManager:
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ConfigManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.config = configparser.ConfigParser(interpolation=None)
        self._initialize_or_load_config()
        logger.info("ConfigManager instance initialized and config loaded/created.")
        self._initialized = True

    def _get_default_config_structure(self) -> dict:
        """Mengembalikan struktur dictionary untuk config default."""
        return {
            "general": {
                "interface_language": "id",
                "project_root_dir": PROJECT_ROOT_DIR,
            },
            "api_keys": {"gemini_api_key": "YOUR_GEMINI_API_KEY_HERE"},
            "llm_settings": {
                "model_name": "gemini-1.5-flash-latest",
                "temperature": "0.7",
                "instruction_path": "config/llm_instructions.json",
                "default_chat_role": "Assistant",
            },
            "translator_plugin": {
                "default_source_language": "id",
                "default_target_language": "en",
            },
        }

    def _initialize_or_load_config(self):
        """
        Membuat file config.ini dengan struktur default jika belum ada,
        atau memuat yang sudah ada ke self.config.
        """
        if not os.path.exists(CONFIG_FILE_PATH):
            logger.info(
                "Configuration file %s not found. Creating with default structure.",
                CONFIG_FILE_PATH,
            )
            default_structure = self._get_default_config_structure()
            for section, options in default_structure.items():
                self.config.add_section(section)
                for key, value in options.items():
                    self.config.set(section, str(key), str(value))
            try:
                # Pastikan direktori ada sebelum menulis
                os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
                with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as configfile:
                    self.config.write(configfile)
                logger.info(
                    "Default configuration file created at %s.", CONFIG_FILE_PATH
                )
            except OSError as e:
                logger.error(
                    "OSError creating default configuration file %s: %s",
                    CONFIG_FILE_PATH,
                    e,
                    exc_info=True,
                )
                # Jika gagal buat file, self.config akan berisi default tapi tidak tersimpan
        else:
            try:
                read_files = self.config.read(CONFIG_FILE_PATH, encoding="utf-8")
                if not read_files:
                    logger.warning(
                        "Configuration file %s was empty or unreadable.Current config object might be empty or only contain defaults if any were set before read.",
                        CONFIG_FILE_PATH,
                    )
                else:
                    logger.info(
                        "Successfully read configuration from %s into ConfigManager instance.",
                        CONFIG_FILE_PATH,
                    )
            except (OSError, configparser.Error) as e:
                logger.error(
                    "Error reading existing configuration file %s: %s. Config object might be empty.",
                    CONFIG_FILE_PATH,
                    e,
                    exc_info=True,
                )

    def save_config(self) -> bool:
        """Menyimpan state config saat ini ke file. Mengembalikan True jika berhasil."""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
            with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as configfile:
                self.config.write(configfile)
            logger.info("Configuration saved successfully to %s.", CONFIG_FILE_PATH)
            return True
        except OSError as e:
            logger.error(
                "OSError saving configuration to %s: %s",
                CONFIG_FILE_PATH,
                e,
                exc_info=True,
            )
            return False
        except configparser.Error as e:
            logger.error(
                "ConfigParser error saving configuration to %s: %s",
                CONFIG_FILE_PATH,
                e,
                exc_info=True,
            )
            return False

    def get_config_value(self, section: str, key: str, default=None) -> str | None:
        try:
            return self.config.get(section, key)
        except configparser.NoSectionError:
            logger.debug(
                "Section [%s] not found. Returning default for key '%s'.", section, key
            )
            return default
        except configparser.NoOptionError:
            logger.debug(
                "Key '%s' not found in section [%s]. Returning default.", key, section
            )
            return default
        except configparser.Error as e:
            logger.error(
                "ConfigParser error reading value for [%s].%s: %s. Returning default.",
                section,
                key,
                e,
                exc_info=True,
            )
            return default

    def get_int(self, section: str, key: str, default: int = 0) -> int:
        value_str = self.get_config_value(section, key)
        if value_str is not None:
            try:
                return int(value_str)
            except ValueError:
                logger.warning(
                    "Value for [%s].%s ('%s') is not a valid integer. Returning default: %d.",
                    section,
                    key,
                    value_str,
                    default,
                )
                return default
        return default

    def get_float(self, section: str, key: str, default: float = 0.0) -> float:
        value_str = self.get_config_value(section, key)
        if value_str is not None:
            try:
                return float(value_str)
            except ValueError:
                logger.warning(
                    "Value for [%s].%s ('%s') is not a valid float. Returning default: %f.",
                    section,
                    key,
                    value_str,
                    default,
                )
                return default
        return default

    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        value_str = self.get_config_value(section, key)
        if value_str is not None:
            val_lower = value_str.lower()
            if val_lower in ["true", "yes", "on", "1"]:
                return True
            elif val_lower in ["false", "no", "off", "0"]:
                return False
            else:
                logger.warning(
                    "Value for [%s].%s ('%s') is not a recognized boolean. Returning default: %s.",
                    section,
                    key,
                    value_str,
                    default,
                )
                return default
        return default

    def set_config_value(self, section: str, key: str, value) -> bool:
        try:
            if not self.config.has_section(section):
                self.config.add_section(section)
                logger.info('Added new section to config object: "%s"', section)

            str_value = str(value)
            self.config.set(section, key, str_value)
            if self.save_config():  # Panggil metode save_config dari instance
                logger.info(
                    "Set [%s].%s = %s and saved to config file.",
                    section,
                    key,
                    str_value,
                )
                return True
            else:
                logger.error(
                    "Failed to save config after setting [%s].%s = %s.",
                    section,
                    key,
                    str_value,
                )
                return False
        except configparser.Error as e:
            logger.error(
                "ConfigParser error setting value for [%s].%s: %s",
                section,
                key,
                e,
                exc_info=True,
            )
            return False

    def set_default_if_not_exists(self, section: str, key: str, default_value) -> bool:
        if self.get_config_value(section, key) is None:
            logger.info(
                'Key "%s" not found in section "%s". Setting default value: "%s".',
                key,
                section,
                default_value,
            )
            return self.set_config_value(section, key, default_value)
        return True

    def list_config(self, section_name: str = None):
        logger.info("Current configuration snapshot from ConfigManager instance:")
        if not self.config.sections():
            logger.info("No sections found in the current configuration.")
            return

        sections_to_list = [section_name] if section_name else self.config.sections()

        if section_name and not self.config.has_section(section_name):
            logger.warning(
                'Section "%s" does not exist in the current configuration.',
                section_name,
            )
            return

        for current_section_name in sections_to_list:
            if self.config.has_section(current_section_name):
                logger.info("[%s]", current_section_name)
                try:
                    for key_val, value_val in self.config.items(current_section_name):
                        logger.info("  %s = %s", key_val, value_val)
                except configparser.Error as e:
                    logger.error(
                        "Error listing items for section [%s]: %s",
                        current_section_name,
                        e,
                    )

    def section_exists(self, section: str) -> bool:
        return self.config.has_section(section)

    def key_exists(self, section: str, key: str) -> bool:
        if self.config.has_section(section):
            return self.config.has_option(section, key)
        return False

    def remove_section(self, section: str) -> bool:
        try:
            if self.config.has_section(section):
                self.config.remove_section(section)
                if self.save_config():
                    logger.info('Removed section "%s" and saved config file.', section)
                    return True
                else:
                    logger.error(
                        'Failed to save config after removing section "%s".', section
                    )
                    self._initialize_or_load_config()  # Coba sinkronkan kembali
                    return False
            else:
                logger.warning(
                    'Attempted to remove non-existent section: "%s".', section
                )
                return True
        except configparser.Error as e:
            logger.error(
                'ConfigParser error removing section "%s": %s',
                section,
                e,
                exc_info=True,
            )
            return False

    def remove_key(self, section: str, key: str) -> bool:
        try:
            if self.key_exists(section, key):
                self.config.remove_option(section, key)
                if self.save_config():
                    logger.info(
                        'Removed key "%s" from section "%s" and saved config file.',
                        key,
                        section,
                    )
                    return True
                else:
                    logger.error(
                        'Failed to save config after removing key "%s" from section "%s".',
                        key,
                        section,
                    )
                    self._initialize_or_load_config()  # Coba sinkronkan kembali
                    return False
            else:
                logger.warning(
                    'Attempted to remove non-existent key "%s" from section "%s".',
                    key,
                    section,
                )
                return True
        except configparser.Error as e:
            logger.error(
                'ConfigParser error removing key "%s" from section "%s": %s',
                key,
                section,
                e,
                exc_info=True,
            )
            return False

    def reset_config(self) -> bool:
        """Mereset objek config di memori ke default dan menyimpannya ke file."""
        try:
            self.config.clear()  # Hapus semua section dari config instance
            default_structure = self._get_default_config_structure()
            for section, options in default_structure.items():
                self.config.add_section(section)
                for key, value in options.items():
                    self.config.set(section, str(key), str(value))

            if self.save_config():
                logger.info(
                    'Configuration file reset to defaults at "%s".', CONFIG_FILE_PATH
                )
                return True
            else:
                logger.error(
                    "Failed to save config after resetting to defaults. Config in memory is reset, but file might be out of sync."
                )
                # Coba muat ulang untuk konsistensi, meskipun ini akan menimpa reset di memori jika file masih lama
                self._initialize_or_load_config()
                return False
        except configparser.Error as e:
            logger.error("ConfigParser error resetting config: %s", e, exc_info=True)
            return False

    def is_config_empty(self) -> bool:
        return not self.config.sections()

    def get_config_object(self) -> configparser.ConfigParser:
        """Mengembalikan objek configparser internal. Gunakan dengan hati-hati."""
        return self.config


# Tidak ada lagi panggilan `ConfigManager()` di akhir file untuk "mengaktifkan" modul.
# Modul ini sekarang menyediakan kelas ConfigManager yang siap digunakan.
# Pengguna modul akan membuat instance: `cfg = ConfigManager()`

if __name__ == "__main__":
    logger.info(
        "=== Configuration Manager - Example Usage (No Global Config Object) ==="
    )

    # Dapatkan instance ConfigManager (akan menginisialisasi config jika belum)
    # Karena Singleton, ini akan selalu objek yang sama
    cfg_manager = ConfigManager()
    cfg_manager_2 = ConfigManager()

    logger.info(
        "Instance 1 ID: %s, Instance 2 ID: %s", id(cfg_manager), id(cfg_manager_2)
    )
    assert id(cfg_manager) == id(cfg_manager_2)  # Memverifikasi Singleton

    logger.info(
        "PROJECT_ROOT_DIR from config: %s",
        cfg_manager.get_config_value("general", "project_root_dir"),
    )

    cfg_manager.list_config("general")

    if cfg_manager.is_config_empty():
        logger.info("Configuration is currently empty (no sections).")
    else:
        logger.info("Configuration is not empty.")

    logger.info("Setting new value for general.test_key...")
    cfg_manager.set_config_value("general", "test_key", "new_value_456")

    retrieved_value = cfg_manager.get_config_value("general", "test_key")
    logger.info("Retrieved general.test_key: %s", retrieved_value)
    assert retrieved_value == "new_value_456"

    logger.info("Setting default for non_existent_section.another_default_key...")
    cfg_manager.set_default_if_not_exists(
        "non_existent_section", "another_default_key", "another_default_set"
    )
    retrieved_default = cfg_manager.get_config_value(
        "non_existent_section", "another_default_key"
    )
    logger.info(
        "Retrieved non_existent_section.another_default_key: %s", retrieved_default
    )
    assert retrieved_default == "another_default_set"

    # Menghapus section yang baru ditambahkan
    logger.info("Removing section 'non_existent_section'...")
    if cfg_manager.remove_section("non_existent_section"):
        logger.info("Section 'non_existent_section' removed.")
        assert not cfg_manager.section_exists("non_existent_section")
    else:
        logger.error("Failed to remove section 'non_existent_section'.")

    gemini_key_config = cfg_manager.get_config_value("api_keys", "gemini_api_key")
    if gemini_key_config == "YOUR_GEMINI_API_KEY_HERE" or gemini_key_config is None:
        logger.warning("GEMINI_API_KEY not set or still default.")
    else:
        logger.info("GEMINI_API_KEY is set: %s", gemini_key_config)

    logger.info("Resetting config to defaults...")
    if cfg_manager.reset_config():
        logger.info("Config reset successfully.")
        cfg_manager.list_config()
    else:
        logger.error("Failed to reset config.")
