# utils/telegram_utils.py
from python_telegram_bot.error import TimedOut  # Исправлено: из библиотеки
import asyncio
import time
from collections import defaultdict
from utils.logger import logger

class RateLimiter:
    def __init__(self, messages_per_second=1, global_messages_per_second=30):
        self.chat_timestamps = defaultdict(list)
        self.global_timestamps = []
        self.messages_per_second = messages_per_second
        self.global_messages_per_second = global_messages_per_second

    async def wait_for_slot(self, chat_id):
        current_time = time.time()
        # Clean old timestamps
        self.chat_timestamps[chat_id] = [t for t in self.chat_timestamps[chat_id] if current_time - t < 1]
        self.global_timestamps = [t for t in self.global_timestamps if current_time - t < 1]
        
        # Wait for chat-specific slot
        while len(self.chat_timestamps[chat_id]) >= self.messages_per_second:
            await asyncio.sleep(0.1)
            current_time = time.time()
            self.chat_timestamps[chat_id] = [t for t in self.chat_timestamps[chat_id] if current_time - t < 1]
        
        # Wait for global slot
        while len(self.global_timestamps) >= self.global_messages_per_second:
            await asyncio.sleep(0.1)
            current_time = time.time()
            self.global_timestamps = [t for t in self.global_timestamps if current_time - t < 1]
        
        # Record timestamps
        self.chat_timestamps[chat_id].append(current_time)
        self.global_timestamps.append(current_time)

# Initialize rate limiter
rate_limiter = RateLimiter()

async def retry_on_timeout(func, max_attempts=3, delay=1, chat_id=None, message_text=None):
    """
    Retries a Telegram API call on TimedOut errors with exponential backoff.
    
    Args:
        func: The async function to execute (e.g., send_message).
        max_attempts: Maximum number of retry attempts.
        delay: Initial delay between retries (seconds).
        chat_id: Chat ID for rate limiting and logging.
        message_text: Text of the message for logging.
    
    Returns:
        Result of the function if successful.
    
    Raises:
        TimedOut: If all retries fail.
    """
    for attempt in range(max_attempts):
        try:
            if chat_id:
                await rate_limiter.wait_for_slot(chat_id)
            return await func()
        except TimedOut as e:
            if attempt == max_attempts - 1:
                logger.error(f"❌ Failed to send to chat_id={chat_id} after {max_attempts} attempts: {e}, message={message_text}")
                raise
            logger.warning(f"⚠️ Telegram TimedOut for chat_id={chat_id}, retrying in {delay}s (attempt {attempt + 1}/{max_attempts}), message={message_text}")
            await asyncio.sleep(delay)
            delay *= 2  # Exponential backoff