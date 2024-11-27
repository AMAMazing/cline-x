import webbrowser
import time
import os
from cf_functions_vCL import optimiseWait

url = 'https://claude.ai/new'
webbrowser.open(url)

# Wait for browser to start loading
time.sleep(2)

print("Starting search for image...")
print(f"Current directory: {os.getcwd()}")
image_path = r"D:\cline-x-claudeweb\images\claudenew.png"
print(f"Looking for image at: {image_path}")
print(f"File exists: {os.path.exists(image_path)}")

# Now use optimiseWait which will keep trying until it finds the image
optimiseWait('claudenew', autopath=r"D:\cline-x-claudeweb\images")