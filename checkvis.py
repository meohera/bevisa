from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import os
import sqlite3
import logging
import requests
from bs4 import BeautifulSoup

# Constants
SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIRECTORY, "bot-token.txt")
DB_PATH = os.path.join(SCRIPT_DIRECTORY, "data.db")

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def write_to_db(user_id: int, word: str, case_number: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO user_commands (user_id, word, case_number) VALUES (?, ?, ?)", (user_id, word, case_number))
        conn.commit()
        success = True
    except sqlite3.Error as e:
        logger.error(f"SQLite error: {str(e)}")
        success = False
    finally:
        conn.close()
    
    return success

def read_from_db(user_id: int, word: str) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT case_number FROM user_commands WHERE user_id = ? AND word = ?", (user_id, word))
        result = cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"SQLite error: {str(e)}")
    finally:
        conn.close()

    if result:
        return result[0]
    else:
        return ""

def get_bot_token():
    try:
        with open(TOKEN_PATH, 'r') as file:
            return file.readline().strip()
    except FileNotFoundError:
        logger.error(f"The file '{TOKEN_PATH}' does not exist.")
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
    return None

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Welcome to the Case Analysis Bot! Please send me a case number.")

def analyze_case(case_number: int) -> (str, str):
    url = f"https://infovisa.ibz.be/ResultNl.aspx?place=THR&visumnr={case_number}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error retrieving data from DVZ: {str(e)}")
        return "Error retrieving data from DVZ.", ""
    
    soup = BeautifulSoup(response.content, 'html.parser')
    dossiernr_element = soup.find(id="dossiernr")
    if dossiernr_element:
        return f"{case_number}: Your search returned no result in DVZ database.", ""

    table = soup.find('table')
    if not table:
        return f"{case_number}: Error.", ""
    
    rows = table.find_all('tr')
    row_state = rows[5].find_all(['th', 'td'])
    case_state = row_state[1].get_text(strip=True)
    row_date = rows[6].find_all(['th', 'td'])
    case_date = row_date[1].get_text(strip=True)
    if not case_date:
        row_date = rows[4].find_all(['th', 'td'])
        case_date = row_date[1].get_text(strip=True)
    short_answer = f'State: *{case_state}*\n(Update: _{case_date}_)'
    long_answer = "\n"
    for row in rows:
        cells = row.find_all(['th', 'td'])
        row_text = f'*{cells[0].get_text(strip=True)}*'
        row_text += (f'\n_{cells[1].get_text(strip=True)}_' if cells[1].get_text(strip=True) else "")
        long_answer += row_text + '\n'

    return short_answer, long_answer

def define(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    args = context.args

    # Check usage
    if len(args) != 2:
        update.message.reply_text("Usage: /define <word> <case_number>")
        return

    word, case_number = args[0], args[1]

    # Check if the word starts with an alphabetic character
    if not word[0].isalpha():
        update.message.reply_text("The word should start with an alphabetic character.")
        return

    # Check if case_number contains only digits
    if not case_number.isdigit():
        update.message.reply_text("The case number should contain only digits.")
        return

    if write_to_db(user_id, word, case_number):
        update.message.reply_text(f"Learned: {word} => {case_number}")

def get_association(update: Update, word: str) -> None:
    user_id = update.message.from_user.id
    case_number = read_from_db(user_id, word)

    if case_number:
        # update.message.reply_text(f"Checking latest information for '{word}' ({case_number})")
        short_result, long_result = analyze_case(case_number)
        short_result = f'{word} ({case_number})\n{short_result}'
        update.message.reply_text(short_result, parse_mode="Markdown")
    else:
        update.message.reply_text(f"No association found for '{word}'")

def check_message(update: Update, context: CallbackContext) -> None:
    msg_text = update.message.text.strip()

    if msg_text.isdigit():
        short_result, long_result = analyze_case(msg_text)
        short_result = f'{msg_text}\n{short_result}'
        update.message.reply_text(short_result, parse_mode="Markdown")
    else:
        get_association(update=update, word=msg_text)

def main():
    bot_token = get_bot_token()
    if not bot_token:
        logger.error("Bot token not found. Exiting.")
        return

    updater = Updater(bot_token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("define", define, pass_args=True))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, check_message))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
