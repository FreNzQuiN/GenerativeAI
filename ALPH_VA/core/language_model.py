# core/language_model.py

import logging, dotenv, os, json
from google import genai
from google.genai import types
from core import context_manager 
from core import config_manager

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

# --- Baca Konfigurasi ---
dotenv.load_dotenv()
GEMINI_API_KEY = config_manager.get_config_value("api_keys", "gemini_api_key")
if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
    # Fallback ke environment variable jika tidak ada di config atau masih default
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY loaded from environment variable. Consider setting it in config.ini.")
    else:
        logger.error("GEMINI_API_KEY not found in config.ini or environment variables.")
        raise RuntimeError("GEMINI_API_KEY belum disetel di config.ini atau environment variable.")

# Inisialisasi client (asumsi Anda masih menggunakan genai.Client berdasarkan kode sebelumnya)
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info("genai.Client initialized successfully.")
except AttributeError:
    logger.error("genai.Client() not found. This code expects an older google-generativeai library version.")
    raise RuntimeError("genai.Client tidak ditemukan. Perbarui kode untuk API modern atau downgrade library.")
except Exception as e_client:
    logger.error(f"Failed to initialize genai.Client: {e_client}")
    raise RuntimeError(f"Gagal menginisialisasi genai.Client: {e_client}")

DEFAULT_MODEL_NAME = "gemini-1.5-flash"
MODEL_NAME_CONFIG = config_manager.get_config_value("llm_settings", "model_name", DEFAULT_MODEL_NAME)
MODEL_NAME_FOR_API = f"models/{MODEL_NAME_CONFIG}" if not MODEL_NAME_CONFIG.startswith("models/") else MODEL_NAME_CONFIG
DEFAULT_TEMPERATURE = config_manager.get_float("llm_settings", "temperature", 0.7)
LLM_INSTRUCTION_PATH = config_manager.get_config_value("llm_settings", "instruction_path", "config/instructions.json")

DEFAULT_SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
]

def get_instruction(json_path, role, lang, task):
    """
    Ambil instruksi dari file JSON berdasarkan peran, bahasa, dan tugas.
    :param json_path: Path ke file JSON instruction.
    :param role: Nama peran (misal: "Girlfriend", "Assistant").
    :param lang: Kode bahasa (misal: "en", "id").
    :param task: Nama tugas spesifik (misal: "greet", "comfort").
    :return: String instruksi, atau None jika tidak ditemukan.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        role_data = data.get(role)
        if not role_data:
            return None
        instructions = role_data.get("INSTRUCTIONS", {})
        lang_instructions = instructions.get(lang)
        if not lang_instructions:
            return None
        return lang_instructions.get(task)
    except Exception as e:
        print(f"Error reading instruction: {e}")
        return None

def get_response(language: str, prompt: str, chat_history: list = None) -> str:
    messages_for_api = []
    
    INSTRUCTION_TEXT = get_instruction(
        LLM_INSTRUCTION_PATH,
        role="Girlfriend",
        lang=language,
        task="FULL"
    )
    
    generate_content_config = types.GenerateContentConfig(
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        response_mime_type="text/plain",
        temperature=DEFAULT_TEMPERATURE,
        system_instruction=types.Content(
            role="model",
            parts=[types.Part(text=INSTRUCTION_TEXT)]
        )
    )

    if chat_history:
        messages_for_api.extend(chat_history)
    messages_for_api.append(types.Content(
        role="user",
        parts=[types.Part(text=prompt)]
    ))
    contents_to_send = messages_for_api
    logger.debug(f"Sending {len(contents_to_send)} messages to model {MODEL_NAME_FOR_API}. Last user prompt: '{prompt[:50]}...'")

    try:
        response_chunks = client.models.generate_content_stream(
            model=MODEL_NAME_FOR_API,
            contents=contents_to_send,
            config=generate_content_config
        )
        full_response = "".join(chunk.text for chunk in response_chunks).strip()
        logger.info(f"Received response from model: '{full_response[:100]}...'")
        return full_response
    except TypeError as te:
        logger.warning(f"TypeError calling generate_content_stream with 'config': {te}. Trying simpler call.")
        _fallback_contents = []
        if 'INSTRUCTION_TEXT' in locals() and INSTRUCTION_TEXT:
             _fallback_contents.append(types.Content(role="user", parts=[types.Part(text=INSTRUCTION_TEXT)]))
        _fallback_contents.extend(messages_for_api)
        try:
            response_chunks = client.models.generate_content_stream(
                model=MODEL_NAME_FOR_API,
                contents=_fallback_contents
            )
            full_response_fallback = "".join(chunk.text for chunk in response_chunks).strip()
            logger.info(f"Received response from model (fallback call): '{full_response_fallback[:100]}...'")
            return full_response_fallback
        except Exception as e_simple:
            logger.error(f"Error in fallback generate_content_stream call: {e_simple}")
            return f"[Gemini Error - Panggilan Sederhana Fallback]: {e_simple}"
    except Exception as e:
        logger.error(f"Main error in generate_content_stream call: {e}")
        return f"[Gemini Error Utama]: {e}"

# Di dalam if __name__ == "__main__": di core/language_model.py

if __name__ == '__main__':
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("Testing language_model.py standalone...")

    # Ambil bahasa dari config
    language = config_manager.get_config_value("general", "language", "id")

    # Ambil daftar session yang ada
    from core.context_manager import ContextManager
    sessions = ContextManager.list_sessions()
    if sessions:
        # Ambil session terakhir
        last_session_id = sessions[-1]['session_id']
        ctx = ContextManager.load_from_archive(last_session_id)
        logger.info(f"Loaded last session: {last_session_id}")
    else:
        # Jika belum ada session, buat baru
        ctx = ContextManager()
        logger.info("No previous session found. Created new session.")

    # Loop interaksi pengguna
    while True:
        user_input = input("Masukkan 'clear' untuk simpan & mulai baru, 'exit' untuk keluar.\n[USER]: ")
        if user_input.strip().lower() == "exit":
            ctx.save_to_archive()
            logger.info("Session saved and exiting.")
            break
        if user_input.strip().lower() == "clear":
            ctx.save_to_archive()
            logger.info("Session archived and cleared. Starting new session.")
            ctx = ContextManager()  # Mulai session baru
            continue
        if not user_input.strip():
            continue

        logger.info(f"User: {user_input}")

        # Kirim riwayat chat ke model
        chat_history = ctx.retrieve()
        response = get_response(language, user_input, chat_history)
        logger.info(f"Assistant: {response}")

        if not response.startswith("[Gemini Error]"):
            ctx.remember("user", user_input)
            ctx.remember("model", response)