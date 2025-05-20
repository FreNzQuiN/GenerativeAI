# core/speech_to_text.py

import speech_recognition as sr
from core import config_manager
import logging
import os
import time

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

# --- Variabel Konfigurasi Global (dibaca sekali saat modul dimuat) ---
DEFAULT_STT_LANGUAGE = config_manager.get_config_value("stt_settings", "default_language", "id-ID")
PAUSE_THRESHOLD = config_manager.get_float("stt_settings", "pause_threshold", 2.0)
ENERGY_THRESHOLD_MANUAL = config_manager.get_int("stt_settings", "energy_threshold", None) 
DYNAMIC_ENERGY_THRESHOLD = config_manager.get_bool("stt_settings", "dynamic_energy_threshold", True)
ADJUST_NOISE_ON_STARTUP = config_manager.get_bool("stt_settings", "adjust_noise_on_startup", True)
DEFAULT_PHRASE_TIME_LIMIT = config_manager.get_float("stt_settings", "phrase_time_limit", None)

# --- Inisialisasi dan Konfigurasi Recognizer Global ---
recognizer_instance = None
try:
    recognizer_instance = sr.Recognizer()
    recognizer_instance.pause_threshold = PAUSE_THRESHOLD
    recognizer_instance.dynamic_energy_threshold = DYNAMIC_ENERGY_THRESHOLD
    
    logger.info(f"SpeechRecognition Recognizer initialized. Pause threshold: {PAUSE_THRESHOLD}s, Dynamic Energy: {DYNAMIC_ENERGY_THRESHOLD}")

    # Penyesuaian energy threshold dilakukan saat instance SpeechToTextProcessor pertama dibuat,
    # karena memerlukan akses ke mikrofon.
except Exception as e:
    logger.error(f"Failed to initialize SpeechRecognition Recognizer: {e}", exc_info=True)
    # recognizer_instance akan tetap None

class SpeechToTextProcessor:
    _microphone_initialized = False # Flag untuk memastikan mikrofon dan adjust_noise hanya sekali

    def __init__(self):
        if recognizer_instance is None:
            logger.critical("Speech Recognizer instance is not available (failed global init). STT will not work.")
            raise RuntimeError("SpeechRecognition Recognizer failed to initialize globally.")
        self.recognizer = recognizer_instance
        
        # Inisialisasi mikrofon dan penyesuaian noise hanya jika belum dilakukan
        if not SpeechToTextProcessor._microphone_initialized:
            try:
                self.microphone = sr.Microphone() # Default device
                logger.info(f"Microphone initialized using default device.")

                if ENERGY_THRESHOLD_MANUAL is not None:
                    self.recognizer.energy_threshold = ENERGY_THRESHOLD_MANUAL
                    logger.info(f"Recognizer energy_threshold manually set to: {self.recognizer.energy_threshold}")
                elif ADJUST_NOISE_ON_STARTUP:
                    with self.microphone as source:
                        logger.info("Adjusting for ambient noise (1 sec)... Please be quiet.")
                        try:
                            self.recognizer.adjust_for_ambient_noise(source, duration=1)
                            logger.info(f"Ambient noise adjustment complete. Energy threshold dynamically set to: {self.recognizer.energy_threshold}")
                        except Exception as e_adjust:
                            logger.warning(f"Could not adjust for ambient noise: {e_adjust}. Current energy threshold: {self.recognizer.energy_threshold}")
                else:
                    logger.info(f"Using default/dynamic energy threshold. Current: {self.recognizer.energy_threshold}")
                
                SpeechToTextProcessor._microphone_initialized = True
            except AttributeError as ae:
                logger.error(f"Failed to initialize sr.Microphone. PyAudio might be missing or not configured: {ae}", exc_info=True)
                raise RuntimeError(f"Failed to initialize sr.Microphone: {ae}")
            except Exception as e_mic:
                logger.error(f"An unexpected error occurred initializing Microphone or adjusting noise: {e_mic}", exc_info=True)
                raise RuntimeError(f"Unexpected error initializing Microphone or adjusting noise: {e_mic}")
        else:
            # Jika sudah diinisialisasi, pastikan kita punya referensi ke mikrofon
            # Ini bisa jadi masalah jika kita membuat >1 instance SpeechToTextProcessor,
            # tapi dengan pola singleton get_stt_processor(), ini seharusnya aman.
            # Untuk lebih aman, microphone bisa jadi class variable juga.
            # Namun, sr.Microphone() biasanya murah untuk dibuat ulang jika perlu.
            # Untuk sekarang, kita asumsikan instance tunggal atau mikrofon default selalu bisa diakses.
            try:
                self.microphone = sr.Microphone() # Buat instance baru jika perlu, atau jadikan class variable
            except Exception as e_mic_reinit:
                 logger.error(f"Failed to re-initialize sr.Microphone for new STTProcessor instance: {e_mic_reinit}")
                 # Jika ini terjadi, STT mungkin tidak berfungsi untuk instance ini.
                 # Ini seharusnya tidak menjadi masalah dengan pola singleton.

    def listen_and_recognize(self, language: str = None, phrase_time_limit: float = None) -> str | None:
        # `duration` dihilangkan karena kita mengandalkan `pause_threshold`
        if self.microphone is None and SpeechToTextProcessor._microphone_initialized:
             # Coba inisialisasi ulang jika _microphone_initialized True tapi self.microphone None (kasus aneh)
             try:
                 self.microphone = sr.Microphone()
                 logger.info("Re-initialized microphone for listen_and_recognize.")
             except Exception as e:
                 logger.error(f"Failed to re-initialize microphone in listen_and_recognize: {e}")
                 return None
        elif not SpeechToTextProcessor._microphone_initialized:
             logger.error("Microphone was not successfully initialized. Cannot listen.")
             return None


        target_language = language if language is not None else DEFAULT_STT_LANGUAGE
        actual_phrase_time_limit = phrase_time_limit if phrase_time_limit is not None else DEFAULT_PHRASE_TIME_LIMIT
        
        logger.info(f"Listening for speech (Language: {target_language}, Phrase Limit: {actual_phrase_time_limit if actual_phrase_time_limit else 'None based on pause'})...")
        logger.debug(f"Recognizer settings: pause_threshold={self.recognizer.pause_threshold}s, energy_threshold={self.recognizer.energy_threshold}, dynamic_energy={self.recognizer.dynamic_energy_threshold}")
        
        with self.microphone as source:
            try:
                audio_data = self.recognizer.listen(source, phrase_time_limit=actual_phrase_time_limit)
                logger.info("Speech detected, attempting to recognize...")
                recognized_text = self.recognizer.recognize_google(audio_data, language=target_language)
                logger.info(f"Google Web Speech API recognized: \"{recognized_text}\"")
                return recognized_text
            except sr.WaitTimeoutError:
                logger.info("No speech detected (listen timed out or no speech before pause).")
                return None
            except sr.UnknownValueError:
                logger.info("Google Web Speech API could not understand audio.")
                return None
            except sr.RequestError as e:
                logger.error(f"Could not request results from Google Web Speech API service; {e}", exc_info=True)
                return None
            except Exception as e:
                logger.error(f"An unexpected error occurred during speech recognition: {e}", exc_info=True)
                return None

