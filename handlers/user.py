from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
import asyncio
import os

from config import ADMIN_ID
from database.models import User, Order
from database.database import async_session
from sheets_manager import sheets

router = Router()

class PurchaseStates(StatesGroup):
    waiting_for_custom_quantity = State()

class DepositStates(StatesGroup):
    waiting_for_amount = State()

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def format_product_message(title, stock, price, description, balance):
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Available Stock:</b> {stock} accounts\n"
        f"💰 <b>Price:</b> ${price} per account\n\n"
        f"📋 <b>Product Details:</b>\n"
        f"<i>{description}</i>\n\n"
        f"💳 <b>Your Balance:</b> ${balance} USDT\n\n"
        f"<b> Choose Quantity:</b>"
    )

def format_purchase_summary(title, quantity, unit_price, total, balance_after):
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Order Summary</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛒 <b>Product:</b> {title}\n"
        f"🔢 <b>Quantity:</b> {quantity} accounts\n"
        f"💵 <b>Unit Price:</b> ${unit_price}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Total Amount:</b> ${total} USDT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ <b>Balance Status:</b> Sufficient\n"
        f"💳 <b>Remaining Balance:</b> ${balance_after} USDT\n\n"
        f"<i>⏳ Processing your order...</i>"
    )

def format_multiple_accounts_details(title, quantity, accounts_list):
    details_text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Purchase Successful!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛒 <b>Product:</b> {title}\n"
        f"🔢 <b>Quantity:</b> {quantity} accounts\n\n"
        f"📋 <b>Account Details:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for idx, acc_info in enumerate(accounts_list, 1):
        details_text += f"<b>Account #{idx}:</b>\n<code>{acc_info}</code>\n\n"
    
    details_text += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔐 <b>Important:</b>\n"
        f"• Save all details immediately\n"
        f"• We are not responsible for lost details\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    return details_text

# ==========================================
# 1. START COMMAND
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            new_user = User(id=message.from_user.id, username=message.from_user.username)
            session.add(new_user)
            await session.commit()

    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Shop Now", callback_data="shop")
    builder.button(text="💰 My Orders", callback_data="my_orders")
    builder.button(text="💳 Deposit", callback_data="deposit")
    builder.button(text="🎧 Support", callback_data="support")
    builder.button(text="👤 Profile", callback_data="profile")
    builder.adjust(2, 2, 1)
    
    await message.answer(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 <b>Welcome to Premium Shop!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Hello <b>{message.from_user.first_name}</b>!\n\n"
        f"🎮 Premium gaming accounts\n"
        f"⚡ Instant delivery\n"
        f"💰 Best prices guaranteed\n\n"
        f"<b>Choose an option:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ==========================================
# 2. SHOP & CATEGORIES
# ==========================================
@router.callback_query(F.data == "shop")
async def process_shop(callback: CallbackQuery):
    await callback.answer()
    
    await callback.message.edit_text(
        "⏳ <b>Loading products...</b>",
        parse_mode="HTML"
    )
    await asyncio.sleep(0.5)
    
    accounts = sheets.get_available_accounts()
    
    if not accounts:
        await callback.message.edit_text(
            "❌ <b>Out of Stock!</b>\n\n"
            "Filhal koi account available nahi hai.\n"
            "Kuch der baad try karein.",
            reply_markup=back_to_menu(),
            parse_mode="HTML"
        )
        return

    categories = list(set(acc.get('Category') for acc in accounts if acc.get('Category')))
    
    builder = InlineKeyboardBuilder()
    for cat in categories:
        cat_stock = len([acc for acc in accounts if acc.get('Category') == cat])
        builder.button(text=f"🎮 {cat} ({cat_stock})", callback_data=f"cat_{cat}")
    builder.button(text="🏠 Main Menu", callback_data="start_menu")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Available Products</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Select a category:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("cat_"))
