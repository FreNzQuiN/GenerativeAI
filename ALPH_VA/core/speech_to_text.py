# core/speech_to_text.py
import speech_recognition as sr
from core.config_manager import ConfigManager
import logging
import os
import time
import threading

# --- Global Config Instance ---
try:
    _cfg = ConfigManager()
except Exception as e_cfg_init_stt:
    print(
        f"CRITICAL ERROR in speech_to_text.py: Failed to initialize ConfigManager: {e_cfg_init_stt}"
    )
    raise RuntimeError(
        f"SpeechToText: ConfigManager initialization failed: {e_cfg_init_stt}"
    ) from e_cfg_init_stt

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        _log_dir_stt = _cfg.get_config_value(
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
        if not os.path.exists(_log_dir_stt):
            os.makedirs(_log_dir_stt, exist_ok=True)
        log_file_path = os.path.join(
            _log_dir_stt, f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
        )
    except Exception as e_log_path_stt:
        logger.error(
            "Error determining log_file_path for speech_to_text: %s. Using fallback.",
            e_log_path_stt,
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
    except OSError as e_fh_stt:
        logger.error(
            "OSError setting up file handler for speech_to_text: %s. Using basicConfig.",
            e_fh_stt,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    except Exception as e_log_stt:
        logger.error(
            "Unexpected error setting up logger for speech_to_text: %s. Using basicConfig.",
            e_log_stt,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

DEFAULT_STT_LANGUAGE = _cfg.get_config_value(
    "stt_settings", "default_language", "id-ID"
)
PAUSE_THRESHOLD = _cfg.get_float("stt_settings", "pause_threshold", 1.0)
ENERGY_THRESHOLD_MANUAL = _cfg.get_int("stt_settings", "energy_threshold", 0)
DYNAMIC_ENERGY_THRESHOLD = _cfg.get_bool(
    "stt_settings", "dynamic_energy_threshold", True
)
ADJUST_NOISE_DURATION = _cfg.get_float("stt_settings", "adjust_noise_duration", 1.0)
DEFAULT_PHRASE_TIME_LIMIT = _cfg.get_float("stt_settings", "phrase_time_limit", 0)

_recognizer_instance_module_level: sr.Recognizer | None = None
try:
    _recognizer_instance_module_level = sr.Recognizer()
    _recognizer_instance_module_level.pause_threshold = PAUSE_THRESHOLD
    _recognizer_instance_module_level.dynamic_energy_threshold = (
        DYNAMIC_ENERGY_THRESHOLD
    )
    if ENERGY_THRESHOLD_MANUAL > 0:
        _recognizer_instance_module_level.energy_threshold = ENERGY_THRESHOLD_MANUAL
        _recognizer_instance_module_level.dynamic_energy_threshold = False
        logger.info(
            "Recognizer energy_threshold manually set to: %d (dynamic energy disabled).",
            ENERGY_THRESHOLD_MANUAL,
        )

    logger.info(
        "SpeechRecognition Recognizer initialized. Pause threshold: %.1fs, Dynamic Energy: %s",
        PAUSE_THRESHOLD,
        DYNAMIC_ENERGY_THRESHOLD,
    )
except Exception as e_rec_init:
    logger.critical(
        "Failed to initialize global SpeechRecognition Recognizer: %s",
        e_rec_init,
        exc_info=True,
    )


class SpeechToTextProcessor:
    _microphone_available = False
    _noise_adjusted_globally = False

    def __init__(self, adjust_noise_on_init: bool = True):
        if _recognizer_instance_module_level is None:
            logger.critical(
                "Global Speech Recognizer instance is not available. STT will not work."
            )
            raise RuntimeError(
                "SpeechRecognition Recognizer failed to initialize globally."
            )
        self.recognizer = _recognizer_instance_module_level
        self.microphone: sr.Microphone | None = None

        if not SpeechToTextProcessor._microphone_available:
            try:
                sr.Microphone.list_microphone_names()
                SpeechToTextProcessor._microphone_available = True
                logger.info(
                    "Microphone interface seems available (PyAudio responding)."
                )
            except AttributeError as ae:
                logger.error(
                    "Failed to access microphone interface (sr.Microphone.list_microphone_names failed). PyAudio might be missing or misconfigured: %s",
                    ae,
                    exc_info=False,
                )
                SpeechToTextProcessor._microphone_available = False
            except Exception as e_mic_check:
                logger.error(
                    "Unexpected error checking microphone availability: %s",
                    e_mic_check,
                    exc_info=True,
                )
                SpeechToTextProcessor._microphone_available = False

        if (
            SpeechToTextProcessor._microphone_available
            and adjust_noise_on_init
            and not SpeechToTextProcessor._noise_adjusted_globally
            and self.recognizer.dynamic_energy_threshold
            and ENERGY_THRESHOLD_MANUAL <= 0
        ):
            self._adjust_for_ambient_noise_once()

    def _get_microphone_instance(self) -> sr.Microphone | None:
        """Mendapatkan atau membuat instance sr.Microphone."""
        if not SpeechToTextProcessor._microphone_available:
            logger.error(
                "Microphone interface is not available. Cannot get microphone instance."
            )
            return None
        try:
            mic = sr.Microphone()
            logger.debug("sr.Microphone instance created/retrieved.")
            return mic
        except sr.WaitTimeoutError as e_mic_timeout:
            logger.error(
                "Timeout error obtaining microphone instance (possibly in use): %s",
                e_mic_timeout,
                exc_info=True,
            )
        except OSError as e_mic_os:
            logger.error(
                "OSError obtaining microphone instance (device issue?): %s",
                e_mic_os,
                exc_info=True,
            )
        except Exception as e_mic_new:
            logger.error(
                "Unexpected error creating sr.Microphone instance: %s",
                e_mic_new,
                exc_info=True,
            )
        return None

    def _adjust_for_ambient_noise_once(self):
        """Menyesuaikan recognizer dengan noise sekitar, hanya dilakukan sekali."""
        if SpeechToTextProcessor._noise_adjusted_globally:
            return

        mic = self._get_microphone_instance()
        if not mic:
            logger.warning(
                "Cannot adjust for ambient noise: microphone instance not available."
            )
            return

        logger.info(
            "Adjusting for ambient noise (duration: %.1fs)... Please be quiet.",
            ADJUST_NOISE_DURATION,
        )
        try:
            with mic as source:
                self.recognizer.adjust_for_ambient_noise(
                    source, duration=ADJUST_NOISE_DURATION
                )
            SpeechToTextProcessor._noise_adjusted_globally = True
            logger.info(
                "Ambient noise adjustment complete. Recognizer energy threshold: %.2f",
                self.recognizer.energy_threshold,
            )
        except sr.WaitTimeoutError:
            logger.warning(
                "Timeout during ambient noise adjustment (no audio input?). Current energy threshold: %.2f",
                self.recognizer.energy_threshold,
            )
        except Exception as e_adjust:
            logger.warning(
                "Could not adjust for ambient noise: %s. Current energy threshold: %.2f",
                e_adjust,
                self.recognizer.energy_threshold,
                exc_info=True,
            )

    def listen_and_recognize(
        self, language: str | None = None, phrase_time_limit: float | int | None = None
    ) -> str | None:
        current_microphone = self._get_microphone_instance()
        if not current_microphone:
            logger.error("Microphone not available for listening.")
            return None

        target_language = language if language is not None else DEFAULT_STT_LANGUAGE
        actual_phrase_time_limit_cfg = (
            DEFAULT_PHRASE_TIME_LIMIT if DEFAULT_PHRASE_TIME_LIMIT > 0 else None
        )
        actual_phrase_time_limit = (
            phrase_time_limit
            if phrase_time_limit is not None
            else actual_phrase_time_limit_cfg
        )

        logger.info(
            "Listening for speech... (Lang: %s, Phrase Limit: %s, Pause: %.1fs, Energy: %.2f)",
            target_language,
            (
                f"{actual_phrase_time_limit:.1f}s"
                if actual_phrase_time_limit
                else "None (pause-based)"
            ),
            self.recognizer.pause_threshold,
            self.recognizer.energy_threshold,
        )

        try:
            with current_microphone as source:
                audio_data = self.recognizer.listen(
                    source, phrase_time_limit=actual_phrase_time_limit
                )
            logger.info(
                "Speech detected, attempting to recognize via Google Web Speech API..."
            )
            recognized_text = self.recognizer.recognize_google(
                audio_data, language=target_language
            )
            logger.info('Google Web Speech API recognized: "%s"', recognized_text)
            return recognized_text
        except sr.WaitTimeoutError:
            logger.info("No speech detected within timeout or before pause.")
            return None
        except sr.UnknownValueError:
            logger.info("Google Web Speech API could not understand audio.")
            return None
        except sr.RequestError as e:
            logger.error("Google Web Speech API request failed; %s", e, exc_info=True)
            return None
        except OSError as e_os:
            logger.error(
                "OSError during listening/recognition (microphone issue?): %s",
                e_os,
                exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error during speech recognition: %s", e, exc_info=True
            )
            return None


_stt_processor_instance_singleton: SpeechToTextProcessor | None = None
_stt_lock = threading.Lock()


def get_stt_processor(
    adjust_noise_on_first_get: bool = True,
) -> SpeechToTextProcessor | None:
    global _stt_processor_instance_singleton
    if _stt_processor_instance_singleton is None:
        with _stt_lock:
            if _stt_processor_instance_singleton is None:
                if _recognizer_instance_module_level is not None:
                    try:
                        logger.info(
                            "Creating STT Processor instance for the first time."
                        )
                        _stt_processor_instance_singleton = SpeechToTextProcessor(
                            adjust_noise_on_init=adjust_noise_on_first_get
                        )
                    except RuntimeError as e:
                        logger.error("Failed to create STT Processor instance: %s", e)
                        _stt_processor_instance_singleton = None
                    except Exception as e_proc:
                        logger.error(
                            "Unexpected error creating STT Processor: %s",
                            e_proc,
                            exc_info=True,
                        )
                        _stt_processor_instance_singleton = None
                else:
                    logger.error(
                        "Cannot create STT Processor: global Recognizer failed to initialize."
                    )
    return _stt_processor_instance_singleton


def listen_and_transcribe(
    language: str | None = None, phrase_time_limit: float | int | None = None
) -> str | None:
    processor = get_stt_processor()
    if processor:
        return processor.listen_and_recognize(
            language=language, phrase_time_limit=phrase_time_limit
        )
    logger.error("STT processor not available for listen_and_transcribe.")
    return None


# --- SpeechToText Test ---
if __name__ == "__main__":
    try:
        if not logging.getLogger().hasHandlers():
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
            )

        logger.info("--- Speech-to-Text (SpeechRecognition) Test ---")

        stt_proc_1 = get_stt_processor()

        if not stt_proc_1:
            logger.error("STT Processor (1) could not be initialized. Aborting test.")
        else:
            logger.info(
                "Silakan berbicara sesuatu dalam Bahasa Indonesia (akan berhenti setelah jeda atau batas waktu frasa)..."
            )
            transcribed_text_id = listen_and_transcribe(
                language="id-ID", phrase_time_limit=7
            )
            if transcribed_text_id:
                logger.info('Anda mengatakan (ID): "%s"', transcribed_text_id)
            else:
                logger.info("Tidak ada yang berhasil ditranskripsi (ID).")

            time.sleep(1)

            logger.info(
                "--- Second STT Processor Instance (should be the same due to singleton) ---"
            )
            stt_proc_2 = get_stt_processor(adjust_noise_on_first_get=False)
            if stt_proc_1 and stt_proc_2:
                logger.info(
                    "ID stt_proc_1: %s, ID stt_proc_2: %s. Match: %s",
                    id(stt_proc_1),
                    id(stt_proc_2),
                    id(stt_proc_1) == id(stt_proc_2),
                )

            logger.info(
                "Please say something in English (will stop after pause or phrase time limit)..."
            )
            transcribed_text_en = listen_and_transcribe(language="en-US")
            if transcribed_text_en:
                logger.info('You said (EN): "%s"', transcribed_text_en)
            else:
                logger.info("Nothing was transcribed (EN).")

            logger.info("\nTest dengan batas waktu frasa 2 detik (English)...")
            short_phrase = listen_and_transcribe(language="en-US", phrase_time_limit=2)
            if short_phrase:
                logger.info('Short phrase (EN): "%s"', short_phrase)
            else:
                logger.info("No short phrase transcribed (EN) or timeout too short.")
    except KeyboardInterrupt:
        logger.info("Aplikasi dihentikan oleh pengguna (KeyboardInterrupt).")
