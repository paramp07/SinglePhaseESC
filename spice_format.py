import re
import os
import shutil

def standardize_value(value_str):
    original = value_str.strip()
    
    # Pattern 1: Decimal values with multipliers (e.g., 4.7uF, 3.3k, 0.5mOhm, or 3W 0.5mOhm)
    # Matches an optional prefix (like "3W "), whole number, decimal, multiplier, and optional unit.
    pattern_dec = re.compile(r'^([A-Za-z0-9]+\s+)?(\d+)\.(\d+)\s*([kMmunpμ]?)(F|Ohm|Ω|ohm)?$', re.IGNORECASE)
    match1 = pattern_dec.match(original)
    
    if match1:
        prefix, whole, decimal, mult, unit = match1.groups()
        prefix = prefix if prefix else ""
        mult = 'u' if mult == 'μ' else (mult if mult else "")
        
        # Apply the letter substitution (e.g., 3.3k -> 3k3)
        if mult:
            return f"{prefix}{whole}{mult}{decimal}"
        # If there is no multiplier but it's an Ohm value (e.g. 4.7 Ohm -> 4R7)
        elif unit and unit.lower() in ['ohm', 'ω']:
            return f"{prefix}{whole}R{decimal}"

    # Pattern 2: Whole values with standard units (e.g., 10uF, 100nF, 22uF)
    # This strips the 'F' or 'Ohm' ONLY if it sits directly after a valid multiplier at the very end of the line.
    pattern_whole = re.compile(r'^([A-Za-z0-9]+\s+)?(\d+)\s*([kMmunpμ])(F|Ohm|Ω|ohm)$', re.IGNORECASE)
    match2 = pattern_whole.match(original)
    
    if match2:
        prefix, whole, mult, unit = match2.groups()
        prefix = prefix if prefix else ""
        mult = 'u' if mult == 'μ' else mult
        return f"{prefix}{whole}{mult}"
        
    # If the string doesn't perfectly match a passive component format, DO NOT TOUCH IT.
    return original

def process_kicad_sch(file_path):
    backup_path = file_path + ".bak"
    shutil.copy2(file_path, backup_path)
    print(f"Backup created at: {backup_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    property_pattern = re.compile(r'(property\s+"Value"\s+")([^"]+)(")')

    def replace_match(match):
        prefix = match.group(1)
        original_value = match.group(2)
        suffix = match.group(3)
        
        new_value = standardize_value(original_value)
        
        if original_value != new_value:
            print(f"Converted: {original_value.ljust(15)} -> {new_value}")
            
        return f"{prefix}{new_value}{suffix}"

    updated_content = property_pattern.sub(replace_match, content)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"Successfully processed {file_path}")

if __name__ == "__main__":
    files_processed = 0
    for filename in os.listdir('.'):
        if filename.endswith(".kicad_sch"):
            print(f"\nScanning {filename}...")
            process_kicad_sch(filename)
            files_processed += 1
            
    if files_processed == 0:
        print("No .kicad_sch files found in the current directory.")