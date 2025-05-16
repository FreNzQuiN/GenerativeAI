# Simple Private Assistance TTS (Alph)

## Deskripsi Singkat

Simple Private Assistance TTS adalah sebuah aplikasi asisten virtual modular berbasis teks dan suara yang dirancang untuk berjalan secara lokal. Aplikasi ini bertujuan untuk menyediakan berbagai fungsionalitas melalui sistem plugin yang dapat diperluas, termasuk interaksi dengan model bahasa (LLM), text-to-speech (TTS) dengan berbagai engine, speech-to-text (STT), dan terjemahan. Fokus utama adalah pada kustomisasi, privasi (dengan menjalankan komponen secara lokal jika memungkinkan), dan modularitas.

## Fitur Utama (Saat Ini & Direncanakan)

*   **Interaksi Model Bahasa**: Berkomunikasi dengan Large Language Models (saat ini terintegrasi dengan Gemini API).
*   **Text-to-Speech (TTS) Modular**:
    *   Dukungan untuk `pyttsx3` (TTS default sistem).
    *   Dukungan untuk Voicevox API (via `plugins/voicevox_api.py` dan `plugins/japanese_tts.py`) untuk suara Bahasa Jepang.
    *   Dukungan untuk model TTS kustom berbasis Coqui TTS (VITS) (via `plugins/custom_model_tts.py`).
    *   Dispatcher TTS (`core/text_to_speech.py`) untuk memilih engine yang sesuai.
*   **Speech-to-Text (STT)**:
    *   Implementasi awal menggunakan `SpeechRecognition` library dengan Google Web Speech API (via `core/speech_to_text.py`) untuk input suara real-time.
*   **Terjemahan**:
    *   Plugin terjemahan menggunakan `googletrans` (via `plugins/translator.py`).
*   **Manajemen Konteks**:
    *   Menyimpan riwayat percakapan dalam memori sesi.
    *   Mengarsipkan sesi percakapan ke file JSON untuk persistensi (`chat_archive.json`).
*   **Manajemen Konfigurasi**:
    *   Pengaturan aplikasi terpusat dalam file `config/config.ini` dan dikelola oleh `core/config_manager.py`.
*   **Logging**:
    *   Pencatatan aktivitas aplikasi dan modul ke dalam file log di direktori `logs/`.
*   **Modularitas (Direncanakan Lebih Lanjut)**:
    *   Sistem plugin (`core/plugin_manager.py`) dan perutean aksi (`core/action_router.py`) untuk kemudahan penambahan fungsionalitas baru.

## 1. Struktur Program dan Data

