# plugins/play_voice.py

import winsound  # Khusus untuk Windows
import os
import platform  # Untuk memeriksa sistem operasi
from core import config_manager
import logging
import time # Diperlukan untuk time.sleep jika kita ingin menunggu audio selesai

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

# --- Baca Konfigurasi Path Audio ---
BASE_AUDIO_OUTPUT_PATH_CONFIG = config_manager.get_config_value("general", "audio_output_path", "data/audio/")
if not os.path.isabs(BASE_AUDIO_OUTPUT_PATH_CONFIG):
    DEFAULT_AUDIO_PATH = os.path.join(config_manager.PROJECT_ROOT_DIR, BASE_AUDIO_OUTPUT_PATH_CONFIG)
else:
    DEFAULT_AUDIO_PATH = BASE_AUDIO_OUTPUT_PATH_CONFIG

if not os.path.exists(DEFAULT_AUDIO_PATH):
    try:
        os.makedirs(DEFAULT_AUDIO_PATH)
        logger.info(f"Created default audio output directory: {DEFAULT_AUDIO_PATH}")
    except Exception as e:
        logger.error(f"Failed to create default audio output directory {DEFAULT_AUDIO_PATH}: {e}")

def play_audio_file(file_path: str, block_until_done: bool = True):
    """
    Plays an audio file using winsound (Windows only).
    Normalizes the file path.

    Args:
        file_path (str): The full, absolute path to the audio file.
        block_until_done (bool): If True, waits for the sound to finish playing.
                                 If False, plays asynchronously.
    """
    if platform.system() != "Windows":
        logger.error("winsound.PlaySound is only available on Windows. Cannot play audio.")
        # Implementasi alternatif untuk OS lain bisa ditambahkan di sini.
        return

    try:
        # os.path.normpath akan mengkonversi '/' menjadi '\' di Windows jika perlu,
        # dan menangani path yang tidak standar.
        normalized_file_path = os.path.normpath(file_path)
        logger.info(f"Attempting to play audio file: {normalized_file_path} (Blocking: {block_until_done})")
        
        if not os.path.exists(normalized_file_path):
            logger.error(f"Audio file not found: {normalized_file_path}")
            return

        flags = winsound.SND_FILENAME
        if not block_until_done:
            flags |= winsound.SND_ASYNC
        else:
            # Untuk mode blocking, kita bisa gunakan SND_SYNC atau SND_FILENAME saja (defaultnya blocking)
            # Namun, SND_FILENAME saja sudah cukup untuk blocking.
            # Jika ingin eksplisit, bisa tambahkan winsound.SND_SYNC, tapi hati-hati karena
            # SND_SYNC akan menginterupsi suara lain yang sedang diputar dengan SND_ASYNC.
            # SND_FILENAME tanpa SND_ASYNC adalah cara paling aman untuk blocking.
            pass # SND_FILENAME saja sudah blocking

        winsound.PlaySound(normalized_file_path, flags)
        
        if block_until_done:
            logger.info(f"Playback finished for: {normalized_file_path}")
        else:
            logger.info(f"Playback started asynchronously for: {normalized_file_path}")

    except TypeError as te:
        logger.error(f"TypeError during audio playback for path '{file_path}': {te}. Ensure path is a valid string.")
    except Exception as e:
        logger.error(f"Error playing audio file '{file_path}': {e}", exc_info=True)


def play_audio_in_default_dir(filename: str, sub_directory: str = None, block_until_done: bool = True):
    """
    Plays an audio file located in the default audio output directory,
    optionally within a specified subdirectory.

    Args:
        filename (str): The name of the audio file (e.g., "voice.wav").
        sub_directory (str, optional): Subdirectory within the default audio path.
        block_until_done (bool): If True, waits for the sound to finish playing.
    """
    play_path = DEFAULT_AUDIO_PATH
    if sub_directory:
        # Pastikan sub_directory juga dinormalisasi jika mengandung separator yang salah
        normalized_sub_dir = os.path.normpath(sub_directory)
        play_path = os.path.join(DEFAULT_AUDIO_PATH, normalized_sub_dir)
        
        if not os.path.exists(play_path):
            logger.error(f"Subdirectory '{normalized_sub_dir}' not found in '{DEFAULT_AUDIO_PATH}'. Cannot play file '{filename}'.")
            return
            
    # Gabungkan path dan nama file, lalu normalisasi seluruh path
    full_file_path = os.path.normpath(os.path.join(play_path, filename))
    play_audio_file(full_file_path, block_until_done=block_until_done)


if __name__ == '__main__':
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("--- Play Voice Test ---")

    dummy_filename = "test_audio_play.wav" # Anda perlu file WAV ini di DEFAULT_AUDIO_PATH
    dummy_file_full_path = os.path.join(DEFAULT_AUDIO_PATH, dummy_filename)

    if os.path.exists(dummy_file_full_path):
        logger.info(f"Testing play_audio_in_default_dir (blocking) with: {dummy_filename}")
        play_audio_in_default_dir(dummy_filename, block_until_done=True)
        logger.info("Blocking playback test finished.")

        # Beri jeda sedikit antar tes jika diperlukan
        time.sleep(1)

        logger.info(f"\nTesting play_audio_in_default_dir (async) with: {dummy_filename}")
        play_audio_in_default_dir(dummy_filename, block_until_done=False)
        logger.info("Async playback test started. Script will continue...")
        
        # Jika async, skrip akan langsung lanjut. Untuk melihat efeknya, kita bisa beri delay di sini.
        # Dalam aplikasi nyata, loop utama akan terus berjalan.
        if platform.system() == "Windows":
            logger.info("Waiting for async audio to play for a bit (e.g., 3 seconds in this test)...")
            time.sleep(3) 
            # Untuk menghentikan suara async yang mungkin masih berjalan (jika perlu untuk tes bersih)
            # winsound.PlaySound(None, winsound.SND_PURGE)
            # logger.info("Async sound (if any) purged for test cleanup.")
    else:
        logger.warning(f"Dummy audio file '{dummy_file_full_path}' not found. Skipping playback test.")
        logger.info(f"Please create a valid .wav file named '{dummy_filename}' in '{DEFAULT_AUDIO_PATH}' for testing.")

    # Contoh path dengan backslash (Windows style)
    # Ganti dengan path file WAV Anda yang valid jika ingin menguji ini.
    # example_backslash_path = "D:\\path\\to\\your\\audio.wav" 
    # if os.path.exists(example_backslash_path):
    #    logger.info(f"\nTesting play_audio_file with backslash path (blocking): {example_backslash_path}")
    #    play_audio_file(example_backslash_path, block_until_done=True)
    # else:
    #    logger.warning(f"Backslash path example file not found: {example_backslash_path}")