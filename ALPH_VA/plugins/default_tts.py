# plugins/default_tts.py
import pyttsx3  # type: ignore
from core.config_manager import ConfigManager
import logging
from typing import Optional, List, Dict
import os, time

try:
    _cfg = ConfigManager()
except Exception as e_cfg_init_tts:
    print(
        f"CRITICAL ERROR in default_tts.py: Failed to initialize ConfigManager: {e_cfg_init_tts}"
    )
    raise RuntimeError(
        f"DefaultTTS: ConfigManager initialization failed: {e_cfg_init_tts}"
    ) from e_cfg_init_tts

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        _log_dir_tts = _cfg.get_config_value(
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
        if not os.path.exists(_log_dir_tts):
            os.makedirs(_log_dir_tts, exist_ok=True)
        log_file_path = os.path.join(
            _log_dir_tts, f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
        )
    except Exception as e_log_path_tts:
        print(
            f"ERROR determining log_file_path for default_tts: {e_log_path_tts}. Using fallback."
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
    except OSError as e_fh_tts:
        print(
            f"ERROR (OSError) setting up file handler for default_tts: {e_fh_tts}. Using basicConfig."
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    except Exception as e_log_tts:
        print(
            f"ERROR (Exception) setting up logger for default_tts: {e_log_tts}. Using basicConfig."
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


PYTTSX3_DEFAULT_RATE = _cfg.get_int("tts_settings", "pyttsx3_rate", 150)
PYTTSX3_DEFAULT_VOLUME = _cfg.get_float("tts_settings", "pyttsx3_volume", 1.0)

_voices_cache: List[Dict] = []
_voices_cache_populated_flag = False


def _populate_voices_cache():
    """Mengisi cache daftar suara. Hanya dijalankan sekali."""
    global _voices_cache, _voices_cache_populated_flag
    if _voices_cache_populated_flag:
        return
    engine = None
    try:
        engine = pyttsx3.init()
        if engine is None:
            logger.error("pyttsx3.init() returned None. Cannot populate voices cache.")
            return

        raw_voices = engine.getProperty("voices")
        processed_voices = []
        for i, voice_obj in enumerate(raw_voices):
            voice_detail = {
                "id": voice_obj.id,
                "name": voice_obj.name,
                "languages": [],
                "gender": None,
                "age": None,
            }
            try:
                if hasattr(voice_obj, "languages") and voice_obj.languages:
                    voice_detail["languages"] = [
                        (
                            lang.decode("utf-8", errors="replace")
                            if isinstance(lang, bytes)
                            else str(lang)
                        )
                        for lang in voice_obj.languages
                    ]
                if hasattr(voice_obj, "gender"):
                    voice_detail["gender"] = (
                        voice_obj.gender.decode("utf-8", errors="replace")
                        if isinstance(voice_obj.gender, bytes)
                        else str(voice_obj.gender)
                    )
                if hasattr(voice_obj, "age"):
                    voice_detail["age"] = voice_obj.age
            except UnicodeDecodeError as e_decode:
                logger.debug(
                    "UnicodeDecodeError for voice %d property: %s", i, e_decode
                )
            except Exception as e_prop:
                logger.debug("Error processing property for voice %d: %s", i, e_prop)
            processed_voices.append(voice_detail)
        _voices_cache = processed_voices
        logger.info(
            "Successfully populated voices cache with %d voices.", len(_voices_cache)
        )
    except RuntimeError as re_init:
        logger.error(
            "RuntimeError initializing pyttsx3 for voice listing: %s",
            re_init,
            exc_info=True,
        )
    except Exception as e_gen_init:
        logger.error(
            "Failed to initialize pyttsx3 for voice listing: %s",
            e_gen_init,
            exc_info=True,
        )
    finally:
        _voices_cache_populated_flag = True


def list_available_voices() -> list[Dict]:
    """Mengembalikan daftar suara yang tersedia dari cache."""
    if not _voices_cache_populated_flag:
        _populate_voices_cache()
    return list(_voices_cache)


def _set_voice_on_engine(engine: pyttsx3.Engine, language_code: str = "id") -> bool:
    """Mencoba mengatur suara pada instance engine berdasarkan kode bahasa."""

    current_voices_data = list_available_voices()
    if not current_voices_data:
        logger.warning(
            "No voices available from cache to set for language %s.", language_code
        )
        return False

    config_voice_id_key = f"pyttsx3_voice_id_{language_code.lower().replace('-', '_')}"
    voice_id_from_config = _cfg.get_config_value(
        "tts_pyttsx3_specifics", config_voice_id_key
    )
    if voice_id_from_config:
        try:
            engine.setProperty("voice", voice_id_from_config)
            logger.info(
                "Set pyttsx3 voice using config ID for '%s': %s",
                language_code,
                voice_id_from_config,
            )
            return True
        except (RuntimeError, ValueError, TypeError) as e_set_id:
            logger.warning(
                "Failed to set voice using config ID '%s': %s. Trying other methods.",
                voice_id_from_config,
                e_set_id,
            )

    target_lang_lower = language_code.lower()
    target_lang_prefix = target_lang_lower.split("-")[0]

    for voice_info in current_voices_data:
        voice_langs_lower = [
            str(lang).lower() for lang in voice_info.get("languages", [])
        ]
        if (
            target_lang_lower in voice_langs_lower
            or target_lang_prefix in voice_langs_lower
        ):
            try:
                engine.setProperty("voice", voice_info["id"])
                logger.info(
                    "Set pyttsx3 voice by language property match for '%s': %s (ID: %s)",
                    language_code,
                    voice_info.get("name", "N/A"),
                    voice_info["id"],
                )
                return True
            except (
                RuntimeError,
                ValueError,
                TypeError,
            ) as e_set_lang:
                logger.warning(
                    "Failed to set voice by language property for %s: %s",
                    voice_info.get("name", "N/A"),
                    e_set_lang,
                )

    for voice_info in current_voices_data:
        voice_name_lower = voice_info.get("name", "").lower()
        found_by_heuristic = False
        if target_lang_prefix == "id" and "indonesia" in voice_name_lower:
            found_by_heuristic = True
        elif target_lang_prefix == "en" and (
            "zira" in voice_name_lower
            or "david" in voice_name_lower
            or "mark" in voice_name_lower
        ):
            found_by_heuristic = True

        if found_by_heuristic:
            try:
                engine.setProperty("voice", voice_info["id"])
                logger.info(
                    "Set pyttsx3 voice by name heuristic for '%s': %s",
                    language_code,
                    voice_info["name"],
                )
                return True
            except (
                RuntimeError,
                ValueError,
                TypeError,
            ):
                pass

    logger.warning(
        "No suitable pyttsx3 voice found for language '%s'. pyttsx3 will use its default.",
        language_code,
    )
    return False


def speak_text_sync(
    text: str,
    language_code: str = "id",
    rate: Optional[int] = None,
    volume: Optional[float] = None,
):
    """
    Menggunakan pyttsx3 untuk mengucapkan teks yang diberikan. Ini adalah fungsi SINKRON/BLOCKING.
    Menginisialisasi engine baru setiap kali dipanggil untuk stabilitas.
    """
    logger.debug("speak_text_sync called for text: '%s...'", text[:30])
    engine = None
    try:
        engine = pyttsx3.init()
        if engine is None:
            logger.error("pyttsx3.init() returned None. Cannot speak.")
            return
        logger.debug("pyttsx3 engine initialized for speak_text_sync.")
    except RuntimeError as re_init:
        logger.error(
            "RuntimeError initializing pyttsx3 engine: %s", re_init, exc_info=True
        )
        return
    except Exception as e_init:
        logger.error("Failed to initialize pyttsx3 engine: %s", e_init, exc_info=True)
        return

    actual_rate = rate if rate is not None else PYTTSX3_DEFAULT_RATE
    actual_volume = volume if volume is not None else PYTTSX3_DEFAULT_VOLUME

    logger.info(
        "pyttsx3 speaking (sync): '%s...' (Lang: %s, Rate: %d, Vol: %.2f)",
        text[:50],
        language_code,
        actual_rate,
        actual_volume,
    )

    try:
        _set_voice_on_engine(engine, language_code)
        engine.setProperty("rate", actual_rate)
        engine.setProperty("volume", actual_volume)

        engine.say(text)
        engine.runAndWait()
        logger.debug("pyttsx3 runAndWait() completed.")

    except RuntimeError as re_speak:
        logger.error("RuntimeError during pyttsx3 speech: %s", re_speak, exc_info=True)
    except Exception as e_speak:
        logger.error("Error during pyttsx3 speech: %s", e_speak, exc_info=True)


if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        )

    logger.info("--- Default TTS (pyttsx3) Test (Sync Functions) ---")

    logger.info("Available pyttsx3 Voices (will populate cache if not already):")
    voices = list_available_voices()
    if voices:
        for i, v_info in enumerate(voices):
            logger.info(
                "  Voice %d: ID=%s, Name=%s, Langs=%s, Gender=%s",
                i,
                v_info.get("id", "N/A"),
                v_info.get("name", "N/A"),
                v_info.get("languages", []),
                v_info.get("gender", "N/A"),
            )
    else:
        logger.info(
            "  No voices found or engine could not be initialized for voice listing."
        )

    logger.info("Testing speak_text_sync (Indonesia)...")
    speak_text_sync(
        "Halo, ini adalah tes suara dari pyttsx3 menggunakan bahasa Indonesia.",
        language_code="id",
    )

    logger.info("Jeda 0.5 detik sebelum tes berikutnya...")
    time.sleep(0.5)

    logger.info("Testing speak_text_sync (English)...")
    speak_text_sync(
        "Hello, this is a test voice from pyttsx3 using English.", language_code="en"
    )

    logger.info("Testing speak_text_sync (English US)...")
    speak_text_sync("This is a test for US English.", language_code="en-US")

    logger.info("Testing speak_text_sync (NonExistent Lang 'xx-XX')...")
    speak_text_sync("This should use default voice.", language_code="xx-XX")

    logger.info("All sync tests finished.")
