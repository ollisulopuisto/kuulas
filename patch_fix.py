import sys
with open('tests/test_fuzz_hardening.py', 'r') as f:
    text = f.read()

text = text.replace('.editor.json', '.take.json')

with open('tests/test_fuzz_hardening.py', 'w') as f:
    f.write(text)

with open('src/kuulas/record_take.py', 'r') as f:
    text = f.read()

# Let's ensure take_position also does track_id truncation
with open('src/kuulas/take_position.py', 'r') as f:
    text2 = f.read()
