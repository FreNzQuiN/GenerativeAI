# plugins/voicevox_api.py

import asyncio
import time
import os
from voicevox import Client # Pastikan library voicevox-client terinstal
import plugins.play_voice as play_voice # Mengganti nama agar lebih jelas
from core import config_manager # Menggunakan ConfigManager yang sudah kita buat
import logging

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

# --- Baca Konfigurasi ---
# Path dasar untuk output audio dari config general
# Kita akan membuat subdirektori 'voicevox' di dalamnya jika belum ada
BASE_AUDIO_OUTPUT_PATH_CONFIG = config_manager.get_config_value("general", "audio_output_path", "data/audio/")
# Pastikan path ini absolut atau relatif terhadap project root
if not os.path.isabs(BASE_AUDIO_OUTPUT_PATH_CONFIG):
    BASE_AUDIO_OUTPUT_PATH = os.path.join(config_manager.PROJECT_ROOT_DIR, BASE_AUDIO_OUTPUT_PATH_CONFIG)
else:
    BASE_AUDIO_OUTPUT_PATH = BASE_AUDIO_OUTPUT_PATH_CONFIG

# Subdirektori spesifik untuk Voicevox agar tidak tercampur dengan TTS lain
VOICEVOX_AUDIO_DIR = os.path.join(BASE_AUDIO_OUTPUT_PATH, "voicevox")
if not os.path.exists(VOICEVOX_AUDIO_DIR):
    try:
        os.makedirs(VOICEVOX_AUDIO_DIR)
        logger.info(f"Created Voicevox audio output directory: {VOICEVOX_AUDIO_DIR}")
    except Exception as e:
        logger.error(f"Failed to create Voicevox audio output directory {VOICEVOX_AUDIO_DIR}: {e}")
        # Fallback ke base audio path jika gagal membuat subdirektori
        VOICEVOX_AUDIO_DIR = BASE_AUDIO_OUTPUT_PATH


# Default speaker ID dari config tts_settings
DEFAULT_SPEAKER_ID = config_manager.get_int("tts_settings", "voicevox_speaker_id", 3) # Default ke 3 jika tidak ada

# Voicevox Host and Port (jika perlu dikonfigurasi)
VOICEVOX_HOST = config_manager.get_config_value("tts_voicevox_specifics", "host", "127.0.0.1") # Contoh
VOICEVOX_PORT = config_manager.get_int("tts_voicevox_specifics", "port", 50021)       # Contoh

async def generate_speech(text: str, speaker_id: int = None) -> str | None:
    """
    Generates speech using Voicevox API and saves it to a file.
    Plays the generated audio.

    Args:
        text (str): The text to synthesize.
        speaker_id (int, optional): The Voicevox speaker ID. 
                                    Defaults to DEFAULT_SPEAKER_ID from config.

    Returns:
        str | None: The full path to the generated audio file if successful, else None.
    """
    actual_speaker_id = speaker_id if speaker_id is not None else DEFAULT_SPEAKER_ID
    
    # Buat nama file unik
    timestamp = str(int(time.time()))
    audio_filename = f"voicevox_{timestamp}_spk{actual_speaker_id}.wav"
    full_audio_path = os.path.join(VOICEVOX_AUDIO_DIR, audio_filename)

    logger.info(f"Attempting to generate speech for text: '{text[:50]}...' with speaker ID: {actual_speaker_id}")
    
    try:
        # Menggunakan host dan port dari config jika library Client mendukungnya
        # Periksa dokumentasi voicevox-client Anda untuk cara set base_url
        # Jika Client() tidak menerima base_url, Anda mungkin perlu set env var VOICEVOX_BASE_URL
        # atau library akan menggunakan defaultnya.
        # Untuk sekarang, kita asumsikan Client() akan menemukan engine Voicevox yang berjalan.
        # Jika voicevox-client versi baru, mungkin: client = Client(base_url=f"http://{VOICEVOX_HOST}:{VOICEVOX_PORT}")
        async with Client() as client: # Anda mungkin perlu Client(base_url=f"http://{VOICEVOX_HOST}:{VOICEVOX_PORT}")
            logger.debug("Voicevox client initialized.")
            audio_query = await client.create_audio_query(text=text, speaker=actual_speaker_id)
            logger.debug(f"Audio query created for speaker {actual_speaker_id}.")
            
            audio_data = await audio_query.synthesis(speaker=actual_speaker_id)
            logger.debug("Speech synthesis complete.")

            with open(full_audio_path, "wb") as f:
                f.write(audio_data)
            logger.info(f"Generated audio file saved to: {full_audio_path}")
        play_blocking = config_manager.get_bool("tts_settings", "voicevox_play_blocking", True)
        play_voice.play_audio_file(full_audio_path, block_until_done=play_blocking)
        
        return full_audio_path
    except ConnectionRefusedError:
        logger.error(f"Connection refused. Ensure Voicevox engine is running and accessible at expected host/port.")
        return None
    except Exception as e:
        logger.error(f"Error during Voicevox speech generation or playback: {e}", exc_info=True)
        return None

def remove_all_voicevox_outputs():
    """Removes all .wav files from the Voicevox audio output directory."""
    removed_count = 0
    if not os.path.exists(VOICEVOX_AUDIO_DIR):
        logger.warning(f"Voicevox audio directory not found, cannot remove files: {VOICEVOX_AUDIO_DIR}")
        return
        
    try:
        for filename in os.listdir(VOICEVOX_AUDIO_DIR):
            if filename.endswith(".wav"): # Hanya hapus file wav
                file_path_to_remove = os.path.join(VOICEVOX_AUDIO_DIR, filename)
                try:
                    os.remove(file_path_to_remove)
                    logger.info(f"Removed audio file: {file_path_to_remove}")
                    removed_count += 1
                except Exception as e_remove:
                    logger.error(f"Failed to remove file {file_path_to_remove}: {e_remove}")
        if removed_count > 0:
            logger.info(f"Successfully removed {removed_count} .wav files from {VOICEVOX_AUDIO_DIR}.")
        else:
            logger.info(f"No .wav files found to remove in {VOICEVOX_AUDIO_DIR}.")
    except Exception as e_list:
        logger.error(f"Error listing files in {VOICEVOX_AUDIO_DIR} for removal: {e_list}")

async def main_test(): # Mengganti nama agar tidak konflik dengan 'main' di aplikasi utama
    text_to_speak = "うん、元気だよ。君は？"
    logger.info(f"--- Voicevox API Test ---")
    logger.info(f"Text to speak: {text_to_speak}")
    
    generated_file = await generate_speech(text_to_speak) # Akan menggunakan speaker default dari config
    
    if generated_file:
        logger.info(f"Test speech generated and played: {generated_file}")
    else:
        logger.error("Test speech generation failed.")
    
    # Contoh menghapus output setelah tes (opsional)
    # remove_all_voicevox_outputs()


if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    try:
        asyncio.run(main_test())
    except Exception as e:
        logger.error(f"Error running Voicevox API main_test: {e[:50]}", exc_info=True)