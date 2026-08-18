"""Telegram entry point for the safe cloud deployment."""

import asyncio
import io
import logging
import sys

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
from google_automation import GoogleAutomationError, check_gemini_offer

logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

AWAIT_EMAIL, AWAIT_PASSWORD, AWAIT_TOTP = range(3)


def _authorized(update: Update) -> bool:
    if config.ADMIN_TELEGRAM_ID is None:
        return True
    user = update.effective_user
    return bool(user and user.id == config.ADMIN_TELEGRAM_ID)


async def _deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("⛔ This bot is private.")


def _get_session(chat_id: int) -> dict:
    return config.SESSION_STORE.setdefault(chat_id, {})


def _make_progress_callback(bot, chat_id: int, loop: asyncio.AbstractEventLoop):
    def _cb(msg: str, screenshot_bytes: bytes | None = None):
        async def _send():
            try:
                if screenshot_bytes:
                    await bot.send_photo(chat_id=chat_id, photo=io.BytesIO(screenshot_bytes), caption=msg[:1024])
                else:
                    await bot.send_message(chat_id=chat_id, text=msg)
            except Exception as exc:
                logger.warning("Progress send error: %s", exc)
        asyncio.run_coroutine_threadsafe(_send(), loop)
    return _cb


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    await update.message.reply_text(
        "🤖 *Google One Offer Checker*\n\n"
        "Uses a standard Chromium session to sign in and check Google One pages for offers visible to your account.\n\n"
        "Commands:\n"
        "• /login – enter Gmail credentials and optional TOTP secret\n"
        "• /check\\_offer – check Google One\n"
        "• /get\\_link – show the last captured link\n"
        "• /status – session status\n\n"
        "Credentials are kept in memory only and disappear when the process restarts.",
        parse_mode="Markdown",
    )


async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _authorized(update):
        await _deny(update)
        return ConversationHandler.END
    await update.message.reply_text("📧 Enter your Gmail address:", reply_markup=ReplyKeyboardRemove())
    return AWAIT_EMAIL


async def login_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["pending_email"] = update.message.text.strip()
    await update.message.reply_text("🔒 Enter your password:")
    return AWAIT_PASSWORD


async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["pending_password"] = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    await update.effective_chat.send_message(
        "🔐 Enter your authenticator TOTP secret, or send `none` if you do not use TOTP.",
        parse_mode="Markdown",
    )
    return AWAIT_TOTP


async def login_totp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    raw = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    session = _get_session(chat_id)
    session.clear()
    session["email"] = context.user_data.pop("pending_email", "")
    session["password"] = context.user_data.pop("pending_password", "")
    session["totp_secret"] = None if raw.lower() == "none" else raw.upper().replace(" ", "")
    session["offer_link"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text="✅ Credentials loaded in memory. Use /check_offer to continue.",
    )
    return ConversationHandler.END


async def login_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("pending_email", None)
    context.user_data.pop("pending_password", None)
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def check_offer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return

    chat_id = update.effective_chat.id
    session = _get_session(chat_id)
    if not session.get("email") or not session.get("password"):
        await update.message.reply_text("Use /login first.")
        return

    await update.message.reply_text("🔎 Starting Google One check…")
    loop = asyncio.get_running_loop()
    progress_cb = _make_progress_callback(context.bot, chat_id, loop)

    try:
        offer_link = await loop.run_in_executor(
            None,
            lambda: check_gemini_offer(
                session["email"],
                session["password"],
                totp_secret=session.get("totp_secret"),
                progress_callback=progress_cb,
            ),
        )
    except GoogleAutomationError as exc:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ {exc}")
        return
    except Exception as exc:
        logger.exception("Unexpected check_offer error")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Unexpected error: {exc}")
        return

    if offer_link:
        session["offer_link"] = offer_link
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Offer link found:\n{offer_link}")
    else:
        await context.bot.send_message(chat_id=chat_id, text="No visible Google One / Google AI offer link was found.")


async def get_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    link = _get_session(update.effective_chat.id).get("offer_link")
    await update.message.reply_text(link or "No link captured yet.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    session = _get_session(update.effective_chat.id)
    email = session.get("email", "—")
    await update.message.reply_text(
        f"Account: {email}\n"
        f"Credentials loaded: {'yes' if session.get('password') else 'no'}\n"
        f"TOTP loaded: {'yes' if session.get('totp_secret') else 'no'}\n"
        f"Offer link captured: {'yes' if session.get('offer_link') else 'no'}"
    )


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set")
        sys.exit(1)
    if config.ADMIN_TELEGRAM_ID is None:
        logger.warning("ADMIN_TELEGRAM_ID is not set; anyone who can reach the bot may use it.")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            AWAIT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)],
            AWAIT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
            AWAIT_TOTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_totp)],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(login_conv)
    app.add_handler(CommandHandler("check_offer", check_offer))
    app.add_handler(CommandHandler("get_link", get_link))
    app.add_handler(CommandHandler("status", status))

    logger.info("Bot is running")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
