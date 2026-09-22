"""
Detect sheets + columns in any uploaded Excel and auto-suggest field mappings.
"""
import pandas as pd
from pathlib import Path

# For each system field: ordered list of common Excel column names to try
ALIASES = {
    "clients": {
        "account_no":       ["Account No", "Account Number", "Acc No", "Acct No", "Account",
                             "Customer ID", "Client ID", "ID", "Account Code"],
        "name":             ["Client Name", "Customer Name", "Name", "Full Name",
                             "Holder Name", "Account Holder", "Customer"],
        "email":            ["Email", "Email Address", "E-mail", "Mail", "Email ID"],
        "phone":            ["Phone", "Mobile", "Phone Number", "Contact", "Mobile No",
                             "Cell", "Contact No"],
        "address":          ["Address", "Location", "City", "Full Address", "Addr", "Residential Address"],
        "account_type":     ["Account Type", "Type", "Category", "Product", "Scheme"],
        "opening_balance":  ["Opening Balance", "Opening Bal", "Starting Balance",
                             "Initial Balance", "Balance", "Amt"],
    },
    "transactions": {
        "account_no":   ["Account No", "Account Number", "Acc No", "Account",
                         "Customer ID", "Client ID"],
        "date":         ["Date", "Transaction Date", "Txn Date", "Value Date",
                         "Trans Date", "Posting Date"],
        "description":  ["Description", "Narration", "Details", "Particular",
                         "Transaction", "Remarks", "Memo", "Particulars"],
        "reference":    ["Reference", "Ref", "UTR", "Cheque No", "Transaction ID",
                         "Txn ID", "Ref No", "Chq No"],
        "debit":        ["Debit", "Debit Amount", "Dr", "Dr Amount", "Withdrawal",
                         "Debit (Dr)", "Out", "Debit Amt"],
        "credit":       ["Credit", "Credit Amount", "Cr", "Cr Amount", "Deposit",
                         "Credit (Cr)", "In", "Credit Amt"],
        "balance":      ["Balance", "Running Balance", "Available Balance",
                         "Closing Balance", "Bal", "Balance Amt"],
    },
}

FIELD_LABELS = {
    "clients": {
        "account_no":      ("Account No *", "Unique account identifier for each client"),
        "name":            ("Client Name *", "Full name of the client"),
        "email":           ("Email *", "Email address — statements will be sent here"),
        "phone":           ("Phone", "Mobile / phone number"),
        "address":         ("Address", "Mailing address"),
        "account_type":    ("Account Type", "Savings / Current / Loan etc."),
        "opening_balance": ("Opening Balance", "Balance at start of the statement period"),
    },
    "transactions": {
        "account_no":  ("Account No *", "Must match a value in the Clients sheet"),
        "date":        ("Date *", "Transaction date"),
        "description": ("Description *", "Transaction narration / details"),
        "reference":   ("Reference", "UTR / NEFT / Cheque reference"),
        "debit":       ("Debit *", "Amount going out (leave empty for credit rows)"),
        "credit":      ("Credit *", "Amount coming in (leave empty for debit rows)"),
        "balance":     ("Balance *", "Running balance after this transaction"),
    },
}


class ColumnDetector:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._xl = pd.ExcelFile(filepath)

    @property
    def sheet_names(self) -> list[str]:
        return self._xl.sheet_names

    def columns_for(self, sheet: str) -> list[str]:
        df = pd.read_excel(self.filepath, sheet_name=sheet, nrows=0)
        return list(df.columns)

    def preview_rows(self, sheet: str, n: int = 3) -> list[dict]:
        df = pd.read_excel(self.filepath, sheet_name=sheet, nrows=n, dtype=str).fillna("")
        return df.to_dict("records")

    def auto_suggest(self, sheet: str, field_type: str) -> dict[str, str]:
        """Return {system_field: best_matching_column} for a sheet."""
        cols = self.columns_for(sheet)
        cols_lower = {c.strip().lower(): c for c in cols}
        suggestion = {}
        for field, aliases in ALIASES[field_type].items():
            for alias in aliases:
                if alias.strip().lower() in cols_lower:
                    suggestion[field] = cols_lower[alias.strip().lower()]
                    break
        return suggestion

    def detect_flat_mode(self, sheet: str) -> bool:
        """Guess if a sheet is a flat all-in-one layout (has both name/email AND date)."""
        cols_lower = {c.strip().lower() for c in self.columns_for(sheet)}
        has_name = any(a.lower() in cols_lower for a in ALIASES["clients"]["name"])
        has_date = any(a.lower() in cols_lower for a in ALIASES["transactions"]["date"])
        return has_name and has_date
