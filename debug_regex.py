import regex
import re as standard_re

original = "Hello\\x00World\\nTabs\\tReturn\\rControl\\x08End"
# Wait, I need the actual characters in the 'original' string for the test
original = "Hello" + chr(0) + "World\nTabs\tReturn\rControl" + chr(8) + "End"
print(f"Original: {repr(original)}")

# Pattern 1: Set subtraction
p1 = r'[\p{Cc}--[\r\n\t]]'
c1 = regex.sub(p1, '', original)
print(f"Cleaned 1 (subtraction): {repr(c1)}")

# Pattern 2: Explicitly list keepers
p2 = r'(?![\r\n\t])\p{Cc}'
c2 = regex.sub(p2, '', original)
print(f"Cleaned 2 (lookahead): {repr(c2)}")

# Pattern 3: Standard RE with explicit ranges
# C0: \x00-\x1F (minus \x09,\x0A,\x0D), plus \x7F
# C1: \x80-\x9F
p3 = r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]'
c3 = standard_re.sub(p3, '', original)
print(f"Cleaned 3 (explicit re): {repr(c3)}")