async def show_category_accounts(callback: CallbackQuery):
    category = callback.data.split("_", 1)[1]
    await callback.answer()
    
    accounts = [acc for acc in sheets.get_available_accounts() if acc.get('Category') == category]
    
    if not accounts:
        await callback.message.answer("⚠️ Is category mein koi account nahi hai!", show_alert=True)
        return
    
    unique_accounts = {}
    for acc in accounts:
        acc_id = str(acc.get('ID')).strip()
        if acc_id and acc_id not in unique_accounts:
            unique_accounts[acc_id] = acc
    
    builder = InlineKeyboardBuilder()
    for acc_id, acc in unique_accounts.items():
        title = acc.get('Title', 'Unknown')
        stock = sheets.get_available_count(acc_id)
        price = acc.get('Price', '0')
        builder.button(
            text=f"💎 {title} - {stock} avail. (${price})",
            callback_data=f"buy_{acc_id}"
        )
    builder.button(text="🔙 Back to Categories", callback_data="shop")
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 <b>{category} Accounts</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Total Products:</b> {len(unique_accounts)}\n"
        f"<b>Select to purchase:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ==========================================
# 3. ACCOUNT DETAILS WITH QUANTITY
# ==========================================
@router.callback_query(F.data.startswith("buy_"))
async def show_account_details(callback: CallbackQuery, state: FSMContext):
    acc_id = callback.data.split("_", 1)[1]
    await callback.answer()
    
    account = sheets.get_account_by_id(acc_id)
    if not account:
        await callback.message.edit_text(
            "❌ <b>Sold Out!</b>\n\n"
            "Yeh account already sell ho chuka hai.",
            reply_markup=back_to_menu(),
            parse_mode="HTML"
        )
        return

    stock = sheets.get_available_count(acc_id)
    title = account.get('Title', 'N/A')
    category = account.get('Category', 'N/A')
    price = int(account.get('Price', '0'))
    description = account.get('Description', 'No details')
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        balance = user.balance if user else 0
    
    await state.set_data({
        'account_id': acc_id,
        'title': title,
        'category': category,
        'price': price,
        'stock': stock,
        'description': description
    })
    
    builder = InlineKeyboardBuilder()
    quantities = [1, 5, 10, 20, 50, 100]
    added_buttons = 0
    
    for qty in quantities:
        if qty <= stock:
            total = qty * price
            builder.button(
                text=f"🔢 {qty} acc = ${total}",
                callback_data=f"qty_{acc_id}_{qty}"
            )
            added_buttons += 1
    
    if stock > 1:
        builder.button(text="📝 Custom Quantity", callback_data=f"custom_qty_{acc_id}")
    
    builder.button(text="🔙 Back to Categories", callback_data="shop")
    builder.button(text="🏠 Main Menu", callback_data="start_menu")
    
    if added_buttons <= 2:
        builder.adjust(added_buttons, 1, 1)
    else:
        builder.adjust(2, 2, 1, 1)

    text = format_product_message(title, stock, price, description, balance)
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ==========================================
# 4. QUANTITY SELECTION
# ==========================================
@router.callback_query(F.data.startswith("qty_"))
async def process_quantity_selection(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split("_")
    acc_id = data_parts[1]
    quantity = int(data_parts[2])
    
    await callback.answer()
    
    state_data = await state.get_data()
    price = state_data.get('price', 0)
    title = state_data.get('title', '')
    stock = state_data.get('stock', 0)
    
    if quantity > stock:
        await callback.message.answer(
            f"❌ <b>Out of Stock!</b>\n\n"
            f"Available: {stock}\n"
            f"Requested: {quantity}",
            show_alert=True,
            parse_mode="HTML"
        )
        return
    
    total_price = quantity * price
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        balance = user.balance if user else 0
    
    await state.update_data(
        quantity=quantity,
        total_price=total_price,
        user_balance=balance
    )
    
    balance_after = balance - total_price
    
    if balance >= total_price:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="✅ Confirm Purchase",
            callback_data="confirm_buy"
        )
        builder.button(text="❌ Cancel", callback_data=f"buy_{acc_id}")
        builder.adjust(1)
        
        text = format_purchase_summary(title, quantity, price, total_price, balance_after)
        
        await callback.message.answer(
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    else:
        shortage = total_price - balance
        builder = InlineKeyboardBuilder()
        builder.button(text="💳 Pay via Crypto", callback_data=f"crypto_pay")
        builder.button(text="💰 Deposit Now", callback_data="deposit")
        builder.button(text="🔙 Back", callback_data=f"buy_{acc_id}")
        builder.adjust(1)
        
        await callback.message.answer(
            f"⚠️ <b>Insufficient Balance!</b>\n\n"
            f"🛒 Product: {title}\n"
            f"🔢 Quantity: {quantity}\n"
            f"💵 Required: ${total_price}\n"
            f"💰 Your Balance: ${balance}\n"
            f"❌ Shortage: ${shortage}\n\n"
            f"<b>Choose payment method:</b>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("custom_qty_"))
async def ask_custom_quantity(callback: CallbackQuery, state: FSMContext):
    acc_id = callback.data.split("_", 1)[1]
    await callback.answer()
    
    state_data = await state.get_data()
    stock = state_data.get('stock', 0)
    price = state_data.get('price', 0)
    
    await state.set_state(PurchaseStates.waiting_for_custom_quantity)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data=f"buy_{acc_id}")
    
    await callback.message.answer(
        f"📝 <b>Bulk Order - Custom Quantity</b>\n\n"
        f"📦 Max Available: <b>{stock}</b> accounts\n"
        f"💰 Price per account: <b>${price}</b>\n\n"
        f"👇 <b>Enter quantity (1-{stock}):</b>\n"
        f"<i>e.g., 25, 50, 75, 100</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(PurchaseStates.waiting_for_custom_quantity)
async def process_custom_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
        state_data = await state.get_data()
        acc_id = state_data.get('account_id')
        stock = state_data.get('stock', 0)
        price = state_data.get('price', 0)
        title = state_data.get('title', '')
        
        if quantity > stock or quantity < 1:
            await message.answer(
                f"❌ <b>Invalid Quantity!</b>\n\n"
                f"Available: 1-{stock}\n"
                f"You entered: {quantity}\n\n"
                f"👇 Try again:",
                parse_mode="HTML"
            )
            return
        
        total_price = quantity * price
        
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == message.from_user.id))
            user = result.scalar_one_or_none()
            balance = user.balance if user else 0
        
        await state.update_data(
            quantity=quantity,
            total_price=total_price,
            user_balance=balance
        )
        
        balance_after = balance - total_price
        
        if balance >= total_price:
            builder = InlineKeyboardBuilder()
            builder.button(
                text="✅ Confirm Bulk Order",
                callback_data="confirm_buy"
            )
            builder.button(text="❌ Cancel", callback_data=f"buy_{acc_id}")
            builder.adjust(1)
            
            text = format_purchase_summary(title, quantity, price, total_price, balance_after)
            text += f"\n\n<i>🚀 Bulk order processing...</i>"
            
            await message.answer(
                text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"⚠️ <b>Insufficient Balance!</b>\n\n"
                f"Required: ${total_price}\n"
                f"Your Balance: ${balance}\n"
                f"Shortage: ${total_price - balance}",
                parse_mode="HTML"
            )
            
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Input!</b>\n"
            "Please enter a valid number.\n"
            "Try again:",
            parse_mode="HTML"
        )

