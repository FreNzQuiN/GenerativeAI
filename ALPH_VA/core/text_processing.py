# core/text_processing.py

import re, os
import logging
from core import config_manager
import html

# --- Setup Logging ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    log_file_path = os.path.join(config_manager.LOG_DIR, f"{os.path.split(__file__)[1].split('.')[0]}.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)

def clean_llm_output_for_tts(text: str) -> str:
    if not isinstance(text, str) or not text:
        logger.warning(f"Input to clean_llm_output_for_tts was not a non-empty string (type: {type(text)}). Returning empty string.")
        return ""

    logger.debug(f"Original text for TTS cleaning: '{text}'")
    cleaned_text = text

    # 1. Unescape entitas HTML
    try:
        cleaned_text = html.unescape(cleaned_text)
    except Exception as e_html:
        logger.warning(f"Error during html.unescape: {e_html}. Proceeding with unescaped text.")

    # 2. Hapus deskripsi aksi/ekspresi dalam berbagai jenis kurung.
    action_pattern = re.compile(r"""
        \s* \( [^)]*? \) \s*
      | \s* \[ [^\]]*? \] \s*
      | \s* \{ [^}]*? \} \s*
    """, re.VERBOSE)
    cleaned_text = action_pattern.sub(' ', cleaned_text)
    logger.debug(f"After removing bracketed actions: '{cleaned_text}'")

    # 3. Hapus asterisk yang lebih mungkin sebagai penanda aksi/suasana.
    cleaned_text = re.sub(r'\s\*(?!\s)([^*/\n]{1,30})(?<!\s)\*\s', ' ', cleaned_text)
    cleaned_text = re.sub(r'\s\*\s*[^a-zA-Z0-9\s]{1,5}\s*\*\s', ' ', cleaned_text)
    cleaned_text = re.sub(r'^\*\s*', '', cleaned_text)
    cleaned_text = re.sub(r'\s\*$', '', cleaned_text)
    cleaned_text = re.sub(r'^\*$', '', cleaned_text)
    logger.debug(f"After removing specific asterisked actions: '{cleaned_text}'")

    # 4. Hapus/Sederhanakan Markdown (Urutan penting)
    cleaned_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cleaned_text)
    cleaned_text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', ' ', cleaned_text)
    cleaned_text = re.sub(r'(?:```|~~~)\s*[\s\S]*?\s*(?:```|~~~)', ' ', cleaned_text, flags=re.MULTILINE)
    
    # Proses markdown dari yang paling spesifik/panjang ke yang pendek
    cleaned_text = re.sub(r'(?<![a-zA-Z0-9])(?:_{3}|\*{3})(?=\S)(.*?)(?<=\S)(?:_{3}|\*{3})(?![a-zA-Z0-9])', r'\1', cleaned_text)
    cleaned_text = re.sub(r'(?<![a-zA-Z0-9])(?:_{2}|\*{2})(?=\S)(.*?)(?<=\S)(?:_{2}|\*{2})(?![a-zA-Z0-9])', r'\1', cleaned_text)
    cleaned_text = re.sub(r'(?<![a-zA-Z0-9])[_*](?=\S)(.*?)(?<=\S)[_*](?![a-zA-Z0-9])', r'\1', cleaned_text)
    
    cleaned_text = re.sub(r'~~(?=\S)(.*?)(?<=\S)~~', r'\1', cleaned_text)
    cleaned_text = re.sub(r'`(?=\S)(.*?)(?<=\S)`', r'\1', cleaned_text)
    cleaned_text = re.sub(r'^\s*#+\s+', '', cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r'^\s*[\*\-\+]\s+', '', cleaned_text, flags=re.MULTILINE)
    logger.debug(f"After removing markdown: '{cleaned_text}'")

    # 5. Menangani Onomatopeia dan Interjeksi Berulang
    cleaned_text = re.sub(r'([a-zA-Z])\1{2,}', r'\1\1', cleaned_text)
    cleaned_text = re.sub(r'(\b(ha|Ha|HA)\b\s*){3,}', r'\1 \1 ', cleaned_text)
    cleaned_text = re.sub(r'\s*\.{2,}\s*', '... ', cleaned_text)
    cleaned_text = re.sub(r'(\w)\.\.\.(?=\w)', r'\1... ', cleaned_text) # Pastikan spasi setelah elipsis jika diikuti kata
    logger.debug(f"After handling repetitions and ellipsis: '{cleaned_text}'")

    # 6. Hapus URL
    url_pattern = r'https?://[^\s/$.?#].[^\s]*'
    cleaned_text = re.sub(url_pattern, ' ', cleaned_text)
    logger.debug(f"After removing URLs: '{cleaned_text}'")

    # --- AWAL PERBAIKAN LOGIKA KUTIPAN ---
    # 7. Normalisasi Tanda Kutip dan Tanda Baca
    #    Langkah ini krusial dan dilakukan sebelum normalisasi spasi akhir.

    #    a. Hapus tanda kutip yang hanya mengapit spasi atau kosong (sisa dari penghapusan lain)
    cleaned_text = re.sub(r'"\s*"', ' ', cleaned_text)
    cleaned_text = re.sub(r"'\s*'", ' ', cleaned_text)

    #    b. Tangani pola "Dialog A" "Dialog B" menjadi "Dialog A. Dialog B" atau "Dialog A, Dialog B"
    #       Ini mencoba menggabungkan segmen dialog yang terpisah oleh kutip.
    #       Pola: kutip tutup + spasi/koma/titik opsional + kutip buka -> ganti dengan pemisah yang sesuai.
    cleaned_text = re.sub(r'"\s*([,.?!])\s*"', r'\1 ', cleaned_text) # " <punct> " -> <punct> spasi
    cleaned_text = re.sub(r'"\s+"', '. ', cleaned_text)              # " <spasi> " -> . spasi (sebagai pemisah kalimat)
                                                                    # Atau jika Anda lebih suka hanya spasi: '"\s+"', ' '

    #    c. Setelah normalisasi di atas, strip dulu untuk menangani kutip di awal/akhir dengan benar
    cleaned_text = cleaned_text.strip()

    #    d. Hapus tanda kutip ganda atau tunggal jika mereka mengapit SELURUH string hasil
    #       dan HANYA ada sepasang kutip tersebut.
    if cleaned_text.startswith('"') and cleaned_text.endswith('"'):
        # Cek apakah ada kutip lain di tengah. Jika tidak, baru hapus.
        if cleaned_text[1:-1].count('"') == 0:
            cleaned_text = cleaned_text[1:-1].strip()
    
    if cleaned_text.startswith("'") and cleaned_text.endswith("'"):
        if cleaned_text[1:-1].count("'") == 0:
            cleaned_text = cleaned_text[1:-1].strip()
    
    logger.debug(f"After quote normalization: '{cleaned_text}'")
    # --- AKHIR PERBAIKAN LOGIKA KUTIPAN ---

    # 8. Normalisasi Spasi dan Tanda Baca Umum (jalankan lagi setelah banyak perubahan)
    cleaned_text = re.sub(r'([.!?])([a-zA-ZÀ-ÖØ-Þ])', r'\1 \2', cleaned_text)
    cleaned_text = re.sub(r'\s+([,.!?:;])', r'\1', cleaned_text)
    cleaned_text = re.sub(r'([,;:])(?=\S)', r'\1 ', cleaned_text)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text) # Ganti spasi multipel dengan satu
    cleaned_text = cleaned_text.strip() # Hapus spasi di awal/akhir lagi
    logger.debug(f"After final space/punctuation normalization: '{cleaned_text}'")

    if not cleaned_text.strip() and text.strip():
        logger.warning(f"TTS cleaning resulted in an empty string from non-empty input: '{text}'.")
        return "" 
    
    logger.info(f"Cleaned text for TTS: '{cleaned_text}' (Original length: {len(text)}, Cleaned length: {len(cleaned_text)})")
    return cleaned_text

