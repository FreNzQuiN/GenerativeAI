# plugins/voicevox_api.py
import asyncio
import time
import os
from voicevox import Client as VoicevoxClient  # Menggunakan alias untuk Client
from voicevox.errors import VoicevoxError  # Menangkap error spesifik Voicevox
import plugins.play_voice as play_voice
from core.config_manager import ConfigManager
import logging

try:
    _cfg = ConfigManager()
except Exception as e_cfg_init_vv:
    print(
        f"CRITICAL ERROR in voicevox_api.py: Failed to initialize ConfigManager: {e_cfg_init_vv}"
    )
    raise RuntimeError(
        f"VoicevoxAPI: ConfigManager initialization failed: {e_cfg_init_vv}"
    ) from e_cfg_init_vv

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        _log_dir_vv = _cfg.get_config_value(
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
        if not os.path.exists(_log_dir_vv):
            os.makedirs(_log_dir_vv, exist_ok=True)
        log_file_path = os.path.join(
            _log_dir_vv, f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
        )
    except Exception as e_log_path_vv:
        logger.error(
            "Error determining log_file_path for voicevox_api: %s. Using fallback.",
            e_log_path_vv,
            exc_info=False,
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
    except OSError as e_fh_vv:
        logger.error(
            "OSError setting up file handler for voicevox_api: %s. Using basicConfig.",
            e_fh_vv,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    except Exception as e_log_vv:
        logger.error(
            "Unexpected error setting up logger for voicevox_api: %s. Using basicConfig.",
            e_log_vv,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

_project_root_vv = _cfg.get_config_value(
    "general",
    "project_root_dir",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
BASE_AUDIO_OUTPUT_PATH_CONFIG = _cfg.get_config_value(
    "general", "audio_output_path", "data/audio/"
)
_base_audio_path = (
    os.path.join(_project_root_vv, BASE_AUDIO_OUTPUT_PATH_CONFIG)
    if not os.path.isabs(BASE_AUDIO_OUTPUT_PATH_CONFIG)
    else BASE_AUDIO_OUTPUT_PATH_CONFIG
)
VOICEVOX_AUDIO_DIR = os.path.join(_base_audio_path, "voicevox")

if not os.path.exists(VOICEVOX_AUDIO_DIR):
    try:
        os.makedirs(VOICEVOX_AUDIO_DIR, exist_ok=True)
        logger.info("Created Voicevox audio output directory: %s", VOICEVOX_AUDIO_DIR)
    except OSError as e:
        logger.error(
            "Failed to create Voicevox audio output directory %s: %s",
            VOICEVOX_AUDIO_DIR,
            e,
            exc_info=True,
        )
        VOICEVOX_AUDIO_DIR = (
            _base_audio_path  # Fallback ke base path jika subdirektori gagal dibuat
        )

DEFAULT_SPEAKER_ID = _cfg.get_int("tts_settings", "voicevox_speaker_id", 3)
VOICEVOX_HOST = _cfg.get_config_value("tts_voicevox_specifics", "host", "127.0.0.1")
VOICEVOX_PORT = _cfg.get_int("tts_voicevox_specifics", "port", 50021)
VOICEVOX_BASE_URL = f"http://{VOICEVOX_HOST}:{VOICEVOX_PORT}"


async def generate_speech(text: str, speaker_id: int | None = None) -> str | None:
    actual_speaker_id = speaker_id if speaker_id is not None else DEFAULT_SPEAKER_ID
    timestamp = str(int(time.time()))
    audio_filename = f"voicevox_{timestamp}_spk{actual_speaker_id}.wav"
    full_audio_path = os.path.join(VOICEVOX_AUDIO_DIR, audio_filename)

    logger.info(
        "Attempting Voicevox speech: '%s...' (Speaker: %d)",
        text[:50],
        actual_speaker_id,
    )

    try:
        async with VoicevoxClient(base_url=VOICEVOX_BASE_URL) as client:
            logger.debug("Voicevox client connected to %s", VOICEVOX_BASE_URL)
            audio_query = await client.create_audio_query(
                text=text, speaker=actual_speaker_id
            )
            logger.debug("Audio query created for speaker %d.", actual_speaker_id)
            audio_data = await audio_query.synthesis(speaker=actual_speaker_id)
            logger.debug("Speech synthesis complete.")

            with open(full_audio_path, "wb") as f:
                f.write(audio_data)
            logger.info("Generated audio file saved: %s", full_audio_path)

        play_blocking = _cfg.get_bool("tts_settings", "voicevox_play_blocking", True)
        play_voice.play_audio_file(full_audio_path, block_until_done=play_blocking)
        return full_audio_path
    except ConnectionRefusedError as e_conn:
        logger.error(
            "Connection refused for Voicevox at %s. Ensure Voicevox engine is running: %s",
            VOICEVOX_BASE_URL,
            e_conn,
        )
        return None
    except VoicevoxError as e_vv_sdk:  # Error spesifik dari SDK Voicevox
        logger.error("Voicevox SDK error: %s", e_vv_sdk, exc_info=True)
        return None
    except OSError as e_os:  # Error saat menulis file
        logger.error(
            "OSError during Voicevox speech generation (file write?): %s",
            e_os,
            exc_info=True,
        )
        return None
    except Exception as e:  # Tangkap error tak terduga lainnya
        logger.error(
            "Unexpected error in Voicevox speech generation/playback: %s",
            e,
            exc_info=True,
        )
        return None


def remove_all_voicevox_outputs():
    removed_count = 0
    if not os.path.isdir(VOICEVOX_AUDIO_DIR):  # Cek jika direktori, bukan hanya exists
        logger.warning(
            "Voicevox audio directory not found or not a directory, cannot remove files: %s",
            VOICEVOX_AUDIO_DIR,
        )
        return
    try:
        for filename in os.listdir(VOICEVOX_AUDIO_DIR):
            if filename.lower().endswith(".wav"):  # Case-insensitive check
                file_path_to_remove = os.path.join(VOICEVOX_AUDIO_DIR, filename)
                try:
                    os.remove(file_path_to_remove)
                    logger.debug("Removed audio file: %s", file_path_to_remove)
                    removed_count += 1
                except OSError as e_remove:
                    logger.error(
                        "Failed to remove file %s: %s", file_path_to_remove, e_remove
                    )
        if removed_count > 0:
            logger.info(
                "Successfully removed %d .wav files from %s.",
                removed_count,
                VOICEVOX_AUDIO_DIR,
            )
        else:
            logger.info("No .wav files found to remove in %s.", VOICEVOX_AUDIO_DIR)
    except OSError as e_list:
        logger.error(
            "Error listing files in %s for removal: %s",
            VOICEVOX_AUDIO_DIR,
            e_list,
            exc_info=True,
        )


async def main_test():
    text_to_speak = "こんにちは、これはボイスボックスのテストです。"
    logger.info("--- Voicevox API Test ---")
    logger.info("Text to speak: %s", text_to_speak)
    generated_file = await generate_speech(text_to_speak, speaker_id=DEFAULT_SPEAKER_ID)
    if generated_file:
        logger.info("Test speech generated and likely played: %s", generated_file)
    else:
        logger.error("Test speech generation failed.")

    logger.info("Attempting to remove generated audio files...")
    remove_all_voicevox_outputs()


if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        )
    try:
        asyncio.run(main_test())
    except RuntimeError as e_rt:  # Misalnya jika Voicevox Client tidak bisa dibuat
        logger.error(
            "RuntimeError running Voicevox API main_test: %s", e_rt, exc_info=True
        )
    except Exception as e:  # Tangkap error tak terduga lainnya
        logger.error(
            "Unexpected error running Voicevox API main_test: %s", e, exc_info=True
        )
