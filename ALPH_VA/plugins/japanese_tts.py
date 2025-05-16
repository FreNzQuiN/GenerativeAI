# plugins/japanese_tts.py

import asyncio, os
from core import config_manager # Menggunakan ConfigManager
import plugins.voicevox_api as voicevox_plugin # Mengimpor modul voicevox_api yang sudah dimodifikasi
import logging

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

# --- Baca Konfigurasi (jika ada yang spesifik untuk japanese_tts selain yang di voicevox_api) ---
DEFAULT_JAPANESE_SPEAKER_ID = config_manager.get_int("tts_settings", "japanese_default_speaker_id", None)
# Jika None, maka akan menggunakan default dari voicevox_api (yang juga dari config)

async def speak_japanese(text: str, speaker_id: int = None) -> bool:
    """
    Uses the Voicevox API (via voicevox_plugin) for Japanese text-to-speech.

    Args:
        text (str): The text to speak.
        speaker_id (int, optional): Specific Voicevox speaker ID. 
                                    If None, uses default from config 
                                    (either japanese_default_speaker_id or voicevox_speaker_id).

    Returns:
        bool: True if speech was likely generated and played, False otherwise.
    """
    # Tentukan speaker ID yang akan digunakan:
    # 1. Gunakan speaker_id yang diberikan jika ada.
    # 2. Jika tidak, gunakan DEFAULT_JAPANESE_SPEAKER_ID dari config jika ada.
    # 3. Jika tidak ada juga, voicevox_plugin.generate_speech akan menggunakan defaultnya sendiri.
    actual_speaker_id = speaker_id
    if actual_speaker_id is None and DEFAULT_JAPANESE_SPEAKER_ID is not None:
        actual_speaker_id = DEFAULT_JAPANESE_SPEAKER_ID
    
    # Jika actual_speaker_id masih None, voicevox_plugin.generate_speech akan menggunakan defaultnya.

    logger.info(f"Requesting Japanese TTS via Voicevox for text: '{text[:50]}...' (Speaker ID: {actual_speaker_id if actual_speaker_id is not None else 'plugin_default'})")
    try:
        # voicevox_plugin.generate_speech sekarang mengembalikan path file atau None
        generated_file_path = await voicevox_plugin.generate_speech(text, speaker_id=actual_speaker_id)
        if generated_file_path:
            logger.info(f"Japanese speech successfully handled by Voicevox plugin. Audio: {generated_file_path}")
            return True
        else:
            logger.error("Voicevox plugin failed to generate/play Japanese speech.")
            return False
    except Exception as e:
        logger.error(f"Error during Japanese TTS (delegating to Voicevox): {e}", exc_info=True)
        return False

async def main_test_japanese(): # Mengganti nama
    logger.info("--- Japanese TTS Plugin Test ---")
    
    logger.info("Testing speak_japanese with plugin default speaker...")
    success1 = await speak_japanese("こんにちは、元気ですか？")
    logger.info(f"Test 1 success: {success1}")

    logger.info("\nTesting speak_japanese with overridden speaker ID (e.g., 2)...")
    # Pastikan speaker ID 2 ada di instalasi Voicevox Anda
    # Jika Anda ingin menggunakan japanese_default_speaker_id, set di config.ini:
    # [tts_settings]
    # japanese_default_speaker_id = 1 ; contoh
    success2 = await speak_japanese("別のスピーカーでのテスト。", speaker_id=2) 
    logger.info(f"Test 2 success: {success2}")

if __name__ == '__main__':
    # Pastikan config.ini ada dan bisa dibaca
    # Tambahkan entri berikut ke config.ini jika belum ada:
    # [tts_settings]
    # japanese_default_speaker_id = 1 ; (Opsional, jika ingin default berbeda untuk modul ini)
    # voicevox_speaker_id = 3         ; (Default untuk Voicevox jika tidak ada override)

    # Setup basic logging jika modul dijalankan sendiri
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    try:
        asyncio.run(main_test_japanese())
    except ImportError:
        logger.error("ImportError. Ensure 'plugins.voicevox_api' is accessible and Voicevox client library is installed.", exc_info=True)
    except Exception as e:
        logger.error(f"An error occurred during test speak_japanese: {e}", exc_info=True)