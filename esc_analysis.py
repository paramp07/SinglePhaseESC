import os
import numpy as np
import matplotlib
matplotlib.use('Agg') # Headless backend to prevent blocking
import matplotlib.pyplot as plt
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
import PySpice.Logging.Logging as Logging

# Setup logger
logger = Logging.setup_logging()

def simulate_current_sense():
    print("--- Simulation 1: Current Sense Low-Pass Filter ---")
    
    # 1. Transient Analysis
    circuit_trans = Circuit('Current Sense Filter - Transient')
    
    # Input is DC (0.5V, 50A telemetry) + 48kHz switching ripple (0.2V peak-to-peak) + 1MHz noise (0.5V peak-to-peak)
    # We sum the sources in series
    circuit_trans.V('dc', 'in_dc', circuit_trans.gnd, 0.5@u_V)
    circuit_trans.PulseVoltageSource('ripple', 'in_ripple', 'in_dc',
                                     initial_value=-0.1@u_V, pulsed_value=0.1@u_V,
                                     pulse_width=10.4@u_us, period=20.8@u_us,
                                     rise_time=0.1@u_us, fall_time=0.1@u_us)
    circuit_trans.SinusoidalVoltageSource('noise', 'in_noise', 'in_ripple',
                                          amplitude=0.25@u_V, frequency=1@u_MHz)
    
    # RC Filter
    circuit_trans.R('27', 'in_noise', 'mcu_adc', 1@u_kOhm)
    circuit_trans.C('30', 'mcu_adc', circuit_trans.gnd, 100@u_nF)
    
    # Simulate for 1 ms to see the long term average
    simulator_trans = circuit_trans.simulator(temperature=25, nominal_temperature=25)
    analysis_trans = simulator_trans.transient(step_time=50@u_ns, end_time=1@u_ms)
    
    # 2. AC Frequency Analysis
    circuit_ac = Circuit('Current Sense Filter - AC')
    circuit_ac.V('input', 'vin', circuit_ac.gnd, 'DC 0V AC 1V')
    circuit_ac.R('27', 'vin', 'mcu_adc', 1@u_kOhm)
    circuit_ac.C('30', 'mcu_adc', circuit_ac.gnd, 100@u_nF)
    
    simulator_ac = circuit_ac.simulator(temperature=25, nominal_temperature=25)
    analysis_ac = simulator_ac.ac(start_frequency=10@u_Hz, stop_frequency=1@u_MHz, number_of_points=10, variation='dec')
    
    # --- Plotting Current Sense LPF ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    
    # Transient plot (zoom on the first 100us)
    t = np.asarray(analysis_trans.time) * 1e6 # convert to microseconds
    vin = np.asarray(analysis_trans.in_noise)
    vout = np.asarray(analysis_trans.mcu_adc)
    
    ax1.plot(t, vin, label='Noisy INA180 Output (Input to Filter)', color='orange', alpha=0.7)
    ax1.plot(t, vout, label='Filtered ADC Input (R27/C30 Output)', color='blue', linewidth=2.5)
    ax1.axhline(0.5, color='green', linestyle=':', label='Target DC Average (0.5V = 50A)')
    ax1.set_xlim(0, 100) # zoom on first 100us to see cycles clearly
    ax1.set_xlabel('Time (Microseconds)')
    ax1.set_ylabel('Voltage (V)')
    ax1.set_title('Transient Response of Current Sense LPF (First 100µs)')
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend()
    
    # AC plot (Bode plot)
    freq = np.asarray(analysis_ac.frequency)
    gain = 20 * np.log10(np.abs(np.asarray(analysis_ac.mcu_adc)))
    phase = np.angle(np.asarray(analysis_ac.mcu_adc), deg=True)
    
    ax2.semilogx(freq, gain, color='blue', linewidth=2)
    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel('Gain (dB)', color='blue')
    ax2.tick_params(axis='y', labelcolor='blue')
    ax2.axvline(1590, color='red', linestyle='--', label='Cutoff Frequency (fc ≈ 1.59 kHz)')
    ax2.axvline(48000, color='purple', linestyle=':', label='Switching Frequency (48 kHz)')
    
    # Find attenuation at 48kHz
    idx_48k = np.abs(freq - 48000).argmin()
    gain_48k = gain[idx_48k]
    ax2.plot(freq[idx_48k], gain_48k, 'ro')
    ax2.annotate(f'{gain_48k:.1f} dB at 48kHz', 
                 xy=(freq[idx_48k], gain_48k), 
                 xytext=(freq[idx_48k]*1.5, gain_48k - 5),
                 arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=6))
    
    ax2.set_title('AC Frequency Response (Bode Gain Plot)')
    ax2.grid(True, which='both', linestyle='--', alpha=0.4)
    ax2.legend()
    
    plt.tight_layout()
    plt.savefig('current_sense_plot.png', dpi=300)
    plt.close()
    print("Saved Current Sense plot to 'current_sense_plot.png'")
    print(f"Attenuation at 48kHz: {gain_48k:.2f} dB")


