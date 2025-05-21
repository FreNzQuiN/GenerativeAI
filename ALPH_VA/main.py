# main.py
import asyncio, configparser
import os, json, logging
from core import config_manager as app_config
from core import module_manager
from plugins import default_tts

try:
    _cfg_for_paths = app_config.ConfigManager()
    _project_root_from_cfg = _cfg_for_paths.get_config_value(
        "general", "project_root_dir", app_config.PROJECT_ROOT_DIR
    )
    LOG_DIR_MAIN = os.path.join(_project_root_from_cfg, "logs")
except AttributeError:
    print(
        "WARNING: app_config.PROJECT_ROOT_DIR not found, using fallback for LOG_DIR_MAIN."
    )
    LOG_DIR_MAIN = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
    )
except Exception as e_path:
    print(
        "ERROR setting up LOG_DIR_MAIN: %s. Using current directory as fallback.",
        e_path,
    )
    LOG_DIR_MAIN = os.getcwd()


if not os.path.exists(LOG_DIR_MAIN):
    try:
        os.makedirs(LOG_DIR_MAIN, exist_ok=True)
    except OSError as e:
        print("ERROR: Could not create main log directory %s: %s", LOG_DIR_MAIN, e)
        LOG_DIR_MAIN = os.getcwd()

APP_LOG_FILE = os.path.join(LOG_DIR_MAIN, "virtual_assistant.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
    handlers=[
        logging.FileHandler(APP_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class VirtualAssistantApp:
    def __init__(self):
        logger.info("Initializing VirtualAssistantApp...")
        try:
            self.config = app_config.ConfigManager()
            self.manager = module_manager.ModuleManager()
        except Exception as e_init_core:
            logger.critical(
                "Failed to initialize core managers: %s", e_init_core, exc_info=True
            )
            raise RuntimeError(
                f"Critical initialization failed: {e_init_core}"
            ) from e_init_core

        self.language = self.config.get_config_value(
            "general", "interface_language", "id"
        )
        self.source_language = self.config.get_config_value(
            "translator_plugin", "default_source_language", "id"
        )
        self.target_language = self.config.get_config_value(
            "translator_plugin", "default_target_language", "id"
        )

        self.instruction_path = self._get_instruction_path()
        self.available_roles = self._load_available_roles()

        self.default_chat_role = "Assistant"
        if self.available_roles:
            self.default_chat_role = self.config.get_config_value(
                "llm_settings", "default_chat_role", self.available_roles[0]
            )
            if self.default_chat_role not in self.available_roles:
                logger.warning(
                    "Default chat role '%s' from config not in available roles. Using first: %s",
                    self.default_chat_role,
                    self.available_roles[0],
                )
                self.default_chat_role = self.available_roles[0]
        self.current_chat_role = self.default_chat_role
        self.current_audio_call_role = self.current_chat_role

        self.language_model_instance = self._init_language_model()
        self.context_manager_instance = self._init_context_manager()
        self.translator_plugin_instance = self._init_translator_plugin()
        self.stt_processor_instance = self._init_stt_processor()
        # self.tts_plugin_instance = self._init_tts_plugin("default_tts")

        logger.info("VirtualAssistantApp initialized successfully.")

    def _get_instruction_path(self) -> str:
        """Mendapatkan path ke file instruksi LLM dari config."""
        try:
            project_root_for_instr = self.config.get_config_value(
                "general", "project_root_dir", app_config.PROJECT_ROOT_DIR
            )
            default_instr_filename = "config/llm_instructions.json"

            path_val = self.config.get_config_value(
                "llm_settings", "instruction_path", default_instr_filename
            )
            if os.path.isabs(path_val):
                return path_val
            return os.path.join(project_root_for_instr, path_val)
        except Exception as e:
            logger.error(
                "Error getting instruction_path: %s. Using fallback.", e, exc_info=False
            )
            return os.path.join(
                app_config.PROJECT_ROOT_DIR, "config", "llm_instructions.json"
            )

    def _load_available_roles(self) -> list[str]:
        """Memuat daftar nama peran yang tersedia dari file llm_instructions.json."""
        if not self.instruction_path or not os.path.exists(self.instruction_path):
            logger.error(
                "Instruction file not found at %s. Cannot load available roles.",
                self.instruction_path,
            )
            return ["Assistant"]

        try:
            with open(self.instruction_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            roles = list(data.keys())
            if not roles:
                logger.warning(
                    "No roles found in %s. Using default 'Assistant'.",
                    self.instruction_path,
                )
                return ["Assistant"]
            logger.info("Available roles loaded: %s", roles)
            return roles
        except json.JSONDecodeError as e:
            logger.error(
                "Error decoding JSON from %s: %s. Using default 'Assistant'.",
                self.instruction_path,
                e,
                exc_info=True,
            )
            return ["Assistant"]
        except OSError as e:
            logger.error(
                "OSError loading available roles from %s: %s. Using default 'Assistant'.",
                self.instruction_path,
                e,
                exc_info=True,
            )
            return ["Assistant"]
        except Exception as e:
            logger.error(
                "Unexpected error loading available roles from %s: %s. Using default 'Assistant'.",
                self.instruction_path,
                e,
                exc_info=True,
            )
            return ["Assistant"]

    def _init_language_model(self):
        """Helper untuk inisialisasi LanguageModel."""
        lm_module = self.manager.get_core_module("language_model")
        if lm_module and hasattr(lm_module, "LanguageModel"):
            try:
                instance = lm_module.LanguageModel(default_role=self.default_chat_role)
                logger.info(
                    "LanguageModel instance created successfully with default role: %s.",
                    self.default_chat_role,
                )
                return instance
            except (
                ImportError,
                AttributeError,
                TypeError,
                RuntimeError,
            ) as e:
                logger.error(
                    "Failed to instantiate LanguageModel: %s", e, exc_info=True
                )
        else:
            logger.error(
                "Core module 'language_model' not loaded or does not have LanguageModel class."
            )
        return None

    def _init_context_manager(self):
        """Helper untuk inisialisasi ContextManager."""
        cm_module = self.manager.get_core_module("context_manager")
        if cm_module and hasattr(cm_module, "ContextManager"):
            try:
                instance = cm_module.ContextManager()
                logger.info(
                    "Active ContextManager instance created (session: %s).",
                    instance.session_id,
                )
                return instance
            except (ImportError, AttributeError, TypeError) as e:
                logger.error(
                    "Failed to instantiate ContextManager: %s", e, exc_info=True
                )
        else:
            logger.error(
                "Core module 'context_manager' not loaded or does not have ContextManager class."
            )
        return None

    def _init_translator_plugin(self):
        """Helper untuk inisialisasi TranslatorPlugin."""
        translator_module = self.manager.get_plugin("translator")
        if translator_module and hasattr(translator_module, "TranslationPlugin"):
            try:
                instance = translator_module.TranslationPlugin()
                if instance:
                    logger.info("TranslationPlugin instance obtained successfully.")
                    return instance
                else:
                    logger.error(
                        "TranslationPlugin() from translator module returned None."
                    )
            except Exception as e:
                logger.error(
                    "Failed to get/instantiate TranslationPlugin: %s", e, exc_info=True
                )
        else:
            logger.error("Plugin 'translator' not loaded.")
        return None

    def _init_stt_processor(self):
        stt_module = self.manager.get_core_module("speech_to_text")
        if stt_module and hasattr(stt_module, "get_stt_processor"):
            try:
                instance = stt_module.get_stt_processor(adjust_noise_on_first_get=True)
                if instance:
                    logger.info("STTProcessor instance obtained.")
                    return instance
                else:
                    logger.error("get_stt_processor() returned None.")
            except RuntimeError as e:
                logger.error("RuntimeError getting STTProcessor: %s", e, exc_info=True)
            except Exception as e:
                logger.error("Failed to get STTProcessor: %s", e, exc_info=True)
        else:
            logger.error("Core module 'speech_to_text' not loaded/valid.")
        return None

    async def run(self):
        logger.info("VA App Run method started.")
        self.select_language_preferences()
        self.select_role_preferences()

        while True:
            print("\n=== Menu Utama Virtual Assistant ===")
            print("1. Chat dengan Gemini")
            print("2. Terjemahkan Kalimat")
            print("3. Panggilan Suara (STT-TTS)")
            print("4. Pengaturan Bahasa")
            print("5. Pengaturan Peran Chat")
            print("6. Keluar")

            prompt_menu = "Pilih mode (1-6) (Bhs: %s, Peran Chat: %s): " % (
                self.source_language,
                self.current_chat_role,
            )
            choice = await asyncio.to_thread(input, prompt_menu)

            if choice == "1":
                await self.mode_chat_gemini()
            elif choice == "2":
                await self.mode_translate_sentence()
            elif choice == "3":
                await self.mode_audio_call()
            elif choice == "4":
                self.select_language_preferences()
            elif choice == "5":
                self.select_role_preferences(context="chat")
            elif choice == "6":
                logger.info("Pengguna memilih keluar dari aplikasi.")
                print("Terima kasih telah menggunakan asisten virtual!")
                if (
                    self.context_manager_instance
                    and not self.context_manager_instance.save_to_archive()
                ):
                    logger.error(
                        "Gagal menyimpan sesi aktif %s sebelum keluar.",
                        self.context_manager_instance.session_id,
                    )
                else:
                    logger.info(
                        "Sesi aktif %s disimpan.",
                        (
                            self.context_manager_instance.session_id
                            if self.context_manager_instance
                            else "N/A"
                        ),
                    )
                break
            else:
                logger.warning("Pilihan menu tidak valid: %s", choice)
                print("Pilihan tidak valid, silakan coba lagi.")
            await asyncio.sleep(0.1)

    async def mode_chat_gemini(self):
        if not self.language_model_instance:
            logger.error(
                "LanguageModel instance not available. Cannot start chat mode."
            )
            print("Model bahasa tidak tersedia. Mode chat tidak dapat dimulai.")
            return
        if not self.context_manager_instance:
            logger.error(
                "Main ContextManager instance not available. Cannot start chat mode."
            )
            print(
                "Manajer konteks utama tidak tersedia. Mode chat tidak dapat dimulai."
            )
            return

        active_chat_session_cm = self.context_manager_instance

        logger.info(
            "Entering chat mode. Initial Session: %s, Target Lang: %s, Source Lang: %s, Chat Role: %s",
            active_chat_session_cm.session_id,
            self.target_language,
            self.source_language,
            self.current_chat_role,
        )
        print(
            f"\n=== Mode Chat (Peran: {self.current_chat_role}, Output: {self.target_language}, Input: {self.source_language}) ==="
        )
        print("Sesi saat ini: %s" % active_chat_session_cm.session_id)
        print(
            "Perintah: 'exit'/'quit', 'delete'/'hapus' (sesi baru), 'load'/'muat' (sesi terakhir), 'load N' (sesi ke-N dari terakhir)."
        )

        while True:
            prompt_user = "[User (%s)]: " % self.source_language
            user_input = await asyncio.to_thread(input, prompt_user)
            user_input_strip = user_input.strip()
            user_input_lower = user_input_strip.lower()

            if user_input_lower in ["exit", "quit", "keluar"]:
                logger.info(
                    "Pengguna keluar dari mode chat. Menyimpan sesi aktif %s.",
                    active_chat_session_cm.session_id,
                )
                if not active_chat_session_cm.save_to_archive():
                    logger.error(
                        "Gagal menyimpan sesi %s saat keluar dari mode chat.",
                        active_chat_session_cm.session_id,
                    )
                print("Keluar dari mode chat. Sesi disimpan.")
                if (
                    self.context_manager_instance.session_id
                    != active_chat_session_cm.session_id
                ):
                    self.context_manager_instance = active_chat_session_cm
                break

            if user_input_lower in ["delete", "del", "hapus"]:
                session_id_to_delete = active_chat_session_cm.session_id
                logger.info(
                    "Pengguna meminta penghapusan sesi %s dari arsip.",
                    session_id_to_delete,
                )
                print(f"Menghapus sesi {session_id_to_delete} dari arsip...")

                if active_chat_session_cm.delete_from_archive():
                    logger.info(
                        "Sesi %s berhasil dihapus dari arsip.", session_id_to_delete
                    )
                    print(f"Sesi {session_id_to_delete} berhasil dihapus.")
                else:
                    logger.warning(
                        "Gagal menghapus sesi %s dari arsip atau sesi tidak ditemukan.",
                        session_id_to_delete,
                    )
                    print(
                        f"Gagal menghapus sesi {session_id_to_delete} atau sesi tidak ditemukan di arsip."
                    )

                print("Memulai sesi baru...")
                new_cm_instance = self._init_context_manager()
                if not new_cm_instance:
                    print(
                        "Gagal memulai sesi baru karena error internal. Mode chat mungkin tidak stabil."
                    )
                    logger.critical(
                        "Gagal re-inisialisasi ContextManager setelah delete command."
                    )
                else:
                    active_chat_session_cm = new_cm_instance
                    self.context_manager_instance = active_chat_session_cm
                    logger.info(
                        "Sesi baru dimulai: %s", active_chat_session_cm.session_id
                    )
                    print(f"Sesi baru dimulai: {active_chat_session_cm.session_id}")
                continue

            load_command_triggered = False
            session_index_to_load = -1

            if user_input_lower.startswith("load ") or user_input_lower.startswith(
                "muat "
            ):
                parts = user_input_strip.split()
                if len(parts) == 2:
                    try:
                        raw_index = int(parts[1])
                        if raw_index > 0:
                            session_index_to_load = raw_index
                        elif raw_index < 0:
                            session_index_to_load = abs(raw_index)
                        else:
                            print(
                                "Indeks sesi tidak valid (tidak boleh 0). Memuat sesi terakhir."
                            )
                            session_index_to_load = 1
                        load_command_triggered = True
                    except ValueError:
                        print(
                            "Perintah 'load' diikuti angka yang tidak valid. Contoh: 'load 2'. Memuat sesi terakhir."
                        )
                        session_index_to_load = 1
                        load_command_triggered = True
                else:
                    session_index_to_load = 1
                    load_command_triggered = True
            elif user_input_lower in ["load", "muat"]:
                session_index_to_load = 1
                load_command_triggered = True

            if load_command_triggered:
                cm_class_from_module = None
                cm_module_for_load = self.manager.get_core_module("context_manager")
                if cm_module_for_load and hasattr(cm_module_for_load, "ContextManager"):
                    cm_class_from_module = cm_module_for_load.ContextManager

                if cm_class_from_module:
                    list_of_sessions = cm_class_from_module.list_sessions()
                    if list_of_sessions:
                        if 0 < session_index_to_load <= len(list_of_sessions):
                            target_python_index = session_index_to_load - 1
                            session_id_to_load = list_of_sessions[target_python_index][
                                "session_id"
                            ]

                            logger.info(
                                "Attempting to load session %d from last (ID: %s)",
                                session_index_to_load,
                                session_id_to_load,
                            )
                            print(
                                f"\nMemuat sesi ke-{session_index_to_load} dari terakhir (ID: {session_id_to_load})..."
                            )

                            loaded_cm_instance = cm_class_from_module.load_from_archive(
                                session_id_to_load
                            )
                            if loaded_cm_instance:
                                active_chat_session_cm = loaded_cm_instance
                                self.context_manager_instance = active_chat_session_cm
                                logger.info(
                                    "Successfully loaded session '%s'. User: '%s'. History: %d messages.",
                                    active_chat_session_cm.session_id,
                                    active_chat_session_cm.user,
                                    len(active_chat_session_cm.retrieve()),
                                )
                                print(
                                    f"Berhasil memuat sesi '{active_chat_session_cm.session_id}'."
                                )
                                print(
                                    f"Sesi saat ini: {active_chat_session_cm.session_id}"
                                )
                            else:
                                logger.warning(
                                    "Failed to load session ID %s.", session_id_to_load
                                )
                                print(
                                    f"Gagal memuat sesi dengan ID '{session_id_to_load}'. Tetap di sesi saat ini."
                                )
                        else:
                            logger.warning(
                                "Requested session index %d is out of bounds (1 to %d).",
                                session_index_to_load,
                                len(list_of_sessions),
                            )
                            print(
                                f"Indeks sesi tidak valid. Hanya ada {len(list_of_sessions)} sesi tersimpan. Tetap di sesi saat ini."
                            )
                    else:
                        logger.info("No saved sessions found to load.")
                        print("Tidak ada sesi tersimpan yang bisa dimuat.")
                else:
                    logger.error(
                        "ContextManager class not available for loading session."
                    )
                    print("Gagal mengakses manajer konteks untuk memuat sesi.")
                continue

            if not user_input_strip:
                continue

            try:
                chat_history_content = active_chat_session_cm.retrieve()

                input_for_lm = user_input_strip
                if self.source_language.lower() != self.target_language.lower():
                    if not self.translator_plugin_instance:
                        logger.warning(
                            "Translator tidak tersedia, menggunakan input asli untuk LM."
                        )
                    else:
                        logger.info(
                            "Translating user input from '%s' to '%s'.",
                            self.source_language,
                            self.target_language,
                        )
                        translated_input = (
                            await self.translator_plugin_instance.translate(
                                user_input_strip,
                                target_lang=self.target_language,
                                source_lang=self.source_language,
                            )
                        )
                        if translated_input and translated_input != user_input_strip:
                            input_for_lm = translated_input
                            logger.info(
                                "Input for LM (after translation): %s...",
                                input_for_lm[:50],
                            )
                        elif not translated_input:
                            logger.warning(
                                "User input translation failed/empty, using original input for LM."
                            )

                response_from_lm = self.language_model_instance.generate_response(
                    language=self.target_language,
                    prompt=input_for_lm,
                    chat_history=chat_history_content,
                    role_override=self.current_chat_role,
                    task="FULL",
                )
                response_from_lm_clean = " ".join(response_from_lm.split())
                logger.info(
                    "Response from LM (in %s, role %s): %s...",
                    self.target_language,
                    self.current_chat_role,
                    response_from_lm_clean[:100],
                )

                final_response_for_user = response_from_lm_clean
                if self.target_language.lower() != self.source_language.lower():
                    if not self.translator_plugin_instance:
                        logger.warning(
                            "Translator tidak tersedia, menampilkan output LM asli kepada pengguna."
                        )
                    else:
                        logger.info(
                            "Translating LM response from '%s' to '%s'.",
                            self.target_language,
                            self.source_language,
                        )
                        translated_response = (
                            await self.translator_plugin_instance.translate(
                                response_from_lm_clean,
                                target_lang=self.source_language,
                                source_lang=self.target_language,
                            )
                        )
                        if (
                            translated_response
                            and translated_response != response_from_lm_clean
                        ):
                            final_response_for_user = translated_response
                        elif not translated_response:
                            logger.warning(
                                "LM response translation failed/empty, using original LM response for user."
                            )

                print(f"[Alph ({self.target_language})]: {response_from_lm_clean}")
                if (
                    final_response_for_user.lower() != response_from_lm_clean.lower()
                    and self.target_language.lower() != self.source_language.lower()
                ):
                    print(f"[Alph ({self.source_language})]: {final_response_for_user}")

                if not response_from_lm.startswith("[Gemini Error]"):
                    active_chat_session_cm.remember("user", user_input_strip)
                    active_chat_session_cm.remember("model", response_from_lm)
            except ConnectionError as e_conn:
                logger.error("Connection error during chat: %s", e_conn, exc_info=True)
                print("Gagal terhubung ke layanan. Periksa koneksi internet Anda.")
            except TimeoutError as e_timeout:
                logger.error("Timeout error during chat: %s", e_timeout, exc_info=True)
                print("Waktu respons habis. Coba lagi nanti.")
            except RuntimeError as e_rt:
                logger.error("Runtime error during chat: %s", e_rt, exc_info=True)
                print(f"Terjadi kesalahan runtime: {e_rt}")
            except Exception as e:
                logger.error("Unexpected error in chat mode: %s", e, exc_info=True)
                print("Terjadi kesalahan tak terduga saat berkomunikasi.")

    async def mode_translate_sentence(self):
        logger.info("Entering sentence translation mode.")
        if not self.translator_plugin_instance:
            logger.error("Translator plugin not available for translation mode.")
            print("Layanan penerjemah tidak tersedia saat ini.")
            return

        print("\n=== Mode Terjemahkan Kalimat ===")
        print(
            f"Bahasa sumber default: {self.source_language}, Bahasa target default: {self.target_language}"
        )
        print("Anda bisa mengubah bahasa default melalui menu Pengaturan Bahasa.")
        print("Ketik 'exit' atau 'quit' untuk kembali ke menu utama.")

        while True:
            text_to_translate = (
                await asyncio.to_thread(input, "Masukkan teks untuk diterjemahkan: ")
            ).strip()
            if text_to_translate.lower() in ["exit", "quit", "keluar"]:
                logger.info("Exiting translation mode.")
                break
            if not text_to_translate:
                continue

            src_lang = input("Bahasa Input: ")
            if src_lang == "":
                self.source_language
            tgt_lang = input("Bahasa Target: ")
            if tgt_lang == "":
                self.target_language

            if src_lang.lower() == tgt_lang.lower():
                print(
                    f"Hasil ({tgt_lang}): {text_to_translate} (bahasa sumber dan target sama)"
                )
                continue

            print(f"Menerjemahkan dari {src_lang} ke {tgt_lang}...")
            translated_text = await self.translator_plugin_instance.translate(
                text_to_translate, tgt_lang, src_lang
            )

            if translated_text is not None:
                print(f"Hasil ({tgt_lang}): {translated_text}")
            else:
                print("Gagal menerjemahkan teks.")
            print("-" * 20)

    def select_language_preferences(self):
        logger.info("Entering language selection.")
        try:
            print("\n=== Pengaturan Bahasa ===")
            lang_options = {
                "1": ("Bahasa Indonesia", "id"),
                "2": ("Bahasa Inggris", "en"),
                "3": ("Bahasa Jepang", "ja"),
            }

            print(f"Bahasa input Anda saat ini: {self.source_language}")
            print("Pilih bahasa input Anda:")
            for k, (name, _) in lang_options.items():
                print(f"{k}. {name}")
            choice_src = input(
                f"Pilihan (1-{len(lang_options)}, atau tekan Enter untuk melewati): "
            ).strip()

            if choice_src in lang_options:
                self.source_language = lang_options[choice_src][1]
                self.config.set_config_value(
                    "translator_plugin", "default_source_language", self.source_language
                )
                logger.info("Bahasa input pengguna diubah ke: %s", self.source_language)
            elif choice_src != "":
                logger.warning(
                    "Pilihan bahasa input tidak valid ('%s'), tetap menggunakan: %s",
                    choice_src,
                    self.source_language,
                )
            print(f"Bahasa input Anda sekarang: {self.source_language}")
            print(f"\nBahasa output Alph saat ini: {self.target_language}")
            print("Pilih bahasa output untuk Alph:")
            for k, (name, _) in lang_options.items():
                print(f"{k}. {name}")
            choice_target = input(
                f"Pilihan (1-{len(lang_options)}, atau tekan Enter untuk melewati): "
            ).strip()

            if choice_target in lang_options:
                self.target_language = lang_options[choice_target][1]
                self.config.set_config_value(
                    "translator_plugin", "default_target_language", self.target_language
                )
                logger.info("Bahasa output Alph diubah ke: %s", self.target_language)
            elif choice_target != "":
                logger.warning(
                    "Pilihan bahasa output tidak valid ('%s'), tetap menggunakan: %s",
                    choice_target,
                    self.target_language,
                )
            print(f"Bahasa output Alph sekarang: {self.target_language}")

            if not self.config.save_config():
                logger.error("Gagal menyimpan preferensi bahasa ke file konfigurasi.")
            else:
                print("Preferensi bahasa disimpan.")

            if (
                self.source_language.lower() != self.target_language.lower()
                and not self.translator_plugin_instance
            ):
                logger.info(
                    "Source and target languages now differ, attempting to initialize translator."
                )
                self.translator_plugin_instance = self._init_translator_plugin()
            elif (
                self.source_language.lower() == self.target_language.lower()
                and self.translator_plugin_instance
            ):
                logger.info(
                    "Source and target languages are now the same. Translator instance might not be needed."
                )

        except KeyboardInterrupt:
            logger.warning("Pemilihan bahasa diinterupsi oleh pengguna.")
            print("\nPemilihan bahasa dibatalkan.")
        except (configparser.Error, OSError) as e_cfg:
            logger.error(
                "Error terkait konfigurasi/file saat pemilihan bahasa: %s",
                e_cfg,
                exc_info=True,
            )
            print("Terjadi error saat menyimpan atau membaca konfigurasi bahasa.")
        except Exception as e:
            logger.error(
                "Error tidak terduga dalam pemilihan bahasa: %s", e, exc_info=True
            )
            print("Terjadi error tidak terduga saat mengatur bahasa.")

    def select_role_preferences(self):
        logger.info("Entering role selection.")
        if not self.available_roles:
            logger.error("Daftar peran tidak tersedia. Tidak dapat memilih peran.")
            print("Maaf, tidak dapat memuat pilihan peran saat ini.")
            return

        try:
            print("\n=== Pengaturan Peran Chat Alph ===")
            print(f"Peran Alph saat ini: {self.current_chat_role}")
            print("Pilih peran untuk Alph:")

            for i, role_name in enumerate(self.available_roles):
                print(f"{i+1}. {role_name}")

            prompt_text = f"Pilihan (1-{len(self.available_roles)}, atau tekan Enter untuk melewati): "
            choice_input = input(prompt_text).strip()

            if choice_input == "":
                logger.info(
                    "Pilihan peran kosong, tetap menggunakan: %s",
                    self.current_chat_role,
                )
            else:
                try:
                    choice_idx = int(choice_input) - 1
                    if 0 <= choice_idx < len(self.available_roles):
                        new_role = self.available_roles[choice_idx]
                        self.current_chat_role = new_role
                        self.config.set_config_value(
                            "llm_settings", "default_chat_role", new_role
                        )
                        if self.language_model_instance and hasattr(
                            self.language_model_instance, "default_role"
                        ):
                            self.language_model_instance.default_role = new_role
                            logger.info(
                                "Default role LanguageModel juga diupdate ke: %s",
                                new_role,
                            )
                        logger.info("Peran Alph diubah menjadi: %s", new_role)
                    else:
                        logger.warning(
                            "Pilihan peran tidak valid ('%s'), tetap menggunakan: %s",
                            choice_input,
                            self.current_chat_role,
                        )
                except ValueError:
                    logger.warning(
                        "Input peran bukan angka ('%s'), tetap menggunakan: %s",
                        choice_input,
                        self.current_chat_role,
                    )

            print(f"Peran Alph sekarang: {self.current_chat_role}")
            if not self.config.save_config():
                logger.error("Gagal menyimpan preferensi peran ke file konfigurasi.")
            else:
                print("Preferensi peran disimpan.")

        except KeyboardInterrupt:
            logger.warning("Pemilihan peran diinterupsi oleh pengguna.")
            print("\nPemilihan peran dibatalkan.")
        except (configparser.Error, OSError) as e_cfg:
            logger.error(
                "Error terkait konfigurasi/file saat pemilihan peran: %s",
                e_cfg,
                exc_info=True,
            )
            print("Terjadi error saat menyimpan atau membaca konfigurasi peran.")
        except Exception as e:
            logger.error(
                "Error tidak terduga dalam pemilihan peran: %s", e, exc_info=True
            )
            print("Terjadi error tidak terduga saat mengatur peran.")

    async def mode_audio_call(self):
        logger.info("Entering audio call mode.")
        if not self.stt_processor_instance:
            logger.error("STT processor not available for audio call mode.")
            print("Layanan pengenalan suara tidak tersedia.")
            return
        if not self.language_model_instance:
            logger.error("Language model not available for audio call mode.")
            print("Model bahasa tidak tersedia.")
            return

        call_cm_module = self.manager.get_core_module("context_manager")
        if not call_cm_module or not hasattr(call_cm_module, "ContextManager"):
            logger.error("Cannot create ContextManager for audio call.")
            print("Gagal memulai sesi konteks untuk panggilan suara.")
            return

        current_call_context = call_cm_module.ContextManager()
        current_call_role = self.current_audio_call_role

        print(f"\n=== Mode Panggilan Suara (Peran Alph: {current_call_role}) ===")
        print("Katakan 'Alpha keluar' untuk mengakhiri panggilan.")
        print("Katakan 'Alpha diam' untuk mute/unmute STT.")
        print("Katakan 'Alpha ganti peran' untuk memilih peran baru.")

        stt_active = True
        initial_greeting = f"Halo! Anda terhubung dengan Alph (peran: {current_call_role}). Ada yang bisa saya bantu?"
        if self.target_language.lower() != "id":
            if self.translator_plugin_instance:
                translated_greeting = await self.translator_plugin_instance.translate(
                    initial_greeting, self.target_language, "id"
                )
                if translated_greeting:
                    initial_greeting = translated_greeting

        print(f"[Alph ({self.target_language})]: {initial_greeting}")
        try:
            await asyncio.to_thread(
                default_tts.speak_text_sync,
                initial_greeting,
                language_code=self.target_language,
            )
        except Exception as e_tts_greet:
            logger.error("Failed to speak initial greeting: %s", e_tts_greet)

        while True:
            if not stt_active:
                cmd_input = (
                    (
                        await asyncio.to_thread(
                            input,
                            "STT Mute. Ketik 'on' untuk aktifkan, 'keluar', 'ganti peran': ",
                        )
                    )
                    .strip()
                    .lower()
                )
                if cmd_input == "on":
                    stt_active = True
                    print("STT diaktifkan.")
                    logger.info("Audio call STT unmuted by user.")
                elif cmd_input == "keluar":
                    logger.info("Audio call ended by user command while muted.")
                    break
                elif cmd_input == "ganti peran":
                    print("Mengganti peran Alph...")
                    self.select_role_preferences(context="call")
                    current_call_role = self.current_audio_call_role
                    current_call_context = call_cm_module.ContextManager()
                    print(
                        f"Peran Alph diubah menjadi {current_call_role}. Sesi panggilan direset."
                    )
                    logger.info(
                        "Audio call role changed to %s, context reset.",
                        current_call_role,
                    )
                else:
                    print("Perintah tidak dikenal saat STT mute.")
                continue

            print("Mendengarkan...")
            user_speech = self.stt_processor_instance.listen_and_recognize(
                language=self.source_language
            )

            if user_speech is None:
                logger.debug("STT returned None (timeout or no speech).")
                continue

            print(f"[User ({self.source_language})]: {user_speech}")
            logger.info("STT recognized: %s", user_speech)

            user_speech_lower = user_speech.lower()
            if (
                "alpha keluar" in user_speech_lower
                or "alfa keluar" in user_speech_lower
            ):
                logger.info("Audio call ended by voice command 'Alpha keluar'.")
                farewell_msg = "Baik, panggilan diakhiri."
                if (
                    self.target_language.lower() != "id"
                    and self.translator_plugin_instance
                ):
                    translated_farewell = (
                        await self.translator_plugin_instance.translate(
                            farewell_msg, self.target_language, "id"
                        )
                    )
                    if translated_farewell:
                        farewell_msg = translated_farewell
                print(f"[Alph ({self.target_language})]: {farewell_msg}")
                try:
                    await asyncio.to_thread(
                        default_tts.speak_text_sync,
                        farewell_msg,
                        language_code=self.target_language,
                    )
                except Exception as e_tts_bye:
                    logger.error("Failed to speak farewell: %s", e_tts_bye)
                break

            if "alpha diam" in user_speech_lower or "alfa diam" in user_speech_lower:
                stt_active = not stt_active
                status_msg = (
                    "STT di-mute." if not stt_active else "STT diaktifkan kembali."
                )
                logger.info(
                    "Audio call STT status toggled by voice command. Active: %s",
                    stt_active,
                )
                if (
                    self.target_language.lower() != "id"
                    and self.translator_plugin_instance
                ):
                    translated_status = await self.translator_plugin_instance.translate(
                        status_msg, self.target_language, "id"
                    )
                    if translated_status:
                        status_msg = translated_status
                print(f"[Alph ({self.target_language})]: {status_msg}")
                try:
                    await asyncio.to_thread(
                        default_tts.speak_text_sync,
                        status_msg,
                        language_code=self.target_language,
                    )
                except Exception as e_tts_mute:
                    logger.error("Failed to speak mute status: %s", e_tts_mute)
                continue

            if (
                "alpha ganti peran" in user_speech_lower
                or "alfa ganti peran" in user_speech_lower
            ):
                logger.info("Audio call role change requested by voice command.")
                role_change_ack = "Baik, silakan pilih peran baru melalui input teks."
                if (
                    self.target_language.lower() != "id"
                    and self.translator_plugin_instance
                ):
                    translated_ack = await self.translator_plugin_instance.translate(
                        role_change_ack, self.target_language, "id"
                    )
                    if translated_ack:
                        role_change_ack = translated_ack
                print(f"[Alph ({self.target_language})]: {role_change_ack}")
                try:
                    await asyncio.to_thread(
                        default_tts.speak_text_sync,
                        role_change_ack,
                        language_code=self.target_language,
                    )
                except Exception as e_tts_role:
                    logger.error("Failed to speak role change ack: %s", e_tts_role)

                stt_active = False
                self.select_role_preferences(context="call")
                current_call_role = self.current_audio_call_role
                current_call_context = call_cm_module.ContextManager()

                role_changed_msg = f"Peran Alph diubah menjadi {current_call_role}. Sesi panggilan direset. Anda bisa bicara lagi."
                if (
                    self.target_language.lower() != "id"
                    and self.translator_plugin_instance
                ):
                    translated_changed = (
                        await self.translator_plugin_instance.translate(
                            role_changed_msg, self.target_language, "id"
                        )
                    )
                    if translated_changed:
                        role_changed_msg = translated_changed
                print(f"[Alph ({self.target_language})]: {role_changed_msg}")
                try:
                    await asyncio.to_thread(
                        default_tts.speak_text_sync,
                        role_changed_msg,
                        language_code=self.target_language,
                    )
                except Exception as e_tts_done_role:
                    logger.error(
                        "Failed to speak role changed msg: %s", e_tts_done_role
                    )
                stt_active = True
                continue

            try:
                input_for_lm = user_speech
                if (
                    self.source_language.lower() != self.target_language.lower()
                    and self.translator_plugin_instance
                ):
                    translated_stt = await self.translator_plugin_instance.translate(
                        user_speech, self.target_language, self.source_language
                    )
                    if translated_stt:
                        input_for_lm = translated_stt

                call_history = current_call_context.retrieve()
                response_lm = self.language_model_instance.generate_response(
                    self.target_language, input_for_lm, call_history, current_call_role
                )
                response_lm_clean = " ".join(response_lm.split())

                print(f"[Alph ({self.target_language})]: {response_lm_clean}")
                await asyncio.to_thread(
                    default_tts.speak_text_sync,
                    response_lm_clean,
                    language_code=self.target_language,
                )

                if not response_lm.startswith("[Gemini Error]"):
                    current_call_context.remember("user", user_speech)
                    current_call_context.remember("model", response_lm)
            except Exception as e_call_logic:
                logger.error(
                    "Error during audio call logic: %s", e_call_logic, exc_info=True
                )
                error_msg = "Maaf, terjadi sedikit gangguan."
                if (
                    self.target_language.lower() != "id"
                    and self.translator_plugin_instance
                ):
                    translated_err = await self.translator_plugin_instance.translate(
                        error_msg, self.target_language, "id"
                    )
                    if translated_err:
                        error_msg = translated_err
                print(f"[Alph ({self.target_language})]: {error_msg}")
                try:
                    await asyncio.to_thread(
                        default_tts.speak_text_sync,
                        error_msg,
                        language_code=self.target_language,
                    )
                except Exception as e_tts_err:
                    logger.error("Failed to speak error message: %s", e_tts_err)


# --- Main execution ---
async def main_async_runner():
    try:
        app = VirtualAssistantApp()
        await app.run()
    except RuntimeError as e_critical_init:
        logger.critical(
            "Gagal menginisialisasi aplikasi secara kritikal: %s",
            e_critical_init,
            exc_info=True,
        )
        print(f"APLIKASI GAGAL DIMULAI: {e_critical_init}")
    except Exception as e_global_app:
        logger.critical(
            "Error fatal tidak tertangani di level aplikasi: %s",
            e_global_app,
            exc_info=True,
        )
        print(f"APLIKASI MENGALAMI ERROR FATAL: {e_global_app}")


if __name__ == "__main__":
    logger.info("Aplikasi Virtual Assistant dimulai.")
    try:
        asyncio.run(main_async_runner())
    except KeyboardInterrupt:
        logger.info("Aplikasi dihentikan oleh pengguna (KeyboardInterrupt).")
    finally:
        logger.info("Aplikasi Virtual Assistant ditutup.")
        print("\nAplikasi ditutup.")
