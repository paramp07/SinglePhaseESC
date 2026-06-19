# SinglePhaseESC Design Review

**Project:** SinglePhaseESC (KiCad 9.0+, 1 sheet, empty PCB layout)
**Date:** June 19, 2026
**Analyzers Run:** `analyze_schematic.py`, `analyze_pcb.py`, `cross_analysis.py`, `analyze_emc.py`, `analyze_thermal.py`

---

## Overview
This design is a single-phase brushless DC (BLDC) motor controller / Electronic Speed Controller (ESC). It features:
*   **Microcontroller:** Artery AT32F421K8T7 (U3) running in the 3.3V domain.
*   **Gate Driver:** FD6288Q 3-phase gate driver (U2) powering the output stage.
*   **Power Management:** LMR51420YDDCR buck regulator (U1) producing +10V for the gate driver, and a TLV76733 LDO (U4) stepping down +10V to +3V3 for the MCU and analog circuitry.
*   **Current Sensing:** INA180A2 current sense amplifier (U5) for current feedback.

At this stage, the schematic design is complete, but the PCB layout has not yet been started (the `.kicad_pcb` file is empty).

---

## Previous Review Delta
*No prior design reviews or cached analyzer runs were found in this workspace. This is the baseline design review.*

---

## Critical Findings

