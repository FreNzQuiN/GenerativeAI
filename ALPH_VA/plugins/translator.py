# plugins/translator.py

from googletrans import Translator, LANGUAGES
from core import config_manager
import logging
import os
import asyncio

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

translator_instance = None
try:
    # Jika ada masalah koneksi, ubah: translator_instance = Translator(service_urls=['translate.google.com'])
    translator_instance = Translator()
    logger.info("Googletrans Translator instance initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Googletrans Translator: {e}", exc_info=True)

# --- Konfigurasi ---
DEFAULT_SOURCE_LANG = config_manager.get_config_value("translator_plugin", "default_source_language", "auto")
DEFAULT_TARGET_LANG = config_manager.get_config_value("translator_plugin", "default_target_language", "en")
SUPPORTED_LANGUAGES_MAP = LANGUAGES

class TranslationPlugin:
    def __init__(self):
        if translator_instance is None:
            logger.critical("Translator instance is not available. Translation will not work.")
        self.translator = translator_instance

    def is_language_supported(self, lang_code: str) -> bool:
        return lang_code.lower() in SUPPORTED_LANGUAGES_MAP

    async def translate(self, text: str, target_lang: str, source_lang: str = "auto") -> str | None:
        if self.translator is None:
            logger.error("Translator not initialized. Cannot perform translation.")
            return None
        if not text.strip():
            logger.warning("Input text for translation is empty.")
            return text
        if not self.is_language_supported(target_lang):
            logger.error(f"Target language '{target_lang}' is not supported.")
            return None
        if source_lang != "auto" and not self.is_language_supported(source_lang):
            logger.error(f"Source language '{source_lang}' is not supported.")
            return None

        logger.info(f"Attempting to translate from '{source_lang}' to '{target_lang}': '{text[:50]}...'")
        try:
            translated_object = await self.translator.translate(text, dest=target_lang.lower(), src=source_lang.lower())
            if translated_object and hasattr(translated_object, 'text'):
                translated_text = translated_object.text
                detected_source_lang = translated_object.src
                logger.info(f"Successfully translated. Detected source: '{detected_source_lang}'. Result: '{translated_text[:50]}...'")
                return translated_text
            else:
                logger.error("Translation attempt returned an unexpected object or no text.")
                return None
        except Exception as e:
            logger.error(f"Error during translation from '{source_lang}' to '{target_lang}': {e}", exc_info=True)
            return None

    async def detect_language(self, text: str) -> tuple[str | None, float | None]:
        if self.translator is None:
            logger.error("Translator not initialized. Cannot perform language detection.")
            return None, None
        if not text.strip():
            logger.warning("Input text for language detection is empty.")
            return None, None
            
        logger.info(f"Attempting to detect language for: '{text[:50]}...'")
        try:
            detected_object = await self.translator.detect(text)
            if detected_object and hasattr(detected_object, 'lang') and hasattr(detected_object, 'confidence'):
                lang_code = detected_object.lang
                confidence = detected_object.confidence
                logger.info(f"Language detected: {lang_code} with confidence: {confidence:.2f}")
                return lang_code, confidence
            else:
                logger.error("Language detection returned an unexpected object.")
                return None, None
        except Exception as e:
            logger.error(f"Error during language detection: {e}", exc_info=True)
            return None, None

_plugin_instance = None
def get_translator_plugin() -> TranslationPlugin | None:
    global _plugin_instance
    if _plugin_instance is None:
        if translator_instance is not None:
            _plugin_instance = TranslationPlugin()
        else:
            logger.error("Cannot create TranslationPlugin instance because global Translator failed to initialize.")
    return _plugin_instance

async def translate_text(text: str, target_lang: str, source_lang: str = "auto") -> str | None:
    plugin = get_translator_plugin()
    if plugin:
        return await plugin.translate(text, target_lang, source_lang)
    return None

async def detect_text_language(text: str) -> tuple[str | None, float | None]:
    plugin = get_translator_plugin()
    if plugin:
        return await plugin.detect_language(text)
    return None, None

if __name__ == '__main__':
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Translator Plugin Test ---")
    async def run_tests():
        translator_plug = get_translator_plugin()
        if not translator_plug:
            logger.error("Translator plugin could not be initialized. Aborting tests.")
            return

        text_id = "Halo, apa kabar dunia?"
        text_en = "Hello, how are you world?"
        text_ja = "こんにちは、世界、お元気ですか？"

        logger.info(f"\nOriginal (ID): {text_id}")
        translated_to_en = await translate_text(text_id, target_lang="en", source_lang="id")
        if translated_to_en: logger.info(f"  -> English: {translated_to_en}")

        translated_to_ja = await translate_text(text_id, target_lang="ja") 
        if translated_to_ja: logger.info(f"  -> Japanese: {translated_to_ja}")
        
        logger.info(f"\nOriginal (EN): {text_en}")
        translated_to_id_from_en = await translate_text(text_en, target_lang="id")
        if translated_to_id_from_en: logger.info(f"  -> Indonesian: {translated_to_id_from_en}")

        logger.info(f"\nOriginal (JA): {text_ja}")
        translated_to_en_from_ja = await translate_text(text_ja, target_lang="en", source_lang="ja")
        if translated_to_en_from_ja: logger.info(f"  -> English: {translated_to_en_from_ja}")

        logger.info("\n--- Language Detection Test ---")
        lang_id, conf_id = await detect_text_language(text_id)
        if lang_id: logger.info(f"Detected for '{text_id[:20]}...': {lang_id} (Confidence: {conf_id:.2f})")
        
        lang_en, conf_en = await detect_text_language(text_en)
        if lang_en: logger.info(f"Detected for '{text_en[:20]}...': {lang_en} (Confidence: {conf_en:.2f})")

        lang_ja, conf_ja = await detect_text_language(text_ja)
        if lang_ja: logger.info(f"Detected for '{text_ja[:10]}...': {lang_ja} (Confidence: {conf_ja:.2f})")

    try:
        asyncio.run(run_tests())
    except Exception as e:
        logger.error(f"Error running translator tests: {e}", exc_info=True)