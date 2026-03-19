import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import sys
import csv

class RS_ZVL_VNA:
    def __init__(self, ip_address: str):
        self.rm = pyvisa.ResourceManager('@py')
        self.address = f"TCPIP::{ip_address}::INSTR"
        self.vna = None

    def connect(self):
        print(f"[*] Pripojuji se k VNA: {self.address}...")
        try:
            self.vna = self.rm.open_resource(self.address)
            self.vna.timeout = 60000  
            self.vna.write("*CLS")
            idn = self.vna.query("*IDN?")
            print(f"[+] Uspesne pripojeno: {idn.strip()}")
        except Exception as e:
            print(f"[-] Chyba pripojeni: {e}")
            sys.exit(1)

    def load_calibration(self, cal_file: str):
        print(f"[*] Nacitam kalibraci: '{cal_file}'...")
        self.vna.write(f"MMEMory:LOAD:CORRection '{cal_file}'")
        time.sleep(1.2)
        
        status = self.vna.query("SENS:CORR:STAT?").strip()
        if status == '1':
            print("[+] Kalibrace je aktivni.")
        else:
            print("[-] Varovani: Kalibrace neni aktivni nebo se nenacetla!")

    def configure_sweep(self, f_start: str, f_stop: str, points: int):
        print(f"[*] Nastavuji sweep: {f_start} az {f_stop}, {points} bodu...")
        self.vna.write(f"SENS1:FREQ:STAR {f_start}")
        self.vna.write(f"SENS1:FREQ:STOP {f_stop}")
        self.vna.write(f"SENS1:SWE:POIN {points}")
        time.sleep(0.2)
        
        print("[*] Konfiguruji Averaging (faktor 10)...")
        self.vna.write("SENS1:AVER ON")
        self.vna.write("SENS1:AVER:COUN 20")
        self.vna.write("SENS1:AVER:MODE CLEar")
        time.sleep(0.2)

        print("[*] Prirazuji stopy: TRC1 = S11, TRC2 = S21...")
        self.vna.write("CALCulate1:PARameter:SDEF 'TRC1','S11'")
        self.vna.write("DISPlay:WINDow1:TRACe1:FEED 'TRC1'")
        time.sleep(0.1)
        
        self.vna.write("CALCulate1:PARameter:SDEF 'TRC2','S21'")
        self.vna.write("DISPlay:WINDow1:TRACe2:FEED 'TRC2'")
        time.sleep(0.1)

        self.vna.write("FORM:DATA ASCII")
        time.sleep(0.5)

    def perform_measurement(self):
        print("[*] Spoustim mereni a cekam na averaging...")
        self.vna.write("INIT:CONT OFF")
        self.vna.write("INIT:IMM")
        self.vna.query("*OPC?") 
        print("[+] Mereni dokonceno.")

    def fetch_data(self) -> tuple:
        print("[*] Stahuji data (ASCII)...")
        
        start = float(self.vna.query("SENS1:FREQ:STAR?"))
        stop = float(self.vna.query("SENS1:FREQ:STOP?"))
        points = int(self.vna.query("SENS1:SWE:POIN?"))
        freq_hz = np.linspace(start, stop, points)
        time.sleep(0.2)
        
        print("  * Stahuji S11 (TRC1)...")
        self.vna.write("CALCulate1:PARameter:SELect 'TRC1'")
        time.sleep(0.2)
        s11_db = np.array(self.vna.query_ascii_values("CALCulate1:DATA? FDAT"))
        
        print("  * Stahuji S21 (TRC2)...")
        self.vna.write("CALCulate1:PARameter:SELect 'TRC2'")
        time.sleep(0.2)
        s21_db = np.array(self.vna.query_ascii_values("CALCulate1:DATA? FDAT"))
        
        print(f"[+] Data uspesne stazena ({len(freq_hz)} bodu).")
        return freq_hz, s11_db, s21_db

    def disconnect(self):
        if self.vna:
            print("[*] Ukoncuji spojeni a vracim pristroj do rezimu Continuous...")
            self.vna.write("INIT:CONT ON")
            time.sleep(0.2)
            self.vna.close()
        self.rm.close()


def save_to_csv(filename: str, freq: np.ndarray, s11: np.ndarray, s21: np.ndarray):
    print(f"[*] Ukladam data do souboru: {filename}...")
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Frekvence [Hz]', 'S11 [dB]', 'S21 [dB]'])
        min_len = min(len(freq), len(s11), len(s21))
        for i in range(min_len):
            writer.writerow([freq[i], s11[i], s21[i]])
    print("[+] Ulozeno.")

def plot_data(freq: np.ndarray, s11: np.ndarray, s21: np.ndarray):
    print("[*] Generuji graf...")
    freq_ghz = freq / 1e9  
    
    plt.figure(figsize=(11, 7))
    plt.plot(freq_ghz, s11, label="S11 (Odraz)", color='blue', linewidth=1.5)
    plt.plot(freq_ghz, s21, label="S21 (Prenos)", color='red', linestyle='--', linewidth=1.5)
    
    plt.xlabel("Frekvence [GHz]", fontsize=12)
    plt.ylabel("Modul [dB]", fontsize=12)
    plt.title("Rozptylove parametry S11 a S21 z R&S ZVL-6 (Vyhlazeno)", fontsize=14)
    plt.grid(True, linestyle=":", alpha=0.5, which='both')
    plt.legend(fontsize=11, loc='lower right')
    plt.tick_params(labelsize=11)
    
    if s21.size > 0 and s11.size > 0:
        plt.ylim(min(np.min(s21), np.min(s11)) - 5, 5)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    IP_ADRESA = "192.168.0.2"
    KALIBRACE = "JL1.cal"
    
    zvl = RS_ZVL_VNA(IP_ADRESA)
    zvl.connect()
    
    try:
        zvl.load_calibration(KALIBRACE)
        zvl.configure_sweep(f_start="200MHz", f_stop="4.6GHz", points=2001)
        zvl.perform_measurement()
        
        frekvence, s11_data, s21_data = zvl.fetch_data()
        
        save_to_csv("zvl_mereni_ciste.csv", frekvence, s11_data, s21_data)
        plot_data(frekvence, s11_data, s21_data)

    except KeyboardInterrupt:
        print("\n[-] Mereni bylo preruseno uzivatelem.")
    except Exception as e:
        print(f"\n[-] Nastala chyba: {e}")
    finally:
        zvl.disconnect()