Berikut adalah gambaran struktur direktori utama dan fungsinya:
```SIMPLEPRIVATEASSISTANCETTS/
├── assets/
│ └── models/ # Tempat menyimpan file model kustom (TTS .pth, .json, speakers.pth)
├── config/
│ └── config.ini # File konfigurasi utama aplikasi (pengaturan API, path, default)
├── core/ # Modul inti aplikasi
│ ├── init.py
│ ├── action_router.py # (Direncanakan) Merutekan perintah/input ke aksi/plugin yang sesuai
│ ├── config_manager.py # Mengelola pembacaan dan penulisan konfigurasi dari config.ini
│ ├── context_manager.py # Mengelola konteks percakapan dan pengarsipan sesi
│ ├── language_model.py # Berinteraksi dengan Large Language Models (misalnya, Gemini)
│ ├── plugin_manager.py # (Direncanakan) Mengelola pemuatan dan interaksi dengan plugin
│ ├── speech_to_text.py # Mengelola input suara (STT) dari mikrofon
│ └── text_to_speech.py # Dispatcher untuk berbagai engine TTS
├── data/ # Data yang dihasilkan atau digunakan oleh aplikasi
│ ├── audio/ # Direktori output default untuk file audio TTS
│ │ ├── default_tts/ # (Disarankan) Output dari pyttsx3
│ │ ├── voicevox/ # Output dari Voicevox
│ │ └── custom_tts/ # Output dari model TTS kustom
│ └── memory/
│ └── chat_archive.json # Arsip sesi percakapan
├── logs/ # File log dari berbagai modul
│ ├── virtual_assistant.log # Log utama aplikasi dari main.py
│ ├── config_manager.log
│ ├── context_manager.log
│ ├── language_model.log
│ ├── speech_to_text.log
│ ├── text_to_speech_dispatcher.log
│ ├── default_tts.log
│ ├── japanese_tts.log
│ ├── voicevox_api.log
│ ├── custom_model_tts.log
│ └── translator.log
├── plugins/ # Modul-modul fungsionalitas tambahan (plugin)
│ ├── init.py
│ ├── default_tts.py # Implementasi TTS menggunakan pyttsx3
│ ├── japanese_tts.py # Wrapper untuk Voicevox khusus output Bahasa Jepang
│ ├── voicevox_api.py # Berinteraksi langsung dengan Voicevox engine
│ ├── custom_model_tts.py # Implementasi TTS menggunakan model Coqui VITS kustom
│ ├── translator.py # Plugin untuk terjemahan teks
│ └── play_voice.py # Memutar file audio (saat ini khusus Windows dengan winsound)
├── .env # (Disarankan) Menyimpan variabel lingkungan sensitif seperti API key
├── .gitignore
├── main.py # Titik masuk utama aplikasi, berisi UI terminal dan loop utama
├── requirements.txt # Daftar dependensi Python
└── README.md # File ini
```
**(Mindmap Sederhana - Representasi Teks)**
```[Asisten Virtual]
|
+-- [main.py (Orchestrator & UI Terminal)]
| |
| +-- Menggunakan [core.ConfigManager] -> [config/config.ini]
| +-- Menggunakan [core.ContextManager] -> [data/memory/chat_archive.json]
| +-- Menggunakan [core.ActionRouter (Direncanakan)]
| | |
| | +-- Rute ke [core.LanguageModel] (Gemini API)
| | +-- Rute ke [plugins.Translator]
| | +-- Rute ke Mode Panggilan ([core.SpeechToText] -> Aksi -> [core.TextToSpeech])
| |
| +-- Menggunakan [core.TextToSpeech (Dispatcher)]
| | |
| | +-- [plugins.DefaultTTS (pyttsx3)]
| | +-- [plugins.JapaneseTTS (Voicevox)]
| | +-- [plugins.CustomModelTTS (Coqui VITS)]
| |
| +-- Menggunakan [core.SpeechToText (SpeechRecognition)]
|
+-- [plugins/] (Fungsionalitas Tambahan)
| |
| +-- [play_voice.py]
| +-- [voicevox_api.py]
|
+-- [data/] (Output & Penyimpanan)
|
+-- [logs/] (Pencatatan)
|
+-- [assets/models/] (Model Kustom)
```
      
## 2. Setup Aplikasi

### Prasyarat

*   Python 3.9+ (disarankan 3.10 atau 3.11 untuk beberapa library modern).
*   `pip` (Python package installer).
*   (Untuk Windows & `plugins.play_voice.py`) Sistem operasi Windows.
*   (Untuk `plugins.voicevox_api.py`) Voicevox engine harus sudah terinstal dan berjalan di sistem Anda.
*   (Untuk `plugins.custom_model_tts.py`) File model `.pth`, `config.json`, dan (jika ada) `speakers.pth` untuk Coqui TTS VITS.
*   (Untuk `core.speech_to_text.py` dengan `PyAudio`) Mungkin memerlukan Microsoft Visual C++ Build Tools di Windows jika instalasi `PyAudio` gagal.
*   (Untuk `core.language_model.py`) API Key untuk Google Gemini, disetel sebagai variabel lingkungan atau di `config.ini`.

### Langkah-Langkah Instalasi

1.  **Clone Repository (Jika Sudah Ada di GitHub)**
    ```bash
    git clone [URL_REPOSITORY_ANDA]
    cd [NAMA_DIREKTORI_PROYEK]
    ```

2.  **Buat dan Aktifkan Virtual Environment (Sangat Direkomendasikan)**
    Ini akan mengisolasi dependensi proyek Anda.
    ```bash
    python -m venv myenv
    ```
    *   Di Windows:
        ```bash
        myenv\Scripts\activate
        ```
    *   Di macOS/Linux:
        ```bash
        source myenv/bin/activate
        ```
    Anda akan melihat `(myenv)` di awal prompt terminal Anda.

3.  **Install Dependensi**
    File `requirements.txt` berisi semua library Python yang dibutuhkan oleh proyek.
    ```bash
    (myenv) pip install -r requirements.txt
    ```
    *(Anda perlu membuat file `requirements.txt` ini. Lihat bagian di bawah)*

