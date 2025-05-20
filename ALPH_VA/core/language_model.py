# core/language_model.py

import logging
import dotenv
import os
import json
from google import genai # type: ignore
from google.genai import types # type: ignore
from core import config_manager

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        if hasattr(config_manager, 'LOG_DIR') and config_manager.LOG_DIR:
            if not os.path.exists(config_manager.LOG_DIR):
                os.makedirs(config_manager.LOG_DIR, exist_ok=True)
            log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
        else:
            logger.warning("config_manager.LOG_DIR not found. Logging to current dir for language_model.")
            log_file_path = f"{os.path.split(__file__)[1].split('.')[0]}.log"
    except Exception as e_log_setup:
        logger.error(f"Error setting up logger for language_model: {e_log_setup}. Logging to current dir.", exc_info=True)
        log_file_path = f"{os.path.split(__file__)[1].split('.')[0]}.log"
        
    if log_file_path:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logger.warning("Could not set up file handler for language_model. Using basicConfig.")
    logger.setLevel(logging.INFO)

dotenv.load_dotenv()

def _get_gemini_api_key():
    api_key = None
    try:
        api_key = config_manager.get_config_value("api_keys", "gemini_api_key")
        if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
            logger.info("GEMINI_API_KEY loaded from config.ini.")
            return api_key
    except AttributeError:
        logger.warning("config_manager.get_config_value not available for API key.")
    except Exception as e_cfg_key:
        logger.warning(f"Error reading GEMINI_API_KEY from config: {e_cfg_key}")

    # Fallback ke environment variable
    api_key_env = os.environ.get("GEMINI_API_KEY")
    if api_key_env:
        logger.info("GEMINI_API_KEY loaded from environment variable.")
        return api_key_env
    
    logger.error("GEMINI_API_KEY not found in config.ini or environment variables.")
    raise RuntimeError("GEMINI_API_KEY belum disetel di config.ini atau environment variable.")

GEMINI_API_KEY = _get_gemini_api_key()

_genai_client = None
try:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("genai.configure(api_key=...) called successfully.")
except AttributeError:
    logger.warning("genai.configure or genai.GenerativeModel not found. Trying legacy genai.Client().")
    try:
        _genai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Legacy genai.Client initialized successfully.")
    except AttributeError:
        logger.error("Neither modern genai API (configure/GenerativeModel) nor legacy genai.Client() found.")
        raise RuntimeError("Versi pustaka google-generativeai tidak kompatibel atau API Key bermasalah.")
    except Exception as e_client_legacy:
        logger.error(f"Failed to initialize legacy genai.Client: {e_client_legacy}", exc_info=True)
        raise RuntimeError(f"Gagal menginisialisasi legacy genai.Client: {e_client_legacy}")
except Exception as e_configure:
    logger.error(f"Failed to configure genai with API key: {e_configure}", exc_info=True)
    raise RuntimeError(f"Gagal mengkonfigurasi genai (modern API): {e_configure}")


DEFAULT_MODEL_NAME = "gemini-1.5-flash-latest"
def _get_model_name_from_config():
    try:
        model_name_cfg = config_manager.get_config_value("llm_settings", "model_name", DEFAULT_MODEL_NAME)
        return model_name_cfg.replace("models/", "") if isinstance(model_name_cfg, str) else DEFAULT_MODEL_NAME
    except AttributeError:
        logger.warning("config_manager.get_config_value not available for model_name.")
        return DEFAULT_MODEL_NAME
    except Exception as e_cfg_model:
        logger.warning(f"Error reading model_name from config: {e_cfg_model}. Using default.")
        return DEFAULT_MODEL_NAME

DEFAULT_TEMPERATURE_VAL = 0.7
def _get_temperature_from_config():
    try:
        return config_manager.get_float("llm_settings", "temperature", DEFAULT_TEMPERATURE_VAL)
    except AttributeError:
        logger.warning("config_manager.get_float not available for temperature.")
        return DEFAULT_TEMPERATURE_VAL
    except Exception as e_cfg_temp:
        logger.warning(f"Error reading temperature from config: {e_cfg_temp}. Using default.")
        return DEFAULT_TEMPERATURE_VAL

