# plugins/custom_model_tts.py

import os
import time
import asyncio
# from TTS.api import TTS # Kita tidak akan menggunakan API level atas ini lagi
from TTS.utils.synthesizer import Synthesizer # Gunakan Synthesizer langsung
from core import config_manager
from plugins import play_voice
import logging

# --- Setup Logging --- (Tetap sama)
# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

_tts_synthesizer_instance = None

class CoquiVITSTTS:
    def __init__(self):
        self.synthesizer = None
        self.speaker_names = []
        self.is_multi_speaker = False # Default ke False
        self.sample_rate = 22050

        logger.info("Initializing Coqui VITS TTS Synthesizer...")
        
        # ... (kode untuk membaca config tetap sama) ...
        self.enabled = config_manager.get_bool("tts_custom_model", "enabled", False)
        if not self.enabled:
            logger.warning("Custom TTS model (Coqui VITS) is disabled in config.")
            return

        model_config_rel_path = config_manager.get_config_value("tts_custom_model", "model_config_path")
        model_checkpoint_rel_path = config_manager.get_config_value("tts_custom_model", "model_checkpoint_path")
        speakers_file_rel_path = config_manager.get_config_value("tts_custom_model", "speakers_file_path")
        self.use_gpu = config_manager.get_bool("tts_custom_model", "use_gpu", False)
        self.default_speaker_name_or_id = config_manager.get_config_value("tts_custom_model", "default_speaker_name_or_id")

        if not model_config_rel_path or not model_checkpoint_rel_path:
            logger.error("Model config path or checkpoint path not found in configuration for custom TTS.")
            self.enabled = False
            return

        self.model_config_path = os.path.join(config_manager.PROJECT_ROOT_DIR, model_config_rel_path)
        self.model_checkpoint_path = os.path.join(config_manager.PROJECT_ROOT_DIR, model_checkpoint_rel_path)
        
        _speakers_file_abs_path = None
        if speakers_file_rel_path:
            _speakers_file_abs_path = os.path.join(config_manager.PROJECT_ROOT_DIR, speakers_file_rel_path)
            logger.info(f"  Speakers File (from config.ini): {_speakers_file_abs_path}")
        else:
            logger.info(f"  Speakers File: Will be loaded based on model's config.json if specified there.")

        logger.info(f"  Model Config: {self.model_config_path}")
        logger.info(f"  Model Checkpoint: {self.model_checkpoint_path}")
        logger.info(f"  Use GPU: {self.use_gpu}")

        try:
            self.synthesizer = Synthesizer(
                tts_checkpoint=self.model_checkpoint_path,
                tts_config_path=self.model_config_path,
                tts_speakers_file=_speakers_file_abs_path,
                use_cuda=self.use_gpu,
            )
            logger.info("Coqui TTS Synthesizer loaded successfully.")

            # --- PERBAIKAN CARA CEK MULTI-SPEAKER ---
            # Cek dari konfigurasi model yang sudah dimuat oleh Synthesizer
            if hasattr(self.synthesizer, 'tts_config') and \
               self.synthesizer.tts_config.get('use_speaker_embedding', False) and \
               self.synthesizer.tts_config.get('num_speakers', 0) > 0:
                self.is_multi_speaker = True
            # Atau jika ada speaker_manager dan memiliki entri
            elif hasattr(self.synthesizer.tts_model, 'speaker_manager') and \
                 hasattr(self.synthesizer.tts_model.speaker_manager, 'name_to_id') and \
                 self.synthesizer.tts_model.speaker_manager.name_to_id: # Pastikan tidak kosong
                self.is_multi_speaker = True
            
            if self.is_multi_speaker:
                # Coba dapatkan nama speaker dari speaker_manager di tts_model
                if hasattr(self.synthesizer.tts_model, 'speaker_manager') and \
                   hasattr(self.synthesizer.tts_model.speaker_manager, 'name_to_id'):
                    self.speaker_names = list(self.synthesizer.tts_model.speaker_manager.name_to_id.keys())
                
                if self.speaker_names:
                    logger.info(f"Model is multi-speaker. Available speakers: {self.speaker_names}")
                else:
                    logger.warning("Model is marked as multi-speaker, but could not retrieve speaker names. Speaker selection might require integer IDs or check 'speakers_file' in model's config.json.")
            else:
                logger.info("Model is determined to be single-speaker based on its configuration.")
            
            if hasattr(self.synthesizer, 'tts_config') and 'audio' in self.synthesizer.tts_config:
                self.sample_rate = self.synthesizer.tts_config.audio.get('sample_rate', self.sample_rate)
            logger.info(f"Model sample rate: {self.sample_rate}")

        except FileNotFoundError as fnf_error:
            logger.error(f"FileNotFoundError during Synthesizer initialization: {fnf_error}. Check paths in config.ini and model's config.json.", exc_info=True)
            self.enabled = False
            self.synthesizer = None
        except Exception as e:
            logger.error(f"Failed to load Coqui TTS Synthesizer: {e}", exc_info=True)
            self.enabled = False
            self.synthesizer = None
            
    def get_speaker_name_for_synthesis(self, speaker_name_or_id):
        """
        Menentukan nama speaker yang akan digunakan untuk argumen `speaker_name` pada `synthesizer.tts()`.
        Coqui Synthesizer biasanya mengharapkan nama speaker jika ada di `speaker_manager.name_to_id`.
        """
        if not self.is_multi_speaker:
            return None 

        target_speaker_name = None
        if speaker_name_or_id is not None:
            if isinstance(speaker_name_or_id, str) and speaker_name_or_id in self.speaker_names:
                target_speaker_name = speaker_name_or_id
            elif isinstance(speaker_name_or_id, int):
                if 0 <= speaker_name_or_id < len(self.speaker_names):
                    target_speaker_name = self.speaker_names[speaker_name_or_id]
                else:
                    logger.warning(f"Speaker ID {speaker_name_or_id} is out of range for available speakers.")
            else: # Jika nama tidak ditemukan
                logger.warning(f"Speaker '{speaker_name_or_id}' not found in available speakers: {self.speaker_names}.")
        
        if target_speaker_name is None and self.default_speaker_name_or_id: 
            if self.default_speaker_name_or_id in self.speaker_names:
                target_speaker_name = self.default_speaker_name_or_id
            else: 
                try:
                    default_idx = int(self.default_speaker_name_or_id)
                    if 0 <= default_idx < len(self.speaker_names):
                        target_speaker_name = self.speaker_names[default_idx]
                except ValueError:
                    logger.warning(f"Default speaker '{self.default_speaker_name_or_id}' not found and is not a valid index.")

        if target_speaker_name is None and self.speaker_names: 
            target_speaker_name = self.speaker_names[0]
            logger.info(f"Using first available speaker as fallback: {target_speaker_name}")
        
        return target_speaker_name

    def synthesize(self, text: str, speaker_name_or_id=None, language_code: str = None) -> str | None:
        if not self.enabled or not self.synthesizer:
            logger.error("Custom TTS Synthesizer is not enabled or not loaded. Cannot synthesize.")
            return None

        speaker_name_for_tts = None
        if self.is_multi_speaker:
            speaker_name_for_tts = self.get_speaker_name_for_synthesis(speaker_name_or_id)
        
        audio_output_subdir = config_manager.get_config_value("tts_custom_model", "audio_output_subdir", "custom_tts")
        output_dir = os.path.join(config_manager.PROJECT_ROOT_DIR, config_manager.get_config_value("general", "audio_output_path", "data/audio/"), audio_output_subdir)
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                logger.info(f"Created custom TTS audio output directory: {output_dir}")
            except Exception as e:
                logger.error(f"Failed to create custom TTS audio output directory {output_dir}: {e}")
                return None

        timestamp = str(int(time.time()))
        speaker_tag = f"_spk-{speaker_name_for_tts.replace(' ', '_')}" if speaker_name_for_tts else ""
        output_filename = f"custom_tts_{timestamp}{speaker_tag}.wav"
        output_path = os.path.join(output_dir, output_filename)

        logger.info(f"Synthesizing text: '{text[:50]}...'")
        if speaker_name_for_tts:
            logger.info(f"Using speaker: {speaker_name_for_tts}")
        try:
            wav = self.synthesizer.tts(
                text=text,
                speaker_name=speaker_name_for_tts,
                language_name=None, 
                speaker_wav=None,   
                reference_wav=None, 
                style_wav=None,     
                style_text=None,
                reference_speaker_name=None
            )
            if wav is not None:
                self.synthesizer.save_wav(wav=wav, path=output_path)
                logger.info(f"Audio successfully synthesized and saved to: {output_path}")

                play_blocking = config_manager.get_bool("tts_settings", "custom_tts_play_blocking", True)
                play_voice.play_audio_file(output_path, block_until_done=play_blocking)
                
                return output_path
            else:
                logger.error("TTS synthesis returned None (no audio data).")
                return None
        except Exception as e:
            logger.error(f"Error during Coqui TTS synthesis with Synthesizer: {e}", exc_info=True)
            return None

