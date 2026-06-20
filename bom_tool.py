import os
import re
import sys
import requests

def is_ref_des(s):
    s = s.upper().strip()
    match = re.match(r'^([A-Z]+)(\d+)[A-Z]?$', s)
    if match:
        prefix, num = match.groups()
        return prefix in ['R', 'C', 'L', 'U', 'Q', 'D', 'J', 'TP', 'F', 'FB', 'Y', 'X', 'SW', 'RV', 'NT', 'H'] and len(s) <= 6
    return False

def normalize_value(v):
    if not v:
        return ""
    v = v.strip().lower()
    # Remove HTML comments
    v = re.sub(r'<!--.*?-->', '', v).strip()
    # Normalize spacing
    v = re.sub(r'\s+', ' ', v)
    # Remove trailing 'f' from cap values if it is 'uf', 'nf', 'pf'
    v = re.sub(r'(\d+)\s*([unp])f$', r'\1\2', v)
    # Remove ohm/ohms/Ω/ω
    v = re.sub(r'\s*(ohm|ohms|Ω|ω)$', '', v)
    # Normalize 3.3k to 3k3
    v = re.sub(r'^(\d+)\.(\d+)k$', r'\1k\2', v)
    # Normalize 2.2R to 2R2
    v = re.sub(r'^(\d+)\.(\d+)r$', r'\1r\2', v)
    return v

def clean_footprint(fp):
    if not fp:
        return ""
    if ":" in fp:
        return fp.split(":")[1]
    return fp

def parse_schematic(file_path):
    if not os.path.exists(file_path):
        print(f"Error: Schematic file '{file_path}' not found.")
        return []
        
    instances = []
    current_instance = []
    in_instance = False
    depth = 0
    in_lib_symbols = False
    lib_symbols_depth = 0
    instance_depth = 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            open_count = stripped.count('(')
            close_count = stripped.count(')')
            
            if '(lib_symbols' in stripped:
                in_lib_symbols = True
                lib_symbols_depth = depth
            
            if not in_lib_symbols and depth == 1 and stripped.startswith('(symbol'):
                in_instance = True
                current_instance = [line]
                instance_depth = depth
            elif in_instance:
                current_instance.append(line)
                
            depth += open_count - close_count
            
            if in_lib_symbols and depth <= lib_symbols_depth:
                in_lib_symbols = False
                
            if in_instance and depth <= instance_depth:
                in_instance = False
                instances.append(''.join(current_instance))
                
    components = []
    for inst_str in instances:
        props = {}
        # Find patterns like (property "Name" "Value" ...)
        pattern = re.compile(r'\(property\s+\"([^\"]+)\"\s+\"([^\"]*)\"')
        for match in pattern.finditer(inst_str):
            name, val = match.groups()
            props[name] = val
            
        ref = props.get("Reference")
        if ref and is_ref_des(ref):
            # Check DNP (Do Not Populate) or in_bom flags if specified
            in_bom = "in_bom yes" in inst_str or "in_bom no" not in inst_str
            dnp = "dnp yes" in inst_str
            
            if in_bom and not dnp:
                components.append({
                    "Reference": ref,
                    "Value": props.get("Value", "").strip(),
                    "Footprint": clean_footprint(props.get("Footprint", "")),
                    "LCSC": props.get("LCSC Part", props.get("LCSC", "")).strip()
                })
                
    return components

def parse_old_bom(file_path):
    if not os.path.exists(file_path):
        print(f"Warning: Old BOM file '{file_path}' not found. Cannot match part numbers.")
        return {}, {}
        
    lcsc_to_val = {}
    val_to_lcsc = {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line.startswith('|'):
                continue
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) < 3:
                continue
            
            # Clean comments
            c0 = re.sub(r'<!--.*?-->', '', cells[0]).replace('<br />', '').strip()
            c1 = re.sub(r'<!--.*?-->', '', cells[1]).replace('<br />', '').strip()
            c2 = re.sub(r'<!--.*?-->', '', cells[2]).replace('<br />', '').strip()
            
            # Find LCSC part number (starts with C followed by digits)
            m = re.search(r'\b(C\d+)\b', c1)
            if not m:
                m = re.search(r'\b(C\d+)\b', c0)
                if not m:
                    m = re.search(r'\b(C\d+)\b', c2)
            
            if m:
                lcsc = m.group(1)
                value = ''
                if c2 and not c2.lower().startswith('lcsc'):
                    value = c2
                elif c0 and not is_ref_des(c0) and not c0.lower().startswith('part'):
                    value = c0
                
                if value:
                    lcsc_to_val[lcsc] = value
                    norm_val = normalize_value(value)
                    if norm_val not in val_to_lcsc:
                        val_to_lcsc[norm_val] = set()
                    val_to_lcsc[norm_val].add(lcsc)
                    
    return lcsc_to_val, val_to_lcsc