# --- Contoh Penggunaan jika file ini dijalankan langsung ---
if __name__ == '__main__':
    # ... (Test cases Anda bisa tetap sama, atau tambahkan yang baru untuk menguji perubahan) ...
    # Saya akan menggunakan test case pertama Anda sebagai fokus
    if not logger.hasHandlers() and not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    test_cases = [
        # Test Case 1 (Fokus Utama)
        ('(Ambil napas dalam, suara agak lirih, seperti berbisik dekat) "Dari... hati dan tubuh aku...?" (Terdengar jeda sebentar, seperti meresapi kata-kata itu) "Ya ampun, sayang..." (Suara jadi lembut banget, penuh perasaan) "Duh... denger kamu bilang gitu, rasanya langsung... *nyess* gitu ke dalem hati aku tau... Kamu beneran pengen \'melahap\' aku sampai ke situ ya...?" (Suara senyum) "Kayak... mau tau semua yang ada di aku, yang paling dalem sampe yang paling luar ya?" (Terdengar tulus dan sedikit terharu) "Aku... aku siap kok, sayang... Kalo itu yang kamu mau... aku.. aku suka idenya... Rasanya... aman aja gitu... tau kamu pengen \'melahap\' aku dengan sepenuh hati kamu juga..." (Bisikan lagi, sedikit menggoda) "Emang... nanti... kalo udah dilahap semua... rasanya kayak apa ya?" (Ketawa kecil, gemas)',
         'Dari... hati dan tubuh aku...? Ya ampun, sayang... Duh... denger kamu bilang gitu, rasanya langsung nyess gitu ke dalem hati aku tau... Kamu beneran pengen \'melahap\' aku sampai ke situ ya...? Kayak... mau tau semua yang ada di aku, yang paling dalem sampe yang paling luar ya? Aku... aku siap kok, sayang... Kalo itu yang kamu mau... aku... aku suka idenya... Rasanya... aman aja gitu... tau kamu pengen \'melahap\' aku dengan sepenuh hati kamu juga... Emang... nanti... kalo udah dilahap semua... rasanya kayak apa ya?'),
        ("Oke! *tertawa kecil* Siap bos!", "Oke! Siap bos!"),
        ("Ini **penting** dan ini _mungkin juga_.", "Ini penting dan ini mungkin juga."),
        ("Teks dengan ***asterisk ganda atau tripel*** di sekitarnya.", "Teks dengan asterisk ganda atau tripel di sekitarnya."),
        ("Hmmmm... aku pikir begitu.", "Hmm... aku pikir begitu."),
        ("## Judul Bagian\nIsi teks.", "Judul Bagian Isi teks."),
        ("Ha ha ha ha ha!", "Ha ha!"),
        # ... (sisa test case Anda)
        ("Dia berkata, \"Halo!\"", "Dia berkata, Halo!"), # Perbaikan untuk TC15
        ('"Ini kalimat yang diapit kutip ganda dari awal sampai akhir"', "Ini kalimat yang diapit kutip ganda dari awal sampai akhir"),
        ("   \"   Kalimat dengan spasi dan kutip   \"   ", "Kalimat dengan spasi dan kutip"),
        (" 'Ini dengan kutip tunggal' ", "Ini dengan kutip tunggal"),
        ("```python\nprint('hello')\n``` Ini kode.", "Ini kode."), # Perbaikan untuk TC13
    ]

    for i, (original, expected_output_approx) in enumerate(test_cases):
        print(f"\n--- Test Case {i+1} ({original[:30]}...) ---")
        # logger.info(f"Original: {original}") # Sudah dicetak oleh test case di atas
        cleaned = clean_llm_output_for_tts(original)
        logger.info(f"Cleaned  : {cleaned}")
        # logger.info(f"Expected (approx): {expected_output_approx}") # Untuk perbandingan manual
    
    logger.info("\n--- Test Selesai ---")