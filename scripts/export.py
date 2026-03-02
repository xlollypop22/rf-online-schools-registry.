import os
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

def main():
    sheet_id = os.environ["GOOGLE_SHEET_ID"].strip()
    creds_json = os.environ["GOOGLE_CREDENTIALS"]

    creds_dict = json.loads(creds_json)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(credentials)

    sh = client.open_by_key(sheet_id)
    ws = sh.get_worksheet(0)

    df = pd.read_csv("data/registry_final.csv")

    if df.empty:
        print("registry_final.csv is empty; skipping upload")
        return

    ws.clear()
    ws.update([df.columns.tolist()] + df.fillna("").values.tolist())

    print("Uploaded to Google Sheets successfully")

if __name__ == "__main__":
    main()
