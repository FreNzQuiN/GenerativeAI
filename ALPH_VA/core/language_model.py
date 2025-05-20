# core/language_model.py
import logging
import dotenv
import os
import json
from google import genai
from google.genai import types
from core.config_manager import ConfigManager

# --- Global Config Instance ---
try:
    _cfg = ConfigManager()
except Exception as e_cfg_init_lm:
    print(
        f"CRITICAL ERROR in language_model.py: Failed to initialize ConfigManager: {e_cfg_init_lm}"
    )
    raise RuntimeError(
        f"LanguageModel: ConfigManager initialization failed: {e_cfg_init_lm}"
    ) from e_cfg_init_lm

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = ""
    try:
        _log_dir_lm = _cfg.get_config_value(
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
        if not os.path.exists(_log_dir_lm):
            os.makedirs(_log_dir_lm, exist_ok=True)
        log_file_path = os.path.join(
            _log_dir_lm, f"{os.path.splitext(os.path.basename(__file__))[0]}.log"
        )
    except Exception as e_log_path_lm:
        logger.error(
            "Error determining log_file_path for language_model: %s. Using fallback.",
            e_log_path_lm,
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
    except OSError as e_fh_lm:
        logger.error(
            "OSError setting up file handler for language_model: %s. Using basicConfig.",
            e_fh_lm,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    except Exception as e_log_lm:
        logger.error(
            "Unexpected error setting up logger for language_model: %s. Using basicConfig.",
            e_log_lm,
            exc_info=True,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

dotenv.load_dotenv()


def _get_gemini_api_key():
    api_key = _cfg.get_config_value("api_keys", "gemini_api_key")
    if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
        logger.info("GEMINI_API_KEY loaded from config.ini.")
        return api_key
    api_key_env = os.environ.get("GEMINI_API_KEY")
    if api_key_env:
        logger.info("GEMINI_API_KEY loaded from environment variable.")
        return api_key_env
    logger.error("GEMINI_API_KEY not found in config.ini or environment variables.")
    raise RuntimeError(
        "GEMINI_API_KEY belum disetel di config.ini atau environment variable."
    )


GEMINI_API_KEY = _get_gemini_api_key()
_genai_client_instance = None

try:
    if hasattr(genai, "Client"):
        _genai_client_instance = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("genai.Client initialized successfully.")
    else:
        logger.critical(
            "genai.Client class not found in google.genai module. Library might be corrupted or an unexpected version."
        )
        raise AttributeError("genai.Client class not found.")
except AttributeError as e_attr:
    logger.error(
        "AttributeError during genai.Client initialization: %s. This should not happen if library is installed correctly.",
        e_attr,
        exc_info=True,
    )
    raise RuntimeError(
        f"Pustaka google-generativeai tidak ditemukan dengan benar: {e_attr}"
    ) from e_attr
except Exception as e_client_init:
    logger.error("Failed to initialize genai.Client: %s", e_client_init, exc_info=True)
    raise RuntimeError(
        f"Gagal menginisialisasi genai.Client: {e_client_init}"
    ) from e_client_init

DEFAULT_MODEL_NAME = "gemini-1.5-flash-latest"


def _get_model_name_from_config():
    model_name_cfg = _cfg.get_config_value(
        "llm_settings", "model_name", DEFAULT_MODEL_NAME
    )
    return model_name_cfg if isinstance(model_name_cfg, str) else DEFAULT_MODEL_NAME


DEFAULT_TEMPERATURE_VAL = 0.7


def _get_temperature_from_config():
    return _cfg.get_float("llm_settings", "temperature", DEFAULT_TEMPERATURE_VAL)


DEFAULT_TOP_P_VAL = 0.92


def _get_top_p_from_config():
    return _cfg.get_float("llm_settings", "top_p", DEFAULT_TOP_P_VAL)


DEFAULT_TOP_K_VAL = 40


def _get_top_k_from_config():
    return _cfg.get_int("llm_settings", "top_k", DEFAULT_TOP_K_VAL)


PROJECT_ROOT = _cfg.get_config_value(
    "general",
    "project_root_dir",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
DEFAULT_INSTRUCTION_FILENAME = "config/llm_instructions.json"


def _get_instruction_path_from_config():
    path_val = _cfg.get_config_value(
        "llm_settings", "instruction_path", DEFAULT_INSTRUCTION_FILENAME
    )
    if os.path.isabs(path_val):
        return path_val
    return os.path.join(PROJECT_ROOT, path_val)


DEFAULT_SAFETY_SETTINGS_FOR_CLIENT_CONFIG = [
    types.SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="BLOCK_NONE",
    ),
]


_instructions_cache = {}


def _load_instructions_from_file(json_path: str) -> dict | None:
    if json_path in _instructions_cache:
        return _instructions_cache[json_path]
    if not os.path.exists(json_path):
        logger.error("Instruction file not found: %s", json_path)
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _instructions_cache[json_path] = data
        return data
    except json.JSONDecodeError as e:
        logger.error(
            "Error decoding JSON from instruction file %s: %s",
            json_path,
            e,
            exc_info=True,
        )
        return None
    except OSError as e:
        logger.error(
            "OSError reading instruction file %s: %s", json_path, e, exc_info=True
        )
        return None


def _get_specific_instruction(
    json_path: str, role: str, lang: str, task: str = "FULL"
) -> str | None:
    all_instructions = _load_instructions_from_file(json_path)
    if not all_instructions:
        return None
    role_data = all_instructions.get(role)
    if not isinstance(role_data, dict):
        logger.warning(
            "Role '%s' not found or invalid in instruction file: %s", role, json_path
        )
        return None
    instructions_for_role = role_data.get("INSTRUCTIONS")
    if not isinstance(instructions_for_role, dict):
        logger.warning("No 'INSTRUCTIONS' block for role '%s' in %s", role, json_path)
        return None
    lang_instructions = instructions_for_role.get(lang)
    if not isinstance(lang_instructions, dict):
        logger.warning("Lang '%s' not found for role '%s'. Trying 'en'.", lang, role)
        lang_instructions = instructions_for_role.get("en")
        if not isinstance(lang_instructions, dict):
            logger.warning("Fallback 'en' not found for role '%s'.", role)
            return None
    instruction_text = lang_instructions.get(task)
    if not isinstance(instruction_text, str):
        logger.warning(
            "Task '%s' not for role '%s', lang '%s' (or 'en').", task, role, lang
        )
        return None
    return instruction_text.strip()


class LanguageModel:
    def __init__(self, default_role: str = "Assistant"):
        if not _genai_client_instance:
            raise RuntimeError(
                "genai.Client (LanguageModel) was not initialized successfully. Cannot create LanguageModel instance."
            )

        self.client = _genai_client_instance
        self.model_name_base = _get_model_name_from_config()
        self.default_temperature = _get_temperature_from_config()
        self.default_top_p = _get_top_p_from_config()
        self.default_top_k = _get_top_k_from_config()
        self.instruction_path = _get_instruction_path_from_config()
        self.default_role = default_role
        self.safety_settings = DEFAULT_SAFETY_SETTINGS_FOR_CLIENT_CONFIG

        logger.info(
            "LanguageModel initialized with base model: '%s', default role: '%s'",
            self.model_name_base,
            self.default_role,
        )

    def _prepare_chat_history(
        self, chat_history: list | None
    ) -> list[types.Content] | None:
        if not chat_history:
            return None
        prepared_history = []
        for item in chat_history:
            if isinstance(item, types.Content):
                prepared_history.append(item)
            elif isinstance(item, dict) and "role" in item and "parts" in item:
                try:
                    parts_data = item.get("parts", [])
                    if not isinstance(parts_data, list):
                        parts_data = []
                    parts = [
                        types.Part(text=str(p.get("text", "")))
                        for p in parts_data
                        if isinstance(p, dict)
                    ]
                    prepared_history.append(
                        types.Content(role=str(item["role"]), parts=parts)
                    )
                except (TypeError, ValueError) as e_hist_conv:
                    logger.warning(
                        "Could not convert chat history item to types.Content: %s. Error: %s",
                        item,
                        e_hist_conv,
                    )
            else:
                logger.warning(
                    "Skipping unknown chat history item type: %s", type(item)
                )
        return prepared_history if prepared_history else None

    def generate_response(
        self,
        language: str,
        prompt: str,
        chat_history: list | None = None,
        role_override: str | None = None,
        task: str = "FULL",
        temperature_override: float | None = None,
        top_p_override: float | None = None,
        top_k_override: int | None = None,
    ) -> str:
        current_role = role_override if role_override else self.default_role
        current_temperature = (
            temperature_override
            if temperature_override is not None
            else self.default_temperature
        )
        current_top_p = (
            top_p_override if top_p_override is not None else self.default_top_p
        )
        current_top_k = (
            top_k_override if top_k_override is not None else self.default_top_k
        )

        system_instruction_text = _get_specific_instruction(
            json_path=self.instruction_path, role=current_role, lang=language, task=task
        )
        if not system_instruction_text:
            logger.warning(
                "No system instruction for role '%s', lang '%s', task '%s'.",
                current_role,
                language,
                task,
            )

        final_contents_for_api = []
        processed_history = self._prepare_chat_history(chat_history)
        if processed_history:
            final_contents_for_api.extend(processed_history)
        final_contents_for_api.append(
            types.Content(role="user", parts=[types.Part(text=prompt)])
        )

        try:
            generation_config_obj = types.GenerateContentConfig(
                temperature=current_temperature,
                top_p=current_top_p,
                top_k=current_top_k,
                safety_settings=self.safety_settings,
                # candidate_count, max_output_tokens, etc.
                system_instruction=(
                    (
                        types.Content(
                            role="model",
                            parts=[types.Part(text=system_instruction_text)],
                        )
                    )
                    if system_instruction_text
                    else None
                ),
            )
        except AttributeError as e_gc_attr:
            logger.warning(
                "AttributeError creating GenerateContentConfig (e.g. system_instruction not found): %s. System instruction might not be applied via config.",
                e_gc_attr,
            )
            generation_config_obj = types.GenerateContentConfig(
                temperature=current_temperature,
                top_p=current_top_p,
                top_k=current_top_k,
                safety_settings=self.safety_settings,
            )
            if system_instruction_text and not any(
                p.text.startswith("[System Instruction:")
                for c in final_contents_for_api
                for p in c.parts
            ):
                logger.info(
                    "Prepending system instruction to contents as GenerateContentConfig does not support it directly or failed."
                )
                final_contents_for_api.insert(
                    0,
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=f"[System Instruction: {system_instruction_text}]"
                            )
                        ],
                    ),
                )

        model_path_for_api = self.model_name_base
        if not model_path_for_api.startswith("models/"):
            model_path_for_api = f"models/{model_path_for_api}"

        logger.info(
            "Sending request via genai.Client to '%s' (Role: %s, Lang: %s, Task: %s)",
            model_path_for_api,
            current_role,
            language,
            task,
        )
        try:
            response_chunks = self.client.models.generate_content_stream(
                model=model_path_for_api,
                contents=final_contents_for_api,
                config=generation_config_obj,
            )
            full_response = "".join(
                chunk.text for chunk in response_chunks if hasattr(chunk, "text")
            ).strip()
            logger.info("Response from genai.Client: '%s...'", full_response[:100])
            return full_response
        except TypeError as te:
            logger.warning(
                "TypeError in genai.Client call: %s. Trying simpler call without full config.",
                te,
            )
            try:
                response_chunks_fb = self.client.models.generate_content_stream(
                    model=model_path_for_api, contents=final_contents_for_api
                )
                full_response_fb = "".join(
                    chunk.text for chunk in response_chunks_fb if hasattr(chunk, "text")
                ).strip()
                logger.info(
                    "Response from genai.Client (fallback call): '%s...'",
                    full_response_fb[:100],
                )
                return full_response_fb
            except Exception as e_simple:
                logger.error(
                    "Error in genai.Client fallback call: %s", e_simple, exc_info=True
                )
                return f"[Gemini Error - Client Fallback]: {str(e_simple)}"
        except Exception as e_main_call:
            logger.error(
                "Main error in genai.Client call: %s", e_main_call, exc_info=True
            )
            return f"[Gemini Error - Client API]: {str(e_main_call)}"


if __name__ == "__main__":
    print("--- LanguageModel Standalone Test (genai.Client focus) ---")
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        )
    try:
        lm = LanguageModel(default_role="Girlfriend")
        print(f"LanguageModel instance created with default role: {lm.default_role}")

        print("\n--- Test 1: Simple prompt, default role (Girlfriend), lang 'id' ---")
        prompt1 = "Halo sayang, kamu lagi ngapain aja hari ini?"
        response1 = lm.generate_response(language="id", prompt=prompt1)
        print(f"User (id): {prompt1}")
        print(f"Alph (id, Girlfriend): {response1}")

        print(
            "\n--- Test 2: With history, role 'Assistant', lang 'en', task 'greet' ---"
        )
        history2 = [
            types.Content(role="user", parts=[types.Part(text="Good morning!")]),
        ]
        prompt2 = "I'd like to know the weather today."
        response2 = lm.generate_response(
            language="en",
            prompt=prompt2,
            chat_history=history2,
            role_override="Assistant",
            task="greet",
        )
        print(f"User (en): {prompt2} (Note: 'greet' task might override this prompt)")
        print(f"Alph (en, Assistant, greet): {response2}")

        print("\n--- Test 3: Assistant 'FULL' task ---")
        prompt3 = "Can you explain what a neural network is in simple terms?"
        response3 = lm.generate_response(
            language="en", prompt=prompt3, role_override="Assistant", task="FULL"
        )
        print(f"User (en): {prompt3}")
        print(f"Alph (en, Assistant, FULL): {response3}")

    except RuntimeError as e_rt:
        print(f"RUNTIME ERROR during test: {e_rt}")
    except Exception as e_test:
        print(f"UNEXPECTED ERROR during test: {e_test}", exc_info=True)