4.  **Konfigurasi Variabel Lingkungan (Opsional tapi Direkomendasikan untuk API Keys)**
    Buat file `.env` di root direktori proyek (sejajar dengan `main.py`). Tambahkan API key Anda di sini, contoh:
    ```env
    GEMINI_API_KEY=AISx***************************
    # Tambahkan API key lain jika diperlukan
    ```
    Modul `core.config_manager.py` akan mencoba membaca `GEMINI_API_KEY` dari `config.ini` terlebih dahulu, kemudian dari environment variable jika tidak ditemukan di config.

5.  **Siapkan File Konfigurasi (`config/config.ini`)**
    *   Saat pertama kali salah satu modul inti (seperti `config_manager.py`) dijalankan, file `config/config.ini` akan dibuat secara otomatis dengan struktur dan nilai default jika belum ada.
    *   Buka `config/config.ini` dan sesuaikan pengaturannya:
        *   Isi `GEMINI_API_KEY` di section `[api_keys]`.
        *   Atur path untuk model TTS kustom Anda di section `[tts_custom_model]` (misalnya, `model_config_path`, `model_checkpoint_path`, `speakers_file_path`). Pastikan path ini benar relatif terhadap root direktori proyek Anda (misalnya, `assets/models/namafile.json`).
        *   Sesuaikan pengaturan lain seperti bahasa default, speaker ID, dll., sesuai kebutuhan.

6.  **Siapkan Aset Model Kustom (Jika Menggunakan)**
    *   Letakkan file model TTS kustom Anda (misalnya, `checkpoint.pth`, `config.json`, `speakers.pth`) di dalam direktori yang Anda tentukan di `config.ini` (disarankan `assets/models/`).

7.  **Jalankan Aplikasi**
    Dari root direktori proyek (dengan virtual environment aktif):
    ```bash
    (myenv) python main.py
    ```

### Membuat `requirements.txt`

Jika Anda belum memiliki file `requirements.txt`, Anda bisa membuatnya setelah menginstal semua dependensi secara manual di virtual environment Anda:

```bash
(myenv) pip freeze > requirements.txt
```

Pastikan untuk menjalankan ini setelah Anda berhasil menginstal semua library yang dibutuhkan (google-generativeai, googletrans==3.1.0a0, SpeechRecognition, PyAudio, pyttsx3, TTS (untuk Coqui), winsound (built-in di Windows), dll.).

3. Cara Penggunaan

    Jalankan python main.py.

    Pilih bahasa output utama saat pertama kali aplikasi dijalankan (pengaturan ini akan disimpan di config.ini).

    Anda akan disajikan dengan menu utama:

        Chat dengan Gemini: Memulai sesi percakapan dengan model bahasa Gemini.

        Terjemahkan Kalimat: Masuk ke mode terjemahan.

        Mode Panggilan Suara (STT-TTS): Mengaktifkan input suara melalui mikrofon, diproses, dan direspons dengan suara.

        Pengaturan Bahasa: Mengubah preferensi bahasa output.

        Keluar: Menutup aplikasi.

    Ikuti instruksi pada setiap mode.

        Dalam mode chat atau panggilan, ketik clear untuk mengarsipkan sesi percakapan saat ini ke data/memory/chat_archive.json dan memulai sesi baru.

        Ketik kembali (atau perintah serupa) untuk kembali ke menu utama dari sub-mode.

4. Struktur Log

    Log utama aplikasi: logs/virtual_assistant.log

    Log per modul: logs/config_manager.log, logs/context_manager.log, dll.
    File log ini berguna untuk debugging dan melacak aktivitas aplikasi.

5. Kontribusi

Saat ini proyek ini dikelola secara pribadi. Jika Anda menemukan bug atau memiliki saran, silakan buat Issue.

6. Rencana Pengembangan Selanjutnya (Roadmap)

    Implementasi penuh core/action_router.py untuk penanganan perintah yang lebih canggih.

    Integrasi core/plugin_manager.py untuk memuat plugin secara dinamis.

    Penambahan lebih banyak plugin (misalnya, cuaca, berita, pemutar musik lokal).

    Peningkatan kemampuan STT (opsi engine alternatif seperti Whisper lokal, penanganan error yang lebih baik).

    Pengembangan UI yang lebih kaya (mungkin web interface atau GUI desktop).

    Dukungan untuk "wake word" agar asisten bisa selalu mendengarkan.

    Manajemen sesi yang lebih canggih (memuat ulang sesi spesifik dari arsip).
