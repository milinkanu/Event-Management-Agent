from app_logging import configure_logging, get_logger
from gdrive_manager import GoogleDriveManager


configure_logging()
logger = get_logger(__name__)

logger.info("Starting OAuth flow...")
logger.info("Keep this window open until authentication completes.")
GoogleDriveManager()
logger.info("Authentication completed. You can close this window.")
