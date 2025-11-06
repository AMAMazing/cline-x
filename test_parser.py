# test_parser.py
import re
import time
import base64
import io

# --- Windows-specific imports for clipboard functionality ---
try:
    import win32clipboard
    import pywintypes
    from PIL import Image
except ImportError:
    print("ERROR: This script requires pywin32 and Pillow.")
    print("Please install them using: pip install pywin32 Pillow")
    exit()

# --- Clipboard function (UNCHANGED) ---
def set_clipboard_image(image_data_uri: str):
    """
    Decodes a data URI and puts the image onto the Windows clipboard.
    Returns True on success, False on failure.
    """
    try:
        header, encoded_data = image_data_uri.split(',', 1)
        binary_data = base64.b64decode(encoded_data)
        image = Image.open(io.BytesIO(binary_data))
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        print(f"  [ERROR] An unexpected error occurred: {e}")
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return False

# --- Image extraction logic ---
def get_images_from_content(content):
    image_list = []
    if isinstance(content, str):
        # <<< FIX START: The regex now includes a length check `{50,}` >>>
        # This ensures that we only capture long strings that are actual base64 data,
        # filtering out short, accidentally captured strings like file paths.
        pattern = re.compile(
            r'media_type.*?[\'\\"](?P<mtype>image/[a-zA-Z]+)[\'\\"]'
            r'.*?'
            r'data.*?[\'\\"](?P<base64>[a-zA-Z0-9+/=]{50,})[\'\\"]', # Added {50,} length check
            re.DOTALL
        )
        # <<< FIX END >>>
        
        for match in pattern.finditer(content):
            media_type = match.group('mtype')
            base64_data = match.group('base64')
            if media_type and base64_data:
                full_data_uri = f"data:{media_type};base64,{base64_data}"
                image_list.append(full_data_uri)
    return image_list

# --- Main test execution ---
if __name__ == "__main__":
    try:
        with open('test_data.txt', 'r', encoding='utf-8') as f:
            messy_string = f.read()

        print("--- Running Full Clipboard Test with Deduplication & Validation ---")
        
        raw_images = get_images_from_content(messy_string)
        
        print(f"\n[1] RAW EXTRACTION: Found {len(raw_images)} valid image occurrences.")
        
        unique_images = list(set(raw_images))
        print(f"[2] DEDUPLICATION: Processing {len(unique_images)} unique images.")
        
        print("-------------------------------------------------------------")
        
        if not unique_images:
            print("No unique images found to test.")
        else:
            for i, img_uri in enumerate(unique_images):
                print(f"\n[3] Processing Unique Image {i+1}/{len(unique_images)}...")
                print(f"    - URI starts with: {img_uri[:60]}...")
                
                success = set_clipboard_image(img_uri)
                
                if success:
                    print("    - SUCCESS: Image has been placed on the clipboard.")
                    print("    - You have 5 seconds to paste it somewhere to verify.")
                    time.sleep(5)
                else:
                    print("    - FAILURE: Could not place image on the clipboard. See error above.")
                    print("    - Skipping to next image in 3 seconds...")
                    time.sleep(3)

        print("\n--- Test Complete ---")

    except FileNotFoundError:
        print("ERROR: Please create 'test_data.txt' and paste your example string into it.")