# main.py

import asyncio
import os
from core import config_manager, module_manager
import logging

# --- Setup Logging ---
LOG_DIR_MAIN = os.path.join(config_manager.PROJECT_ROOT_DIR, "logs")
if not os.path.exists(LOG_DIR_MAIN):
    try:
        os.makedirs(LOG_DIR_MAIN, exist_ok=True)
    except OSError as e:
        print(f"ERROR: Could not create main log directory {LOG_DIR_MAIN}: {e}")
        LOG_DIR_MAIN = os.getcwd() # Log ke direktori kerja saat ini

APP_LOG_FILE = os.path.join(LOG_DIR_MAIN, "virtual_assistant.log")

# Konfigurasi logger utama aplikasi
logging.basicConfig(
    level=logging.INFO, # Level default, bisa diubah oleh config
    format='%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler(APP_LOG_FILE, encoding='utf-8'),
        logging.StreamHandler() # Juga output ke console
    ]
)
logger = logging.getLogger(__name__) # Logger khusus untuk main.py

class VirtualAssistantApp:
    def __init__(self):
        logger.info("Initializing VirtualAssistantApp...")
        self.config = config_manager.ConfigManager()
        self.manager = module_manager.ModuleManager()
        
        self.language = self.config.get_config_value("general", "interface_language", "id")
        self.source_language = self.config.get_config_value("translator_plugin", "default_source_language", "id")
        self.target_language = self.config.get_config_value("translator_plugin", "default_target_language", "id")
        
        self.language_model_instance = None
        lm_module = self.manager.get_core_module("language_model")
        if lm_module and hasattr(lm_module, "LanguageModel"):
            try:
                self.language_model_instance = lm_module.LanguageModel()
                logger.info("LanguageModel instance created successfully.")
            except Exception as e:
                logger.error(f"Failed to instantiate LanguageModel: {e}", exc_info=True)
        else:
            logger.error("Core module 'language_model' not loaded or does not have LanguageModel class.")

        self.context_manager_instance = None
        cm_module = self.manager.get_core_module("context_manager")
        if cm_module and hasattr(cm_module, "ContextManager"):
            try:
                self.context_manager_instance = cm_module.ContextManager()
                logger.info(f"Active ContextManager instance created (session: {self.context_manager_instance.session_id}).")
            except Exception as e:
                logger.error(f"Failed to instantiate ContextManager: {e}", exc_info=True)
        else:
            logger.error("Core module 'context_manager' not loaded or does not have ContextManager class.")
            
        self.translator_plugin_instance = None
        if self.target_language != self.source_language:
            translator_module = self.manager.get_plugin("translator")
            if translator_module and hasattr(translator_module, "get_translator_plugin"):
                try:
                    self.translator_plugin_instance = translator_module.get_translator_plugin()
                    if self.translator_plugin_instance:
                        logger.info("TranslationPlugin instance obtained successfully.")
                    else:
                        logger.error("get_translator_plugin() from translator module returned None.")
                except Exception as e:
                    logger.error(f"Failed to get/instantiate TranslationPlugin: {e}", exc_info=True)
            else:
                logger.error("Plugin 'translator' not loaded or does not have get_translator_plugin function.")
            
            logger.info("VirtualAssistantApp initialized.")

    async def run(self):
        """Loop utama aplikasi untuk menampilkan menu dan memilih mode."""
        logger.info("VA App Run method started.")
        self.select_language_preferences()

        while True:
            print("\n=== Menu Utama Virtual Assistant ===")
            print("1. Chat dengan Gemini")
            print("2. Terjemahkan Kalimat (Belum diimplementasikan)")
            print("3. Mode Panggilan Suara (STT-TTS) (Belum diimplementasikan)")
            print("4. Pengaturan Bahasa")
            print("5. Keluar")
            
            choice = await asyncio.to_thread(input, f"Pilih mode (1-5) (Bahasa: {self.source_language}): ")

            if choice == "1":
                await self.mode_chat_gemini()
            # elif choice == "2":
            #     await self.mode_translate_sentence() # Contoh
            # elif choice == "3":
            #     logger.warning("Mode Panggilan Suara belum diimplementasikan.")
            #     print("Mode ini belum tersedia.")
            elif choice == "4":
                self.select_language_preferences()
            elif choice == "5":
                self.select_role_preferences()
            elif choice == "6":
                logger.info("Pengguna memilih keluar dari aplikasi.")
                print("Terima kasih telah menggunakan asisten virtual!")
                if self.context_manager_instance:
                    self.context_manager_instance.save_to_archive()
                    logger.info(f"Sesi aktif {self.context_manager_instance.session_id} disimpan sebelum keluar.")
                break
            else:
                print("Pilihan tidak valid, silakan coba lagi.")
            await asyncio.sleep(0.1)
    
    async def mode_chat_gemini(self):
        """Mode untuk berinteraksi dengan Gemini."""
        if not self.language_model_instance:
            logger.error("LanguageModel instance is not available. Cannot start chat mode.")
            print("Model bahasa tidak tersedia. Mode chat tidak dapat dimulai.")
            return
        if not self.context_manager_instance:
            logger.error("ContextManager instance is not available. Cannot start chat mode.")
            print("Manajer konteks tidak tersedia. Mode chat tidak dapat dimulai.")
            return

        # Sesi aktif saat ini dipegang oleh self.context_manager_instance
        # Kita bisa memutuskan untuk memuat sesi terakhir di sini atau menggunakan yang baru
        # Untuk contoh ini, kita akan menggunakan sesi aktif yang sudah ada (yang bisa jadi baru atau dimuat sebelumnya)
        
        logger.info(f"Entering chat mode. Session: {self.context_manager_instance.session_id}, Target Lang: {self.target_language}, Source Lang: {self.source_language}")
        print(f"\n=== Mode Chat dengan Gemini (Output: {self.target_language}, Input: {self.source_language}) ===")
        print("Ketik 'exit' atau 'quit' untuk keluar (menyimpan), 'delete' atau 'hapus' untuk memulai sesi baru (tanpa menyimpan).")

        while True:
            user_input = await asyncio.to_thread(input, f"[User ({self.source_language})]: ")
            user_input_lower = user_input.strip().lower()

            if user_input_lower in ["exit", "quit", "keluar"]:
                logger.info(f"Pengguna keluar dari mode chat. Menyimpan sesi {self.context_manager_instance.session_id}.")
                self.context_manager_instance.save_to_archive()
                print("Keluar dari mode chat. Sesi disimpan.")
                break
            
            if user_input_lower in ["delete", "del", "hapus"]:
                logger.info(f"Pengguna memilih menghapus chat saat ini (sesi {self.context_manager_instance.session_id}) dan memulai baru.")
                print("Menghapus chat saat ini dan memulai sesi baru...")
                cm_module = self.manager.get_core_module("context_manager")
                if cm_module:
                    self.context_manager_instance = cm_module.ContextManager()
                    logger.info(f"Sesi baru dimulai: {self.context_manager_instance.session_id}")
                else:
                    logger.error("Gagal mendapatkan modul context_manager untuk membuat sesi baru.")
                    print("Gagal memulai sesi baru karena error internal.")
                continue
            if user_input_lower in ["load","muat"]:
                logger.info(f"Pengguna memilih memuat chat (sesi {self.context_manager_instance.session_id}).")
                print("Memuat chat sebelumnya...")
                chat_history_content: list = self.context_manager_instance.retrieve() 
            else: 
                chat_history_content:list = []
            if not user_input.strip():
                continue

            try:
                input_for_lm = user_input
                if self.source_language.lower() != self.target_language.lower():
                    logger.info(f"Translating user input from '{self.source_language}' to '{self.target_language}'.")
                    input_for_lm = await self.translate_text_via_plugin(user_input, 
                                                                        target_lang=self.target_language, 
                                                                        source_lang=self.source_language)
                    if not input_for_lm:
                        logger.warning("User input translation failed, using original input for LM.")
                        input_for_lm = user_input
                    logger.info(f"Input for LM (after translation): {input_for_lm[:50]}...")

                response_from_lm = self.language_model_instance.generate_response(
                    language=self.target_language,
                    prompt=input_for_lm,
                    chat_history=chat_history_content,
                    role_override=self.current_chat_role
                )
                response_from_lm = response_from_lm.replace("\n", " ") 
                logger.info(f"Response from LM (in {self.target_language}): {response_from_lm[:100]}...")
                
                final_response_for_user = response_from_lm
                if self.target_language.lower() != self.source_language.lower():
                    logger.info(f"Translating LM response from '{self.target_language}' to '{self.source_language}'.")
                    final_response_for_user = await self.translate_text_via_plugin(response_from_lm, 
                                                                                target_lang=self.source_language, 
                                                                                source_lang=self.target_language)
                    if not final_response_for_user:
                        logger.warning("LM response translation failed. Using original LM response for user.")
                        final_response_for_user = response_from_lm
                
                print(f"[Alph ({self.target_language})]: {response_from_lm}")
                print(f"[Alph ({self.source_language})]: {final_response_for_user}")

                if not response_from_lm.startswith("[Gemini Error]"):
                    self.context_manager_instance.remember("user", user_input) 
                    self.context_manager_instance.remember("model", response_from_lm)
                
            except Exception as e:
                logger.error(f"Error dalam mode chat: {e}", exc_info=True)
                print("Terjadi kesalahan saat berkomunikasi dengan Gemini.")
    
    async def translate_text_via_plugin(self, text: str, target_lang: str, source_lang: str | None = None) -> str | None:
        """Wrapper untuk memanggil metode translate pada instance plugin translator."""
        if not self.translator_plugin_instance:
            logger.error("Translator plugin instance is not available. Cannot translate.")
            return text
        
        actual_source_lang = source_lang or self.source_language
        
        logger.debug(f"Attempting translation via plugin: '{text[:30]}...' from {actual_source_lang} to {target_lang}")
        try:
            translated_text = await self.translator_plugin_instance.translate(
                text, 
                target_lang=target_lang, 
                source_lang=actual_source_lang
            )
            if translated_text is None:
                logger.warning(f"Translation returned None for text: '{text[:30]}...'")
                return text
            return translated_text
        except Exception as e:
            logger.error(f"Error during translation via plugin: {e}", exc_info=True)
            return text # Fallback ke teks asli jika ada error
    
    def select_language_preferences(self):
        """Memungkinkan pengguna memilih bahasa input dan output."""
        logger.info("Entering language selection.")
        try:
            print(f"\n=== Pengaturan Bahasa ===")
            # Pilihan Bahasa Input Pengguna
            print(f"Bahasa input Anda saat ini: {self.source_language}")
            print("Pilih bahasa input Anda:")
            print("1. Bahasa Indonesia (id)")
            print("2. Bahasa Inggris (en)")
            print("3. Bahasa Jepang (ja)")
            choice_src = input("Pilihan (1-3, atau tekan Enter untuk melewati): ").strip()

            lang_map = {"1": "id", "2": "en", "3": "ja"}
            if choice_src in lang_map:
                self.source_language = lang_map[choice_src]
                self.config.set_config_value("translator_plugin", "default_source_language", self.source_language)
                logger.info(f"Bahasa input pengguna diubah ke: {self.source_language}")
            elif choice_src == "":
                logger.info(f"Pilihan bahasa input kosong, tetap menggunakan: {self.source_language}")
            else:
                logger.warning(f"Pilihan bahasa input tidak valid ('{choice_src}'), tetap menggunakan: {self.source_language}")
            print(f"Bahasa input Anda sekarang: {self.source_language}")

            # Pilihan Bahasa Output Alph (Model)
            print(f"\nBahasa output Alph saat ini: {self.target_language}")
            print("Pilih bahasa output untuk Alph:")
            print("1. Bahasa Indonesia (id)")
            print("2. Bahasa Inggris (en)")
            print("3. Bahasa Jepang (ja)")
            choice_target = input("Pilihan (1-3, atau tekan Enter untuk melewati): ").strip()

            if choice_target in lang_map:
                self.target_language = lang_map[choice_target]
                self.config.set_config_value("translator_plugin", "default_target_language", self.target_language)
                logger.info(f"Bahasa output Alph diubah ke: {self.target_language}")
            elif choice_target == "":
                logger.info(f"Pilihan bahasa output kosong, tetap menggunakan: {self.target_language}")
            else:
                logger.warning(f"Pilihan bahasa output tidak valid ('{choice_target}'), tetap menggunakan: {self.target_language}")
            print(f"Bahasa output Alph sekarang: {self.target_language}")
            print("Preferensi bahasa disimpan.")

        except KeyboardInterrupt:
            logger.warning("Pemilihan bahasa diinterupsi oleh pengguna.")
            print("\nPemilihan bahasa dibatalkan.")
        except Exception as e:
            logger.error(f"Error dalam pemilihan bahasa: {e}", exc_info=True)
            print("Terjadi error saat mengatur bahasa.")
            
    def select_role_preferences(self):
        """Memungkinkan pengguna memilih peran default untuk Alph."""
        logger.info("Entering role selection.")
        if not self.available_roles or not isinstance(self.available_roles, list):
            logger.error("Daftar peran tidak tersedia atau tidak valid. Tidak dapat memilih peran.")
            print("Maaf, tidak dapat memuat pilihan peran saat ini.")
            return

        try:
            print(f"\n=== Pengaturan Peran Chat Alph ===")
            print(f"Peran Alph saat ini: {self.current_chat_role}")
            print("Pilih peran untuk Alph:")
            
            for i, role_name in enumerate(self.available_roles):
                print(f"{i+1}. {role_name}")
            
            prompt_text = f"Pilihan (1-{len(self.available_roles)}, atau tekan Enter untuk melewati): "
            choice_input = input(prompt_text).strip()

            if choice_input == "":
                logger.info(f"Pilihan peran kosong, tetap menggunakan: {self.current_chat_role}")
            else:
                try:
                    choice_idx = int(choice_input) - 1
                    if 0 <= choice_idx < len(self.available_roles):
                        self.current_chat_role = self.available_roles[choice_idx]
                        self.config.set_config_value("llm_settings", "default_chat_role", self.current_chat_role)
                        logger.info(f"Peran Alph diubah menjadi: {self.current_chat_role}")
                    else:
                        logger.warning(f"Pilihan peran tidak valid ('{choice_input}'), tetap menggunakan: {self.current_chat_role}")
                except ValueError:
                    logger.warning(f"Input peran bukan angka ('{choice_input}'), tetap menggunakan: {self.current_chat_role}")
            
            print(f"Peran Alph sekarang: {self.current_chat_role}")
            self.config.save_config()
            print("Preferensi peran disimpan.")

        except KeyboardInterrupt:
            logger.warning("Pemilihan peran diinterupsi oleh pengguna.")
            print("\nPemilihan peran dibatalkan.")
        except Exception as e:
            logger.error(f"Error dalam pemilihan peran: {e}", exc_info=True)
            print("Terjadi error saat mengatur peran.")

async def main_async_runner():
    app = VirtualAssistantApp()
    await app.run()

if __name__ == "__main__":
    logger.info("Aplikasi Virtual Assistant dimulai.")
    try:
        asyncio.run(main_async_runner())
    except KeyboardInterrupt:
        logger.info("Aplikasi dihentikan oleh pengguna (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Terjadi error tidak tertangani di level aplikasi utama: {e}", exc_info=True)
    finally:
        logger.info("Aplikasi Virtual Assistant ditutup.")
        print("\nAplikasi ditutup.")