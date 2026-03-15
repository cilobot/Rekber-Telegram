import os
import sqlite3
import logging
import asyncio
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 7777471529  # GANTI DENGAN ID TELEGRAM KAMU
QRIS_IMAGE_PATH = "qris.png"

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# ================= DATABASE =================

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id INTEGER,
    seller_id INTEGER,
    amount INTEGER,
    fee INTEGER,
    status TEXT,
    proof_file_id TEXT,
    created_at TEXT
)
""")
conn.commit()

# ================= TELEGRAM HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("💰 Buat Transaksi", callback_data="buat")]]

    await update.message.reply_text(
        "🤝 BOT REKBER QRIS\n\n"
        "💰 Fee Admin Flat: Rp1.000\n"
        "Dana masuk ke QRIS admin & ditahan sampai selesai.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "buat":
        context.user_data["step"] = "amount"
        await query.edit_message_text("Masukkan nominal transaksi:")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "step" not in context.user_data:
        return

    if context.user_data["step"] == "amount":
        try:
            amount = int(update.message.text)
        except:
            await update.message.reply_text("Masukkan angka yang benar.")
            return

        fee = 1000
        total = amount + fee

        context.user_data.clear()

        await update.message.reply_text(
            f"💰 Total Bayar: Rp{total}\n\nSilakan scan QRIS."
        )

# ================= INIT TELEGRAM =================

telegram_app = Application.builder().token(TOKEN).build()

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT, message_handler))

# 🔥 PENTING — INITIALIZE SEKALI SAAT START
asyncio.run(telegram_app.initialize())

# ================= WEBHOOK =================

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.run(telegram_app.process_update(update))
    return "ok"

@app.route("/")
def home():
    return "Bot Running!"
