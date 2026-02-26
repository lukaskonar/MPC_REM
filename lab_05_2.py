import time
import argparse
import sys
import cmath
import pyvisa as visa
import numpy as np
import matplotlib.pyplot as plt

def init_instrument(rm, resource, is_osc=False):
    """Inicializace přístroje s ošetřením chyb."""
    try:
        inst = rm.open_resource(resource)
        inst.timeout = 10000  # Vyšší timeout pro pomalý Autoscale a RS-232
        if is_osc:
            # Specifické nastavení pro Agilent 54621A
            inst.write_termination = '\n'
            inst.read_termination = '\n'
        
        inst.write("*RST")
        time.sleep(1.5) 
        idn = inst.query("*IDN?").strip()
        print(f"Připojeno k: {idn}")
        return inst
    except Exception as e:
        print(f"Chyba při připojování k {resource}: {e}", file=sys.stderr)
        sys.exit(1)

def measure_impedance():
    parser = argparse.ArgumentParser(description="Měření impedance pomocí :AUT a záchrany CH2")
    parser.add_argument("--gen", default="USB0::0x0957::0x0407::MY44035813::INSTR")
    parser.add_argument("--osc", default="ASRL3::INSTR")
    args = parser.parse_args()

    rm = visa.ResourceManager()
    print("Inicializace přístrojů...")
    gen = init_instrument(rm, args.gen)
    osc = init_instrument(rm, args.osc, is_osc=True)

    R_ref = 50.0  # Tvůj referenční odpor
    
    try:
        # --- Základní nastavení generátoru ---
        gen.write("VOLT:UNIT dBm")
        gen.write("FUNC SIN")
        gen.write("VOLT +9dBm")  # Bezpečné 2V špička-špička
        gen.write("VOLT:OFFSET 0")
        gen.write("OUTP ON")
        
        # 50 bodů logaritmicky od 100 Hz do 100 kHz
        frequencies = np.logspace(2, 5, num=20)
        
        measured_freqs = []
        impedances = []

        for f in frequencies:
            print(f"\n>>> Měření: {f:.2f} Hz", end=" ", flush=True)
            gen.write(f"FREQ {f}")
            
            # 1. Spuštění Autoscale (zabere čas a cvaká)
            osc.write(":AUT")
            time.sleep(1.0) # Dostatek času na mechanické přepnutí relé
            
            # 2. Záchranná mise pro Kanál 2
            # Vynutíme zobrazení obou kanálů, i kdyby je Autoscale vypnul
            osc.write(":CHAN1:DISP ON")
            osc.write(":CHAN2:DISP ON")
            
            try:
                # Zkusíme přečíst VPP na CH2, abychom zjistili, jestli "žije"
                vpp2 = float(osc.query(":MEAS:VPP? CHAN2"))
                if vpp2 < 0.02 or vpp2 > 1e20:
                    # Pokud nic nevidí, skočíme na citlivých 10mV/div
                    osc.write(":CHAN2:SCAL 0.01")
                    time.sleep(0.1)
            except:
                osc.write(":CHAN2:SCAL 0.01")

            # 3. Oprava časové základny a průměrování (Autoscale je přenastavil)
            t_range = 3.5 / f
            osc.write(f":TIM:RANGE {t_range}")
            osc.write(":ACQ:TYPE AVER")
            osc.write(":ACQ:COUNT 4")
            time.sleep(0.5) # Čas na ustálení průměru

            # 4. Samotné vyčtení dat
            osc.write(":SING")
            osc.query("*OPC?")
            
            try:
                u1_rms = float(osc.query(":MEAS:VRMS? CHAN1"))
                u2_rms = float(osc.query(":MEAS:VRMS? CHAN2"))
                phase_deg = float(osc.query(":MEAS:PHAS?"))
                phase_rad = np.radians(phase_deg)
                
                # Výpočet impedance pomocí komplexních čísel
                # K = (U2/U1) s fázovým posuvem
                K = (u2_rms / u1_rms) * cmath.rect(1, phase_rad)
                # Z = (K * R_ref) / (1 - K)
                Z_complex = (K * R_ref) / (1 - K)
                
                z_modul = abs(Z_complex)
                
                measured_freqs.append(f)
                impedances.append(z_modul)
                
                print(f"-> |Z| = {z_modul:.2f} Ω (U2={u2_rms*1000:.1f} mV)")
            except Exception as e:
                print(f"-> Chyba: {e}")

        # --- Finální graf ---
        plt.figure(figsize=(10, 6))
        plt.loglog(measured_freqs, impedances, 'r-o', linewidth=1.5, markersize=4)
        plt.title('Impedanční charakteristika')
        plt.xlabel('Frekvence [Hz]')
        plt.ylabel('Impedance [Ω]')
        plt.grid(True, which="both", ls="--", alpha=0.7)
        plt.show()

    finally:
        print("\nUkončování a úklid...")
        gen.write("OUTP OFF")
        gen.close()
        osc.close()
        rm.close()

if __name__ == "__main__":
    measure_impedance()