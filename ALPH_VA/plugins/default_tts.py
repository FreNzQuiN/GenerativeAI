# core/default_tts.py

import pyttsx3
from core import config_manager
import logging
from typing import Optional, List, Dict
import os, time

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)


def _initialize_engine_and_get_voices() -> tuple[Optional[pyttsx3.Engine], List[Dict]]:
    """Helper untuk inisialisasi engine dan mendapatkan daftar suara. Dijalankan di thread yang sama."""
    local_engine = None
    voices_list = []
    try:
        local_engine = pyttsx3.init()
        if local_engine is None:
            logger.error("pyttsx3.init() returned None. Engine not available.")
            return None, []
        
        voices = local_engine.getProperty('voices')
        for i, voice in enumerate(voices):
            voice_detail = {
                "id": voice.id, "name": voice.name,
                "languages": voice.languages, "gender": voice.gender, "age": voice.age
            }
            try:
                voice_detail["languages"] = [lang.decode('utf-8', errors='replace') if isinstance(lang, bytes) else lang for lang in voice.languages]
                if isinstance(voice.gender, bytes):
                    voice_detail["gender"] = voice.gender.decode('utf-8', errors='replace')
            except Exception as e_decode:
                logger.debug(f"Could not decode all properties for voice {i}: {e_decode}")
            voices_list.append(voice_detail)
        logger.debug(f"Engine initialized in helper, found {len(voices_list)} voices.")
        return local_engine, voices_list
    except Exception as e:
        logger.error(f"Failed to initialize pyttsx3 engine or get voices in helper: {e}", exc_info=True)
        if local_engine:
            try:
                local_engine.stop()
            except: pass
        return None, []


def list_available_voices() -> list:
    """Lists available pyttsx3 voices. Inisialisasi engine sementara untuk ini."""
    _, voices = _initialize_engine_and_get_voices()
    return voices

def _set_voice_on_engine(engine_instance, language_code: str = "id") -> bool:
    """Mencoba menyetel suara pada instance engine yang diberikan."""
    if engine_instance is None: return False
    
    logger.debug(f"Attempting to set voice for language: {language_code} on provided engine.")
    try:
        voices_objects = engine_instance.getProperty('voices') 
        available_voices_data = []
        for v_obj in voices_objects:
            vd = {"id": v_obj.id, "name": v_obj.name, "languages": v_obj.languages, "gender": v_obj.gender, "age": v_obj.age}
            try:
                vd["languages"] = [lang.decode('utf-8', errors='replace') if isinstance(lang, bytes) else lang for lang in v_obj.languages]
                if isinstance(v_obj.gender, bytes): vd["gender"] = v_obj.gender.decode('utf-8', errors='replace')
            except: pass
            available_voices_data.append(vd)
    except Exception as e_get_voices:
        logger.error(f"Could not get voices from provided engine instance: {e_get_voices}")
        return False

    config_voice_id_key = f"voice_id_{language_code.lower()}"
    voice_id_from_config = config_manager.get_config_value("tts_pyttsx3_specifics", config_voice_id_key)

    if voice_id_from_config:
        try:
            engine_instance.setProperty('voice', voice_id_from_config)
            logger.info(f"Set pyttsx3 voice using config ID for '{language_code}': {voice_id_from_config}")
            return True
        except Exception as e_set_id:
            logger.warning(f"Failed to set voice using config ID '{voice_id_from_config}': {e_set_id}. Will try other methods.")

    for voice_info in available_voices_data:
        if language_code.lower() in [lang.lower() for lang in voice_info.get("languages", [])]:
            try:
                engine_instance.setProperty('voice', voice_info["id"])
                logger.info(f"Set pyttsx3 voice by language property match for '{language_code}': {voice_info['name']}")
                return True
            except Exception as e_set_lang:
                 logger.warning(f"Failed to set voice by language property for {voice_info['name']}: {e_set_lang}")
    
    for voice_info in available_voices_data:
        voice_name_lower = voice_info.get("name", "").lower()
        if language_code.lower() == "id" and "indonesia" in voice_name_lower:
            try:
                engine_instance.setProperty('voice', voice_info["id"])
                logger.info(f"Set pyttsx3 voice by name heuristic for '{language_code}': {voice_info['name']}")
                return True
            except: pass
        elif language_code.lower() == "en" and ("zira" in voice_name_lower or "david" in voice_name_lower):
            try:
                engine_instance.setProperty('voice', voice_info["id"])
                logger.info(f"Set pyttsx3 voice by name heuristic for '{language_code}': {voice_info['name']}")
                return True
            except: pass
    logger.warning(f"No suitable pyttsx3 voice explicitly found for language '{language_code}'. pyttsx3 will use its default voice.")
    return False