try:
    PROJECT_ROOT = config_manager.PROJECT_ROOT_DIR
except AttributeError:
    logger.error("config_manager.PROJECT_ROOT_DIR is not defined. Using fallback for instruction path.")
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_INSTRUCTION_FILENAME = "config/llm_instructions.json"
def _get_instruction_path_from_config():
    try:
        path_val = config_manager.get_config_value("llm_settings", "instruction_path", DEFAULT_INSTRUCTION_FILENAME)
        if os.path.isabs(path_val):
            return path_val
        return os.path.join(PROJECT_ROOT, path_val)
    except AttributeError:
        logger.warning("config_manager.get_config_value not available for instruction_path.")
        return os.path.join(PROJECT_ROOT, DEFAULT_INSTRUCTION_FILENAME)
    except Exception as e_cfg_instr:
        logger.warning(f"Error reading instruction_path from config: {e_cfg_instr}. Using default.")
        return os.path.join(PROJECT_ROOT, DEFAULT_INSTRUCTION_FILENAME)

DEFAULT_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
] 

_instructions_cache = {}

def _load_instructions_from_file(json_path: str) -> dict | None:
    """Memuat semua instruksi dari file JSON."""
    if json_path in _instructions_cache:
        return _instructions_cache[json_path]
    
    if not os.path.exists(json_path):
        logger.error(f"Instruction file not found: {json_path}")
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _instructions_cache[json_path] = data
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from instruction file {json_path}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error reading instruction file {json_path}: {e}", exc_info=True)
        return None

def _get_specific_instruction(json_path: str, role: str, lang: str, task: str = "FULL") -> str | None:
    """Mengambil instruksi spesifik dari data yang sudah dimuat."""
    all_instructions = _load_instructions_from_file(json_path)
    if not all_instructions:
        return None

    role_data = all_instructions.get(role)
    if not role_data or not isinstance(role_data, dict):
        logger.warning(f"Role '{role}' not found or invalid in instruction file: {json_path}")
        return None
    
    instructions_for_role = role_data.get("INSTRUCTIONS")
    if not instructions_for_role or not isinstance(instructions_for_role, dict):
        logger.warning(f"No 'INSTRUCTIONS' block found for role '{role}' in {json_path}")
        return None
        
    lang_instructions = instructions_for_role.get(lang)
    if not lang_instructions or not isinstance(lang_instructions, dict):
        logger.warning(f"Language '{lang}' not found for role '{role}'. Trying fallback to 'en'.")
        lang_instructions = instructions_for_role.get("en")
        if not lang_instructions or not isinstance(lang_instructions, dict):
            logger.warning(f"Fallback language 'en' also not found for role '{role}'.")
            return None
            
    instruction_text = lang_instructions.get(task)
    if not instruction_text or not isinstance(instruction_text, str):
        logger.warning(f"Task '{task}' not found for role '{role}', lang '{lang}' (or fallback 'en').")
        return None
    return instruction_text.strip()


