import matplotlib.pyplot as plt
import numpy as np
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
import PySpice.Logging.Logging as Logging

# Suppress verbose SPICE engine logs for a clean terminal
logger = Logging.setup_logging()

def simulate_gate_drive(gate_resistor_value):
    print(f"Simulating gate drive with {gate_resistor_value} Ohm resistor...")
    
    # Initialize the SPICE circuit environment
    circuit = Circuit('ESC Gate Drive Transient Analysis')

    # 1. The Gate Driver (Simulating the FD6288Q at 48kHz)
    # 20.8us period equals ~48kHz. 10us pulse width. 20ns switching speed.
    circuit.PulseVoltageSource('GateDriver', 'driver_out', circuit.gnd,
                               initial_value=0@u_V, pulsed_value=10@u_V,
                               pulse_width=10@u_us, period=20.8@u_us,
                               rise_time=20@u_ns, fall_time=20@u_ns, delay_time=1@u_us)

    # 2. The Gate Resistor
    circuit.R('GateRes', 'driver_out', 'trace_start', gate_resistor_value@u_Ohm)

    # 3. PCB Trace Parasitic Inductance 
    # (A 15mm copper trace routing from the driver to the MOSFET adds roughly 15nH)
    circuit.L('TraceParasitic', 'trace_start', 'mosfet_gate', 15@u_nH)

    # 4. The MOSFET Gate Capacitance
    # (Simulating the heavy internal Ciss of a high-current 197A MOSFET)
    circuit.C('MosfetCap', 'mosfet_gate', circuit.gnd, 5@u_nF)

    # Execute the Transient Analysis
    simulator = circuit.simulator(temperature=25, nominal_temperature=25)
    
    # We step every 1 nanosecond, and only simulate for 3 microseconds 
    # to zoom in closely on the rising edge ringing
    analysis = simulator.transient(step_time=1@u_ns, end_time=3@u_us)

    return analysis

# Run the simulation with your current 10R value
analysis_10R = simulate_gate_drive(10)

# Run a comparative simulation with a 0R (straight wire) to see the danger
analysis_0R = simulate_gate_drive(0.1) 

# --- Plotting the Results ---
plt.figure(figsize=(12, 7))

# Convert PySpice waveforms to standard numpy arrays for matplotlib compatibility
time_10R = np.asarray(analysis_10R.time) * 1e6
driver_out_10R = np.asarray(analysis_10R.driver_out)
time_0R = np.asarray(analysis_0R.time) * 1e6
mosfet_gate_0R = np.asarray(analysis_0R.mosfet_gate)
mosfet_gate_10R = np.asarray(analysis_10R.mosfet_gate)

# Plot the ideal 10V driver output
plt.plot(time_10R, driver_out_10R, 
         label='Raw Driver Output (10V)', color='gray', linestyle='--')

# Plot the dangerous 0R ringing
plt.plot(time_0R, mosfet_gate_0R, 
         label='Gate Voltage (0Ω - No Protection)', color='red', alpha=0.5)

# Plot your 10R damped response
plt.plot(time_10R, mosfet_gate_10R, 
         label='Gate Voltage (10Ω Resistor)', color='blue', linewidth=2.5)

# Add the 20V Silicon Rupture limit line
plt.axhline(y=20, color='black', linestyle=':', linewidth=2, label='Absolute Max Vgs Limit (20V)')

# Formatting the graph
plt.title('48kHz Cinematic ESC: Gate Drive Turn-On Transient', fontsize=14, fontweight='bold')
plt.xlabel('Time (Microseconds)', fontsize=12)
plt.ylabel('Voltage (V)', fontsize=12)
plt.xlim(0.9, 2.0) # Zoomed exactly on the rising edge
plt.grid(True, which='both', linestyle='--', alpha=0.6)
plt.legend(loc='upper right', fontsize=10)
plt.tight_layout()

# Save the plot to a file
plt.savefig('gate_sim_plot.png', dpi=300)
print("Simulation plot saved as 'gate_sim_plot.png'")

# Render the graph
plt.show()