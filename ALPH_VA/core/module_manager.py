# core/plugin_manager.py
import importlib
import logging
import os
from core import config_manager # Pastikan config_manager.py ada dan LOG_DIR terdefinisi

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        # Pastikan LOG_DIR ada sebelum mencoba menulis log
        if not os.path.exists(config_manager.LOG_DIR):
            os.makedirs(config_manager.LOG_DIR)
            logger.info(f"Created log directory: {config_manager.LOG_DIR}")
        log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    except AttributeError: # Jika config_manager atau LOG_DIR tidak ada
        logger.warning("config_manager.LOG_DIR not found. Logging to current directory.")
        log_file_path = f"{os.path.split(__file__)[1].split('.')[0]}.log"
    except OSError as e:
        logger.error(f"Error creating log directory {config_manager.LOG_DIR}: {e}. Logging to current directory.")
        log_file_path = f"{os.path.split(__file__)[1].split('.')[0]}.log"
    except Exception as e: # Tangkap error yang lebih umum
        logger.error(f"Unexpected error during logger setup for plugin_manager: {e}. Logging to current directory.")
        log_file_path = f"{os.path.split(__file__)[1].split('.')[0]}.log"

    if log_file_path: # Hanya setup handler jika path ada
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s'))
        logger.addHandler(file_handler)
    else: # Fallback jika path log tidak bisa ditentukan
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        logger.warning("Could not set up file handler for plugin_manager. Using basicConfig.")
    logger.setLevel(logging.INFO)


class ModuleManager:
    def __init__(self):
        logger.info("Initializing ModuleManager (Lazy Loading Mode)...")
        # Dictionaries ini akan menyimpan modul yang SUDAH diimpor
        self.loaded_plugins = {}
        self.loaded_core_modules = {}
        
        self.project_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Pindai nama modul yang tersedia, tapi jangan impor sekarang
        self.available_plugins = self._scan_available_modules("plugins")
        self.available_core_modules = self._scan_available_modules("core")
        
        logger.info(f"ModuleManager initialized. Available plugins: {list(self.available_plugins)}")
        logger.info(f"Available core modules: {list(self.available_core_modules)}")

    def _scan_available_modules(self, module_type_dir_name: str) -> set[str]:
        """Memindai direktori untuk menemukan nama modul Python yang tersedia (tanpa .py)."""
        available = set()
        dir_path = os.path.join(self.project_root_dir, module_type_dir_name)
        
        if not os.path.isdir(dir_path):
            logger.warning(f"Directory for '{module_type_dir_name}' ('{dir_path}') not found. No modules will be available from here.")
            return available

        for file in os.listdir(dir_path):
            if file.endswith(".py") and not file.startswith("__"):
                module_name = file[:-3]
                # Hindari menambahkan diri sendiri atau config_manager jika berada di 'core'
                if module_type_dir_name == "core" and module_name in ["plugin_manager", "config_manager"]:
                    continue
                available.add(module_name)
        return available

    def _import_module_if_needed(self, name: str, module_type: str):
        """
        Helper untuk mengimpor modul jika belum ada dan tersedia.
        module_type bisa 'plugin' atau 'core_module'.
        """
        target_dict = self.loaded_plugins if module_type == "plugin" else self.loaded_core_modules
        available_set = self.available_plugins if module_type == "plugin" else self.available_core_modules
        package_prefix = "plugins" if module_type == "plugin" else "core"

        if name in target_dict: # Sudah diimpor sebelumnya
            logger.debug(f"{module_type.capitalize()} '{name}' already loaded. Returning cached.")
            return target_dict[name]

        if name not in available_set:
            logger.warning(f"{module_type.capitalize()} '{name}' is not in the list of available modules. Cannot load.")
            return None

        full_module_name = f"{package_prefix}.{name}"
        try:
            logger.info(f"Attempting to lazy load {module_type} '{name}' (from {full_module_name})...")
            module = importlib.import_module(full_module_name)
            target_dict[name] = module
            logger.info(f"{module_type.capitalize()} '{name}' loaded successfully.")
            return module
        except ImportError as e:
            logger.error(f"Failed to lazy load {module_type} '{name}' (from {full_module_name}): {e}", exc_info=True)
            # Hapus dari available jika gagal diimpor agar tidak dicoba lagi kecuali di-scan ulang
            if name in available_set:
                 available_set.remove(name)
                 logger.info(f"Removed '{name}' from available {module_type}s due to import error.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error lazy loading {module_type} '{name}' (from {full_module_name}): {e}", exc_info=True)
            if name in available_set:
                 available_set.remove(name)
                 logger.info(f"Removed '{name}' from available {module_type}s due to unexpected error.")
            return None

    def get_plugin(self, name: str):
        return self._import_module_if_needed(name, "plugin")

    def get_core_module(self, name: str):
        return self._import_module_if_needed(name, "core_module")

    def reload_plugin(self, name: str):
        if name in self.loaded_plugins:
            try:
                logger.info(f"Attempting to reload plugin '{name}'...")
                importlib.reload(self.loaded_plugins[name])
                logger.info(f"Plugin '{name}' reloaded successfully.")
            except Exception as e:
                logger.error(f"Failed to reload plugin '{name}': {e}", exc_info=True)
        else:
            logger.warning(f"Plugin '{name}' not loaded. Cannot reload. Try get_plugin('{name}') first.")
            
    def reload_all_plugins(self):
        logger.info("Reloading all currently loaded plugins...")
        # Hanya reload yang sudah ada di self.loaded_plugins
        for name in list(self.loaded_plugins.keys()): 
            self.reload_plugin(name)

    def reload_core_module(self, name: str):
        if name in ["plugin_manager", "config_manager"]:
            logger.warning(f"Reloading '{name}' dynamically is generally not recommended. Skipping.")
            return
        if name in self.loaded_core_modules:
            try:
                logger.info(f"Attempting to reload core module '{name}'...")
                importlib.reload(self.loaded_core_modules[name])
                logger.info(f"Core module '{name}' reloaded successfully.")
            except Exception as e:
                logger.error(f"Failed to reload core module '{name}': {e}", exc_info=True)
        else:
            logger.warning(f"Core module '{name}' not loaded. Cannot reload. Try get_core_module('{name}') first.")
        
    def reload_all_core_modules(self):
        logger.info("Reloading all currently loaded core modules...")
        # Hanya reload yang sudah ada di self.loaded_core_modules
        for name in list(self.loaded_core_modules.keys()):
            self.reload_core_module(name)
            
    def list_available_plugins(self) -> list[str]:
        return sorted(list(self.available_plugins))

    def list_available_core_modules(self) -> list[str]:
        return sorted(list(self.available_core_modules))

    def list_loaded_plugins(self) -> list[str]:
        return sorted(list(self.loaded_plugins.keys()))

    def list_loaded_core_modules(self) -> list[str]:
        return sorted(list(self.loaded_core_modules.keys()))