# ==========================================
# 5. CONFIRM PURCHASE WITH TXT FILE FEATURE (FIXED)
# ==========================================
@router.callback_query(F.data == "confirm_buy")
async def confirm_purchase_with_balance(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Processing order...", show_alert=False)
    
    state_data = await state.get_data()
    acc_id = state_data.get('account_id')
    quantity = state_data.get('quantity')
    total_price = state_data.get('total_price')
    title = state_data.get('title', 'Account')
    
    if not acc_id or quantity is None or total_price is None:
        await callback.message.answer(
            "❌ <b>Error!</b>\n"
            "Session expired. Please start the purchase again.",
            parse_mode="HTML"
        )
        await state.clear()
        return
    
    await callback.message.answer(
        "⏳ <b>Processing your order...</b>\n"
        "<i>Please wait while we prepare your accounts.</i>",
        parse_mode="HTML"
    )
    await asyncio.sleep(1)
    
    all_accounts = sheets.get_available_accounts()
    
    if not all_accounts:
        await callback.message.answer(
            "❌ <b>System Error!</b>\n"
            "Account database is currently empty or syncing. Please try again in a minute.",
            parse_mode="HTML"
        )
        return
    
    accounts_to_deliver = []
    target_id_str = str(acc_id).strip().lower()
    
    for acc in all_accounts:
        if len(accounts_to_deliver) >= quantity:
            break
            
        acc_id_from_sheet = acc.get('ID')
        if acc_id_from_sheet is None:
            continue
            
        if str(acc_id_from_sheet).strip().lower() == target_id_str:
            login_info = acc.get('LoginDetails', 'Details not available')
            accounts_to_deliver.append(login_info)
    
    if not accounts_to_deliver:
        await callback.message.answer(
            f"❌ <b>Error!</b>\n"
            f"Could not find {quantity} accounts with ID '{acc_id}' in stock.\n"
            f"Total available in system: {len(all_accounts)}\n"
            f"Please contact admin.",
            parse_mode="HTML"
        )
        return
    
    user_id = callback.from_user.id
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user and user.balance >= total_price:
            user.balance -= total_price
            
            order = Order(
                user_id=user_id,
                account_id=str(acc_id),
                account_title=title,
                amount=total_price,
                quantity=quantity,
                payment_method="balance",
                status="completed"
            )
            session.add(order)
            await session.commit()
            
            sheets.mark_multiple_as_sold(acc_id, quantity)
            
            # ✅ FIXED: TXT File Generation & Sending using FSInputFile
            if quantity > 5:
                filename = f"accounts_{user_id}_{acc_id}.txt"
                
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"========================================\n")
                    f.write(f"  PURCHASE SUCCESSFUL - PREMIUM SHOP\n")
                    f.write(f"========================================\n\n")
                    f.write(f"Product: {title}\n")
                    f.write(f"Quantity: {quantity} accounts\n")
                    f.write(f"Amount Paid: ${total_price} USDT\n\n")
                    f.write(f"========================================\n")
                    f.write(f"  ACCOUNT DETAILS\n")
                    f.write(f"========================================\n\n")
                    
                    for idx, acc_info in enumerate(accounts_to_deliver, 1):
                        f.write(f"Account #{idx}:\n")
                        f.write(f"{acc_info}\n\n")
                        f.write(f"----------------------------------------\n\n")
                        
                    f.write(f"⚠️ IMPORTANT: Save this file immediately!\n")
                
                # Use FSInputFile for Aiogram 3.x compatibility
                file_to_send = FSInputFile(filename)
                
                await callback.message.answer_document(
                    document=file_to_send,
                    caption=f"✅ <b>Purchase Successful!</b>\n\n"
                            f"🛒 <b>Product:</b> {title}\n"
                            f"🔢 <b>Quantity:</b> {quantity} accounts\n"
                            f"💰 <b>Deducted:</b> ${total_price} USDT\n"
                            f"💳 <b>Remaining Balance:</b> ${user.balance} USDT\n\n"
                            f"📎 <i>Aapki {quantity} accounts ki details attached file mein hain. Please isay download karke save kar lein!</i>",
                    parse_mode="HTML"
                )
                
                # Delete temporary file
                if os.path.exists(filename):
                    os.remove(filename)
                    
            else:
                # Send as text message for small orders (<= 5)
                delivery_text = format_multiple_accounts_details(title, quantity, accounts_to_deliver)
                await callback.message.answer(delivery_text, parse_mode="HTML")
                
                await callback.message.answer(
                    f"💵 <b>Payment Successful!</b>\n"
                    f"💰 Deducted: ${total_price} USDT\n"
                    f"💳 Remaining: ${user.balance} USDT",
                    parse_mode="HTML"
                )
        else:
            await callback.message.answer(
                "❌ <b>Payment Failed!</b>\n"
                "Insufficient balance.",
                parse_mode="HTML"
            )
    
    await state.clear()

