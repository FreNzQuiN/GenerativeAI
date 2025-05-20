# main.py
import asyncio, configparser
import os, json, logging
from core import config_manager as app_config
from core import module_manager

# --- Setup Logging ---
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
    )  # Fallback
except Exception as e_path:  # Tangkap error lain saat setup path
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
                "Failed to initialize core managers (ConfigManager or ModuleManager): %s",
                e_init_core,
                exc_info=True,
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
                    "Default chat role '%s' from config not in available roles. Using first available: %s",
                    self.default_chat_role,
                    self.available_roles[0],
                )
                self.default_chat_role = self.available_roles[0]
        self.current_chat_role = self.default_chat_role

        self.language_model_instance = self._init_language_model()
        self.context_manager_instance = self._init_context_manager()
        self.translator_plugin_instance = self._init_translator_plugin()

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
        except OSError as e:  # Lebih spesifik untuk error file I/O
            logger.error(
                "OSError loading available roles from %s: %s. Using default 'Assistant'.",
                self.instruction_path,
                e,
                exc_info=True,
            )
            return ["Assistant"]
        except Exception as e:  # Tangkap error umum lainnya
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
            ) as e:  # RuntimeError dari LM jika API key salah
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
        # Hanya inisialisasi jika benar-benar dibutuhkan (bahasa berbeda)
        if self.target_language.lower() == self.source_language.lower():
            logger.info(
                "Source and target languages are the same. Translator plugin not initialized."
            )
            return None

        translator_module = self.manager.get_plugin("translator")
        if translator_module and hasattr(translator_module, "get_translator_plugin"):
            try:
                instance = translator_module.get_translator_plugin()
                if instance:
                    logger.info("TranslationPlugin instance obtained successfully.")
                    return instance
                else:
                    logger.error(
                        "get_translator_plugin() from translator module returned None."
                    )
            except (
                Exception
            ) as e:  # Bisa jadi error koneksi saat get_translator_plugin()
                logger.error(
                    "Failed to get/instantiate TranslationPlugin: %s", e, exc_info=True
                )
        else:
            logger.error(
                "Plugin 'translator' not loaded or does not have get_translator_plugin function."
            )
        return None

    async def run(self):
        logger.info("VA App Run method started.")
        self.select_language_preferences()
        self.select_role_preferences()

        while True:
            print("\n=== Menu Utama Virtual Assistant ===")
            print("1. Chat dengan Gemini")
            print("2. Terjemahkan Kalimat (Belum tersedia)")
            print("3. Panggilan Suara (STT-TTS) (Belum tersedia)")
            print("4. Pengaturan Bahasa")
            print("5. Pengaturan Peran Chat")
            print("6. Keluar")

            prompt_menu = "Pilih mode (1-6) (Bahasa: %s, Peran: %s): " % (
                self.source_language,
                self.current_chat_role,
            )
            choice = await asyncio.to_thread(input, prompt_menu)

            if choice == "1":
                await self.mode_chat_gemini()
            elif choice == "4":
                self.select_language_preferences()
            elif choice == "5":
                self.select_role_preferences()
            elif choice == "6":
                logger.info("Pengguna memilih keluar dari aplikasi.")
                print("Terima kasih telah menggunakan asisten virtual!")
                if self.context_manager_instance:
                    # save_to_archive sekarang mengembalikan bool
                    if not self.context_manager_instance.save_to_archive():
                        logger.error(
                            "Gagal menyimpan sesi aktif %s sebelum keluar.",
                            self.context_manager_instance.session_id,
                        )
                    else:
                        logger.info(
                            "Sesi aktif %s disimpan sebelum keluar.",
                            self.context_manager_instance.session_id,
                        )
                break
            elif choice in ["2", "3"]:
                logger.info(
                    "Pengguna memilih opsi '%s' yang belum diimplementasikan.", choice
                )
                print("Fitur ini belum tersedia, silakan pilih opsi lain.")
            else:
                logger.warning("Pilihan menu tidak valid: %s", choice)
                print("Pilihan tidak valid, silakan coba lagi.")
            await asyncio.sleep(0.1)

    async def mode_chat_gemini(self):
        if not self.language_model_instance:
            logger.error(
                "LanguageModel instance is not available. Cannot start chat mode."
            )
            print("Model bahasa tidak tersedia. Mode chat tidak dapat dimulai.")
            return
        if not self.context_manager_instance:
            logger.error(
                "ContextManager instance is not available. Cannot start chat mode."
            )
            print("Manajer konteks tidak tersedia. Mode chat tidak dapat dimulai.")
            return

        logger.info(
            "Entering chat mode. Session: %s, Target Lang: %s, Source Lang: %s, Chat Role: %s",
            self.context_manager_instance.session_id,
            self.target_language,
            self.source_language,
            self.current_chat_role,
        )
        print(
            f"\n=== Mode Chat dengan Gemini (Output: {self.target_language}, Input: {self.source_language}, Peran Alph: {self.current_chat_role}) ==="
        )
        print(
            "Ketik 'exit' atau 'quit' untuk keluar (menyimpan), 'delete' atau 'hapus' untuk memulai sesi baru (tanpa menyimpan)."
        )
        print(
            "Ketik 'load' atau 'muat' untuk memuat ulang histori dari sesi saat ini (jika diperlukan)."
        )

        while True:
            prompt_user = "[User (%s)]: " % self.source_language
            user_input = await asyncio.to_thread(input, prompt_user)
            user_input_strip = user_input.strip()
            user_input_lower = user_input_strip.lower()

            if user_input_lower in ["exit", "quit", "keluar"]:
                logger.info(
                    "Pengguna keluar dari mode chat. Menyimpan sesi %s.",
                    self.context_manager_instance.session_id,
                )
                if not self.context_manager_instance.save_to_archive():
                    logger.error(
                        "Gagal menyimpan sesi %s saat keluar dari mode chat.",
                        self.context_manager_instance.session_id,
                    )
                print("Keluar dari mode chat. Sesi disimpan.")
                break

            if user_input_lower in ["delete", "del", "hapus"]:
                logger.info(
                    "Pengguna memilih menghapus chat saat ini (sesi %s) dan memulai baru.",
                    self.context_manager_instance.session_id,
                )
                print("Menghapus chat saat ini dan memulai sesi baru...")
                self.context_manager_instance = (
                    self._init_context_manager()
                )  # Re-inisialisasi CM
                if not self.context_manager_instance:  # Jika gagal re-inisialisasi
                    print(
                        "Gagal memulai sesi baru karena error internal. Keluar dari mode chat."
                    )
                    logger.critical(
                        "Gagal re-inisialisasi ContextManager setelah delete command."
                    )
                    break
                logger.info(
                    "Sesi baru dimulai: %s", self.context_manager_instance.session_id
                )
                continue

            chat_history_content: list = []  # Default ke histori kosong
            if user_input_lower in ["load", "muat"]:
                logger.info(
                    "Pengguna memilih memuat ulang histori untuk sesi %s.",
                    self.context_manager_instance.session_id,
                )
                chat_history_content = self.context_manager_instance.retrieve()
                print(
                    f"Histori sesi saat ini ({len(chat_history_content)} pesan) dimuat ulang."
                )
                # Biasanya, kita tidak perlu input lagi setelah 'load', jadi continue
                # Jika Anda ingin pengguna mengetik sesuatu setelah 'load', hapus continue.
                # Untuk sekarang, asumsikan 'load' adalah aksi tunggal.
                # Jika ingin 'load' diikuti prompt, maka jangan continue dan pastikan user_input_strip bukan 'load'
                if (
                    user_input_strip == user_input_lower
                ):  # Hanya continue jika inputnya HANYA 'load' atau 'muat'
                    continue

            if (
                not user_input_strip
            ):  # Abaikan input kosong (setelah pemeriksaan command)
                continue

            try:
                # Ambil histori terbaru jika belum dimuat ulang oleh 'load'
                if not chat_history_content:  # Jika bukan command 'load'
                    chat_history_content = self.context_manager_instance.retrieve()

                input_for_lm = user_input_strip  # Gunakan versi yang sudah di-strip
                if self.source_language.lower() != self.target_language.lower():
                    if not self.translator_plugin_instance:  # Cek jika translator ada
                        logger.warning(
                            "Translator tidak tersedia, menggunakan input asli untuk LM."
                        )
                    else:
                        logger.info(
                            "Translating user input from '%s' to '%s'.",
                            self.source_language,
                            self.target_language,
                        )
                        translated_input = await self.translate_text_via_plugin(
                            user_input_strip,
                            target_lang=self.target_language,
                            source_lang=self.source_language,
                        )
                        if (
                            translated_input and translated_input != user_input_strip
                        ):  # Hanya gunakan jika translasi berhasil & berbeda
                            input_for_lm = translated_input
                            logger.info(
                                "Input for LM (after translation): %s...",
                                input_for_lm[:50],
                            )
                        elif (
                            not translated_input
                        ):  # Jika translasi mengembalikan None atau string kosong
                            logger.warning(
                                "User input translation returned empty or None, using original input for LM."
                            )
                        # Jika sama, berarti translasi tidak mengubah apa-apa atau kembali ke teks asli

                response_from_lm = self.language_model_instance.generate_response(
                    language=self.target_language,
                    prompt=input_for_lm,
                    chat_history=chat_history_content,
                    role_override=self.current_chat_role,
                    task="FULL",  # Default task, bisa dibuat dinamis
                )
                # Hapus spasi ekstra tapi pertahankan newline tunggal jika ada
                response_from_lm = " ".join(response_from_lm.split())
                logger.info(
                    "Response from LM (in %s, role %s): %s...",
                    self.target_language,
                    self.current_chat_role,
                    response_from_lm[:100],
                )

                final_response_for_user = response_from_lm
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
                        translated_response = await self.translate_text_via_plugin(
                            response_from_lm,
                            target_lang=self.source_language,
                            source_lang=self.target_language,
                        )
                        if (
                            translated_response
                            and translated_response != response_from_lm
                        ):
                            final_response_for_user = translated_response
                        elif not translated_response:
                            logger.warning(
                                "LM response translation returned empty or None, using original LM response for user."
                            )

                # Menampilkan kedua versi jika berbeda, atau hanya satu jika sama
                print(f"[Alph ({self.target_language})]: {response_from_lm}")
                if (
                    final_response_for_user.lower() != response_from_lm.lower()
                    and self.target_language.lower() != self.source_language.lower()
                ):
                    print(f"[Alph ({self.source_language})]: {final_response_for_user}")
                elif (
                    self.target_language.lower() == self.source_language.lower()
                    and final_response_for_user.lower() != response_from_lm.lower()
                ):
                    # Ini seharusnya tidak terjadi jika bahasa sama, tapi sebagai jaga-jaga
                    print(
                        f"[Alph ({self.source_language}, translated?)]: {final_response_for_user}"
                    )

                if not response_from_lm.startswith("[Gemini Error]"):
                    self.context_manager_instance.remember(
                        "user", user_input_strip
                    )  # Simpan input asli pengguna
                    self.context_manager_instance.remember(
                        "model", response_from_lm
                    )  # Simpan output asli LM

            except ConnectionError as e_conn:  # Tangkap error koneksi spesifik
                logger.error("Connection error during chat: %s", e_conn, exc_info=True)
                print("Gagal terhubung ke layanan. Periksa koneksi internet Anda.")
            except TimeoutError as e_timeout:  # Tangkap error timeout
                logger.error("Timeout error during chat: %s", e_timeout, exc_info=True)
                print("Waktu respons habis. Coba lagi nanti.")
            except (
                RuntimeError
            ) as e_rt:  # Misalnya dari LanguageModel jika API key bermasalah
                logger.error("Runtime error during chat: %s", e_rt, exc_info=True)
                print(f"Terjadi kesalahan runtime: {e_rt}")
            except Exception as e:  # Tangkap error umum lainnya
                logger.error("Unexpected error in chat mode: %s", e, exc_info=True)
                print("Terjadi kesalahan tak terduga saat berkomunikasi.")

    async def translate_text_via_plugin(
        self, text: str, target_lang: str, source_lang: str | None = None
    ) -> str | None:
        if not self.translator_plugin_instance:
            logger.warning(
                "Translator plugin instance is not available. Cannot translate. Returning original text."
            )
            return text

        actual_source_lang = source_lang or self.source_language

        logger.debug(
            "Attempting translation via plugin: '%s...' from %s to %s",
            text[:30],
            actual_source_lang,
            target_lang,
        )
        try:
            translated_text = await self.translator_plugin_instance.translate(
                text, target_lang=target_lang, source_lang=actual_source_lang
            )
            # Plugin translator harusnya mengembalikan string (bisa kosong) atau None jika gagal total
            if translated_text is None:  # Gagal total
                logger.warning(
                    "Translation returned None for text: '%s...'. Returning original.",
                    text[:30],
                )
                return text  # Kembalikan teks asli jika None
            return translated_text  # Kembalikan string (bisa kosong)
        except ConnectionError as e_conn_trans:
            logger.error(
                "Connection error during translation: %s", e_conn_trans, exc_info=True
            )
            return text  # Fallback
        except Exception as e:  # Tangkap error lain dari plugin
            logger.error("Error during translation via plugin: %s", e, exc_info=True)
            return text

    def select_language_preferences(self):
        logger.info("Entering language selection.")
        try:
            print("\n=== Pengaturan Bahasa ===")
            lang_options = {
                "1": ("Bahasa Indonesia", "id"),
                "2": ("Bahasa Inggris", "en"),
                "3": ("Bahasa Jepang", "ja"),
            }

            # Pilihan Bahasa Input Pengguna
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

            # Pilihan Bahasa Output Alph (Model)
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

            if not self.config.save_config():  # Simpan perubahan config
                logger.error("Gagal menyimpan preferensi bahasa ke file konfigurasi.")
            else:
                print("Preferensi bahasa disimpan.")

            # Re-inisialisasi translator jika bahasa berubah dan sebelumnya tidak diinisialisasi
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
                # Anda bisa memilih untuk men-None-kan translator_plugin_instance di sini jika mau
                # self.translator_plugin_instance = None

        except KeyboardInterrupt:
            logger.warning("Pemilihan bahasa diinterupsi oleh pengguna.")
            print("\nPemilihan bahasa dibatalkan.")
        except (configparser.Error, OSError) as e_cfg:  # Tangkap error config atau file
            logger.error(
                "Error terkait konfigurasi/file saat pemilihan bahasa: %s",
                e_cfg,
                exc_info=True,
            )
            print("Terjadi error saat menyimpan atau membaca konfigurasi bahasa.")
        except Exception as e:  # Tangkap error umum lainnya
            logger.error(
                "Error tidak terduga dalam pemilihan bahasa: %s", e, exc_info=True
            )
            print("Terjadi error tidak terduga saat mengatur bahasa.")

    def select_role_preferences(self):
        logger.info("Entering role selection.")
        if (
            not self.available_roles
        ):  # available_roles selalu list, minimal berisi fallback
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
                        # Jika LanguageModel mendukung perubahan role on-the-fly atau re-init dengan role baru
                        if self.language_model_instance and hasattr(
                            self.language_model_instance, "default_role"
                        ):
                            self.language_model_instance.default_role = (
                                new_role  # Asumsi LM punya atribut ini
                            )
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
                except ValueError:  # Jika input bukan angka
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
