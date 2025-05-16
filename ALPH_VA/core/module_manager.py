# core/plugin_manager.py

import importlib, logging, os
from core import config_manager

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

PLUGINS = {}
CORE = {}

def load_plugins():
    plugin_dir = "plugins"
    for file in os.listdir(plugin_dir):
        try:
            if file.endswith(".py") and not file.startswith("__"):
                module_name = file[:-3]
                module = importlib.import_module(f"plugins.{module_name}")
                PLUGINS[module_name] = module
                logger.info(f"Plugin '{module_name}' loaded successfully.")
            else:
                logger.info(f"Skipping non-Python file or __init__.py: {file}")
        except ImportError as e:
            logger.error(f"Failed to load plugin '{file}': {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error loading plugin '{file}': {e}", exc_info=True)

def load_core():
    core_dir = "core"
    for file in os.listdir(core_dir):
        try:
            if file.endswith(".py") and not file.startswith("__"):
                module_name = file[:-3]
                module = importlib.import_module(f"core.{module_name}")
                CORE[module_name] = module
                logger.info(f"Core module '{module_name}' loaded successfully.")
            else:
                logger.info(f"Skipping non-Python file or __init__.py: {file}")
        except ImportError as e:
            logger.error(f"Failed to load core module '{file}': {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error loading core module '{file}': {e}", exc_info=True)

def get_plugin(name):
    if name not in PLUGINS:
        logger.warning(f"Plugin '{name}' not found. Returning None.")
        return None
    logger.debug(f"Retrieving plugin '{name}'.")
    return PLUGINS.get(name)

def reload_plugin(name):
    if name in PLUGINS:
        importlib.reload(PLUGINS[name])
        logger.debug(f"Plugin '{name}' reloaded successfully.")
    else:
        logger.warning(f"Plugin '{name}' not found. Cannot reload.")
        
def reload_all_plugins():
    for name in PLUGINS:
        try:
            importlib.reload(PLUGINS[name])
            logger.debug(f"Plugin '{name}' reloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to reload plugin '{name}': {e}", exc_info=True)

def get_core(name):
    if name not in CORE:
        logger.warning(f"Core module '{name}' not found. Returning None.")
        return None
    logger.info(f"Retrieving core module '{name}'.")
    return CORE.get(name)

def reload_core(name):
    if name in CORE:
        importlib.reload(CORE[name])
        logger.debug(f"Core module '{name}' reloaded successfully.")
    else:
        logger.warning(f"Core module '{name}' not found. Cannot reload.")
        
def reload_all_core():
    for name in CORE:
        try:
            importlib.reload(CORE[name])
            logger.debug(f"Core module '{name}' reloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to reload core module '{name}': {e}", exc_info=True)

class ModuleManager:
    def __init__(self):
        logger.info("Initializing ModuleManager...")
        self.plugins = PLUGINS
        self.core = CORE
        logger.info("ModuleManager initialized with loaded plugins and core modules.")
        load_core()
        load_plugins()
        logger.info("All plugins and core modules loaded successfully.")
    
    def get_plugin(self, name):
        return get_plugin(name)
    
    def get_core(self, name):
        return get_core(name)
    
    def reload_plugin(self, name):
        reload_plugin(name)
        
    def reload_core(self, name):
        reload_core(name)
    
    def reload_all_plugins(self):
        reload_all_plugins()
    
    def reload_all_core(self):
        reload_all_core()
    

if __name__ == "__main__":
    manager = ModuleManager()
    logger.info("ModuleManager loaded all plugins and core modules.")