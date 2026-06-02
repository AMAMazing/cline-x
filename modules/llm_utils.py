from typing import Union, List, Dict
from modules.clipboard_utils import set_clipboard_image

def get_content_text(content: Union[str, List[Dict[str, str]], Dict[str, str]], debug: bool = False) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item["text"])
            elif item.get("type") == "image_url":
                image_data = item.get("image_url", {}).get("url", "")
                if image_data.startswith('data:image'):
                    set_clipboard_image(image_data, debug=debug)
                parts.append("[Image: An uploaded image]")
        return "\n".join(parts)
    return ""