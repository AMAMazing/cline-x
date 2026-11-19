import codecs

try:
    with codecs.open('main.py', 'r', 'utf-8') as f:
        content = f.read()

    target1 = "                'gemini-3.1-flash-lite-preview',\r\n                'aistudio-argon',"
    target2 = "                'gemini-3.1-flash-lite-preview',\n                'aistudio-argon',"

    replacement = "                'gemini-3.1-flash-lite-preview',\n                'aistudio-carbon',\n                'gemini-4-carbon',\n                'aistudio-neon',\n                'gemini-4-neon',\n                'aistudio-argon',"

    if "'aistudio-carbon'" in content:
        print("ALREADY UPDATED")
    elif target1 in content:
        content = content.replace(target1, replacement.replace('\n', '\r\n'))
        with codecs.open('main.py', 'w', 'utf-8') as f:
            f.write(content)
        print("SUCCESS (CRLF)")
    elif target2 in content:
        content = content.replace(target2, replacement)
        with codecs.open('main.py', 'w', 'utf-8') as f:
            f.write(content)
        print("SUCCESS (LF)")
    else:
        print("TARGET NOT FOUND")
except Exception as e:
    print(f"ERROR: {e}")