if __name__ == "__main__":
    print(f"Running plugin_manager.py directly for testing (Lazy Loading Mode)...")
    
    # --- Mocking untuk standalone test ---
    class MockConfigManager:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # your_project
        LOG_DIR = os.path.join(BASE_DIR, "logs_test_pm") # Direktori log terpisah untuk tes

    # Patch config_manager jika tidak ada atau LOG_DIR tidak ada atributnya
    # Ini penting agar logger di atas modul bisa berfungsi saat tes standalone
    if 'config_manager' not in globals() or not hasattr(config_manager, 'LOG_DIR'):
        print("Mocking config_manager for standalone test of plugin_manager.")
        if not os.path.exists(MockConfigManager.LOG_DIR):
            os.makedirs(MockConfigManager.LOG_DIR)
        # Membuat objek config_manager tiruan jika tidak ada sama sekali
        if 'config_manager' not in globals():
            config_manager = type('ConfigManager', (), {'LOG_DIR': MockConfigManager.LOG_DIR})()
        else: # Jika config_manager ada tapi tidak punya LOG_DIR
            config_manager.LOG_DIR = MockConfigManager.LOG_DIR
    # --- End Mocking ---

    project_r = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dummy_plugin_dir = os.path.join(project_r, "plugins")
    dummy_core_dir = os.path.join(project_r, "core")

    # Buat file __init__.py di root project jika belum ada agar 'plugins' dan 'core' bisa diimpor relatif
    # Ini mungkin tidak diperlukan tergantung bagaimana Anda menjalankan, tapi aman untuk dimiliki
    if not os.path.exists(os.path.join(project_r, "__init__.py")):
        with open(os.path.join(project_r, "__init__.py"), "w") as f: f.write("# Project root init\n")
        print(f"Created dummy __init__.py in project root: {project_r}")

    # Buat direktori dan file dummy jika tidak ada untuk pengujian
    if not os.path.exists(dummy_plugin_dir): os.makedirs(dummy_plugin_dir)
    if not os.path.exists(os.path.join(dummy_plugin_dir, "__init__.py")):
        with open(os.path.join(dummy_plugin_dir, "__init__.py"), "w") as f: f.write("# Plugins init\n")
    if not os.path.exists(os.path.join(dummy_plugin_dir, "test_plugin.py")):
        with open(os.path.join(dummy_plugin_dir, "test_plugin.py"), "w") as f:
            f.write("print('test_plugin.py loaded by import')\nclass TestPlugin:\n    def run(self):\n        return 'Test plugin running!'\n")
        print(f"Created dummy test_plugin.py for testing.")
    if not os.path.exists(os.path.join(dummy_plugin_dir, "another_plugin.py")):
        with open(os.path.join(dummy_plugin_dir, "another_plugin.py"), "w") as f:
            f.write("print('another_plugin.py loaded by import')\nMESSAGE = 'Hello from another plugin!'\n")
        print(f"Created dummy another_plugin.py for testing.")


    # File ini sendiri (plugin_manager.py) ada di core, tidak perlu membuat dummy untuk itu.
    # Buat __init__.py di core jika belum ada
    if not os.path.exists(os.path.join(dummy_core_dir, "__init__.py")):
        with open(os.path.join(dummy_core_dir, "__init__.py"), "w") as f: f.write("# Core init\n")
    if not os.path.exists(os.path.join(dummy_core_dir, "sample_core_module.py")):
         with open(os.path.join(dummy_core_dir, "sample_core_module.py"), "w") as f:
            f.write("print('sample_core_module.py loaded by import')\nCORE_MESSAGE = 'Hello from sample core module!'\n")
         print(f"Created dummy sample_core_module.py for testing.")

    print("\n--- Initializing ModuleManager ---")
    manager = ModuleManager()
    print(f"Available plugins: {manager.list_available_plugins()}")
    print(f"Available core modules: {manager.list_available_core_modules()}")
    print(f"Loaded plugins (should be empty): {manager.list_loaded_plugins()}")
    print(f"Loaded core modules (should be empty): {manager.list_loaded_core_modules()}")

    print("\n--- Getting 'test_plugin' for the first time ---")
    test_plug_module = manager.get_plugin("test_plugin") # Ini akan memicu impor
    if test_plug_module:
        print(f"Type of test_plug_module: {type(test_plug_module)}")
        instance = test_plug_module.TestPlugin()
        logger.info(f"Test plugin output: {instance.run()}")
    else:
        logger.error("Failed to get 'test_plugin'.")
    print(f"Loaded plugins after get: {manager.list_loaded_plugins()}")

    print("\n--- Getting 'test_plugin' again (should be cached) ---")
    test_plug_module_cached = manager.get_plugin("test_plugin")
    if test_plug_module_cached:
        logger.info(f"Cached 'test_plugin' retrieved. ID: {id(test_plug_module_cached)}, Original ID: {id(test_plug_module)}")
    else:
        logger.error("Failed to get cached 'test_plugin'.")

    print("\n--- Getting 'another_plugin' ---")
    another_plug_module = manager.get_plugin("another_plugin")
    if another_plug_module:
        logger.info(f"Another plugin message: {another_plug_module.MESSAGE}")
    else:
        logger.error("Failed to get 'another_plugin'.")
    print(f"Loaded plugins now: {manager.list_loaded_plugins()}")
    
    print("\n--- Getting 'sample_core_module' ---")
    sample_core_mod = manager.get_core_module("sample_core_module")
    if sample_core_mod:
        logger.info(f"Sample core module message: {sample_core_mod.CORE_MESSAGE}")
    else:
        logger.error("Failed to get 'sample_core_module'.")
    print(f"Loaded core modules now: {manager.list_loaded_core_modules()}")

    print("\n--- Attempting to get non_existent_plugin ---")
    non_existent = manager.get_plugin("non_existent_plugin")
    if non_existent is None:
        logger.info("Correctly returned None for non_existent_plugin.")

    print("\n--- Reloading 'test_plugin' ---")
    manager.reload_plugin("test_plugin")
    # Anda akan melihat "test_plugin.py loaded by import" lagi jika reload berhasil

    # Membersihkan (opsional, nonaktifkan jika ingin memeriksa file)
    # import shutil
    # if os.path.exists(dummy_plugin_dir) and "test_plugin.py" in os.listdir(dummy_plugin_dir):
    #     # shutil.rmtree(dummy_plugin_dir)
    #     # print("Cleaned up dummy plugin directory.")
    #     pass
    # if os.path.exists(os.path.join(dummy_core_dir, "sample_core_module.py")):
    #     # os.remove(os.path.join(dummy_core_dir, "sample_core_module.py"))
    #     # print("Cleaned up dummy sample_core_module.py.")
    #     pass
    # if os.path.exists(MockConfigManager.LOG_DIR):
    #     # shutil.rmtree(MockConfigManager.LOG_DIR)
    #     # print(f"Cleaned up {MockConfigManager.LOG_DIR}")
    #     pass