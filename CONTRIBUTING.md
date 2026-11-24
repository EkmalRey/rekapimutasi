# Panduan Kontribusi (Contributing Guide)

Terima kasih atas ketertarikan Anda untuk berkontribusi di **rekapimutasi**! Proyek ini terbuka untuk siapa saja yang ingin memperbaiki bug, menambah bank baru, mempercepat parsing, atau menyempurnakan tampilan web.

---

## 🔒 Prinsip Utama: Privasi Data Finansial

> [!CAUTION]
> **JANGAN PERNAH** mengunggah file PDF/CSV mutasi bank asli yang memuat data pribadi (nama, nomor rekening asli, saldo, atau detail transaksi pribadi) ke Issues, Pull Requests, atau repositori ini!
>
> Gunakan **data sintetis / data dummy** (misal: "BUDI SANTOSO", rekening "100000000001", transaksi dummy) saat menulis unit test atau mendiskusikan bug format.

---

## 🛠️ Persiapan Lingkungan Pengembangan (Local Setup)

1. **Fork & Clone Repositori:**
   ```bash
   git clone https://github.com/<username>/rekapimutasi.git
   cd rekapimutasi
   ```

2. **Gunakan Python 3.10+ & Siapkan Virtual Environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Linux / macOS
   # atau: .venv\Scripts\activate  # Windows
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install ruff pytest
   ```

---

## 🏦 Cara Menambahkan Parser Bank Baru

1. **Buat File Parser Bank:**
   Tambahkan file baru di `rekapimutasi/banks/<nama_bank>.py`. Implementasikan parser yang mengekstrak metadata rekening, kantong (*pockets*), dan baris transaksi.

2. **Daftarkan di Registry:**
   Buka `rekapimutasi/registry.py` dan daftarkan kode bank serta parser baru Anda.

3. **Buat Unit Test dengan Data Sintetis:**
   Buat file pengujian di `tests/test_<nama_bank>.py` menggunakan representasi teks PDF dummy sintetis untuk memverifikasi logika parsing dan rekonsiliasi mutasi.

4. **Jalankan Test Suite:**
   ```bash
   python -m unittest discover tests
   ```

5. **Jalankan Linter & Formatter:**
   ```bash
   ruff check .
   ruff format .
   ```

6. **Build Ulang Web Assets (Jika Perlu):**
   Jika Anda mengubah kode Python inti dan ingin memperbarui bundle Pyodide WebAssembly untuk demo web:
   ```bash
   python scripts/build_pages.py
   ```

---

## 🚀 Alur Pengajuan Pull Request (PR)

1. Buat branch baru dari `master`:
   ```bash
   git checkout -b feat/tambah-bank-xyz
   ```
2. Lakukan perubahan, pastikan semua unit test lulus dan `ruff check .` tidak ada warning.
3. Commit perubahan dengan pesan commit yang jelas:
   ```bash
   git commit -m "feat(bank): tambah parser mutasi rekening Bank XYZ"
   ```
4. Push ke fork Anda dan buka Pull Request di GitHub.
5. Lengkapi checklist pada template PR yang tersedia.

Terima kasih atas kontribusi Anda dalam membantu ekosistem open-source finansial Indonesia!
