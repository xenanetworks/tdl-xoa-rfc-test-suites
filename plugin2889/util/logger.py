import sys
from loguru import logger


#FILE_PATH_FORMAT = "{time:HH:mm:ss.SSS} | <level>{level: <8}</level> | <cyan>{file.path}:{line:}</cyan> <green>{function}</green> | {message}"
FILE_PATH_FORMAT = "{time:HH:mm:ss.SSS} | <cyan>{file.path}:{line:}</cyan> <green>{function}</green> | {message}"


logger.remove()
logger.add(sys.stdout, colorize=True, level="DEBUG", format=FILE_PATH_FORMAT)