def query_lcsc_api(lcsc_code):
    url = "https://wwwapi.lcsc.com/v1/search/global-search"
    try:
        response = requests.get(url, params={"keyword": lcsc_code}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # If search matches product details
            if data and "productResult" in data and data["productResult"]:
                products = data["productResult"].get("result", [])
                if products:
                    prod = products[0]
                    return {
                        "Manufacturer": prod.get("manufacturerNameEn", "Unknown"),
                        "Footprint": prod.get("packageValue", "Unknown"),
                        "Description": prod.get("productIntroEn", "Unknown"),
                        "Model": prod.get("productModel", "Unknown")
                    }
    except Exception:
        pass
    return None

OFFLINE_LCSC_SPECS = {
    "C13585": "MLCC Capacitor 10uF ±10% 50V X7R 0805",
    "C96446": "MLCC Capacitor 10uF ±20% 10V X5R 0603",
    "C14663": "MLCC Capacitor 100nF ±10% 50V X7R 0603",
    "C24497": "MLCC Capacitor 100nF ±10% 16V X7R 0402",
    "C15849": "MLCC Capacitor 1uF ±10% 25V X7R 0603",
    "C45783": "MLCC Capacitor 22uF ±20% 10V X5R 0805",
    "C191023": "Schottky Diode 1N5819WS 40V 1A SOD-323",
    "C5349699": "Shielded Power Inductor 15uH 2.5A SMD",
    "C1002": "Ferrite Bead 600Ω @ 100MHz 2A 0603",
    "C25804": "Chip Resistor 10kΩ ±1% 1/10W 0603",
    "C22859": "Chip Resistor 10Ω ±1% 1/10W 0603",
    "C21190": "Chip Resistor 1kΩ ±1% 1/10W 0603",
    "C22962": "Chip Resistor 220Ω ±1% 1/10W 0603",
    "C4216": "Chip Resistor 33kΩ ±1% 1/10W 0603",
    "C4211": "Chip Resistor 3kΩ ±1% 1/10W 0603",
    "C22978": "Chip Resistor 3.3kΩ ±1% 1/10W 0603",
    "C25792": "Chip Resistor 47kΩ ±1% 1/16W 0402",
    "C3029575": "MCU AT32F421K8T7 ARM Cortex-M4 120MHz LQFP-32",
    "C54423134": "3-Phase Gate Driver FD6288Q 33V QFN-24",
    "C192764": "Current Sense Amplifier INA180A2 26V SOT-23-5",
    "C5383002": "Buck Regulator LMR51420YDDCR 36V 2A SOT-23-6",
    "C2848334": "LDO Regulator TLV76733DRVR 1A 3.3V WSON-6",
    "C7527437": "N-Channel MOSFET JMSH0401AGQ 40V 100A DFN-8",
    "C49067823": "Shunt Resistor 0.5mΩ 3W ±1% 2512",
    "C19077583": "TVS Diode SMBJ28CA 28V 600W Bi-directional SMB",
    "C145952": "Pin Header 5-Pin 2.54mm Pitch Straight",
}

def write_bom_markdown(components, output_path, lcsc_to_val=None):
    # Group components by Value + Footprint + LCSC
    grouped = {}
    for c in components:
        key = (normalize_value(c["Value"]), c["Footprint"], c["LCSC"])
        if key not in grouped:
            grouped[key] = {
                "Value": c["Value"],
                "Footprint": c["Footprint"],
                "LCSC": c["LCSC"],
                "Refs": []
            }
        grouped[key]["Refs"].append(c["Reference"])
        
    # Sort groups by reference designator type and value
    def sort_key(k):
        val, fp, lcsc = k
        # Try to find reference designator type from the first ref
        refs = grouped[k]["Refs"]
        first_ref = sorted(refs)[0] if refs else ""
        match = re.match(r'^([A-Z]+)', first_ref)
        prefix = match.group(1) if match else "Z"
        return (prefix, val, fp)
        
    sorted_keys = sorted(grouped.keys(), key=sort_key)
    
    # Cache descriptions for matched LCSC numbers locally
    # If network offline, we'll try to query or show empty
    local_lcsc_desc = {}
    print("\nLooking up component specifications...")
    for key in sorted_keys:
        lcsc = grouped[key]["LCSC"]
        if lcsc:
            print(f"  Querying {lcsc}...", end="", flush=True)
            details = query_lcsc_api(lcsc)
            if details:
                local_lcsc_desc[lcsc] = f"{details['Manufacturer']} - {details['Description']}"
                print(" Success!")
            else:
                # Fall back to offline specifications database
                if lcsc in OFFLINE_LCSC_SPECS:
                    local_lcsc_desc[lcsc] = f"[Offline Spec] {OFFLINE_LCSC_SPECS[lcsc]}"
                    print(" Match found in offline specs cache.")
                elif lcsc_to_val and lcsc in lcsc_to_val:
                    local_lcsc_desc[lcsc] = f"[Offline Value] {lcsc_to_val[lcsc]}"
                    print(" Match found in old BOM value cache.")
                else:
                    local_lcsc_desc[lcsc] = ""
                    print(" Offline / No details found.")
                
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Bill of Materials (BOM)\n\n")
        f.write("| Index | Qty | Value | Footprint | LCSC Part Number | Designators | Description / Specs |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        
        for idx, key in enumerate(sorted_keys, 1):
            val = grouped[key]["Value"]
            fp = grouped[key]["Footprint"]
            lcsc = grouped[key]["LCSC"]
            refs = sorted(grouped[key]["Refs"], key=lambda r: (re.match(r'^([A-Z]+)', r).group(1), int(re.search(r'(\d+)', r).group(1)) if re.search(r'(\d+)', r) else 0))
            qty = len(refs)
            refs_str = ", ".join(refs)
            desc = local_lcsc_desc.get(lcsc, "")
            
            f.write(f"| {idx} | {qty} | {val} | {fp} | {lcsc if lcsc else ''} | {refs_str} | {desc} |\n")
            
    print(f"\nBOM successfully written to '{output_path}'!")

def interactive_menu():
    print("==================================================")
    print("          ESC Interactive BOM Tool v1.0")
    print("==================================================")
    
    sch_file = input("Enter KiCad schematic file path [VegaESC.kicad_sch]: ").strip()
    if not sch_file:
        sch_file = "VegaESC.kicad_sch"
        
    old_bom_file = input("Enter old BOM file path [bom.md]: ").strip()
    if not old_bom_file:
        old_bom_file = "bom.md"
        
    out_file = input("Enter output BOM file path [bom_new.md]: ").strip()
    if not out_file:
        out_file = "bom_new.md"
        
    print("\nReading schematic...")
    components = parse_schematic(sch_file)
    if not components:
        return
    print(f"Found {len(components)} components in schematic.")
    
    print("\nLoading options:")
    print("[1] Generate simple BOM list (empty LCSC column)")
    print("[2] Match LCSC parts from old BOM (interactively resolve duplicates)")
    print("[3] Query specific LCSC part specs")
    print("[4] Exit")
    
    choice = input("\nSelect option (1-4): ").strip()
    
    if choice == '1':
        for c in components:
            c["LCSC"] = ""
        write_bom_markdown(components, out_file)
        
    elif choice == '2':
        lcsc_to_val, val_to_lcsc = parse_old_bom(old_bom_file)
        
        # Keep track of user decisions for duplicates to avoid asking repeatedly for the same value
        remembered_decisions = {}
        
        print("\nMatching schematic components with old BOM...")
        for c in components:
            ref = c["Reference"]
            val = c["Value"]
            norm_val = normalize_value(val)
            
            # If the component already has a valid LCSC part in the schematic, keep it
            if c["LCSC"] and re.match(r'^C\d+$', c["LCSC"]):
                continue
                
            if norm_val in val_to_lcsc:
                lcsc_options = list(val_to_lcsc[norm_val])
                if len(lcsc_options) == 1:
                    c["LCSC"] = lcsc_options[0]
                else:
                    # Duplicate found
                    if norm_val in remembered_decisions:
                        c["LCSC"] = remembered_decisions[norm_val]
                    else:
                        print(f"\nConflict for component {ref} (Value: {val}):")
                        print("Multiple LCSC part numbers found in old BOM:")
                        for idx, lcsc in enumerate(lcsc_options, 1):
                            # Try to show description
                            assoc_val = lcsc_to_val.get(lcsc, "Unknown component")
                            print(f"  [{idx}] {lcsc} (Old BOM value: {assoc_val})")
                        print(f"  [{len(lcsc_options) + 1}] Leave Empty")
                        print(f"  [{len(lcsc_options) + 2}] Enter manually")
                        
                        while True:
                            ans = input(f"Select LCSC part number (1-{len(lcsc_options) + 2}): ").strip()
                            if ans.isdigit():
                                ans_idx = int(ans)
                                if 1 <= ans_idx <= len(lcsc_options):
                                    selected_lcsc = lcsc_options[ans_idx - 1]
                                    c["LCSC"] = selected_lcsc
                                    # Ask if we should remember this for all components of this value
                                    rem = input(f"Apply {selected_lcsc} to all components with value '{val}'? (y/n): ").strip().lower()
                                    if rem == 'y':
                                        remembered_decisions[norm_val] = selected_lcsc
                                    break
                                elif ans_idx == len(lcsc_options) + 1:
                                    c["LCSC"] = ""
                                    break
                                elif ans_idx == len(lcsc_options) + 2:
                                    manual = input("Enter LCSC part number (e.g. C13585): ").strip()
                                    c["LCSC"] = manual
                                    rem = input(f"Apply {manual} to all components with value '{val}'? (y/n): ").strip().lower()
                                    if rem == 'y':
                                        remembered_decisions[norm_val] = manual
                                    break
            else:
                # No match in old BOM
                if norm_val in remembered_decisions:
                    c["LCSC"] = remembered_decisions[norm_val]
                else:
                    print(f"\nValue '{val}' (component {ref}) not found in old BOM.")
                    print("  [1] Leave Empty")
                    print("  [2] Enter LCSC part number manually")
                    while True:
                        ans = input("Select option (1-2): ").strip()
                        if ans == '1':
                            c["LCSC"] = ""
                            remembered_decisions[norm_val] = ""
                            break
                        elif ans == '2':
                            manual = input("Enter LCSC part number (e.g. C13585): ").strip().upper()
                            c["LCSC"] = manual
                            rem = input(f"Apply {manual} to all components with value '{val}'? (y/n): ").strip().lower()
                            if rem == 'y':
                                remembered_decisions[norm_val] = manual
                            break
                
        write_bom_markdown(components, out_file, lcsc_to_val)
        
    elif choice == '3':
        lcsc_code = input("\nEnter LCSC Part Number (e.g., C13585): ").strip().upper()
        if not lcsc_code.startswith('C') or not lcsc_code[1:].isdigit():
            print("Invalid LCSC part number format.")
            return
            
        print(f"Querying specs for {lcsc_code}...")
        details = query_lcsc_api(lcsc_code)
        if details:
            print("\n================ Part Specifications ================")
            print(f"LCSC Code:    {lcsc_code}")
            print(f"Model:        {details['Model']}")
            print(f"Manufacturer: {details['Manufacturer']}")
            print(f"Package:      {details['Footprint']}")
            print(f"Description:  {details['Description']}")
            print("=====================================================")
        else:
            # Fall back to old BOM check
            lcsc_to_val, _ = parse_old_bom(old_bom_file)
            if lcsc_code in lcsc_to_val:
                print("\n================ Part Specifications (Offline Cache) ================")
                print(f"LCSC Code:    {lcsc_code}")
                print(f"Value/Name:   {lcsc_to_val[lcsc_code]}")
                print("Note: Network API offline. Displaying cached information from old BOM.")
                print("=====================================================================")
            else:
                print("Could not retrieve specifications (Offline and part not found in old BOM cache).")
                
    elif choice == '4':
        print("Exiting tool.")
        return
    else:
        print("Invalid option selected.")

if __name__ == '__main__':
    try:
        interactive_menu()
    except KeyboardInterrupt:
        print("\nTool terminated by user.")
        sys.exit(0)
