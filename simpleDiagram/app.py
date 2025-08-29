import subprocess
import os
import platform

def convert_vsdx_to_svg(input_path, output_dir):
    """
    Mengonversi satu file VSDX menjadi SVG menggunakan LibreOffice CLI.

    Args:
        input_path (str): Path lengkap ke file .vsdx yang akan dikonversi.
        output_dir (str): Path ke folder tempat menyimpan hasil .svg.
    
    Returns:
        bool: True jika berhasil, False jika gagal.
    """
    # Menentukan path ke soffice.exe secara otomatis (disesuaikan untuk Windows)
    # Anda bisa mengubah ini jika lokasi instalasi Anda berbeda.
    if platform.system() == "Windows":
        soffice_path = r"C:\Program Files\LibreOffice\program\soffice.exe"
    else:
        # Untuk Linux atau macOS, 'soffice' biasanya sudah ada di PATH
        soffice_path = "soffice"

    # --- Membuat Perintah sebagai List ---
    # Ini adalah cara paling aman untuk menghindari error karena spasi/karakter khusus
    command = [
        soffice_path,
        "--headless",
        "--convert-to", "svg",
        "--outdir", output_dir,
        input_path
    ]

    print("INFO: Menjalankan perintah konversi...")
    print(f"CMD: {' '.join(command)}")

    try:
        # Menjalankan perintah
        # check=True akan otomatis memunculkan error jika konversi gagal
        # capture_output=True akan menangkap pesan dari LibreOffice untuk debugging
        result = subprocess.run(
            command, 
            check=True, 
            capture_output=True, 
            text=True
        )
        print("✅ SUKSES: File berhasil dikonversi!")
        # stdout dari libreoffice biasanya kosong jika sukses
        if result.stdout:
            print(f"INFO: {result.stdout}")
        return True

    except FileNotFoundError:
        print(f"❌ ERROR: Perintah '{soffice_path}' tidak ditemukan.")
        print("Pastikan LibreOffice terinstal di lokasi yang benar.")
        return False
        
    except subprocess.CalledProcessError as e:
        print("❌ ERROR: LibreOffice gagal melakukan konversi.")
        # stderr akan berisi pesan error dari LibreOffice, sangat berguna untuk debugging
        print(f"Pesan Error dari LibreOffice: {e.stderr}")
        return False

# --- BAGIAN UTAMA UNTUK MENJALANKAN KODE ---
if __name__ == "__main__":
    # 1. Tentukan path input dan output Anda di sini
    # Gunakan path lengkap (absolut) untuk menghindari kebingungan
    base_dir = r"C:\Users\ACER\Documents\KeperluanKP\PelaksanaanKP\terkaitKP\VSDX_TO_SVG\simpleDiagram"
    
    # SESUDAH
    input_file = os.path.join(base_dir, "testing.vsdx")
    output_folder = os.path.join(base_dir, "output")
    
    print(f"Direktori kerja saat ini: {os.getcwd()}")
    print(f"Mencari file di path lengkap: {input_file}")

    # 2. Pastikan file input ada dan folder output sudah dibuat
    if not os.path.exists(input_file):
        print(f"File input tidak ditemukan di: {input_file}")
    else:
        if not os.path.exists(output_folder):
            print(f"Membuat folder output di: {output_folder}")
            os.makedirs(output_folder)
        
        # 3. Panggil fungsi konversi
        convert_vsdx_to_svg(input_file, output_folder)