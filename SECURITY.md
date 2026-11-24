# Kebijakan Keamanan & Privasi (Security Policy)

Keamanan dan privasi data finansial pengguna adalah prioritas tertinggi di **rekapimutasi**.

---

## 🛡️ Prinsip Privasi: 100% Client-Side Processing

Aplikasi web **rekapimutasi** dirancang dengan arsitektur *Zero-Server Data Transmission*:
- Seluruh engine parsing Python berjalan secara lokal di browser pengguna menggunakan **Pyodide WebAssembly**.
- File PDF/CSV mutasi bank, password file, nomor rekening, saldo, dan seluruh transaksi diproses di memori browser lokal dan **TIDAK PERNAH dikirim atau disimpan ke server mana pun**.
- Tidak ada database atau penyimpanan awan pihak ketiga yang menyimpan dokumen Anda.

---

## ⚠️ Peringatan untuk Kontributor & Pelapor Masalah

Saat melaporkan kendala format mutasi atau membuka issue:
- **JANGAN PERNAH melampirkan file mutasi asli** yang memuat identitas personal (Nama Lengkap, Nomor Rekening Asli, Saldo Asli, Riwayat Transaksi Riil).
- Selalu sensor (*redact*) atau gunakan data tiruan (*dummy/synthetic*) sebelum membagikan cuplikan teks atau tangkapan layar.

---

## 🚨 Melaporkan Kerentanan Keamanan (Reporting a Vulnerability)

Jika Anda menemukan celah keamanan (*security vulnerability*) atau potensi kebocoran data pada repositori ini:

1. **Gunakan Fitur Private Vulnerability Reporting:**
   Laporkan secara rahasia melalui tab [Security Advisories](https://github.com/EkmalRey/rekapimutasi/security/advisories/new) di repositori GitHub kami.
2. **Jangan Membuka Public Issue:**
   Harap tidak memublikasikan detail kerentanan di issue publik sebelum perbaikan (*fix*) siap dirilis.
3. **Informasi yang Dibutuhkan:**
   - Deskripsi detail mengenai celah yang ditemukan.
   - Langkah-langkah untuk mereproduksi (Proof of Concept).
   - Dampak potensial terhadap pengguna atau keamanan browser.

Pengelola proyek berkomitmen untuk merespons dan meninjau laporan keamanan yang masuk sesegera mungkin.