def speak_default(text: str, language_code: str = "id", rate: Optional[int] = None, volume: Optional[float] = None):
    """Uses pyttsx3 to speak the given text. Initializes engine per call for thread safety."""
    local_engine = None
    try:
        local_engine = pyttsx3.init()
        if local_engine is None:
            logger.error("pyttsx3.init() returned None in speak_default. Engine not available.")
            return
        logger.debug("pyttsx3 engine initialized for speak_default call.")
    except Exception as e_init:
        logger.error(f"pyttsx3 engine failed to initialize in speak_default: {e_init}", exc_info=True)
        return

    actual_rate = rate if rate is not None else config_manager.get_int("tts_settings", "pyttsx3_rate", 150)
    actual_volume = volume if volume is not None else config_manager.get_float("tts_settings", "pyttsx3_volume", 1.0)

    logger.info(f"pyttsx3 speaking: '{text[:50]}...' (Lang: {language_code}, Rate: {actual_rate}, Vol: {actual_volume})")

    try:
        _set_voice_on_engine(local_engine, language_code) 
        
        local_engine.setProperty('rate', actual_rate)
        local_engine.setProperty('volume', actual_volume)
        
        local_engine.say(text)
        local_engine.runAndWait()
        logger.debug("pyttsx3 runAndWait() completed.")
    except RuntimeError as re:
        logger.error(f"RuntimeError during pyttsx3 speech: {re}", exc_info=True)
    except Exception as e:
        logger.error(f"Error during pyttsx3 speech: {e}", exc_info=True)
    finally:
        # Meskipun runAndWait() seharusnya membersihkan, tidak ada salahnya mencoba stop
        # Ini mungkin tidak selalu diperlukan atau bahkan tidak ada di semua driver pyttsx3
        if local_engine:
            try:
                # local_engine.stop() # Hati-hati, stop() bisa menghentikan loop event yang sedang berjalan
                # Untuk pyttsx3, runAndWait() adalah cara utama untuk memastikan semua selesai.
                # Tidak ada metode 'shutdown' atau 'del' yang eksplisit dan aman untuk instance engine.
                # Biarkan instance engine lokal ini di-garbage collect.
                pass
            except Exception as e_stop:
                logger.debug(f"Exception while trying to stop local_engine (ignoring): {e_stop}")


if __name__ == '__main__':
    # ... (Blok __main__ Anda bisa tetap sama, tapi sekarang list_available_voices
    #      dan speak_default akan menginisialisasi engine mereka sendiri secara internal) ...
    if not logging.getLogger().hasHandlers() and not logger.hasHandlers():
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("--- Default TTS (pyttsx3) Test ---")

    logger.info("Available pyttsx3 Voices (engine will be init/stopped for this):")
    voices_data = list_available_voices() # Ganti nama variabel
    if voices_data:
        for i, voice_info_item in enumerate(voices_data):
            logger.info(f"  Voice {i}: {voice_info_item}")
    else:
        logger.info("  No voices found or engine not initialized.")
    logger.info("-" * 20)
    
    logger.info("Testing speak_default with config values (Indonesia)...")
    speak_default("Halo, ini adalah tes suara dari pyttsx3 menggunakan bahasa Indonesia.", language_code="id")
    
    time.sleep(0.5) 

    logger.info("\nTesting speak_default with config values (English)...")
    speak_default("Hello, this is a test voice from pyttsx3 using English.", language_code="en")
