# bot.py — Render-ready, async (python-telegram-bot v20), full onboarding flow
import os
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

(ASK_NAME, ASK_GENDER, ASK_PHONE, ASK_EMAIL, ASK_WHATSAPP, ASK_TELE_ID, ASK_ACCOUNT, ASK_IFSC, ASK_BANK, CONFIRM) = range(10)

BOT_TOKEN = os.getenv("BOT_TOKEN")
HR_TELEGRAM_USERNAME = os.getenv("HR_TELEGRAM_USERNAME")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
ONBOARDING_IMAGE_URL = os.getenv("ONBOARDING_IMAGE_URL")
GOOGLE_CREDS_JSON_CONTENT = os.getenv("GOOGLE_CREDS_JSON_CONTENT")
APP_URL = os.getenv("APP_URL")
PORT = int(os.getenv("PORT", 10000))

if not BOT_TOKEN or not SPREADSHEET_ID or not GOOGLE_CREDS_JSON_CONTENT or not APP_URL:
    logger.error("Required environment variables missing. Exiting.")
    raise SystemExit("Environment variables missing")

GOOGLE_CREDS_JSON_PATH = "/tmp/service_account.json"
with open(GOOGLE_CREDS_JSON_PATH, "w") as f:
    f.write(GOOGLE_CREDS_JSON_CONTENT)

def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(GOOGLE_CREDS_JSON_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.sheet1

def generate_emp_code(phone: str) -> str:
    digits = "".join([c for c in phone if c.isdigit()])
    last4 = digits[-4:] if len(digits) >= 4 else digits.zfill(4)
    return f"CHEGG{last4}"

def is_valid_phone(phone: str) -> bool:
    digits = "".join([c for c in phone if c.isdigit()])
    return len(digits) >= 7

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collected"] = {}
    await update.message.reply_text("Welcome to the Onboarding Bot! First — what's your full name?")
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collected"]["name"] = update.message.text.strip()
    kb = ReplyKeyboardMarkup([["Male", "Female", "Other"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("What's your gender?", reply_markup=kb)
    return ASK_GENDER

async def ask_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collected"]["gender"] = update.message.text.strip()
    await update.message.reply_text("Please enter your Phone Number:", reply_markup=ReplyKeyboardRemove())
    return ASK_PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not is_valid_phone(phone):
        await update.message.reply_text("Invalid phone number. Try again.")
        return ASK_PHONE
    context.user_data["collected"]["phone"] = phone
    await update.message.reply_text("Enter your Email address:")
    return ASK_EMAIL

async def ask_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collected"]["email"] = update.message.text.strip()
    await update.message.reply_text("WhatsApp Number (or type 'same'):")
    return ASK_WHATSAPP

async def ask_whatsapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    whats = update.message.text.strip()
    if whats.lower() == "same":
        whats = context.user_data["collected"].get("phone", "")
    context.user_data["collected"]["whatsapp"] = whats
    await update.message.reply_text("Send your Telegram UserId (without @):")
    return ASK_TELE_ID

async def ask_tele_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collected"]["telegram_user"] = update.message.text.strip().lstrip("@")
    await update.message.reply_text("Enter your Account Number:")
    return ASK_ACCOUNT

async def ask_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collected"]["account_number"] = update.message.text.strip()
    await update.message.reply_text("Enter your Bank IFSC code:")
    return ASK_IFSC

async def ask_ifsc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collected"]["ifsc"] = update.message.text.strip().upper()
    await update.message.reply_text("Enter your Bank Name:")
    return ASK_BANK

async def ask_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["collected"]["bank_name"] = update.message.text.strip()
    c = context.user_data["collected"]
    summary = (
        f"Summary:\\nName: {c.get('name')}\\nGender: {c.get('gender')}\\nPhone: {c.get('phone')}\\n"
        f"Email: {c.get('email')}\\nWhatsApp: {c.get('whatsapp')}\\nTelegram: {c.get('telegram_user')}\\n"
        f"Account: {c.get('account_number')}\\nIFSC: {c.get('ifsc')}\\nBank: {c.get('bank_name')}\\n\\n"
        "Send 'confirm' to submit or 'cancel' to abort."
    )
    await update.message.reply_text(summary)
    return CONFIRM

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() not in ("confirm", "yes"):
        await update.message.reply_text("Onboarding canceled. Send /start to retry.")
        return ConversationHandler.END

    c = context.user_data["collected"]
    emp_code = generate_emp_code(c.get("phone", ""))
    c["employee_code"] = emp_code
    c["created_at"] = datetime.utcnow().isoformat()

    try:
        sheet = get_sheet()
        header = ["Employee Code","Name","Gender","Phone","Email","WhatsApp","Telegram User","Account Number","IFSC","Bank Name","Timestamp"]
        try:
            first_row = sheet.row_values(1)
        except Exception:
            first_row = []
        if first_row != header:
            try:
                sheet.insert_row(header, index=1)
            except Exception:
                pass
        row = [c.get('employee_code'),c.get('name'),c.get('gender'),c.get('phone'),c.get('email'),
               c.get('whatsapp'),c.get('telegram_user'),c.get('account_number'),c.get('ifsc'),
               c.get('bank_name'),c.get('created_at')]
        sheet.append_row(row)
    except Exception:
        logger.exception("Failed to write to Google Sheet")
        await update.message.reply_text("Error saving details. Try again later.")
        return ConversationHandler.END

    await update.message.reply_text(f"Your Employee Code: *{emp_code}*", parse_mode="Markdown")
    if ONBOARDING_IMAGE_URL:
        try:
            await update.message.reply_photo(photo=ONBOARDING_IMAGE_URL)
        except Exception:
            await update.message.reply_text("(Could not send image)")

    if HR_TELEGRAM_USERNAME:
        await update.message.reply_text(f"Share your Employee Code with HR: https://t.me/{HR_TELEGRAM_USERNAME}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Onboarding canceled. Send /start to retry.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

app = ApplicationBuilder().token(BOT_TOKEN).build()
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        ASK_GENDER:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_gender)],
        ASK_PHONE:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        ASK_EMAIL:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_email)],
        ASK_WHATSAPP:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_whatsapp)],
        ASK_TELE_ID:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_tele_id)],
        ASK_ACCOUNT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_account)],
        ASK_IFSC:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_ifsc)],
        ASK_BANK:[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_bank)],
        CONFIRM:[MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
app.add_handler(conv_handler)

if __name__ == "__main__":
    logger.info("Bot started in webhook mode...")
    app.run_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN, webhook_url=f"{APP_URL}/{BOT_TOKEN}")
