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

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 7777471529  # GANTI ID TELEGRAM KAMU
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
    buyer_username TEXT,
    seller_id INTEGER,
    amount INTEGER,
    fee INTEGER,
    status TEXT,
    created_at TEXT
)
""")
conn.commit()

# ================= TELEGRAM =================

telegram_app = Application.builder().token(TOKEN).build()

# 🔥 WAJIB INITIALIZE
asyncio.run(telegram_app.initialize())

# ================= HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("💰 Buat Transaksi", callback_data="buat")]]

    await update.message.reply_text(
        "🤝 *BOT REKBER QRIS*\n\n"
        "💰 Fee Admin Flat: Rp1.000\n"
        "Dana ditahan sampai transaksi selesai.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "buat":
        context.user_data["step"] = "amount"
        await query.edit_message_text("Masukkan nominal transaksi (angka saja):")

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

        context.user_data["amount"] = amount
        context.user_data["fee"] = fee
        context.user_data["step"] = "seller"

        await update.message.reply_text(
            f"🧾 DETAIL TRANSAKSI\n\n"
            f"💰 Harga: Rp{amount}\n"
            f"📊 Fee Admin: Rp{fee}\n"
            f"💵 Total Bayar: Rp{total}\n\n"
            f"Masukkan ID Telegram Seller:"
        )

    elif context.user_data["step"] == "seller":
        try:
            seller_id = int(update.message.text)
        except:
            await update.message.reply_text("Masukkan ID Telegram seller yang valid.")
            return

        amount = context.user_data["amount"]
        fee = context.user_data["fee"]
        total = amount + fee

        buyer = update.effective_user

        cursor.execute("""
        INSERT INTO transactions 
        (buyer_id, buyer_username, seller_id, amount, fee, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            buyer.id,
            buyer.username,
            seller_id,
            amount,
            fee,
            "waiting_payment",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

        trx_id = cursor.lastrowid

        # Kirim QRIS
        with open(QRIS_IMAGE_PATH, "rb") as qris:
            await update.message.reply_photo(
                photo=qris,
                caption=(
                    f"🆔 ID Transaksi: RBX-{trx_id}\n"
                    f"👤 Buyer: @{buyer.username}\n"
                    f"🧑‍💼 Seller ID: {seller_id}\n\n"
                    f"💰 Total Bayar: Rp{total}\n\n"
                    f"Silakan scan QRIS di atas."
                )
            )

        context.user_data.clear()

# ================= REGISTER HANDLER =================

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT, message_handler))

# ================= WEBHOOK =================

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.run(telegram_app.process_update(update))
    return "ok"

@app.route("/")
def home():
    return "Rekber QRIS Bot Running!"