# --- Fungsi antarmuka publik ---
def get_tts_instance() -> CoquiVITSTTS | None:
    """Mengembalikan instance singleton dari CoquiVITSTTS, membuatnya jika belum ada."""
    global _tts_synthesizer_instance
    if _tts_synthesizer_instance is None:
        logger.debug("Creating new CoquiVITSTTS (Synthesizer) instance.")
        _tts_synthesizer_instance = CoquiVITSTTS()
    # ... (logika re-inisialisasi jika enabled di config tetap sama) ...
    elif not _tts_synthesizer_instance.enabled and config_manager.get_bool("tts_custom_model", "enabled", False):
        logger.info("Custom TTS was disabled, but config now shows enabled. Re-initializing.")
        _tts_synthesizer_instance = CoquiVITSTTS()
        
    if _tts_synthesizer_instance and not _tts_synthesizer_instance.enabled:
        return None
    return _tts_synthesizer_instance

async def speak_custom(text: str, speaker_name_or_id=None, language: str = None) -> str | None:
    tts_instance = get_tts_instance()
    if tts_instance:
        try:
            if asyncio.get_running_loop().is_running():
                 return await asyncio.to_thread(tts_instance.synthesize, text, speaker_name_or_id, language)
            else:
                 return tts_instance.synthesize(text, speaker_name_or_id, language)
        except RuntimeError:
            return tts_instance.synthesize(text, speaker_name_or_id, language)
    else:
        logger.error("Custom TTS instance not available or not enabled.")
        return None