@router.callback_query(F.data.startswith("crypto_pay"))
async def process_crypto_payment(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Generating Invoice...")
    
    data = await state.get_data()
    quantity = data.get('quantity', 1)
    total_price = data.get('total_price', 0)
    title = data.get('title', 'Account')
    acc_id = data.get('account_id', 'unknown')
    
    wallet_address = "TYourUSDTTRC20WalletAddressHere123456789"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Payment Sent", callback_data=f"checkpay_{acc_id}")
    builder.button(text="❌ Cancel", callback_data="start_menu")
    builder.adjust(2)

    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Crypto Payment</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛒 Product: {title}\n"
        f"🔢 Quantity: {quantity}\n"
        f"💰 <b>Total: ${total_price} USDT</b>\n\n"
        f"📍 <b>Send to:</b>\n"
        f"<code>{wallet_address}</code>\n\n"
        f"⚠️ Network: TRC20 (Tron)\n"
        f"👉 After payment, click 'Payment Sent'"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ==========================================
# 6. DEPOSIT SYSTEM
# ==========================================
@router.callback_query(F.data == "deposit")
async def process_deposit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(DepositStates.waiting_for_amount)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data="start_menu")
    
    await callback.message.answer(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Deposit Funds</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 Enter amount to deposit:\n"
        f"🔹 Min: <b>$0.01 USDT</b>\n"
        f"🔹 Max: <b>$10,000 USDT</b>\n\n"
        f"👇 <b>Type amount below:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(DepositStates.waiting_for_amount)
async def process_amount_input(message: Message, state: FSMContext):
    raw_text = message.text.strip().replace(',', '')
    
    try:
        amount = float(raw_text)
        
        if 0.01 <= amount <= 10000:
            await state.update_data(amount=amount)
            
            wallet_address = "TYourUSDTTRC20WalletAddressHere123456789"
            
            builder = InlineKeyboardBuilder()
            builder.button(text="✅ I have sent", callback_data="checkpay_deposit")
            builder.button(text="❌ Cancel", callback_data="start_menu")
            builder.adjust(2)

            text = (
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 <b>Deposit Invoice</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 Amount: <b>${amount} USDT</b>\n"
                f"🌐 Network: TRC20 (Tron)\n\n"
                f"📍 <b>Send to:</b>\n"
                f"<code>{wallet_address}</code>\n\n"
                f"⚠️ <i>Send exact amount only!</i>"
            )
            
            await message.answer(
                text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "❌ <b>Invalid Amount!</b>\n"
                f"Min: $0.01 | Max: $10,000\n"
                "Try again:",
                parse_mode="HTML"
            )
            
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Number!</b>\n"
            "Enter numbers only (e.g., 100, 500.5)\n"
            "Try again:",
            parse_mode="HTML"
        )