def simulate_bootstrap():
    print("\n--- Simulation 2: Bootstrap Capacitor Discharge ---")
    
    circuit = Circuit('Bootstrap Capacitor Discharge')
    
    # Diode: 1N5819WS Schottky Diode Model
    circuit.model('D1N5819WS', 'D', IS=1e-6, N=1.1, RS=0.1)
    
    # 12V Vcc gate driver supply
    circuit.V('cc', 'vcc', circuit.gnd, 12@u_V)
    
    # Diode from Vcc to BST pin
    circuit.Diode('1', 'vcc', 'bst', model='D1N5819WS')
    
    # Bootstrap Capacitor C_boot (1uF) connected between BST and PHASE
    circuit.C('boot', 'bst', 'phase', 1@u_uF)
    
    # MOSFET Gate-Source capacitance (5nF) connected between GATE and PHASE
    circuit.C('gate', 'gate', 'phase', 5@u_nF)
    
    # Resistor representing the external or internal gate-source discharge path
    # We will simulate 100kOhm as standard, and print the math for 10kOhm.
    circuit.R('pull', 'gate', 'phase', 100@u_kOhm)
    
    # Voltage Controlled Switch to connect BST to GATE when high-side driver is ON
    circuit.model('MySwitch', 'SW', RON=1, ROFF=1e10, VT=1)
    circuit.VoltageControlledSwitch('gate_drive', 'bst', 'gate', 'ctrl', circuit.gnd, model='MySwitch')
    
    # Control signals:
    # 'ctrl' goes HIGH at 100us to close the gate drive switch
    circuit.PulseVoltageSource('ctrl_src', 'ctrl', circuit.gnd, 
                               initial_value=0@u_V, pulsed_value=2@u_V, 
                               pulse_width=2.5@u_ms, period=5@u_ms, delay_time=100@u_us)
                               
    # 'phase' node: at 0V during low-side ON, flies to 25.2V (Vbat) at 100us when high-side turns ON
    circuit.PulseVoltageSource('phase_src', 'phase', circuit.gnd, 
                               initial_value=0@u_V, pulsed_value=25.2@u_V, 
                               pulse_width=2.5@u_ms, period=5@u_ms, delay_time=100@u_us)
    
    # Quiescent current source of high-side gate driver (150uA) drawing from BST to PHASE
    circuit.I('quiescent', 'bst', 'phase', 150@u_uA)
    
    # Simulate transient behavior for 2.5 ms
    simulator = circuit.simulator(temperature=25, nominal_temperature=25)
    analysis = simulator.transient(step_time=1@u_us, end_time=2.5@u_ms)
    
    t = np.asarray(analysis.time) * 1e3 # convert to milliseconds
    vbst = np.asarray(analysis.bst)
    vphase = np.asarray(analysis.phase)
    vgate = np.asarray(analysis.gate)
    
    vboot = vbst - vphase # Voltage across bootstrap capacitor
    vgs = vgate - vphase # MOSFET Gate-Source voltage
    
    # Plotting
    plt.figure(figsize=(10, 6))
    plt.plot(t, vboot, label='Bootstrap Cap Voltage (V_bst - V_phase)', color='blue', linewidth=2.5)
    plt.plot(t, vgs, label='MOSFET Gate-Source Voltage (V_gs)', color='red', linestyle='--', linewidth=2)
    
    # Threshold lines
    plt.axhline(8.0, color='orange', linestyle=':', label='Safe Miller Threshold Limit (8V)')
    plt.axhline(5.0, color='red', linestyle=':', label='Linear Region Gate Destruct Threshold (5V)')
    
    plt.xlabel('Time (Milliseconds)')
    plt.ylabel('Voltage (V)')
    plt.title('Bootstrap Capacitor Discharge transient during 2ms 100% Throttle Hold')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.xlim(0, 2.5)
    plt.legend(loc='lower right')
    
    plt.tight_layout()
    plt.savefig('bootstrap_plot.png', dpi=300)
    plt.close()
    
    idx_90u = np.abs(t - 0.09).argmin()
    idx_110u = np.abs(t - 0.11).argmin()
    idx_2100u = np.abs(t - 2.1).argmin()
    
    print("Saved Bootstrap plot to 'bootstrap_plot.png'")
    print(f"Pre-turn-on Vboot: {vboot[idx_90u]:.2f} V")
    print(f"Post-turn-on Vboot (immediately after gate charge draw): {vboot[idx_110u]:.2f} V")
    print(f"Gate-Source Vgs immediately after turn-on: {vgs[idx_110u]:.2f} V")
    print(f"End of 2.0ms throttle hold: Vboot = {vboot[idx_2100u]:.2f} V, Vgs = {vgs[idx_2100u]:.2f} V")
    if vgs[idx_2100u] >= 8.0:
        print("RESULT: Safe! MOSFET Gate voltage remains well above the 8V Miller limit.")
    else:
        print("RESULT: Warning! MOSFET Gate voltage dropped below 8V.")


