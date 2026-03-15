import os
import sqlite3
import logging
from datetime import datetime
from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
ADMIN_ID = 123456789  # GANTI DENGAN ID TELEGRAM KAMU
QRIS_IMAGE_PATH = "qris.png"

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# ================= DATABASE =================

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    join_date TEXT
)
""")

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

# ================= FUNCTIONS =================

def add_user(user):
    cursor.execute("""
    INSERT OR IGNORE INTO users 
    (telegram_id, username, first_name, join_date)
    VALUES (?, ?, ?, ?)
    """, (
        user.id,
        user.username,
        user.first_name,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)

    keyboard = [
        [InlineKeyboardButton("💰 Buat Transaksi", callback_data="buat")]
    ]

    await update.message.reply_text(
        "🤝 *BOT REKBER QRIS*\n\n"
        "💰 Fee Admin Flat: Rp1.000\n"
        "📌 Berapapun nominal transaksi, fee tetap Rp1.000\n\n"
        "Dana masuk ke QRIS admin & ditahan sampai selesai.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ================= BUTTON HANDLER =================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buat":
        context.user_data["step"] = "amount"
        await query.edit_message_text("Masukkan nominal transaksi (angka saja):")

    elif query.data.startswith("verify_") and user_id == ADMIN_ID:
        trx_id = int(query.data.split("_")[1])

        cursor.execute("UPDATE transactions SET status='escrow' WHERE id=?", (trx_id,))
        conn.commit()

        await query.edit_message_text(f"✅ Transaksi RBX-{trx_id} diverifikasi.\nStatus: ESCROW")

        cursor.execute("SELECT buyer_id, seller_id FROM transactions WHERE id=?", (trx_id,))
        buyer_id, seller_id = cursor.fetchone()

        await context.bot.send_message(buyer_id, "✅ Pembayaran diverifikasi. Dana ditahan (ESCROW).")
        await context.bot.send_message(seller_id, "🔔 Dana sudah diterima admin & ditahan.")

# ================= MESSAGE HANDLER =================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)

    if "step" not in context.user_data:
        return

    step = context.user_data["step"]

    if step == "amount":
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
            f"📊 Fee: Rp{fee}\n"
            f"💵 Total Bayar: Rp{total}\n\n"
            f"Masukkan ID Telegram Seller:"
        )

    elif step == "seller":
        try:
            seller_id = int(update.message.text)
        except:
            await update.message.reply_text("Masukkan ID Telegram seller yang valid.")
            return

        amount = context.user_data["amount"]
        fee = context.user_data["fee"]

        cursor.execute("""
        INSERT INTO transactions 
        (buyer_id, seller_id, amount, fee, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user.id,
            seller_id,
            amount,
            fee,
            "pending_payment",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

        trx_id = cursor.lastrowid

        with open(QRIS_IMAGE_PATH, "rb") as qris_file:
            await update.message.reply_photo(
                photo=qris_file,
                caption=(
                    f"🆔 ID: RBX-{trx_id}\n"
                    f"💰 Total Bayar: Rp{amount+fee}\n\n"
                    "Silakan scan QRIS di atas.\n"
                    "Setelah bayar, kirim foto bukti transfer."
                )
            )

        context.user_data["trx_id"] = trx_id
        context.user_data["step"] = "upload_proof"

    elif step == "upload_proof":
        if not update.message.photo:
            await update.message.reply_text("Kirim foto bukti transfer.")
            return

        file_id = update.message.photo[-1].file_id
        trx_id = context.user_data["trx_id"]

        cursor.execute("""
        UPDATE transactions 
        SET status='waiting_verification', proof_file_id=?
        WHERE id=?
        """, (file_id, trx_id))
        conn.commit()

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Verifikasi", callback_data=f"verify_{trx_id}")]
        ])

        await context.bot.send_photo(
            ADMIN_ID,
            photo=file_id,
            caption=f"📥 Bukti pembayaran RBX-{trx_id}",
            reply_markup=keyboard
        )

        await update.message.reply_text("⏳ Bukti dikirim ke admin. Menunggu verifikasi.")
        context.user_data.clear()

# ================= SELESAI =================

async def selesai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Gunakan: /selesai ID_TRANSAKSI")
        return

    trx_id = int(context.args[0])

    cursor.execute("""
    SELECT buyer_id, seller_id, amount, status 
    FROM transactions WHERE id=?
    """, (trx_id,))
    trx = cursor.fetchone()

    if not trx:
        await update.message.reply_text("Transaksi tidak ditemukan.")
        return

    buyer_id, seller_id, amount, status = trx

    if status != "escrow":
        await update.message.reply_text("Transaksi belum di-escrow.")
        return

    cursor.execute("UPDATE transactions SET status='selesai' WHERE id=?", (trx_id,))
    conn.commit()

    await update.message.reply_text(
        "🎉 Transaksi selesai.\nAdmin akan transfer manual ke seller."
    )

    await context.bot.send_message(
        ADMIN_ID,
        f"💸 Transfer manual ke seller ID {seller_id}\nNominal: Rp{amount}"
    )

# ================= TELEGRAM APP INIT =================

telegram_app = Application.builder().token(TOKEN).build()

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("selesai", selesai))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, message_handler))

# ================= WEBHOOK ROUTE =================

@app.route("/webhook", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    await telegram_app.process_update(update)
    return "ok"

@app.route("/")
def home():
    return "Rekber QRIS Bot Running!"
