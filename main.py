from utils.GormBot import GormBot
from dotenv import load_dotenv
from os import getenv


def main():
    token = getenv("BOT_TOKEN", None)
    if not token:
        raise ValueError("BOT_TOKEN environment variable is not set.")

    bot = GormBot(token)
    bot.run(token)


if __name__ == "__main__":
    load_dotenv()
    main()
