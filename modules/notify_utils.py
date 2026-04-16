import requests
import logging

logger = logging.getLogger(__name__)

def send_ntfy_notification(topic: str, simple_title: str, full_content: str, add_chat_message_func, tags: str = "tada"):
    """Sends a push notification via ntfy.sh and adds to local chat history"""
    add_chat_message_func('system', f"{simple_title}: {full_content}")

    if not topic:
        logger.debug("ntfy_topic not configured. Skipping notification.")
        return

    target_url = topic
    if not target_url.startswith("http"):
        target_url = f"https://ntfy.sh/{target_url}"

    try:
        response = requests.post(
            target_url,
            data=full_content.encode('utf-8'),
            headers={
                "Title": simple_title.encode('utf-8'),
                "Priority": "high",
                "Tags": tags
            }
        )
        response.raise_for_status()
        logger.info(f"Successfully sent ntfy notification to topic: {topic}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send ntfy notification: {e}")