import time
import argparse
import sys
import cmath
import pyvisa as visa
import numpy as np
import matplotlib.pyplot as plt

def init_instrument(rm, resource, is_osc=False):
    """Inicializace s ošetřením chyb."""
    try:
        inst = rm.open_resource(resource)
        inst.timeout = 5000
        if is_osc:
            # Specifické pro Agilent 54621A na RS-232
            inst.write_termination = '\n'
            inst.read_termination = '\n'
        
        inst.write("*RST")
        time.sleep(1) 
        idn = inst.query("*IDN?").strip()
        print(f"Připojeno k: {idn}")
        return inst
    except Exception as e:
        print(f"Chyba při připojování k {resource}: {e}", file=sys.stderr)
        sys.exit(1)

def measure_impedance():
    parser = argparse.ArgumentParser(description="Měření impedance s perfektním autoscalem")
    parser.add_argument("--gen", default="USB0::0x0957::0x0407::MY44035813::INSTR")
    parser.add_argument("--osc", default="ASRL3::INSTR")
    args = parser.parse_args()

    rm = visa.ResourceManager()
    print("Inicializace přístrojů...")
    gen = init_instrument(rm, args.gen)
    osc = init_instrument(rm, args.osc, is_osc=True)

    R_ref = 50.0 
    
    try:
        # --- Nastavení osciloskopu ---
        osc.write(":ACQ:TYPE AVER")
        osc.write(":ACQ:COUNT 4") 
        osc.write(":CHAN1:DISP ON")
        osc.write(":CHAN2:DISP ON")

        # --- Nastavení generátoru ---
        gen.write("VOLT:UNIT dBm")
        gen.write("FUNC SIN")
        gen.write("VOLT +9dBm") 
        gen.write("VOLT:OFFSET 0")
        gen.write("OUTP ON")
        
        frequencies = np.logspace(2, 5, num=20)
        
        measured_freqs = []
        impedances = []

        for f in frequencies:
            print(f"\n--- Měření při {f:.2f} Hz ---")
            gen.write(f"FREQ {f}")
            
            # 1. Nastavení časové základny (3.5 periody)
            t_range = 3.5 / f
            osc.write(f":TIM:RANGE {t_range}")
            
            # =================================================================
            # 2. INTELIGENTNÍ AUTOSCALE (Až 3 iterace pro nalezení dokonalosti)
            # =================================================================
            for pokus in range(3):
                # Vynucení nového měření do vyčištěného bufferu
                osc.write(":RUN")
                time.sleep(0.1)
                osc.write(":SING")
                osc.query("*OPC?") # Počká na zachycení
                
                potreba_zmeny = False
                
                for ch in [1, 2]:
                    try:
                        vpp = float(osc.query(f":MEAS:VPP? CHAN{ch}"))
                        current_scale = float(osc.query(f":CHAN{ch}:SCAL?"))
                        
                        if vpp > 1e30: 
                            # Měření je přetečené (saturace), oddálíme to na bezpečné 2 Volty/dílek
                            osc.write(f":CHAN{ch}:SCAL 2.0")
                            potreba_zmeny = True
                        else:
                            # Máme reálnou hodnotu VPP, chceme aby vyplnila 6 z 8 dílků
                            ideal_scale = vpp / 6.0
                            
                            # Ochranné oříznutí pro limity Agilentu (2 mV až 5 V)
                            ideal_scale = max(0.002, min(ideal_scale, 5.0))
                            
                            # Změníme měřítko pouze, pokud je rozdíl větší než 15 %
                            if abs(ideal_scale - current_scale) / current_scale > 0.15:
                                osc.write(f":CHAN{ch}:SCAL {ideal_scale}")
                                potreba_zmeny = True
                    except ValueError:
                        pass # Ignoruj dočasné chyby čtení
                
                # Pokud v tomto cyklu nedošlo ke změně, měřítko je dokonalé! Můžeme jít měřit.
                if not potreba_zmeny:
                    break
                    
            # Krátká pauza pro uklidnění hardwarových relátek
            time.sleep(0.3)
            
            # =================================================================
            # 3. FINÁLNÍ MĚŘENÍ SE SPRÁVNÝMI ROZSAHY
            # =================================================================
            osc.write(":RUN")   # Reset průměrování
            time.sleep(0.1)
            osc.write(":SING")  # Čisté zachycení
            osc.query("*OPC?")
            
            try:
                u1_rms = float(osc.query(":MEAS:VRMS? CHAN1"))
                u2_rms = float(osc.query(":MEAS:VRMS? CHAN2"))
                phase_deg = float(osc.query(":MEAS:PHAS?"))
                phase_rad = np.radians(phase_deg)
                
                real_f = float(osc.query(":MEAS:FREQ? CHAN1"))
                
                K = (u2_rms / u1_rms) * cmath.rect(1, phase_rad)
                Z = (K * R_ref) / (1 - K)
                
                measured_freqs.append(real_f)
                impedances.append(abs(Z))
                
                print(f"  U1={u1_rms:.3f}V, U2={u2_rms:.3f}V, Fáze={phase_deg:.1f}°")
                print(f"  |Z| = {abs(Z):.2f} Ohm")
            except Exception as e:
                print(f"  Chyba v bodě {f} Hz: {e}")

        # --- Vykreslení výsledků ---
        plt.figure(figsize=(10, 6))
        plt.loglog(measured_freqs, impedances, 'b-o', label='Změřená impedance')
        plt.title('Impedanční charakteristika (Log-Log)')
        plt.xlabel('Frekvence [Hz]')
        plt.ylabel('Impedance [Ω]')
        plt.grid(True, which="both", ls="--")
        plt.legend()
        plt.show()

    finally:
        print("\nVypínám výstup a zavírám porty...")
        gen.write("OUTP OFF")
        gen.close()
        osc.close()
        rm.close()

if __name__ == "__main__":
    measure_impedance()