import time
import pyvisa
import numpy as np
import matplotlib.pyplot as plt

# ==========================================
# 1. KONFIGURACE PARAMETRŮ
# ==========================================
ADRESA_ZDROJE = "GPIB0::16::INSTR"
ADRESA_MULTIMETRU = "GPIB0::22::INSTR"

POCET_VZORKU = 450
PRODLEVA_S = 0.5
IGNOROVAT_PRVNICH = 100  
DOBA_USTALENI_S = 30     # Čas na tepelné nahřátí zátěže před měřením v sekundách

NAPETI_V = 5.0
PROUD_A = 2.0

# ==========================================
# 2. POMOCNÉ FUNKCE
# ==========================================
def pripoj_pristroje():
    """Naváže spojení přes VISA a vrátí objekty pro komunikaci."""
    rm = pyvisa.ResourceManager()
    zdroj = rm.open_resource(ADRESA_ZDROJE, timeout=5000, write_termination="\n", read_termination="\n")
    multimetr = rm.open_resource(ADRESA_MULTIMETRU, timeout=12000, write_termination="\n", read_termination="\n")
    return rm, zdroj, multimetr

def nastav_pristroje(zdroj, multimetr):
    """Provede výchozí inicializaci zdroje a multimetru."""
    print(f"Identifikace multimetru: {multimetr.query('ID?')}")
    print(f"Identifikace zdroje: {zdroj.query('MODEL?')}")
    
    # Zdroj 
    zdroj.write("OUT 0")
    time.sleep(0.2)
    zdroj.write(f"VSET {NAPETI_V}")
    zdroj.write(f"ISET {PROUD_A}")
    zdroj.write("OUT 1")
    
    # Multimetr
    multimetr.write("RESET")
    time.sleep(1)
    multimetr.write("DCV AUTO")
    multimetr.write("NPLC 10")
    multimetr.write("OFORMAT ASCII")
    multimetr.write("TRIG HOLD")

def pockej_na_ustaleni(sekundy):

    print(f"\n[INFO] Čekám {sekundy} sekund na tepelné ustálení zátěže...")
    for i in range(sekundy, 0, -1):
        
        print(f"Spuštění měření za: {i:2d} s ", end="\r")
        time.sleep(1)
    print("Spuštění měření za:  0 s \n[INFO] Start měřicí smyčky.\n")

def zmer_hodnotu(multimetr):

    multimetr.write("TRIG SGL")
    odpoved = multimetr.read().strip().replace(',', '.')
    return float(odpoved)

def aktualizuj_grafy(fig, ax_graf, ax_hist, odchylky):

    ax_graf.clear()
    ax_graf.plot(odchylky, marker=".", color="blue")
    ax_graf.set_title("Odchylka napětí od průměru (ΔU)")
    ax_graf.set_ylabel("ΔU [V]")
    ax_graf.grid(True)
    
    ax_hist.clear()
    ax_hist.hist(odchylky, bins=20, color="green", edgecolor="black")
    ax_hist.set_title("Histogram odchylek")
    ax_hist.set_xlabel("ΔU [V]")
    ax_hist.set_ylabel("Četnost")
    ax_hist.grid(True)
    
    fig.tight_layout()
    plt.pause(0.01)

def vyhodnot_chyby(data_pole, zadane_napeti):

    prumer = data_pole.mean()
    
    # Výpočet chyb
    abs_chyba = prumer - zadane_napeti
    rel_chyba_pct = (abs_chyba / zadane_napeti) * 100
    
    max_odchylka = np.max(np.abs(data_pole - zadane_napeti))
    max_chyba_pct = (max_odchylka / zadane_napeti) * 100

    print("\n" + "="*50)
    print("ZÁVĚREČNÉ VYHODNOCENÍ MĚŘENÍ")
    print("="*50)
    print(f"Nastavená hodnota (ideál): {zadane_napeti:.5f} V")
    print(f"Naměřený průměr:           {prumer:.5f} V")
    print("-" * 50)
    print(f"Absolutní chyba průměru:   {abs_chyba:+.5f} V")
    print(f"Relativní chyba průměru:   {rel_chyba_pct:+.5f} %")
    print(f"Maximální chyba vzorku:    {max_chyba_pct:+.5f} %")
    print(f"Směrodatná odchylka šumu:  {data_pole.std(ddof=1):.2e} V")
    nejistota_A = data_pole.std(ddof=1) / np.sqrt(len(data_pole))
    print(f"Standardní nejistota (Typ A): {nejistota_A:.2e} V")
    print("="*50 + "\n")

def bezpecne_odpoj(rm, zdroj, multimetr):
    """Vždy bezpečně odpojí zátěž a uzavře sběrnici."""
    print("Ukončuji měření a bezpečně odpojuji přístroje...")
    try:
        zdroj.write("OUT 0")  # Hlavní bezpečnostní krok!
    except Exception:
        pass
    
    try:
        zdroj.close()
        multimetr.close()
        rm.close()
    except Exception:
        pass

# ==========================================
# 3. HLAVNÍ PROGRAM
# ==========================================
def main():
    rm, zdroj, multimetr = pripoj_pristroje()
    
    # Příprava grafiky
    plt.ion()
    fig, (ax_graf, ax_hist) = plt.subplots(2, 1, figsize=(10, 8))
    namerene_hodnoty = []

    try:
        nastav_pristroje(zdroj, multimetr)
        
        # --- TEPLNÉ USTÁLENÍ ZÁTĚŽE ---
        pockej_na_ustaleni(DOBA_USTALENI_S)

        # --- MĚŘICÍ SMYČKA ---
        for i in range(POCET_VZORKU):
            start_cas = time.time()
            
            # Samotné měření
            hodnota = zmer_hodnotu(multimetr)
            namerene_hodnoty.append(hodnota)
            
            # --- ZPRACOVÁNÍ A VYKRESLENÍ ---
            if len(namerene_hodnoty) > IGNOROVAT_PRVNICH:
                platna_data = np.array(namerene_hodnoty[IGNOROVAT_PRVNICH:])
                odchylky = platna_data - platna_data.mean()
                
                print(f"[{i+1}/{POCET_VZORKU}] U = {hodnota:.6f} V | Průměr: {platna_data.mean():.6f} | Směr. odch: {platna_data.std(ddof=1):.2e}")
                aktualizuj_grafy(fig, ax_graf, ax_hist, odchylky)
            else:
                print(f"[{i+1}/{POCET_VZORKU}] U = {hodnota:.6f} V (fáze ustálení DMM...)")

            zbyva_casu = PRODLEVA_S - (time.time() - start_cas)
            if zbyva_casu > 0:
                time.sleep(zbyva_casu)

        # --- ZÁVĚREČNÉ STATISTIKY ---
        platna_data = np.array(namerene_hodnoty[IGNOROVAT_PRVNICH:])
        vyhodnot_chyby(platna_data, NAPETI_V)

        # --- ULOŽENÍ ---
        np.savetxt("vysledky_mereni.csv", namerene_hodnoty, delimiter=";", fmt="%.8f")
        print("Data uložena do 'vysledky_mereni.csv'. Zavřete okno s grafem pro ukončení.")
        
        plt.ioff()
        plt.show()

    except KeyboardInterrupt:
        print("\n[UPOZORNĚNÍ] Měření bylo přerušeno uživatelem (Ctrl+C)!")
    except Exception as e:
        print(f"\n[CHYBA] Nastala chyba: {e}")
    finally:
        bezpecne_odpoj(rm, zdroj, multimetr)

if __name__ == "__main__":
    main()