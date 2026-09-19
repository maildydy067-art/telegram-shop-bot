from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
import logging

from config import ADMIN_ID
from sheets_manager import sheets
from database.models import User, Order
from database.database import async_session

router = Router()

# ==========================================
# 1. ADMIN COMMANDS
# ==========================================
@router.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    text = (
        "<b>🛠 Admin Panel</b>\n\n"
        "/sync - Google Sheets refresh\n"
        "/stats - Bot statistics"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("sync"), F.from_user.id == ADMIN_ID)
async def sync_sheets_command(message: Message):
    await message.answer("🔄 Syncing...")
    await sheets.sync_accounts()
    await message.answer(f"✅ Done! {len(sheets.get_available_accounts())} accounts loaded.")

@router.message(Command("stats"), F.from_user.id == ADMIN_ID)
async def show_stats(message: Message):
    async with async_session() as session:
        total_users = await session.scalar(select(func.count()).select_from(User))
        total_orders = await session.scalar(select(func.count()).select_from(Order))
        pending_orders = await session.scalar(select(func.count()).select_from(Order).where(Order.status == 'pending'))
        
    text = (
        "<b>📊 Stats</b>\n\n"
        f" Users: <b>{total_users}</b>\n"
        f"🛒 Orders: <b>{total_orders}</b>\n"
        f"⏳ Pending: <b>{pending_orders}</b>\n"
        f" Available: <b>{len(sheets.get_available_accounts())}</b>"
    )
    await message.answer(text, parse_mode="HTML")

# ==========================================
# 2. ACCOUNT PURCHASE VERIFICATION
# ==========================================
@router.callback_query(F.data.startswith("verify_received_"))
async def payment_received_callback(callback: CallbackQuery):
    await callback.answer("✅ Verifying...", show_alert=False)
    
    data = callback.data.split("_")
    if len(data) < 4:
        await callback.message.edit_text(" Invalid data!")
        return
    
    user_id = int(data[2])
    account_id = data[3]
    
    try:
        account = sheets.get_account_by_id(account_id)
        if not account:
            await callback.message.edit_text("❌ Account nahi mila!")
            return
        
        login_info = account.get('LoginDetails', 'Details not available')
        
        user_text = (
            f"✅ <b>Payment Confirmed!</b>\n\n"
            f"🎮 <b>{account['Title']}</b>\n\n"
            f"📝 <b>Login Details:</b>\n"
            f"<code>{login_info}</code>\n\n"
            f"🔐 <i>Details save kar lein!</i>"
        )
        
        await callback.bot.send_message(user_id, user_text, parse_mode="HTML")
        sheets.mark_as_sold(account_id)
        
        await callback.message.edit_text(
            f"✅ <b>Delivered!</b>\n\n"
            f"👤 User: <code>{user_id}</code>\n"
            f" {account['Title']}\n"
            f"💰 {account['Price']} USDT\n\n"
            f"Sheet mein 'Sold' mark ho gaya."
        )
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Error: {str(e)}")

@router.callback_query(F.data.startswith("verify_not_received_"))
async def payment_not_received_callback(callback: CallbackQuery):
    await callback.answer("❌ Notifying user...", show_alert=False)
    
    data = callback.data.split("_")
    if len(data) < 5:
        await callback.message.edit_text(" Invalid data!")
        return
    
    user_id = int(data[2])
    account_id = data[3]
    
    try:
        user_text = (
            "⚠️ <b>Payment Not Received</b>\n\n"
            "Admin ne payment receive nahi ki. Ho sakta hai:\n"
            "• Transaction pending ho\n"
            "• Galat network use kiya\n\n"
            "📝 TXID support ko bhejein."
        )
        
        await callback.bot.send_message(user_id, user_text, parse_mode="HTML")
        
        await callback.message.edit_text(
            f"❌ <b>User notified</b>\n\n"
            f"👤 User: <code>{user_id}</code>\n"
            f"🛒 ID: {account_id}"
        )
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Error: {str(e)}")

# ==========================================
# 3. DEPOSIT VERIFICATION
# ==========================================
@router.callback_query(F.data.startswith("vdr_"))
async def deposit_received_callback(callback: CallbackQuery):
    """
    Jab admin deposit ke liye '✅ Received' dabaye
    Format: vdr_USERID_AMOUNT
    """
    await callback.answer("✅ Deposit verified!", show_alert=False)
    
    data = callback.data.split("_")
    if len(data) < 3:
        await callback.message.edit_text("❌ Invalid data!")
        return
    
    user_id = int(data[1])
    amount = data[2]
    
    try:
        # User ko confirm message bhejna WITH SHOP BUTTON
        user_text = (
            f"✅ <b>Deposit Confirmed!</b>\n\n"
            f"💰 <b>{amount} USDT</b> aapke account mein add kar diye gaye hain.\n\n"
            f"🎉 Ab aap shop se accounts khareed sakte hain!\n\n"
            f"<i>Shukriya!</i>"
        )
        
        # User ko shop ka button bhejna
        builder = InlineKeyboardBuilder()
        builder.button(text="🛒 Shop Now", callback_data="shop")
        builder.button(text="👤 View Profile", callback_data="profile")
        
        await callback.bot.send_message(
            user_id, 
            user_text, 
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
        # Admin ko confirmation
        await callback.message.edit_text(
            f"✅ <b>Deposit Confirmed!</b>\n\n"
            f"👤 User: <code>{user_id}</code>\n"
            f"💰 Amount: <b>{amount} USDT</b>\n\n"
            f"User ko notify kar diya gaya hai + Shop button bhej diya."
        )
        
        # Database mein user ka balance update karna
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.balance += float(amount)
                await session.commit()
                logging.info(f"✅ User {user_id} balance updated: {user.balance} USDT")
            else:
                # Agar user nahi hai toh naya banao
                new_user = User(id=user_id, balance=float(amount))
                session.add(new_user)
                await session.commit()
        
    except Exception as e:
        logging.error(f"Error in deposit_received: {str(e)}")
        await callback.message.edit_text(f"❌ Error: {str(e)}")

@router.callback_query(F.data.startswith("vdn_"))
async def deposit_not_received_callback(callback: CallbackQuery):
    """
    Jab admin deposit ke liye '❌ Not Received' dabaye
    Format: vdn_USERID_AMOUNT
    """
    await callback.answer("❌ Notifying user...", show_alert=False)
    
    data = callback.data.split("_")
    if len(data) < 3:
        await callback.message.edit_text("❌ Invalid data!")
        return
    
    user_id = int(data[1])
    amount = data[2]
    
    try:
        user_text = (
            f"⚠️ <b>Deposit Not Received</b>\n\n"
            f"Admin ne <b>{amount} USDT</b> receive nahi kiye.\n\n"
            f"Ho sakta hai:\n"
            f"• Transaction abhi pending ho (10-30 min)\n"
            f"• Galat network use kiya (TRC20 use karein)\n"
            f"• Amount kam/zyada bheja\n\n"
            f"📝 Please <b>TXID</b> support ko bhejein."
        )
        
        await callback.bot.send_message(user_id, user_text, parse_mode="HTML")
        
        await callback.message.edit_text(
            f"❌ <b>User notified</b>\n\n"
            f"👤 User: <code>{user_id}</code>\n"
            f" Amount: {amount} USDT\n\n"
            f"User se TXID mangwa gaya hai."
        )
        
    except Exception as e:
        logging.error(f"Error in deposit_not_received: {str(e)}")
        await callback.message.edit_text(f"❌ Error: {str(e)}")