# --- Fungsi antarmuka publik (Singleton) ---
_stt_processor_instance = None

def get_stt_processor() -> SpeechToTextProcessor | None:
    global _stt_processor_instance
    if _stt_processor_instance is None:
        if recognizer_instance is not None:
            try:
                _stt_processor_instance = SpeechToTextProcessor()
            except RuntimeError as e:
                logger.error(f"Failed to create STT Processor instance during get_stt_processor: {e}")
                _stt_processor_instance = None
        else:
            logger.error("Cannot create STT Processor instance: global Recognizer failed to initialize.")
    return _stt_processor_instance

def listen_and_transcribe(language: str = None, phrase_time_limit: float = None) -> str | None:
    # Menggunakan default phrase_time_limit dari config jika tidak diberikan
    actual_phrase_limit = phrase_time_limit if phrase_time_limit is not None else DEFAULT_PHRASE_TIME_LIMIT
    
    processor = get_stt_processor()
    if processor:
        return processor.listen_and_recognize(language=language, phrase_time_limit=actual_phrase_limit)
    return None

if __name__ == '__main__':
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("--- Speech-to-Text (SpeechRecognition with Google Web API) Test ---")
    
    # Config yang relevan di config.ini:
    # [stt_settings]
    # default_language = id-ID
    # pause_threshold = 2.0
    # energy_threshold = 3000  ; (atau kosongkan jika adjust_noise_on_startup = true)
    # dynamic_energy_threshold = true
    # adjust_noise_on_startup = true
    # phrase_time_limit = 10.0 ; (opsional, batas keras per frasa)

    stt_proc = get_stt_processor() # Ini akan menginisialisasi Recognizer dan Microphone (termasuk adjust_noise jika disetel)
    
    if not stt_proc:
        logger.error("STT Processor could not be initialized. Aborting test.")
    else:
        logger.info("Silakan berbicara sesuatu dalam Bahasa Indonesia (akan berhenti setelah jeda atau batas waktu frasa)...")
        # Menggunakan default phrase_time_limit dari config jika tidak dispesifikkan di sini
        transcribed_text_id = listen_and_transcribe(language="id-ID")
        if transcribed_text_id:
            logger.info(f"Anda mengatakan (ID): \"{transcribed_text_id}\"")
        else:
            logger.info("Tidak ada yang berhasil ditranskripsi (ID).")

        time.sleep(1)

        logger.info("\nPlease say something in English (will stop after pause or phrase time limit)...")
        transcribed_text_en = listen_and_transcribe(language="en-US", phrase_time_limit=7) # Contoh override phrase_time_limit
        if transcribed_text_en:
            logger.info(f"You said (EN): \"{transcribed_text_en}\"")
        else:
            logger.info("Nothing was transcribed (EN).")