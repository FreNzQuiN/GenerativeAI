# plugins/translator.py
from googletrans import Translator, LANGUAGES  # type: ignore
from core.config_manager import ConfigManager
import logging
import os
import asyncio
import httpx  # googletrans menggunakan httpx

try:
    _cfg = ConfigManager()
except Exception as e_cfg_init_tr:
    print(
        f"CRITICAL ERROR in translator.py: Failed to initialize ConfigManager: {e_cfg_init_tr}"
    )
    raise RuntimeError(
        f"Translator: ConfigManager initialization failed: {e_cfg_init_tr}"
    ) from e_cfg_init_tr

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        # Menggunakan _cfg untuk path log
        _log_dir_tr = _cfg.get_config_value(
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
        if not os.path.exists(_log_dir_tr):
            os.makedirs(_log_dir_tr, exist_ok=True)
        log_file_path = os.path.join(
            _log_dir_tr, f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
        )
    except Exception as e_log_path_tr:
        logger.error(
            "Error determining log_file_path for translator: %s. Using fallback.",
            e_log_path_tr,
            exc_info=False,
        )
        log_file_path = (
            f"{os.path.splitext(os.path.basename(__file__))[0]}.log"  # Fallback
        )
    try:
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)
    except OSError as e_fh_tr:
        logger.error(
            "OSError setting up file handler for translator: %s. Using basicConfig.",
            e_fh_tr,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    except Exception as e_log_tr:  # Tangkap error umum lainnya saat setup logger
        logger.error(
            "Unexpected error setting up logger for translator: %s. Using basicConfig.",
            e_log_tr,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

_google_translator_obj: Translator | None = None
_translator_init_lock = asyncio.Lock()  # Lock untuk inisialisasi _google_translator_obj


async def _get_google_translator_instance() -> Translator | None:
    """Menginisialisasi dan mengembalikan instance googletrans.Translator secara lazy dan thread-safe."""
    global _google_translator_obj
    if _google_translator_obj is None:
        async with _translator_init_lock:
            if _google_translator_obj is None:  # Double check setelah mendapatkan lock
                try:
                    logger.info("Initializing googletrans.Translator instance...")
                    # Translator() mungkin melakukan I/O awal, tapi metode translate/detect adalah async
                    # Jika Translator() sendiri blocking, perlu to_thread. Tapi kita coba langsung dulu.
                    # Berdasarkan error log, metode .translate/.detect adalah async.
                    _google_translator_obj = (
                        Translator()
                    )  # Asumsi konstruktornya sendiri tidak berat atau non-blocking
                    logger.info(
                        "Googletrans Translator instance created (methods are async)."
                    )
                except httpx.RequestError as e_http:
                    logger.error(
                        "HTTP request error initializing Googletrans Translator: %s",
                        e_http,
                        exc_info=True,
                    )
                    _google_translator_obj = None
                except Exception as e_trans_init:
                    logger.error(
                        "Failed to initialize Googletrans Translator: %s",
                        e_trans_init,
                        exc_info=True,
                    )
                    _google_translator_obj = None
    return _google_translator_obj


DEFAULT_SOURCE_LANG = _cfg.get_config_value(
    "translator_plugin", "default_source_language", "auto"
)
DEFAULT_TARGET_LANG = _cfg.get_config_value(
    "translator_plugin", "default_target_language", "en"
)
SUPPORTED_LANGUAGES_MAP = LANGUAGES


class TranslationPlugin:
    def __init__(self):
        logger.debug(
            "TranslationPlugin instance created. Underlying Translator object will be lazy loaded."
        )

    def is_language_supported(self, lang_code: str) -> bool:
        return lang_code.lower() in SUPPORTED_LANGUAGES_MAP

    async def translate(
        self, text: str, target_lang: str | None = None, source_lang: str | None = None
    ) -> str | None:
        translator = await _get_google_translator_instance()
        if translator is None:
            logger.error(
                "Translator not available (init failed). Cannot perform translation."
            )
            return None
        if not isinstance(text, str) or not text.strip():
            logger.warning("Input text for translation is empty or not a string.")
            return "" if isinstance(text, str) else None

        actual_target_lang = (target_lang or DEFAULT_TARGET_LANG).lower()
        actual_source_lang = (source_lang or DEFAULT_SOURCE_LANG).lower()

        if not self.is_language_supported(actual_target_lang):
            logger.error("Target language '%s' is not supported.", actual_target_lang)
            return None
        if actual_source_lang != "auto" and not self.is_language_supported(
            actual_source_lang
        ):
            logger.error("Source language '%s' is not supported.", actual_source_lang)
            return None

        logger.info(
            "Attempting to translate from '%s' to '%s': '%s...'",
            actual_source_lang,
            actual_target_lang,
            text[:50],
        )
        try:
            # ---- PERBAIKAN UTAMA ADA DI SINI ----
            # Langsung await metode async dari library googletrans
            translated_object = await translator.translate(
                text, dest=actual_target_lang, src=actual_source_lang
            )
            # ------------------------------------

            if translated_object and hasattr(translated_object, "text"):
                translated_text = translated_object.text
                detected_source_lang = translated_object.src
                logger.info(
                    "Successfully translated. Detected source: '%s'. Result: '%s...'",
                    detected_source_lang,
                    translated_text[:50],
                )
                return translated_text
            else:
                logger.error(
                    "Translation attempt returned an unexpected object or no text: %s",
                    translated_object,
                )
                return None
        except httpx.TimeoutException as e_timeout:  # Tangkap timeout dari httpx
            logger.error(
                "Timeout during translation request: %s", e_timeout, exc_info=True
            )
            return None
        except httpx.RequestError as e_http_trans:
            logger.error(
                "HTTP request error during translation: %s", e_http_trans, exc_info=True
            )
            return None
        except Exception as e_trans:
            logger.error(
                "Error during translation from '%s' to '%s': %s",
                actual_source_lang,
                actual_target_lang,
                e_trans,
                exc_info=True,
            )
            return None

    async def detect_language(self, text: str) -> tuple[str | None, float | None]:
        translator = await _get_google_translator_instance()
        if translator is None:
            logger.error(
                "Translator not available (init failed). Cannot perform language detection."
            )
            return None, None
        if not isinstance(text, str) or not text.strip():
            logger.warning(
                "Input text for language detection is empty or not a string."
            )
            return None, None

        logger.info("Attempting to detect language for: '%s...'", text[:50])
        try:
            # ---- PERBAIKAN UTAMA ADA DI SINI ----
            # Langsung await metode async dari library googletrans
            detected_object = await translator.detect(text)
            # ------------------------------------

            if (
                detected_object
                and hasattr(detected_object, "lang")
                and hasattr(detected_object, "confidence")
            ):
                lang_code = detected_object.lang
                confidence = detected_object.confidence
                if isinstance(confidence, list):
                    confidence = confidence[0] if confidence else 0.0
                try:
                    confidence_float = float(confidence)
                except (ValueError, TypeError):
                    logger.warning(
                        "Could not convert confidence '%s' to float. Defaulting to 0.0.",
                        confidence,
                    )
                    confidence_float = 0.0
                logger.info(
                    "Language detected: %s with confidence: %.2f",
                    lang_code,
                    confidence_float,
                )
                return lang_code, confidence_float
            else:
                logger.error(
                    "Language detection returned an unexpected object: %s",
                    detected_object,
                )
                return None, None
        except httpx.TimeoutException as e_timeout_detect:
            logger.error(
                "Timeout during language detection request: %s",
                e_timeout_detect,
                exc_info=True,
            )
            return None, None
        except httpx.RequestError as e_http_detect:
            logger.error(
                "HTTP request error during language detection: %s",
                e_http_detect,
                exc_info=True,
            )
            return None, None
        except Exception as e_detect:
            logger.error("Error during language detection: %s", e_detect, exc_info=True)
            return None, None


_plugin_instance_singleton: TranslationPlugin | None = None
_plugin_init_lock = asyncio.Lock()


async def get_translator_plugin() -> TranslationPlugin | None:
    global _plugin_instance_singleton
    if _plugin_instance_singleton is None:
        async with _plugin_init_lock:
            if _plugin_instance_singleton is None:
                # Pastikan underlying translator bisa diinisialisasi
                if await _get_google_translator_instance() is not None:
                    try:
                        _plugin_instance_singleton = TranslationPlugin()
                        logger.info("TranslationPlugin singleton instance created.")
                    except Exception as e_plugin_create:
                        logger.error(
                            "Failed to create TranslationPlugin instance: %s",
                            e_plugin_create,
                            exc_info=True,
                        )
                else:
                    logger.error(
                        "Cannot create TranslationPlugin: underlying Google Translator failed to initialize."
                    )
    return _plugin_instance_singleton


async def translate_text(
    text: str, target_lang: str | None = None, source_lang: str | None = None
) -> str | None:
    plugin = await get_translator_plugin()
    if plugin:
        return await plugin.translate(text, target_lang, source_lang)
    logger.warning("translate_text: Translator plugin not available.")
    return None


async def detect_text_language(text: str) -> tuple[str | None, float | None]:
    plugin = await get_translator_plugin()
    if plugin:
        return await plugin.detect_language(text)
    logger.warning("detect_text_language: Translator plugin not available.")
    return None, None


if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        )
    logger.info("--- Translator Plugin Test (Corrected Async) ---")

    async def run_tests():
        translator_plug = await get_translator_plugin()
        if not translator_plug:
            logger.error("Translator plugin could not be initialized. Aborting tests.")
            return

        test_cases = [
            {
                "lang_key": "id",
                "text": "Halo, apa kabar dunia? Semoga harimu menyenangkan!",
                "target_trans": "en",
            },
            {
                "lang_key": "en",
                "text": "Hello, how are you world? Hope you have a great day!",
                "target_trans": "id",
            },
            {
                "lang_key": "ja",
                "text": "こんにちは、世界、お元気ですか？素晴らしい一日をお過ごしください！",
                "target_trans": "en",
            },
            {
                "lang_key": "fr",
                "text": "Bonjour le monde, comment allez-vous?",
                "target_trans": "en",
            },  # Bahasa baru
            {
                "lang_key": "es",
                "text": "¿Hola Mundo como estas?",
                "target_trans": "en",
            },
        ]

        for case in test_cases:
            text_original = case["text"]
            lang_key_original = case["lang_key"]
            target_for_translation = case["target_trans"]

            logger.info("\nOriginal (%s): %s", lang_key_original.upper(), text_original)

            translated = await translate_text(
                text_original,
                target_lang=target_for_translation,
                source_lang=lang_key_original,
            )
            if translated:
                logger.info(
                    "  -> Translated to %s: %s",
                    target_for_translation.upper(),
                    translated,
                )
            else:
                logger.warning(
                    "  -> Translation to %s FAILED.", target_for_translation.upper()
                )

            detected_lang, confidence = await detect_text_language(text_original)
            if detected_lang:
                logger.info(
                    "  -> Detected as: %s (Confidence: %.2f)",
                    detected_lang,
                    confidence or 0.0,
                )
            else:
                logger.warning("  -> Language detection FAILED.")
            await asyncio.sleep(1)

        logger.info("\n--- Test dengan teks kosong ---")
        empty_trans = await translate_text("", target_lang="en")
        logger.info(
            "Translation of empty string: '%s' (expected empty string)", empty_trans
        )
        empty_detect, empty_conf = await detect_text_language("")
        logger.info(
            "Detection of empty string: lang=%s, conf=%s (expected None, None)",
            empty_detect,
            empty_conf,
        )

    try:
        asyncio.run(run_tests())
    except RuntimeError as e_rt_main:
        if "cannot be called from a running event loop" in str(e_rt_main).lower():
            logger.warning(
                "Asyncio loop already running. Skipping standalone translator test run."
            )
        else:
            logger.error(
                "RuntimeError running translator tests: %s", e_rt_main, exc_info=True
            )
    except Exception as e_main:
        logger.error(
            "Unexpected error running translator tests: %s", e_main, exc_info=True
        )
