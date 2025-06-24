from datetime import datetime

class LogModule:
    def __init__(self, log_file_path="log.txt"):
        """
        Initializes the log module with the specified log file path.
        :param log_file_path: Path to the log file.
        """
        self.log_file_path = log_file_path

    def log(self, message):
        """
        Logs a message with a timestamp to the specified log file.
        :param message: The string message to log.
        """
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")  # Format: [YYYY-MM-DD HH:MM:SS]
        log_entry = f"{timestamp} || {message}\n"

        try:
            with open(self.log_file_path, "a") as log_file:  # Open in append mode
                log_file.write(log_entry)
        except Exception as e:
            raise IOError(f"Failed to write to log file: {e}")

# Usage example
if __name__ == "__main__":
    logger = LogModule("log.txt")  # Specify the log file path
    logger.log("This is a test log entry.")
    logger.log("Another log message with a timestamp.")
