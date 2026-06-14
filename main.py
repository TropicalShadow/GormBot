from utils.GormBot import GormBot
from dotenv import load_dotenv
from os import getenv
import logging


def main():
    logging.basicConfig(level=logging.INFO)
    token = getenv("BOT_TOKEN", None)
    if not token:
        raise ValueError("BOT_TOKEN environment variable is not set.")

    bot = GormBot(token)
    bot.run()


if __name__ == "__main__":
    load_dotenv()
    main()