class LanguageModel:
    def __init__(self, default_role: str = "Assistant"):
        self.model_name = _get_model_name_from_config()
        self.default_temperature = _get_temperature_from_config()
        self.instruction_path = _get_instruction_path_from_config()
        self.default_role = default_role
        self.safety_settings = DEFAULT_SAFETY_SETTINGS
        
        self.model_instance = None
        if _genai_client is None: 
            try:
                self.model_instance = genai.GenerativeModel(
                    model_name=self.model_name,
                    safety_settings=self.safety_settings
                )
                logger.info(f"Modern genai.GenerativeModel '{self.model_name}' instance created.")
            except Exception as e_model_create:
                logger.error(f"Failed to create GenerativeModel instance '{self.model_name}': {e_model_create}", exc_info=True)
                raise RuntimeError(f"Gagal membuat instance GenerativeModel: {e_model_create}")
        logger.info(f"LanguageModel initialized with model: '{self.model_name}', default role: '{self.default_role}'")

    def _prepare_chat_history(self, chat_history: list | None) -> list[types.Content] | None:
        """Memastikan histori chat dalam format yang benar (list of types.Content)."""
        if not chat_history:
            return None
        
        prepared_history = []
        for item in chat_history:
            if isinstance(item, types.Content):
                prepared_history.append(item)
            elif isinstance(item, dict) and "role" in item and "parts" in item:
                try:
                    parts = [types.Part(text=p.get("text", "")) for p in item["parts"] if isinstance(p, dict)]
                    prepared_history.append(types.Content(role=item["role"], parts=parts))
                except Exception as e_hist_conv:
                    logger.warning(f"Could not convert chat history item to types.Content: {item}. Error: {e_hist_conv}")
            else:
                logger.warning(f"Skipping unknown chat history item type: {type(item)}")
        return prepared_history if prepared_history else None

    def generate_response(self, 
                          language: str, 
                          prompt: str, 
                          chat_history: list | None = None, 
                          role_override: str | None = None,
                          task: str = "FULL",
                          temperature_override: float | None = None
                          ) -> str:
        
        current_role = role_override if role_override else self.default_role
        current_temperature = temperature_override if temperature_override else self.default_temperature

        system_instruction_text = _get_specific_instruction(
            json_path=self.instruction_path,
            role=current_role,
            lang=language,
            task=task
        )

        if not system_instruction_text:
            logger.warning(f"No system instruction found for role '{current_role}', lang '{language}', task '{task}'. Proceeding without specific system instruction.")
            # Anda bisa memiliki system instruction default jika tidak ada yang spesifik
            # system_instruction_text = "You are a helpful AI assistant." 

        # API modern (genai.GenerativeModel)
        if self.model_instance:
            # Histori harus berupa list types.Content
            processed_history = self._prepare_chat_history(chat_history)
            
            # Gabungkan histori dengan prompt baru dari pengguna
            # API modern menangani histori sebagai bagian dari chat session
            # atau sebagai list `contents` jika tidak menggunakan `start_chat`.
            # Jika menggunakan `start_chat`:
            # chat_session = self.model_instance.start_chat(history=processed_history or [])
            # response = chat_session.send_message(prompt, stream=True)
            
            # Jika tidak menggunakan `start_chat` (lebih mirip API lama):
            contents_for_api = []
            if processed_history:
                contents_for_api.extend(processed_history)
            contents_for_api.append(types.Content(role="user", parts=[types.Part(text=prompt)]))

            generation_config = types.GenerationConfig(
                temperature=current_temperature
                # candidate_count, max_output_tokens, stop_sequences bisa ditambahkan di sini
            )

            try:
                logger.info(f"Sending request to modern API model '{self.model_name}' with role '{current_role}', lang '{language}', task '{task}'.")
                logger.debug(f"System Instruction: {system_instruction_text[:100] if system_instruction_text else 'None'}")
                logger.debug(f"User Prompt: {prompt[:100]}")
                logger.debug(f"History length: {len(processed_history or [])}")

                # Untuk model modern, system_instruction bisa menjadi bagian dari model atau request.
                # Jika tidak diset saat membuat model, bisa diset di sini (jika API mendukungnya per request)
                # atau ditambahkan sebagai pesan pertama di `contents_for_api` dengan role 'system' atau 'user'.
                # Periksa dokumentasi API terbaru untuk cara terbaik menyisipkan system prompt.
                # Untuk sekarang, mari kita coba tambahkan sebagai pesan pertama jika ada.
                
                # Cara 1: Jika model mendukung system_instruction di generate_content
                # response_chunks = self.model_instance.generate_content(
                #     contents_for_api,
                #     stream=True,
                #     generation_config=generation_config,
                #     system_instruction=types.Content(role="system", parts=[types.Part(text=system_instruction_text)]) if system_instruction_text else None
                # )

                # Cara 2: Tambahkan system instruction ke contents jika tidak ada cara lain (kurang ideal tapi umum)
                final_contents_for_api = []
                if system_instruction_text:
                    # Beberapa model mungkin mengharapkan role 'user' untuk system prompt,
                    # yang lain 'system'. Untuk Gemini, `system_instruction` adalah parameter terpisah saat membuat model atau di `GenerationConfig` (tergantung versi).
                    # Jika disuntikkan ke `contents`, role 'user' atau 'model' bisa dicoba.
                    # Mari kita coba dengan role 'user' sebagai pesan pertama jika tidak ada system_instruction khusus.
                    # Ini adalah area yang paling mungkin perlu disesuaikan berdasarkan perilaku API.
                    # Jika system_instruction sudah di-set di model saat __init__, ini tidak perlu.
                    final_contents_for_api.append(types.Content(role="user", parts=[types.Part(text=f"[System Instruction for this turn: {system_instruction_text}]")]))
                final_contents_for_api.extend(contents_for_api)


                response_chunks = self.model_instance.generate_content( # generate_content lebih umum, bisa stream atau tidak
                    final_contents_for_api, # Menggunakan list of Contents
                    stream=True, # Streaming
                    generation_config=generation_config,
                    # safety_settings=self.safety_settings # Sudah di-set saat buat model
                )
                
                full_response = "".join(chunk.text for chunk in response_chunks if hasattr(chunk, 'text')).strip()
                logger.info(f"Modern API response: '{full_response[:100]}...'")
                return full_response
            except Exception as e:
                logger.error(f"Error with modern API generate_content call: {e}", exc_info=True)
                return f"[Gemini Error - Modern API]: {e}"

        # API lama (genai.Client) - Fallback jika self.model_instance tidak ada (yaitu _genai_client yang ada)
        elif _genai_client:
            messages_for_api = []
            if system_instruction_text: # Untuk API lama, ini bagian dari config
                pass # Akan dimasukkan ke GenerateContentConfig
            
            processed_history = self._prepare_chat_history(chat_history)
            if processed_history:
                messages_for_api.extend(processed_history)
            messages_for_api.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
            
            # Konfigurasi untuk API lama
            safety_settings_legacy = [
                types.SafetySetting(category=s["category"], threshold=s["threshold"]) for s in self.safety_settings
            ]
            generate_content_config_legacy = types.GenerateContentConfig(
                safety_settings=safety_settings_legacy,
                response_mime_type="text/plain", # Biasanya default
                temperature=current_temperature,
                # System instruction untuk API lama (jika didukung oleh model tertentu)
                system_instruction=types.Content(role="model", parts=[types.Part(text=system_instruction_text)]) if system_instruction_text else None
            )
            
            model_name_for_legacy_api = self.model_name
            if not model_name_for_legacy_api.startswith("models/"):
                model_name_for_legacy_api = f"models/{model_name_for_legacy_api}"

            logger.info(f"Sending request to legacy API model '{model_name_for_legacy_api}' with role '{current_role}', lang '{language}', task '{task}'.")
            try:
                response_chunks = _genai_client.models.generate_content_stream( # type: ignore
                    model=model_name_for_legacy_api,
                    contents=messages_for_api,
                    config=generate_content_config_legacy
                )
                full_response = "".join(chunk.text for chunk in response_chunks if hasattr(chunk, 'text')).strip()
                logger.info(f"Legacy API response: '{full_response[:100]}...'")
                return full_response
            except TypeError as te: # Jika 'config' tidak diterima
                logger.warning(f"TypeError in legacy API call with 'config': {te}. Trying simpler call.")
                # Fallback call tanpa config, menyuntikkan system instruction ke messages jika ada
                fallback_messages = []
                if system_instruction_text:
                    fallback_messages.append(types.Content(role="user", parts=[types.Part(text=f"[System Instruction: {system_instruction_text}]")]))
                fallback_messages.extend(messages_for_api)
                try:
                    response_chunks_fb = _genai_client.models.generate_content_stream(model=model_name_for_legacy_api, contents=fallback_messages) # type: ignore
                    full_response_fb = "".join(chunk.text for chunk in response_chunks_fb if hasattr(chunk, 'text')).strip()
                    logger.info(f"Legacy API response (fallback call): '{full_response_fb[:100]}...'")
                    return full_response_fb
                except Exception as e_simple:
                    logger.error(f"Error in legacy API fallback call: {e_simple}", exc_info=True)
                    return f"[Gemini Error - Legacy API Fallback]: {e_simple}"
            except Exception as e:
                logger.error(f"Main error in legacy API call: {e}", exc_info=True)
                return f"[Gemini Error - Legacy API]: {e}"
        else:
            logger.error("No valid genai API client or model instance available.")
            return "[Error: Gemini client not configured]"


