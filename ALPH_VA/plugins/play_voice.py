# plugins/play_voice.py
import winsound
import os
import platform
from core.config_manager import ConfigManager
import logging
import time

try:
    _cfg = ConfigManager()
except Exception as e_cfg_init_pv:
    print(
        f"CRITICAL ERROR in play_voice.py: Failed to initialize ConfigManager: {e_cfg_init_pv}"
    )
    raise RuntimeError(
        f"PlayVoice: ConfigManager initialization failed: {e_cfg_init_pv}"
    ) from e_cfg_init_pv

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        _log_dir_pv = _cfg.get_config_value(
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
        if not os.path.exists(_log_dir_pv):
            os.makedirs(_log_dir_pv, exist_ok=True)
        log_file_path = os.path.join(
            _log_dir_pv, f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
        )
    except Exception as e_log_path_pv:
        logger.error(
            "Error determining log_file_path for play_voice: %s. Using fallback.",
            e_log_path_pv,
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
    except OSError as e_fh_pv:
        logger.error(
            "OSError setting up file handler for play_voice: %s. Using basicConfig.",
            e_fh_pv,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    except Exception as e_log_pv:
        logger.error(
            "Unexpected error setting up logger for play_voice: %s. Using basicConfig.",
            e_log_pv,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

_project_root_pv = _cfg.get_config_value(
    "general",
    "project_root_dir",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
BASE_AUDIO_OUTPUT_PATH_CONFIG = _cfg.get_config_value(
    "general", "audio_output_path", "data/audio/"
)
DEFAULT_AUDIO_PATH = (
    os.path.join(_project_root_pv, BASE_AUDIO_OUTPUT_PATH_CONFIG)
    if not os.path.isabs(BASE_AUDIO_OUTPUT_PATH_CONFIG)
    else BASE_AUDIO_OUTPUT_PATH_CONFIG
)

if not os.path.exists(DEFAULT_AUDIO_PATH):
    try:
        os.makedirs(DEFAULT_AUDIO_PATH, exist_ok=True)
        logger.info("Created default audio output directory: %s", DEFAULT_AUDIO_PATH)
    except OSError as e:
        logger.error(
            "Failed to create default audio output directory %s: %s",
            DEFAULT_AUDIO_PATH,
            e,
            exc_info=True,
        )


def play_audio_file(file_path: str, block_until_done: bool = True):
    if platform.system() != "Windows":
        logger.error(
            "winsound.PlaySound is only available on Windows. Cannot play audio: %s",
            file_path,
        )
        return
    try:
        normalized_file_path = os.path.normpath(file_path)
        logger.info(
            "Attempting to play audio file: %s (Blocking: %s)",
            normalized_file_path,
            block_until_done,
        )
        if not os.path.exists(normalized_file_path):
            logger.error("Audio file not found: %s", normalized_file_path)
            return

        flags = winsound.SND_FILENAME
        if not block_until_done:
            flags |= winsound.SND_ASYNC

        winsound.PlaySound(normalized_file_path, flags)

        if block_until_done:
            logger.info("Playback finished for: %s", normalized_file_path)
        else:
            logger.info("Playback started asynchronously for: %s", normalized_file_path)
    except TypeError as te:
        logger.error(
            "TypeError during audio playback for path '%s': %s. Ensure path is a valid string.",
            file_path,
            te,
        )
    except RuntimeError as re:
        logger.error(
            "RuntimeError playing audio file '%s': %s", file_path, re, exc_info=True
        )
    except Exception as e:
        logger.error(
            "Unexpected error playing audio file '%s': %s", file_path, e, exc_info=True
        )


def play_audio_in_default_dir(
    filename: str, sub_directory: str | None = None, block_until_done: bool = True
):
    play_path = DEFAULT_AUDIO_PATH
    if sub_directory:
        normalized_sub_dir = os.path.normpath(sub_directory)
        play_path = os.path.join(DEFAULT_AUDIO_PATH, normalized_sub_dir)
        if not os.path.exists(play_path):
            logger.error(
                "Subdirectory '%s' not found in '%s'. Cannot play file '%s'.",
                normalized_sub_dir,
                DEFAULT_AUDIO_PATH,
                filename,
            )
            return
    full_file_path = os.path.normpath(os.path.join(play_path, filename))
    play_audio_file(full_file_path, block_until_done=block_until_done)


if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        )
    logger.info("--- Play Voice Test ---")
    dummy_filename = "test_audio_play.wav"
    dummy_file_full_path = os.path.join(DEFAULT_AUDIO_PATH, dummy_filename)
    if not os.path.exists(dummy_file_full_path):
        logger.warning(
            "Dummy audio file '%s' not found. Creating a simple sine wave for testing.",
            dummy_file_full_path,
        )
        try:
            import wave, math, struct

            sample_rate = 44100
            duration_s = 1
            freq_hz = 440
            amplitude = 0.5
            n_samples = int(sample_rate * duration_s)
            max_amplitude = 32767  # For 16-bit audio
            with wave.open(dummy_file_full_path, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                for i in range(n_samples):
                    value = int(
                        max_amplitude
                        * amplitude
                        * math.sin(2 * math.pi * freq_hz * i / sample_rate)
                    )
                    wf.writeframes(struct.pack("<h", value))
            logger.info("Created dummy WAV file: %s", dummy_file_full_path)
        except Exception as e_create_dummy:
            logger.error(
                "Failed to create dummy WAV file for testing: %s", e_create_dummy
            )

    if os.path.exists(dummy_file_full_path):
        logger.info(
            "Testing play_audio_in_default_dir (blocking) with: %s", dummy_filename
        )
        play_audio_in_default_dir(dummy_filename, block_until_done=True)
        logger.info("Blocking playback test finished.")
        time.sleep(1)
        logger.info(
            "Testing play_audio_in_default_dir (async) with: %s", dummy_filename
        )
        play_audio_in_default_dir(dummy_filename, block_until_done=False)
        logger.info("Async playback test started. Script will continue...")
        if platform.system() == "Windows":
            logger.info("Waiting 2s for async audio to play... then purging.")
            time.sleep(2)
            winsound.PlaySound(None, winsound.SND_PURGE)
            logger.info("Async sound (if any) purged.")
    else:
        logger.warning(
            "Dummy audio file '%s' not found and could not be created. Skipping playback test.",
            dummy_file_full_path,
        )
