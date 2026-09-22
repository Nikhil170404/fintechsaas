import pandas as pd
from pathlib import Path


class ExcelReader:
    """Reads client master + transactions from a two-sheet Excel workbook."""

    def __init__(self, filepath: Path):
        self.filepath = filepath

    def get_clients(self) -> list[dict]:
        xl = pd.ExcelFile(self.filepath)
        if "Clients" not in xl.sheet_names:
            raise ValueError(
                "Sheet named 'Clients' not found. "
                "Download the template to see the required format."
            )

        clients_df = pd.read_excel(self.filepath, sheet_name="Clients", dtype=str).fillna("")
        clients = []

        for _, row in clients_df.iterrows():
            acct = str(row.get("Account No", "")).strip()
            if not acct or acct.lower() == "nan":
                continue

            clients.append(
                {
                    "account_no": acct,
                    "name": str(row.get("Client Name", "")).strip(),
                    "email": str(row.get("Email", "")).strip(),
                    "phone": str(row.get("Phone", "")).strip(),
                    "address": str(row.get("Address", "")).strip(),
                    "account_type": str(row.get("Account Type", "")).strip(),
                    "opening_balance": _to_float(row.get("Opening Balance", 0)),
                    "transactions": self._get_transactions(acct, xl),
                }
            )

        return clients

    def _get_transactions(self, account_no: str, xl: pd.ExcelFile) -> list[dict]:
        if "Transactions" not in xl.sheet_names:
            return []

        txn_df = pd.read_excel(self.filepath, sheet_name="Transactions", dtype=str).fillna("")
        subset = txn_df[txn_df["Account No"].str.strip() == account_no.strip()]

        rows = []
        for _, row in subset.iterrows():
            rows.append(
                {
                    "date": str(row.get("Date", "")).strip(),
                    "description": str(row.get("Description", "")).strip(),
                    "reference": str(row.get("Reference", "")).strip(),
                    "debit": _to_float(row.get("Debit", 0)),
                    "credit": _to_float(row.get("Credit", 0)),
                    "balance": _to_float(row.get("Balance", 0)),
                }
            )
        return rows


def _to_float(val) -> float:
    try:
        return float(val) if val not in ("", None, "nan") else 0.0
    except (ValueError, TypeError):
        return 0.0