if __name__ == '__main__':
    # Blok test ini mungkin perlu disesuaikan karena ContextManager sekarang di core/
    # dan mungkin tidak langsung bisa diimpor jika dijalankan dari core/
    # Lebih baik menguji LanguageModel dengan input langsung.

    print("--- LanguageModel Standalone Test ---")
    if not logging.getLogger().hasHandlers(): # Pastikan logger di-setup untuk test
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Dapatkan path instruksi yang benar (asumsi file ini di core/)
    test_instruction_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), # project root
        "config", 
        "llm_instructions.json" # atau nama file Anda
    )
    print(f"Using instruction path for test: {test_instruction_path}")
    # Overwrite instruction path jika default dari config tidak benar untuk tes standalone
    LanguageModel.instruction_path = test_instruction_path


    try:
        # Buat instance LanguageModel, ini akan memicu loading config dan model
        lm = LanguageModel(default_role="Girlfriend") # Set default role saat membuat instance
        print(f"LanguageModel instance created with default role: {lm.default_role}")

        # Skenario 1: Chat sederhana tanpa histori, menggunakan default role
        print("\n--- Test 1: Simple prompt, default role (Girlfriend), lang 'id' ---")
        prompt1 = "Hai sayang, lagi apa?"
        response1 = lm.generate_response(language="id", prompt=prompt1)
        print(f"User (id): {prompt1}")
        print(f"Alph (id, Girlfriend): {response1}")

        # Skenario 2: Dengan histori, override role ke Assistant, lang 'en'
        print("\n--- Test 2: With history, role 'Assistant', lang 'en' ---")
        history2 = [
            types.Content(role="user", parts=[types.Part(text="Can you help me with a Python problem?")]),
            types.Content(role="model", parts=[types.Part(text="Of course! What's the problem?")])
        ]
        prompt2 = "I'm getting an AttributeError."
        response2 = lm.generate_response(language="en", prompt=prompt2, chat_history=history2, role_override="Assistant")
        print(f"User (en): {prompt2}")
        print(f"Alph (en, Assistant): {response2}")

        # Skenario 3: Role 'Girlfriend', task spesifik 'comfort', lang 'id'
        print("\n--- Test 3: Role 'Girlfriend', task 'comfort', lang 'id' ---")
        prompt3 = "Aku lagi sedih banget hari ini..."
        response3 = lm.generate_response(language="id", prompt=prompt3, role_override="Girlfriend", task="comfort")
        print(f"User (id): {prompt3}")
        print(f"Alph (id, Girlfriend, comfort): {response3}")

        # Skenario 4: Role tidak ada di JSON
        print("\n--- Test 4: Non-existent role ---")
        prompt4 = "Hello there."
        response4 = lm.generate_response(language="en", prompt=prompt4, role_override="NonExistentRole")
        print(f"User (en): {prompt4}")
        print(f"Alph (en, NonExistentRole then fallback): {response4}") # Akan menggunakan default atau tanpa instruksi khusus

    except RuntimeError as e:
        print(f"RUNTIME ERROR during test: {e}")
    except Exception as e:
        print(f"UNEXPECTED ERROR during test: {e}", exc_info=True)