def simulate_bemf():
    print("\n--- Simulation 3: BEMF Voltage Divider Sweep ---")
    
    circuit = Circuit('BEMF Divider Sweep')
    
    # Swept input voltage source representing phase voltage
    circuit.V('phase', 'phase_in', circuit.gnd, 0@u_V)
    
    # BEMF Voltage Divider (R_upper = 33k, R_lower = 3.3k)
    circuit.R('upper', 'phase_in', 'mcu_pin', 33@u_kOhm)
    circuit.R('lower', 'mcu_pin', circuit.gnd, 3.3@u_kOhm)
    
    # Run DC Sweep on phase_in source from 0 to 40V
    simulator = circuit.simulator(temperature=25, nominal_temperature=25)
    analysis = simulator.dc(vphase=slice(0, 40, 0.1))
    
    v_phase_sweep = np.asarray(analysis.sweep)
    v_mcu_pin = np.asarray(analysis.mcu_pin)
    
    # Find exact point where MCU pin voltage crosses 3.3V
    cross_idx = np.abs(v_mcu_pin - 3.3).argmin()
    phase_cross_voltage = v_phase_sweep[cross_idx]
    mcu_cross_val = v_mcu_pin[cross_idx]
    
    # Plotting
    plt.figure(figsize=(10, 6))
    plt.plot(v_phase_sweep, v_mcu_pin, color='green', linewidth=2.5, label='MCU Pin Voltage')
    plt.axhline(3.3, color='red', linestyle='--', label='Absolute Max MCU Pin Limit (3.3V)')
    
    # Mark crossing point
    plt.plot(phase_cross_voltage, mcu_cross_val, 'ro', markersize=8)
    plt.annotate(f'MCU Pin = 3.3V\nat Phase = {phase_cross_voltage:.2f}V', 
                 xy=(phase_cross_voltage, mcu_cross_val), 
                 xytext=(phase_cross_voltage - 10, mcu_cross_val + 0.3),
                 arrowprops=dict(facecolor='black', shrink=0.08, width=1, headwidth=6),
                 bbox=dict(boxstyle='round,pad=0.3', fc='yellow', alpha=0.5))
                 
    plt.xlabel('Motor Phase Voltage (V)')
    plt.ylabel('Microcontroller Pin Voltage (V)')
    plt.title('BEMF Voltage Divider DC Sweep (Phase Input vs. MCU Pin)')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.xlim(0, 40)
    plt.ylim(0, 4)
    plt.legend()
    
    plt.tight_layout()
    plt.savefig('bemf_plot.png', dpi=300)
    plt.close()
    
    print("Saved BEMF plot to 'bemf_plot.png'")
    print(f"MCU input pin crosses the 3.3V destruction line at Phase Voltage = {phase_cross_voltage:.1f} V")
    print(f"BEMF divider scaling factor: {v_mcu_pin[10]/v_phase_sweep[10]:.4f} (expected 1/11 approx. 0.0909)")