| Severity | Issue | Section |
|----------|-------|---------|
| **ERROR** | **BOM Sourcing Block: <50% MPN Coverage** | [Sourcing Audit](#sourcing-audit) |
| **WARNING** | **Layout Empty: 104 Components Missing from PCB** | [PCB Layout Status](#pcb-layout-status) |
| **WARNING** | **EMI Filter Cutoff Too High** | [EMI Filter Performance](#emi-filter-performance) |
| **WARNING** | **Connector P1 Unconnected and Floating** | [Connector Auditing](#connector-auditing) |
| **WARNING** | **Net +BATT Missing PWR_FLAG** | [ERC Warnings](#erc-warnings) |

---

## Component Summary

*   **Total Components:** 110
*   **Unique Part Lines (BOM):** 32
*   **Nets:** 83
*   **Wires:** 137
*   **No-Connects:** 12
*   **Sourcing Audit:** **18.8% MPN Coverage** (6 of 32 unique BOM lines have a Manufacturer Part Number).

---

## Power Tree

```
 +BATT (Input Power)
   │
   ├──> U1 (LMR51420YDDCR switching buck, Vref = 0.6V [lookup])
   │     ├── Feedback: R3 (47kΩ, top), R5 (3kΩ, bottom)
   │     └──> +10V (Gate Driver VCC Power)
   │           │
   │           ├──> U2 (FD6288Q gate driver VCC supply)
   │           │
   │           └──> U4 (TLV76733 LDO)
   │                 └──> +3V3 (Microcontroller & Logic Power)
   │                       ├──> U3 (AT32F421 MCU VDD)
   │                       ├──> U5 (INA180 current sense V+)
   │                       └──> +3V3_A (VDDA analog rail via L1 filter)
```

*   **U1 regulator output voltage verification:**
    $$\text{V}_{out} = \text{V}_{ref} \times \left(1 + \frac{\text{R}_{top}}{\text{R}_{bottom}}\right) = 0.6\text{ V} \times \left(1 + \frac{47\text{ k}\Omega}{3\text{ k}\Omega}\right) = 10.0\text{ V}$$
    This matches the estimated rail target of **+10V** exactly.

---

## Analyzer Verification

### Component Count Match
*   **Schematic Components:** 110 (excluding power symbols).
*   **PCB Footprints:** 0.
*   **Status:** Layout has not started, so there is an expected mismatch of 104 layout-bound components.

### Pinout Verification & Ambiguities
*   **Critical ICs (U1, U3, U4):** Pinouts verified against KiCad symbol models.
*   **Gate Driver U2 & Current Amp U5:** Symbols matched, but lack MPNs. Their physical pinout *must* be validated against the manufacturer's datasheet pin diagram once MPNs are assigned.
*   **Transistors & MOSFETs:** Standard symbols are used, but their pin configurations (e.g., G-D-S for MOSFETs) must be cross-checked with the selected manufacturer's package drawing before routing.

### Connector Pin Tables
*   **J3 (5-pin Header):** Traces correctly:
    *   Pin 1: `+BATT` (Supply)
    *   Pin 2: `GND` (Ground)
    *   Pin 3: `CURRENT` (Current telemetry feedback)
    *   Pin 4: `TELEMETRY` (MCU transmit telemetry)
    *   Pin 5: `SIGNAL_INPUT` (PWM control signal)
*   **P1 (JST-SH 8-pin with shield tabs):** Pins 1-10 are floating and connect to local unnamed nets (`__unnamed_41` to `__unnamed_50`).

### Net Tracing
*   Critical nets (`+BATT`, `GND`, `+10V`, `+3V3`, `+3V3_A`) traced correctly end-to-end through power pins, filters, and decoupling caps.

---

## Signal Analysis Review

### Power Regulators
*   **U1 (LMR51420YDDCR buck):** Verified output of 10.0V. Has bulk and bypass decoupling capacitors (`C11`, `C12`, `C16`, `C2`, `C3`, `C17`) on input and output.
*   **U4 (TLV76733DRVR fixed LDO):** Output +3V3 is stable and correctly decoupled by a bulk/bypass cap bank (`C19`, `C20`, `C4`, `C5`, `C18`, `C6`, `C32`).

### EMI Filter Performance
*   `U1` input filter uses `L2` (estimated LC filter with `fc = 130 kHz`). 
*   Because `U1` switches at **500 kHz**, the switching frequency to filter cutoff ratio is only **3.8×**. 
*   **Recommendation:** For adequate attenuation (minimum -40 dB/decade roll-off), the cutoff frequency $f_c$ should be $\leq f_{sw}/5$ (i.e. $\leq 100\text{ kHz}$, ideally $\leq 50\text{ kHz}$). Increasing the input inductor `L2` value or capacitor capacitance will lower the cutoff and improve input conducted EMI.

### Connector Auditing
*   `P1` (JST-SH 8-pin connector) has **0 ground pins** connected and is completely unconnected.
*   **Recommendation:** If this connector was placed for debugging, expansion, or display purposes, ensure it is wired to the MCU. If it is a leftover from a previous design, delete it from the schematic.

### ERC Warnings
*   **`RS-001` (warning): Net `+BATT` has no declared source.**
    *   *Cause:* `+BATT` connects to connector pin `J3.1` (passive pin) and regulator `U1` inputs (power input pins), meaning KiCad has no declared source on this net.
    *   *Recommendation:* Place a `PWR_FLAG` symbol on `+BATT` and `GND` to satisfy KiCad's ERC checker.

---

## PCB Layout Status
*   **Dimensions:** Bounding box is empty.
*   **Tracks, Vias, Zones:** None found.
*   **Via Stitching VS-001 (warning):** Via stitching checks report 0 vias, which is normal for an empty layout.
*   **Recommendation:** Use **Tools > Update PCB from Schematic** in KiCad to import all 104 components and begin footprint placement.

---

## False Positives / Reviewer Overrides

### VM-001: 10V / 3.3V Domain Crossing on AHIGH, ALOW, BHIGH, BLOW, CHIGH, CLOW
*   **Finding:** The schematic analyzer flagged a direct connection between `U3` (3.3V microcontroller) and `U2` (10V gate driver) as a high-voltage threat.
*   **Reviewer Override:** **Benign / Dismissed.** While `U2` (`FD6288Q`) is powered by `+10V`, its logic control inputs are specifically designed to be compatible with 3.3V and 5V CMOS logic. The datasheet specifies input thresholds of $V_{IH} \geq 2.7\text{ V}$ and $V_{IL} \leq 0.8\text{ V}$. The `AT32F421` MCU outputs will comfortably drive these inputs directly. Level shifters are not required.

---

## Not Performed / Review Limits
*   **SPICE Simulation:** Not performed — `ngspice` is not installed on the host system.
*   **PCB Trace/DFM checks:** Not performed — PCB layout has not been started.
*   **Gerber verification:** Not performed — no Gerber fabrication outputs exist yet.
*   **Lifecycle audit:** Not performed — missing manufacturer part numbers on the majority of components.

---

## Final Verdict & Readiness Statement
**Status: NOT READY FOR FABRICATION (BOM Sourcing Gaps & Layout Pending)**

The schematic circuit design is functionally sound and logically correct. The 10V/3.3V domain crossings to the gate driver are verified as safe. However, before the board can proceed:
1.  **BOM Enrichment:** Populate the Manufacturer Part Numbers (MPNs) for all components (especially the gate driver, current shunt amp, and power MOSFETs).
2.  **EMI Filter Adjust:** Consider adjusting the input filter inductors/capacitors to lower the cutoff frequency below 100 kHz.
3.  **Layout Phase:** Synchronize the schematic to the layout and complete the PCB trace routing, ground pour stitching, and DFM compliance sweeps.
