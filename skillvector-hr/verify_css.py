import requests
import re

try:
    response = requests.get('http://127.0.0.1:5000/static/css/style.css')
    content = response.text
    
    # Check for box-sizing
    if 'box-sizing: border-box' in content:
        print("PASS: box-sizing: border-box found")
    else:
        print("FAIL: box-sizing: border-box NOT found")

    # Check for border color definition
    if '--border: #cbd5e1' in content:
        print("PASS: --border: #cbd5e1 definition found")
    else:
        print("FAIL: --border definition NOT found (or incorrect)")

    # Check that old hex codes are gone (or significantly reduced)
    # Common old greys: #e5e7eb, #e2e8f0
    count_old_1 = content.count('#e5e7eb')
    count_old_2 = content.count('#e2e8f0')
    
    if count_old_1 == 0 and count_old_2 == 0:
        print("PASS: No hardcoded light grey borders found.")
    else:
        print(f"WARNING: Found {count_old_1} occurrences of #e5e7eb and {count_old_2} occurrences of #e2e8f0.")

    # Check for usage of var(--border)
    count_var = content.count('var(--border)')
    print(f"INFO: var(--border) used {count_var} times.")
    
    if count_var > 10: # Arbitrary threshold to ensure meaningful replacement
         print("PASS: Significant usage of var(--border) found.")
    else:
         print("FAIL: var(--border) usage seems low.")

except Exception as e:
    print(f"Error connecting to server: {e}")
