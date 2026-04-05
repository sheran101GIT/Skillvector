import re
import os

FILE_PATH = r'z:\SkillVector\skillvector-hr\app\static\css\style.css'

def fix_borders():
    if not os.path.exists(FILE_PATH):
        print(f"File not found: {FILE_PATH}")
        return

    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to match border properties with specific hex codes
    # Captures:
    # 1. Property name (border, border-top, border-color, etc.)
    # 2. Values before the color hash
    # 3. The hex code (to be replaced)
    # We target #e5e7eb (Slate-200) and #e2e8f0 (Slate-200/similar)
    
    pattern = r'(border(?:-top|-bottom|-left|-right|-color)?\s*:\s*[^;]*?)(#(?:e5e7eb|e2e8f0))'
    
    def replacement(match):
        prefix = match.group(1)
        old_hex = match.group(2)
        print(f"Replacing {prefix}{old_hex} -> {prefix}var(--border)")
        return f"{prefix}var(--border)"

    new_content, count = re.subn(pattern, replacement, content, flags=re.IGNORECASE)

    if count > 0:
        with open(FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Successfully replaced {count} occurrences.")
    else:
        print("No occurrences found to replace.")

if __name__ == "__main__":
    fix_borders()
