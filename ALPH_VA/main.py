# main.py
import asyncio, os
from core import config_manager, context_manager, language_model, speech_to_text, text_processing
from plugins import translator, japanese_tts, default_tts, custom_model_tts
import logging

LOG_DIR_MAIN = os.path.join(config_manager.PROJECT_ROOT_DIR, "logs")
if not os.path.exists(LOG_DIR_MAIN):
    os.makedirs(LOG_DIR_MAIN)

APP_LOG_FILE = os.path.join(LOG_DIR_MAIN, "virtual_assistant.log")
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(APP_LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VirtualAssistantApp:
    def __init__(self):
        logger.info("Initializing Virtual Assistant Application...")
        self.target_language = config_manager.get_config_value("general", "language", "id")
        self.source_language = config_manager.get_config_value("translator_plugin", "default_source_language", "id")
        self.translator_plugin = translator.get_translator_plugin()
        self.clean_llm_output_for_tts = text_processing.clean_llm_output_for_tts
        self.stt_processor = None
        self.tts_engines = {
            "japanese": japanese_tts,
            "default": default_tts,
            "custom": custom_model_tts
        }
        self.default_tts_engine_name = config_manager.get_config_value("tts_settings", "default_engine", "default")
        logger.info(f"App initialized. Target lang: {self.target_language}, Source lang: {self.source_language}")

    def select_language_preferences(self):
        logger.info("Displaying language selection menu.")
        print("\n=== Pengaturan Bahasa ===")
        print(f"Bahasa Anda Saat Ini: {self.source_language}")
        print(f"Bahasa Output Saat Ini: {self.target_language}")
        print("\nPilih Bahasa Output:")
        print("1. Bahasa Indonesia (id)")
        print("2. Bahasa Inggris (en)")
        print("3. Bahasa Jepang (ja)")
        choice = input("Pilihan Anda (biarkan kosong untuk tidak mengubah): ").strip()
        if choice == "1": self.target_language = "id"
        elif choice == "2": self.target_language = "en"
        elif choice == "3": self.target_language = "ja"
        logger.info(f"Bahasa target diubah menjadi: {self.target_language}")
        config_manager.set_config_value("general", "language", self.target_language)

    async def speak_response(self, text_to_speak: str, lang_code: str, 
                             rate: int = None, volume: float = None, 
                             speaker_name_or_id=None, engine_override: str = None):
        """Menggunakan engine TTS yang sesuai untuk mengucapkan teks."""
        if not text_to_speak:
            return

        selected_engine = engine_override

        if not selected_engine:
            if lang_code.lower() == "ja":
                selected_engine = "japanese"
            else:
                selected_engine = self.default_tts_engine_name
        
        logger.info(f"Attempting to speak (Lang: {lang_code}, Engine: {selected_engine}): '{text_to_speak[:50]}...'")

        try:
            loop = asyncio.get_event_loop()

            if selected_engine == "japanese":
                await self.tts_engines["japanese"].speak_japanese(
                    text_to_speak, 
                    speaker_id=speaker_name_or_id
                )
            
            elif selected_engine == "custom":
                await self.tts_engines["custom"].speak_custom(
                    text_to_speak, 
                    speaker_name_or_id=speaker_name_or_id,
                    language=lang_code
                )

            elif selected_engine == "default":
                async def run_default_tts_in_executor():
                    try:
                        await loop.run_in_executor(None, 
                                                  self.tts_engines["default"].speak_default, 
                                                  text_to_speak, 
                                                  lang_code,
                                                  rate,
                                                  volume
                                                  )
                        logger.info(f"Background task for Default TTS ({lang_code.upper()}) for '{text_to_speak[:30]}...' completed.")
                    except Exception as e_exec:
                        logger.error(f"Error in default_tts executor task: {e_exec}", exc_info=True)
                asyncio.create_task(run_default_tts_in_executor())
                logger.info(f"Default TTS ({lang_code.upper()}) for '{text_to_speak[:30]}...' dispatched to background.")
            
            else: # Engine tidak dikenal, fallback ke default
                logger.warning(f"Unknown TTS engine '{selected_engine}' specified. Falling back to default engine ('{self.default_tts_engine_name}').")
                # Ini akan memanggil ulang logika di atas dengan self.default_tts_engine_name
                # Untuk menghindari rekursi tak terbatas jika default_tts_engine_name juga salah,
                # kita bisa langsung panggil default_tts di sini sebagai fallback akhir.
                async def run_fallback_tts_in_executor():
                    try:
                        await loop.run_in_executor(None, self.tts_engines["default"].speak_default, text_to_speak, lang_code, rate, volume)
                        logger.info(f"Background task for Fallback (Default) TTS ({lang_code.upper()}) for '{text_to_speak[:30]}...' completed.")
                    except Exception as e_exec_fallback:
                        logger.error(f"Error in fallback_tts executor task: {e_exec_fallback}", exc_info=True)
                asyncio.create_task(run_fallback_tts_in_executor())
                logger.info(f"Fallback TTS (Default) for '{text_to_speak[:30]}...' dispatched to background.")

        except Exception as e:
            logger.error(f"Error during TTS dispatch for engine '{selected_engine}': {e}", exc_info=True)

    async def mode_chat_gemini(self):
        logger.info("Memasuki Mode Chat Gemini.")
        print(f"\n=== Mode Chat Gemini (Bahasa: {self.target_language}) ===")
        print("Ketik 'kembali' untuk ke menu utama, 'clear' untuk arsipkan sesi ini.")

        context_manager.load_archived_session_to_memory(session_index=-1, set_as_current=True)
        
        while True:
            current_chat_history = context_manager.retrieve()
            user_input_raw = await asyncio.to_thread(input, f"[You][{self.target_language}]: ")

            if user_input_raw.strip().lower() == "kembali":
                logger.info("Keluar dari Mode Chat Gemini.")
                break
            if user_input_raw.strip().lower() == "clear":
                context_manager.archive_and_clear_session()
                current_chat_history = context_manager.retrieve()
                print("Sesi chat saat ini diarsipkan dan dibersihkan.")
                continue
            if not user_input_raw.strip():
                continue
            
            final_input_for_llm = user_input_raw if (self.target_language == self.source_language) else await translator.translate_text(user_input_raw, self.target_language, self.source_language)

            context_manager.remember("user", final_input_for_llm)

            response_text = language_model.get_response(
                self.target_language, 
                final_input_for_llm, 
                current_chat_history
            )
            print(f"[Assistant]: {response_text}")

            if not response_text.startswith("[Gemini Error]"):
                context_manager.remember("model", response_text)
                cleaned_response = text_processing.clean_llm_output_for_tts(response_text)
                await self.speak_response(cleaned_response, self.target_language)
                logger.info("speak_response has completed/returned in mode_chat_gemini.")
            else:
                logger.error(f"Gemini Error received: {response_text}")


    async def mode_translate_sentence(self):
        logger.info("Memasuki Mode Terjemah Kalimat.")
        print("\n=== Mode Terjemah Kalimat ===")
        print("Ketik 'kembali' untuk ke menu utama.")

        if not self.translator_plugin:
            logger.error("Translator plugin tidak tersedia.")
            print("Maaf, layanan terjemahan tidak tersedia saat ini.")
            return

        while True:
            text_to_translate = await asyncio.to_thread(input, "Masukkan teks yang ingin diterjemahkan: ")
            if text_to_translate.strip().lower() == "kembali":
                logger.info("Keluar dari Mode Terjemah.")
                break
            if not text_to_translate.strip():
                continue

            current_source = await asyncio.to_thread(input, f"Bahasa asal (default: {self.source_language}, 'auto' untuk deteksi): ") or self.source_language
            current_target = await asyncio.to_thread(input, f"Bahasa tujuan (default: {self.target_language}): ") or self.target_language
            
            translated_text = await translator.translate_text(text_to_translate, current_target, current_source)

            if translated_text:
                print(f"[{current_source.upper()}]: {text_to_translate}")
                print(f"[{current_target.upper()}]: {translated_text}")
                # Ucapkan hasil terjemahan dalam bahasa target
                await self.speak_response(translated_text, current_target)
            else:
                print("Gagal menerjemahkan teks.")
    
    async def mode_voice_call(self):
        logger.info("Memasuki Mode Panggilan Suara (STT -> LLM -> TTS).")
        print("\n=== 🎙️ Mode Panggilan Suara 🎙️ ===")
        await self.speak_response(f"Mode panggilan suara aktif dalam bahasa {self.target_language}. Katakan 'stop panggilan' untuk mengakhiri.", self.target_language)
        # Beri jeda agar TTS pengantar selesai sebelum mulai mendengarkan
        await asyncio.sleep(1) # Sesuaikan durasi jeda jika perlu

        if self.stt_processor is None:
            try:
                self.stt_processor = speech_to_text.get_stt_processor()
                if self.stt_processor is None:
                    raise RuntimeError("STT Processor gagal diinisialisasi dari get_stt_processor.")
            except Exception as e:
                logger.error(f"Tidak dapat memulai mode panggilan: STT Processor gagal diinisialisasi. Error: {e}", exc_info=True)
                error_message = "Maaf, mode panggilan tidak tersedia saat ini karena masalah dengan sistem pengenalan suara."
                print(error_message)
                await self.speak_response(error_message, self.target_language)
                return
        
        # Muat konteks terakhir atau mulai baru.
        # Ini akan mengatur _chat_session_history di context_manager.
        context_manager.load_archived_session_to_memory(session_index=-1, set_as_current=True)
        logger.info("Konteks sesi (jika ada) telah dimuat untuk mode panggilan.")

        keep_listening = True
        consecutive_stt_failures = 0
        max_stt_failures = 3 # Jumlah kegagalan STT berturut-turut sebelum memberi pesan khusus

        while keep_listening:
            current_chat_history = context_manager.retrieve() # Selalu ambil konteks terbaru
            
            # Tampilkan pesan mendengarkan ke pengguna
            # Kita tidak bisa print saat STT sedang listen karena akan tertangkap STT juga
            # logger.info(f"({self.target_language}) Mendengarkan...") 
            # Sebagai gantinya, mungkin ada indikator visual jika ini GUI, atau suara "ping" singkat.
            # Untuk terminal, kita bisa print sebelum listen.
            print(f"\n({self.target_language}) Saya mendengarkan...")

            user_speech = None
            try:
                # `listen_and_transcribe` adalah blocking, jalankan di executor
                stt_lang_code = self.target_language
                if self.target_language == "id": stt_lang_code = "id-ID"
                elif self.target_language == "en": stt_lang_code = "en-US"
                # Tambahkan mapping lain jika perlu untuk STT

                user_speech = await asyncio.to_thread(
                    speech_to_text.listen_and_transcribe, 
                    language=stt_lang_code,
                    phrase_time_limit=config_manager.get_float("stt_settings", "phrase_time_limit", 7.0) # Beri batas waktu frasa yang wajar
                )
            except Exception as e_stt_thread:
                logger.error(f"Error dalam thread STT: {e_stt_thread}", exc_info=True)
                user_speech = None # Anggap gagal

            if user_speech:
                consecutive_stt_failures = 0 # Reset counter kegagalan
                print(f"[Anda 🗣️]: {user_speech}")
                
                # Periksa kata kunci keluar
                # TODO: Buat kata kunci keluar bisa dikonfigurasi
                exit_keywords = ["stop panggilan", "berhenti panggilan", "akhiri panggilan", "keluar mode suara"]
                if any(keyword in user_speech.lower() for keyword in exit_keywords):
                    logger.info("Mode panggilan dihentikan oleh pengguna via kata kunci.")
                    await self.speak_response("Baik, mode panggilan suara diakhiri.", self.target_language)
                    keep_listening = False # Hentikan loop
                    continue # Langsung ke iterasi berikutnya untuk keluar dari loop

                # Simpan ucapan pengguna (setelah STT) ke konteks
                context_manager.remember("user", user_speech)
                current_chat_history = context_manager.retrieve() # Update konteks untuk LLM

                # Dapatkan respons dari LLM
                # Kita asumsikan action router belum ada, jadi langsung ke language_model
                print("[Asisten 思考中...]") # Beri indikasi sedang berpikir
                response_text_raw = language_model.get_response(
                    self.target_language,
                    user_speech,
                    current_chat_history 
                )
                
                # Bersihkan respons LLM sebelum ditampilkan dan diucapkan
                # (Asumsi clean_llm_output_for_tts ada di scope, misal dari self atau import)
                # Jika tidak, Anda perlu: from core.text_processing import clean_llm_output_for_tts
                response_text_cleaned = self.clean_llm_output_for_tts(response_text_raw) # Panggil sebagai metode jika ada di kelas
                
                print(f"[Asisten 🤖]: {response_text_cleaned}") # Tampilkan versi bersih

                if not response_text_raw.startswith("[Gemini Error]"): # Cek error pada respons MENTAH
                    context_manager.remember("model", response_text_cleaned) # Simpan versi bersih ke konteks
                    await self.speak_response(response_text_cleaned, self.target_language)
                else:
                    logger.error(f"Gemini Error in voice call mode: {response_text_raw}")
                    error_speech = "Maaf, sepertinya ada sedikit gangguan saat memproses permintaan Anda."
                    print(f"[Asisten 🤖]: {error_speech}")
                    await self.speak_response(error_speech, self.target_language)
            
            else: # Tidak ada ucapan yang terdeteksi atau error STT
                consecutive_stt_failures += 1
                logger.info(f"Tidak ada ucapan terdeteksi atau STT gagal. Percobaan ke-{consecutive_stt_failures}.")
                
                if consecutive_stt_failures >= max_stt_failures:
                    logger.warning(f"STT gagal {max_stt_failures} kali berturut-turut.")
                    no_detection_message = "Saya masih belum mendengar apa-apa. Apakah mikrofon Anda berfungsi? Katakan 'stop panggilan' jika ingin keluar."
                    print(f"[Asisten 🤖]: {no_detection_message}")
                    await self.speak_response(no_detection_message, self.target_language)
                    consecutive_stt_failures = 0 # Reset setelah memberi pesan
                # Loop akan berlanjut untuk mendengarkan lagi
            
            # Beri jeda singkat agar tidak terlalu cepat kembali mendengarkan,
            # terutama jika STT gagal dan langsung loop kembali.
            # Ini juga memberi waktu untuk TTS selesai jika non-blocking.
            await asyncio.sleep(0.5) 

        logger.info("Keluar dari Mode Panggilan Suara.")


    async def run(self):
        """Loop utama aplikasi untuk menampilkan menu dan memilih mode."""
        self.select_language_preferences()

        while True:
            print("\n=== Menu Utama Virtual Assistant ===")
            print("1. Chat dengan Gemini")
            print("2. Terjemahkan Kalimat")
            print("3. Mode Panggilan Suara (STT-TTS)")
            print("4. Pengaturan Bahasa")
            print("5. Keluar")
            choice = await asyncio.to_thread(input, "Pilih mode (1-5): ")

            if choice == "1":
                await self.mode_chat_gemini()
            elif choice == "2":
                await self.mode_translate_sentence()
            elif choice == "3":
                await self.mode_voice_call()
            elif choice == "4":
                self.select_language_preferences()
            elif choice == "5":
                logger.info("Aplikasi keluar.")
                print("Terima kasih telah menggunakan asisten virtual!")
                break
            else:
                print("Pilihan tidak valid, silakan coba lagi.")
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    app = VirtualAssistantApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Aplikasi dihentikan oleh pengguna (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Terjadi error tidak tertangani di level aplikasi utama: {e}", exc_info=True)
    finally:
        print("\nAplikasi ditutup.")