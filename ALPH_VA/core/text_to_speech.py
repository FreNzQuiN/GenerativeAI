# core/text_to_speech.py

import asyncio, os, logging
from core import config_manager
import plugins.default_tts as default_tts_plugin
import plugins.japanese_tts as japanese_tts_plugin
import plugins.custom_model_tts as custom_model_tts_plugin

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

DEFAULT_APP_LANGUAGE = config_manager.get_config_value("general", "interface_language", "id")
DEFAULT_TTS_ENGINE = config_manager.get_config_value("tts_settings", "default_engine", "default")

async def speak(text: str, language: str = None, rate: int = None, volume: float = None, 
                speaker_name_or_id=None, engine_override: str = None):
    """
    Mengucapkan teks menggunakan engine TTS yang sesuai.
    Memilih engine berdasarkan `engine_override`, kemudian `language`, lalu `DEFAULT_TTS_ENGINE`.

    Args:
        text (str): Teks yang akan diucapkan.
        language (str, optional): Kode bahasa (misalnya, "id", "en", "ja").
                                  Jika None, menggunakan DEFAULT_APP_LANGUAGE.
        rate (int, optional): Kecepatan bicara (untuk pyttsx3).
        volume (float, optional): Volume suara (untuk pyttsx3).
        speaker_name_or_id (str/int, optional): Nama atau ID speaker (untuk Voicevox/Custom TTS).
        engine_override (str, optional): Paksa penggunaan engine tertentu ("default", "japanese", "custom").
    """
    if not text.strip():
        logger.warning("Speak function called with empty text.")
        return

    actual_language = language if language is not None else DEFAULT_APP_LANGUAGE
    selected_engine = engine_override
    if not selected_engine:
        if actual_language.lower() == "ja":
            selected_engine = "japanese"
        else:
            selected_engine = DEFAULT_TTS_ENGINE
    logger.info(f"Dispatching TTS: Engine='{selected_engine}', Lang='{actual_language}', Text='{text[:30]}...'")

    try:
        if selected_engine == "default":
            if asyncio.get_running_loop().is_running():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, default_tts_plugin.speak_default, text, actual_language, rate, volume)
            else:
                default_tts_plugin.speak_default(text, actual_language, rate, volume)
        elif selected_engine == "japanese":
            await japanese_tts_plugin.speak_japanese(text, speaker_id=speaker_name_or_id)
        elif selected_engine == "custom":
            await custom_model_tts_plugin.speak_custom(text, speaker_name_or_id=speaker_name_or_id, language=actual_language)
        else:
            logger.error(f"Unknown or unhandled TTS engine specified: '{selected_engine}'. Falling back to default.")
            if asyncio.get_running_loop().is_running():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, default_tts_plugin.speak_default, text, actual_language, rate, volume)
            else:
                default_tts_plugin.speak_default(text, actual_language, rate, volume)
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e).lower():
            logger.error(f"Async TTS function called incorrectly from a sync context or nested asyncio.run: {e}")
            if selected_engine == "japanese":
                asyncio.ensure_future(japanese_tts_plugin.speak_japanese(text, speaker_id=speaker_name_or_id))
            elif selected_engine == "custom":
                asyncio.ensure_future(custom_model_tts_plugin.speak_custom(text, speaker_name_or_id=speaker_name_or_id, language=actual_language))
            else:
                 default_tts_plugin.speak_default(text, actual_language, rate, volume)
        else:
            logger.error(f"RuntimeError during TTS dispatch for engine '{selected_engine}': {e}", exc_info=True)
    except Exception as e:
        logger.error(f"General error during TTS dispatch for engine '{selected_engine}': {e}", exc_info=True)


async def main_test_tts_dispatcher():
    logger.info("--- Text-to-Speech Dispatcher Test ---")

    # Tes Bahasa Indonesia (seharusnya menggunakan default_engine dari config)
    logger.info("\nTesting Indonesian (default engine from config):")
    await speak("Halo, ini tes suara bahasa Indonesia.", language="id")

    # Tes Bahasa Inggris (seharusnya menggunakan default_engine dari config)
    logger.info("\nTesting English (default engine from config):")
    await speak("Hello, this is an English test.", language="en", rate=180) # Override rate

    # Tes Bahasa Jepang (seharusnya menggunakan engine 'japanese')
    # Pastikan Voicevox berjalan
    logger.info("\nTesting Japanese (should use 'japanese' engine):")
    await speak("おはようございます、今日はどうですか？", language="ja", speaker_name_or_id=config_manager.get_int("tts_settings","voicevox_speaker_id",3))

    # Tes override engine ke 'custom'
    # Pastikan model kustom Anda dikonfigurasi dengan benar di [tts_custom_model]
    logger.info("\nTesting Custom TTS engine (explicit override):")
    custom_speaker = config_manager.get_config_value("tts_custom_model", "default_speaker_name_or_id", "gadis")
    await speak("Ini adalah tes menggunakan model kustom yang dipaksa.", language="id", engine_override="custom", speaker_name_or_id=custom_speaker)

    logger.info("\nTesting fallback for unknown language (should use default_engine from config):")
    await speak("Ceci est un test en français.", language="fr")

    logger.info("\nTesting unknown engine (should fallback to default_engine from config):")
    await speak("Testing unknown engine fallback.", language="en", engine_override="non_existent_engine")

