## Ringkasan Perubahan (Summary)
Jelaskan secara singkat apa yang dilakukan pada Pull Request ini:

- **Tipe Perubahan:**
  - [ ] 🐛 **Perbaikan Bug Parser** (memperbaiki format mutasi bank yang sudah ada)
  - [ ] 🏦 **Penambahan Bank Baru** (menambahkan parser untuk bank baru)
  - [ ] 🎨 **Tampilan Web / UI** (tampilan, responsivitas, style)
  - [ ] ⚡ **Optimasi / Engine WASM** (performa Pyodide, ekspor file, dll.)
  - [ ] 📝 **Dokumentasi / Typo**
- **Bank yang Terkait:** (Contoh: BCA / Mandiri / Jago / BNI / Tidak terkait bank spesifik)

---

## 🔒 Kebijakan Privasi (Wajib untuk Semua PR)
- [ ] **Bebas Data Pribadi:** Saya memastikan **TIDAK ADA dokumen asli atau data pribadi finansial** (nama lengkap, nomor rekening riil, saldo asli) yang diikutsertakan ke dalam repositori ini.

---

## Checklist Kontributor

*(Centang yang relevan dengan perubahan Anda, biarkan kosong jika tidak berlaku)*

### Jika Mengubah / Menambah Parser Bank:
- [ ] Menyertakan pengujian dengan **data dummy/sintetis** (nama samaran, nomor rekening dummy).
- [ ] Logika rekonsiliasi (saldo awal, mutasi kredit/debet, saldo akhir) terverifikasi dengan benar.

### Untuk Semua Kontributor:
- [ ] Semua pengujian lokal tetap lulus (`python -m unittest discover tests`).
- [ ] Kode bersih dan lolos pemeriksaan linter (`ruff check .` dan `ruff format .`).
- [ ] *(Jika mengubah tampilan/Python inti)* Sudah mencoba build web lokal via `python scripts/build_pages.py`.

---

## Issue yang Terkait (Opsional)
Closes #
