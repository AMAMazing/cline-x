import pyautogui
from time import sleep
import os
from PIL import Image

class ResolutionManager:
    def __init__(self, base_path, resolution='1080p'):
        self.base_path = base_path
        self.resolution = resolution
        
    def get_image_paths(self, filename):
        """Get all possible image paths for different resolutions."""
        paths = []
        
        # Add base image path
        base_path = os.path.join(self.base_path, f"{filename}.png")
        if os.path.exists(base_path):
            paths.append(base_path)
            
        # Add resolution-specific image path
        if self.resolution != '1080p':
            res_path = os.path.join(self.base_path, f"{filename}_{self.resolution}.png")
            if os.path.exists(res_path):
                paths.append(res_path)
                
        return paths

_default_autopath = r'C:\\'
_res_manager = None

def set_autopath(path, resolution='1080p'):
    """Set the base path and resolution for image operations."""
    global _default_autopath, _res_manager
    _default_autopath = path
    _res_manager = ResolutionManager(path, resolution)

def optimiseWait(filename, dontwait=False, specreg=None, clicks=1, xoff=0, yoff=0, autopath=None, confidence=0.7):
    """
    Enhanced optimiseWait function with multi-resolution support.
    Now tries multiple image variations and adjusts confidence threshold.
    """
    global _default_autopath, _res_manager
    autopath = autopath if autopath is not None else _default_autopath
    
    # Initialize resolution manager if not already done
    if _res_manager is None:
        _res_manager = ResolutionManager(autopath)
    
    # Convert inputs to lists if they aren't already
    if not isinstance(filename, list):
        filename = [filename]
    if not isinstance(clicks, list):
        clicks = [clicks] * len(filename)
    if not isinstance(xoff, list):
        xoff = [xoff] * len(filename)
    if not isinstance(yoff, list):
        yoff = [yoff] * len(filename)
    
    # Ensure all lists are the same length
    max_len = max(len(filename), len(clicks), len(xoff), len(yoff))
    filename = filename + [filename[-1]] * (max_len - len(filename))
    clicks = clicks + [clicks[-1]] * (max_len - len(clicks))
    xoff = xoff + [xoff[-1]] * (max_len - len(xoff))
    yoff = yoff + [yoff[-1]] * (max_len - len(yoff))
    
    clicked = 0
    while True:
        findloc = None
        for i, fname in enumerate(filename):
            # Get all possible image paths for this filename
            image_paths = _res_manager.get_image_paths(fname)
            
            # Try each image path with different confidence levels
            for image_path in image_paths:
                try:
                    if specreg is None:
                        # Try with different confidence levels if needed
                        for conf in [confidence, confidence - 0.1]:  # Try original confidence, then lower if needed
                            loc = pyautogui.locateCenterOnScreen(image_path, confidence=conf)
                            if loc and clicked == 0:
                                findloc = loc
                                clicked = i + 1
                                break
                    else:
                        loc = pyautogui.locateOnScreen(image_path, region=specreg, confidence=confidence)
                        if loc:
                            findloc = loc
                            clicked = i + 1
                            
                    if findloc:  # If we found a match, break the image path loop
                        break
                        
                except pyautogui.ImageNotFoundException:
                    continue
                except Exception as e:
                    print(f"Error processing image {fname} at {image_path}: {str(e)}")
                    continue
                    
            if findloc:  # If we found a match, break the filename loop
                break
        
        if dontwait:
            return {
                'found': findloc is not None,
                'image': filename[clicked - 1] if clicked > 0 else None
            }
            
        if findloc:
            break
            
        sleep(1)
    
    if findloc is not None:
        if specreg is None:
            x, y = findloc
        else:
            x, y, width, height = findloc
            
        current_xoff = xoff[clicked - 1]
        current_yoff = yoff[clicked - 1]
        xmod = x + current_xoff
        ymod = y + current_yoff
        sleep(1)
        
        click_count = clicks[clicked - 1]
        if click_count > 0:
            for _ in range(click_count):
                pyautogui.click(xmod, ymod)
                sleep(0.1)
        
        return {'found': True, 'image': filename[clicked - 1]}
    
    return {'found': False, 'image': None}