def simulate_shoot_through():
    print("\n--- Simulation 4: Shoot-Through Analysis ---")
    
    # We will simulate a half-bridge with 10 Ohm gate resistors and 20ns dead-time.
    # We compare:
    # 1. No bypass diodes (Standard 10R resistors)
    # 2. With Schottky bypass diodes (anode at gate, cathode at driver)
    
    def run_bridge_sim(with_diodes):
        circuit = Circuit('Half-Bridge Shoot-Through')
        circuit.model('MyMOS', 'nmos', VTO=2.5, KP=50)
        
        # Power supply 25.2V
        circuit.V('bat', 'vbat', circuit.gnd, 25.2@u_V)
        
        # High-Side and Low-Side MOSFETs
        circuit.M('HS', 'vbat', 'gate_hs', 'phase', 'phase', model='MyMOS')
        circuit.M('LS', 'phase', 'gate_ls', circuit.gnd, circuit.gnd, model='MyMOS')
        
        # Gate Drive Signals
        # HS turns off at t = 5us
        circuit.PulseVoltageSource('hs_drive', 'gate_hs_drive', 'phase', 
                                   initial_value=10@u_V, pulsed_value=0@u_V, 
                                   delay_time=5@u_us, rise_time=20@u_ns, fall_time=20@u_ns, 
                                   pulse_width=10@u_us, period=20@u_us)
        
        # LS turns on at t = 5.02us (20ns dead-time to demonstrate shoot-through risk)
        circuit.PulseVoltageSource('ls_drive', 'gate_ls_drive', circuit.gnd, 
                                   initial_value=0@u_V, pulsed_value=10@u_V, 
                                   delay_time=5.02@u_us, rise_time=20@u_ns, fall_time=20@u_ns, 
                                   pulse_width=4@u_us, period=20@u_us)
        
        # Gate Resistors (10 Ohm)
        circuit.R('gate_hs', 'gate_hs_drive', 'gate_hs', 10@u_Ohm)
        circuit.R('gate_ls', 'gate_ls_drive', 'gate_ls', 10@u_Ohm)
        
        # Bleed resistor to prevent floating phase node convergence issues
        circuit.R('bleed', 'phase', circuit.gnd, 1@u_MOhm)
        
        # Parasitic/Gate Capacitances
        circuit.C('gs_hs', 'gate_hs', 'phase', 4.8@u_nF)
        circuit.C('gd_hs', 'gate_hs', 'vbat', 0.2@u_nF)
        circuit.C('ds_hs', 'vbat', 'phase', 0.5@u_nF)
        
        circuit.C('gs_ls', 'gate_ls', circuit.gnd, 4.8@u_nF)
        circuit.C('gd_ls', 'gate_ls', 'phase', 0.2@u_nF)
        circuit.C('ds_ls', 'phase', circuit.gnd, 0.5@u_nF)
        
        if with_diodes:
            circuit.model('D_Schottky', 'D', IS=1e-6, N=1.1, RS=0.1)
            circuit.Diode('gate_hs_bypass', 'gate_hs', 'gate_hs_drive', model='D_Schottky')
            circuit.Diode('gate_ls_bypass', 'gate_ls', 'gate_ls_drive', model='D_Schottky')
            
        simulator = circuit.simulator(temperature=25, nominal_temperature=25)
        analysis = simulator.transient(step_time=5@u_ns, end_time=10@u_us)
        
        return (np.asarray(analysis.time) * 1e6, 
                np.asarray(analysis.gate_hs) - np.asarray(analysis.phase),
                np.asarray(analysis.gate_ls),
                -np.asarray(analysis.branches['vbat']))
                
    t, vgs_hs_no_d, vgs_ls_no_d, ibat_no_d = run_bridge_sim(False)
    t_d, vgs_hs_d, vgs_ls_d, ibat_d = run_bridge_sim(True)
    
    # Plotting
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    # Gate voltages plot
    ax1.plot(t, vgs_hs_no_d, label='HS Vgs (No Diode)', color='red', alpha=0.5)
    ax1.plot(t, vgs_ls_no_d, label='LS Vgs (No Diode)', color='blue', alpha=0.5)
    ax1.plot(t_d, vgs_hs_d, label='HS Vgs (With Diode)', color='darkred', linewidth=2)
    ax1.plot(t_d, vgs_ls_d, label='LS Vgs (With Diode)', color='darkblue', linewidth=2)
    ax1.axhline(2.5, color='gray', linestyle=':', label='MOSFET Threshold Vth (2.5V)')
    ax1.set_ylabel('Gate-Source Voltage (V)')
    ax1.set_title('Gate Voltages and Shoot-Through Current During Turn-Off Transition')
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(loc='upper right')
    
    # Battery current plot
    ax2.plot(t, ibat_no_d, label='Battery Current (No Diode)', color='orange', alpha=0.7, linewidth=2)
    ax2.plot(t_d, ibat_d, label='Battery Current (With Diode)', color='green', linewidth=2)
    ax2.set_xlabel('Time (Microseconds)')
    ax2.set_ylabel('Current Drawn from Bat (A)')
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.set_xlim(4.8, 5.5) # Zoom in closely on the switching transition at t = 5.0us
    ax2.legend(loc='upper right')
    
    plt.tight_layout()
    plt.savefig('shoot_through_plot.png', dpi=300)
    plt.close()
    
    peak_no_d = ibat_no_d.max()
    peak_d = ibat_d.max()
    
    print("Saved Shoot-Through plot to 'shoot_through_plot.png'")
    print(f"Peak current without Schottky bypass diodes: {peak_no_d:.2f} A")
    print(f"Peak current with Schottky bypass diodes:    {peak_d:.2f} A")
    
    if peak_no_d > 5.0 and peak_d < 3.0:
        print("RESULT: Shoot-through confirmed and successfully suppressed by Schottky diodes!")
    else:
        print("RESULT: No significant shoot-through detected under these conditions.")

if __name__ == '__main__':
    simulate_current_sense()
    simulate_bootstrap()
    simulate_bemf()
    simulate_shoot_through()
