import time
import argparse
import sys
import cmath
import pyvisa as visa
import numpy as np
import matplotlib.pyplot as plt

def init_instrument(rm, resource, is_osc=False):
    try:
        inst = rm.open_resource(resource)
        inst.timeout = 10000
        if is_osc:
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
    parser = argparse.ArgumentParser(description="Měření impedance s plynulým autoscalem")
    parser.add_argument("--gen", default="USB0::0x0957::0x0407::MY44035813::INSTR")
    parser.add_argument("--osc", default="ASRL3::INSTR")
    args = parser.parse_args()

    rm = visa.ResourceManager()
    gen = init_instrument(rm, args.gen)
    osc = init_instrument(rm, args.osc, is_osc=True)

    R_ref = 50.0 
    # Standardní řada Agilentu pro vertikální citlivost
    SCALES = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
    
    try:
        gen.write("VOLT:UNIT dBm")
        gen.write("FUNC SIN")
        gen.write("VOLT +9dBm") 
        gen.write("VOLT:OFFSET 0")
        gen.write("OUTP ON")
        
        frequencies = np.logspace(2, 5, num=100)
        measured_freqs = []
        impedances = []
        phases = []

        for f in frequencies:
            print(f"\n--- Frekvence {f:.2f} Hz ---")
            gen.write(f"FREQ {f}")
            osc.write(f":TIM:RANGE {3.5 / f}")
            
            # --- POSTUPNÝ SMART SCALE ---
            for ch in [1, 2]:
                print(f" Ladím CH{ch}...", end="", flush=True)
                for _ in range(5):  # Max 5 kroků pro nalezení rozsahu
                    osc.write(":SING")
                    osc.query("*OPC?")
                    vpp = float(osc.query(f":MEAS:VPP? CHAN{ch}"))
                    curr_s = float(osc.query(f":CHAN{ch}:SCAL?"))
                    
                    # Najdeme index aktuálního měřítka v řadě
                    idx = min(range(len(SCALES)), key=lambda i: abs(SCALES[i]-curr_s))

                    if vpp > 1e30: # SATURACE -> zvýšit o jeden krok
                        if idx < len(SCALES) - 1:
                            osc.write(f":CHAN{ch}:SCAL {SCALES[idx+1]}")
                            time.sleep(0.2)
                            continue
                    
                    dilky = vpp / curr_s
                    if dilky < 2.0: # MOC MALÉ -> snížit o jeden krok
                        if idx > 0:
                            osc.write(f":CHAN{ch}:SCAL {SCALES[idx-1]}")
                            time.sleep(0.2)
                            continue
                    
                    if dilky > 7.5: # SKORO SATURACE -> zvýšit o jeden krok
                        if idx < len(SCALES) - 1:
                            osc.write(f":CHAN{ch}:SCAL {SCALES[idx+1]}")
                            time.sleep(0.2)
                            continue
                    
                    break # Rozsah je OK
                print(" OK", end="")

            # --- FINÁLNÍ SBĚR DAT ---
            osc.write(":ACQ:TYPE AVER")
            osc.write(":ACQ:COUNT 4")
            time.sleep(0.5)
            osc.write(":SING")
            osc.query("*OPC?")
            
            try:
                u1 = float(osc.query(":MEAS:VRMS? CHAN1"))
                u2 = float(osc.query(":MEAS:VRMS? CHAN2"))
                
                ph_deg = (float(osc.query(":MEAS:PHAS?")))
                
                
                ph_rad = np.radians(ph_deg)
                
                K = (u2 / u1) * cmath.rect(1, ph_rad)
                Z = (K * R_ref) / (1 - K)
                
                measured_freqs.append(f)
                impedances.append(abs(Z))
                if (ph_deg>1000):
                    phases.append(0)
                else:
                    phases.append(ph_deg)
                print(f"\n  |Z| = {abs(Z):.2f} Ohm (U2: {u2*1000:.1f} mV)")
                print(f"\n  degree = {ph_deg} rad { ph_rad}")
            except:
                print("\n  Chyba výpočtu.")

        # Graf
        plt.figure(figsize=(10, 6))
        plt.loglog(measured_freqs, impedances, color='red', linestyle='-', marker='x')
        plt.grid(True, which="both", ls="--")
        plt.title("Modulová impedanční charakteristika")
        plt.xlabel("Frekvence [Hz]")
        plt.ylabel("Modul impedance [Ω]")
        plt.show(block=False)
        
        plt.figure(figsize=(10, 6))
        plt.semilogx(measured_freqs, phases, color='blue', linestyle='-', marker='x')
        plt.grid(True, which="both", ls="--")
        plt.title("Fázová impedanční charakteristika")
        plt.xlabel("Frekvence [Hz]")
        plt.ylabel("Fáze [°]")
        plt.show()
    finally:
        gen.write("OUTP OFF")
        gen.close()
        osc.close()

if __name__ == "__main__":
    measure_impedance()