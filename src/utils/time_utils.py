import time
import logging
from typing import Optional, Callable, Any
from functools import wraps

def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to a human-readable string.
    
    Args:
        seconds (float): Duration in seconds
        
    Returns:
        str: Formatted duration string (e.g., "2h 30m 15s")
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{int(hours)}h")
    if minutes > 0:
        parts.append(f"{int(minutes)}m")
    if seconds > 0 or not parts:
        parts.append(f"{int(seconds)}s")
    
    return " ".join(parts)

def timed(func: Callable) -> Callable:
    """
    Decorator to time function execution and log the duration.
    
    Args:
        func (Callable): Function to time
        
    Returns:
        Callable: Wrapped function
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start_time
        logging.info(f"{func.__name__} completed in {format_duration(elapsed)}")
        return result
    return wrapper

class ProgressTracker:
    """
    Class to track progress of long-running operations with detailed metrics.
    """
    def __init__(self, 
                 total_items: int, 
                 description: str = "Processing", 
                 update_interval: int = 500):
        self.total_items = total_items
        self.description = description
        self.start_time = time.time()
        self.processed_items = 0
        self.update_interval = update_interval
        
    def update(self, items_processed: int = 1) -> None:
        """
        Update progress and log metrics.
        
        Args:
            items_processed (int): Number of items processed in this update
        """
        self.processed_items += items_processed
        elapsed = time.time() - self.start_time
        
        progress = (self.processed_items / self.total_items) * 100
        items_remaining = self.total_items - self.processed_items
        rate = self.processed_items / elapsed if elapsed > 0 else 0
        time_remaining = items_remaining / rate if rate > 0 else 0
        
        if self.processed_items % self.update_interval == 0:
            logging.info(
                f"{self.description}: {progress:.1f}% ({self.processed_items}/{self.total_items}) | "
                f"{rate:.1f} items/s | ETA: {format_duration(time_remaining)}"
            ) 