class TTS:
    """
    Kelas untuk mengelola Text-to-Speech (TTS) dengan berbagai engine.
    """
    def __init__(self):
        self.default_engine = DEFAULT_TTS_ENGINE
        self.language = DEFAULT_APP_LANGUAGE
        
        
    async def speak(self, text: str, language: str = None, rate: int = None, volume: float = None,
              speaker_name_or_id=None, engine_override: str = None):
        """
        Mengucapkan teks menggunakan engine TTS yang sesuai.
        Memilih engine berdasarkan `engine_override`, kemudian `language`, lalu `DEFAULT_TTS_ENGINE`.

        Args:
            text (str): Teks yang akan diucapkan.
            language (str, optional): Kode bahasa (misalnya, "id", "en", "ja").
                                      Jika None, menggunakan DEFAULT_APP_LANGUAGE.
            rate (int, optional): Kecepatan bicara (untuk pyttsx3).
            volume (float, optional): Volume suara (untuk pyttsx3).
            speaker_name_or_id (str/int, optional): Nama atau ID speaker (untuk Voicevox/Custom TTS).
            engine_override (str, optional): Paksa penggunaan engine tertentu ("default", "japanese", "custom").
        """
        if not text.strip():
            logger.warning("Speak function called with empty text.")
            return
        actual_language = language if language is not None else self.language
        selected_engine = engine_override
        if not selected_engine:
            if actual_language.lower() == "ja":
                selected_engine = "japanese"
            else:
                selected_engine = self.default_engine
        logger.info(f"Dispatching TTS: Engine='{selected_engine}', Lang='{actual_language}', Text='{text[:30]}...'")
        try:
            if selected_engine == "default":
                if asyncio.get_running_loop().is_running():
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, default_tts_plugin.speak_default, text, actual_language, rate, volume)
                else:
                    default_tts_plugin.speak_default(text, actual_language, rate, volume)
            elif selected_engine == "japanese":
                await japanese_tts_plugin.speak_japanese(text, speaker_id=speaker_name_or_id)
            elif selected_engine == "custom":
                await custom_model_tts_plugin.speak_custom(text, speaker_name_or_id=speaker_name_or_id, language=actual_language)
            else:
                logger.error(f"Unknown or unhandled TTS engine specified: '{selected_engine}'. Falling back to default.")
                if asyncio.get_running_loop().is_running():
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, default_tts_plugin.speak_default, text, actual_language, rate, volume)
                else:
                    default_tts_plugin.speak_default(text, actual_language, rate, volume)
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e).lower():
                logger.error(f"Async TTS function called incorrectly from a sync context or nested asyncio.run: {e}")
                if selected_engine == "japanese":
                    asyncio.ensure_future(japanese_tts_plugin.speak_japanese(text, speaker_id=speaker_name_or_id))
                elif selected_engine == "custom":
                    asyncio.ensure_future(custom_model_tts_plugin.speak_custom(text, speaker_name_or_id=speaker_name_or_id, language=actual_language))
                else:
                     default_tts_plugin.speak_default(text, actual_language, rate, volume)
            else:
                logger.error(f"RuntimeError during TTS dispatch for engine '{selected_engine}': {e}", exc_info=True)
        except Exception as e:
            logger.error(f"General error during TTS dispatch for engine '{selected_engine}': {e}", exc_info=True)
            
    def get_tts_engine(engine_name: str):
        """
        Mengembalikan instance engine TTS berdasarkan nama engine.
        """
        if engine_name == "default":
            return default_tts_plugin
        elif engine_name == "japanese":
            return japanese_tts_plugin
        elif engine_name == "custom":
            return custom_model_tts_plugin
        else:
            logger.error(f"Unknown TTS engine requested: {engine_name}")
            return None
        
        
if __name__ == '__main__':
    # Setup basic logging jika modul dijalankan sendiri
    if not logging.getLogger().hasHandlers() and not logger.hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    asyncio.run(main_test_tts_dispatcher())