@router.callback_query(F.data == "checkpay_deposit")
async def process_deposit_sent(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get('amount')
    
    if not amount:
        await callback.answer("Session expired. Try again.", show_alert=True)
        await state.clear()
        return

    await callback.answer("⏳ Notifying admin...")
    await state.clear()
    
    user_id = callback.from_user.id
    username = callback.from_user.username or "N/A"
    
    await callback.message.answer(
        f"✅ <b>Deposit Request Sent!</b>\n\n"
        f"Admin will verify ${amount} USDT shortly.\n"
        f"You will be notified once confirmed.",
        parse_mode="HTML"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Received", callback_data=f"vdr_{user_id}_{amount}")
    builder.button(text="❌ Not Received", callback_data=f"vdn_{user_id}_{amount}")
    builder.adjust(2)
    
    admin_text = (
        f"💰 <b>New Deposit Request!</b>\n\n"
        f"👤 User: {user_id} (@{username})\n"
        f"💵 Amount: <b>${amount} USDT</b>\n\n"
        f"Check wallet and verify:"
    )
    
    await callback.bot.send_message(
        ADMIN_ID,
        admin_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ==========================================
# 7. OTHER MENUS
# ==========================================
@router.callback_query(F.data == "my_orders")
async def process_my_orders(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "📦 <b>Your Orders</b>\n\n"
        "No orders yet.\n"
        "Visit shop to make your first purchase!",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "support")
async def process_support(callback: CallbackQuery):
    await callback.answer()
    admin_username = "YourAdminUsername"
    await callback.message.answer(
        f"🎧 <b>Customer Support</b>\n\n"
        f"Need help? Contact admin:\n\n"
        f"👤 <a href='https://t.me/{admin_username}'>@{admin_username}</a>\n\n"
        f"<i>Available 24/7</i>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "profile")
async def process_profile(callback: CallbackQuery):
    await callback.answer()
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        
        balance = user.balance if user else 0
    
    await callback.message.answer(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Your Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>Balance:</b> ${balance} USDT\n"
        f"📦 <b>Total Orders:</b> 0\n\n"
        f"<i>Balance updates automatically</i>",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "start_menu")
async def back_to_menu_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await cmd_start(callback.message)

# ==========================================
# 8. CATCH-ALL
# ==========================================
@router.callback_query()
async def handle_unhandled_callback(callback: CallbackQuery):
    await callback.answer("⚠️ Feature coming soon!", show_alert=True)

@router.message()
async def handle_text_input(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        pass

def back_to_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Main Menu", callback_data="start_menu")
    return builder.as_markup()