async def main_test_custom():
    logger.info("--- Custom TTS (Coqui VITS - Synthesizer) Plugin Test ---")
    tts_instance = get_tts_instance()
    if not tts_instance or not tts_instance.enabled:
        logger.error("Custom TTS failed to initialize or is disabled. Aborting test.")
        return

    if tts_instance.is_multi_speaker and tts_instance.speaker_names:
        logger.info(f"Available speakers for custom model: {tts_instance.speaker_names}")
        speaker_to_test = tts_instance.default_speaker_name_or_id if tts_instance.default_speaker_name_or_id in tts_instance.speaker_names else tts_instance.speaker_names[0]
        
        logger.info(f"Testing with speaker: {speaker_to_test}")
        await speak_custom("Halo, ini adalah tes suara dari model kustom VITS.", speaker_name_or_id=speaker_to_test)
        
        if len(tts_instance.speaker_names) > 1:
            idx_to_try = 1 % len(tts_instance.speaker_names)
            if tts_instance.speaker_names[idx_to_try] != speaker_to_test :
                 speaker_to_test_2 = tts_instance.speaker_names[idx_to_try]
                 logger.info(f"Testing with another speaker: {speaker_to_test_2}")
                 await speak_custom("Ini adalah suara dari speaker yang berbeda.", speaker_name_or_id=speaker_to_test_2)
    else:
        logger.info("Testing with default/single speaker configuration...")
        await speak_custom("Tes suara dari model kustom VITS, mode single speaker atau default.")

if __name__ == "__main__":
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    asyncio.run(main_test_custom())