import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import logging

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

class SheetsManager:
    def __init__(self, credentials_file="credentials.json", sheet_name="ShopAccounts"):
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, SCOPE)
        self.client = gspread.authorize(self.creds)
        self.sheet = self.client.open(sheet_name).sheet1
        self.cached_accounts = []
        
    def sync_accounts(self):
        try:
            records = self.sheet.get_all_records()
            # Robust matching: strip spaces and lowercase
            self.cached_accounts = [
                row for row in records 
                if str(row.get('Status', '')).strip().lower() == 'available'
            ]
            logging.info(f"✅ Sheets synced! {len(self.cached_accounts)} accounts loaded.")
        except Exception as e:
            logging.error(f"❌ Error syncing sheets: {e}")

    def get_available_accounts(self):
        return self.cached_accounts

    def get_account_by_id(self, account_id):
        target_id = str(account_id).strip().lower()
        for acc in self.cached_accounts:
            acc_id = acc.get('ID')
            if acc_id is not None and str(acc_id).strip().lower() == target_id:
                return acc
        return None

    def get_available_count(self, account_id):
        target_id = str(account_id).strip().lower()
        count = 0
        for acc in self.cached_accounts:
            acc_id = acc.get('ID')
            if acc_id is not None and str(acc_id).strip().lower() == target_id:
                count += 1
        return count

    def mark_as_sold(self, account_id):
        try:
            target_id = str(account_id).strip().lower()
            cell = self.sheet.find(target_id) # Note: find might be case-sensitive, but usually okay for IDs
            if cell:
                self.sheet.update_cell(cell.row, 7, "Sold")
                self.cached_accounts = [
                    acc for acc in self.cached_accounts 
                    if str(acc.get('ID')).strip().lower() != target_id
                ]
                return True
        except Exception as e:
            logging.error(f"Error marking sold: {e}")
        return False

    def mark_multiple_as_sold(self, account_id, quantity):
        try:
            sold_count = 0
            all_records = self.sheet.get_all_records()
            target_id_str = str(account_id).strip().lower()
            
            for idx, row in enumerate(all_records, start=2):
                if sold_count >= quantity:
                    break
                    
                row_id = row.get('ID')
                if row_id is None:
                    continue
                    
                # Robust matching
                if str(row_id).strip().lower() == target_id_str and str(row.get('Status', '')).strip().lower() == 'available':
                    self.sheet.update_cell(idx, 7, "Sold")
                    sold_count += 1
            
            # Update cache
            removed = 0
            new_cache = []
            for acc in self.cached_accounts:
                acc_id_val = acc.get('ID')
                if acc_id_val is not None and str(acc_id_val).strip().lower() == target_id_str and removed < quantity:
                    removed += 1
                else:
                    new_cache.append(acc)
            
            self.cached_accounts = new_cache
            logging.info(f"✅ Marked {sold_count} accounts as sold for ID {account_id}")
            return sold_count
        except Exception as e:
            logging.error(f"Error marking multiple as sold: {e}")
            return 0

sheets = SheetsManager(sheet_name="ShopAccounts")

async def auto_sync_sheets():
    while True:
        await asyncio.to_thread(sheets.sync_accounts)
        await asyncio.sleep(120)