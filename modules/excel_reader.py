import pandas as pd
from pathlib import Path

# Default column names (used when no custom mapping is provided)
DEFAULT_MAP = {
    "clients": {
        "account_no":      "Account No",
        "name":            "Client Name",
        "email":           "Email",
        "phone":           "Phone",
        "address":         "Address",
        "account_type":    "Account Type",
        "opening_balance": "Opening Balance",
    },
    "transactions": {
        "account_no":  "Account No",
        "date":        "Date",
        "description": "Description",
        "reference":   "Reference",
        "debit":       "Debit",
        "credit":      "Credit",
        "balance":     "Balance",
    },
}


class ExcelReader:
    """
    Reads client + transaction data from any Excel workbook.

    mapping dict shape (from column-mapper UI):
    {
      "client_sheet":  "Sheet1",          # name of the clients sheet
      "txn_sheet":     "Sheet1",          # name of the transactions sheet (may equal client_sheet)
      "flat_mode":     false,             # true → single sheet, group by account_no
      "clients":       { "account_no": "Acct#", "name": "Customer", ... },
      "transactions":  { "account_no": "Acct#", "date": "Date", ... }
    }
    """

    def __init__(self, filepath: Path, mapping: dict | None = None):
        self.filepath = filepath
        self.mapping = mapping or {}
        self._xl = pd.ExcelFile(filepath)

    # ── public ────────────────────────────────────────────────────────────────

    def get_clients(self) -> list[dict]:
        flat = self.mapping.get("flat_mode", False)
        if flat:
            return self._read_flat()

        client_sheet = self.mapping.get("client_sheet") or self._guess_sheet(["Clients", "Client", "Master", "Customers"])
        if client_sheet not in self._xl.sheet_names:
            raise ValueError(
                f"Sheet '{client_sheet}' not found. "
                "Use the column mapper to select the correct sheet, or download the standard template."
            )

        txn_sheet = self.mapping.get("txn_sheet") or self._guess_sheet(["Transactions", "Transaction", "Txn", "Statement"])

        clients_df = self._read_sheet(client_sheet)
        c_col = {**DEFAULT_MAP["clients"], **self.mapping.get("clients", {})}

        clients = []
        for _, row in clients_df.iterrows():
            acct = _str(row.get(c_col["account_no"], ""))
            if not acct:
                continue
            clients.append({
                "account_no":      acct,
                "name":            _str(row.get(c_col["name"], "")),
                "email":           _str(row.get(c_col["email"], "")),
                "phone":           _str(row.get(c_col["phone"], "")),
                "address":         _str(row.get(c_col["address"], "")),
                "account_type":    _str(row.get(c_col["account_type"], "")),
                "opening_balance": _to_float(row.get(c_col["opening_balance"], 0)),
                "transactions":    self._get_transactions(acct, txn_sheet),
            })
        return clients

    # ── private ───────────────────────────────────────────────────────────────

    def _get_transactions(self, account_no: str, txn_sheet: str | None) -> list[dict]:
        if not txn_sheet or txn_sheet not in self._xl.sheet_names:
            return []
        txn_df = self._read_sheet(txn_sheet)
        t_col = {**DEFAULT_MAP["transactions"], **self.mapping.get("transactions", {})}

        acct_col = t_col["account_no"]
        if acct_col not in txn_df.columns:
            return []

        subset = txn_df[txn_df[acct_col].str.strip() == account_no.strip()]
        rows = []
        for _, row in subset.iterrows():
            rows.append({
                "date":        _str(row.get(t_col["date"], "")),
                "description": _str(row.get(t_col["description"], "")),
                "reference":   _str(row.get(t_col["reference"], "")),
                "debit":       _to_float(row.get(t_col["debit"], 0)),
                "credit":      _to_float(row.get(t_col["credit"], 0)),
                "balance":     _to_float(row.get(t_col["balance"], 0)),
            })
        return rows

    def _read_flat(self) -> list[dict]:
        """
        Single-sheet mode: every row is a transaction.
        Clients are inferred from the first occurrence of each account_no.
        """
        sheet = self.mapping.get("client_sheet") or self._xl.sheet_names[0]
        df = self._read_sheet(sheet)

        c_col = {**DEFAULT_MAP["clients"], **self.mapping.get("clients", {})}
        t_col = {**DEFAULT_MAP["transactions"], **self.mapping.get("transactions", {})}

        clients: dict[str, dict] = {}
        for _, row in df.iterrows():
            acct = _str(row.get(c_col["account_no"], ""))
            if not acct:
                continue
            if acct not in clients:
                clients[acct] = {
                    "account_no":      acct,
                    "name":            _str(row.get(c_col["name"], "")),
                    "email":           _str(row.get(c_col["email"], "")),
                    "phone":           _str(row.get(c_col.get("phone", "__"), "")),
                    "address":         _str(row.get(c_col.get("address", "__"), "")),
                    "account_type":    _str(row.get(c_col.get("account_type", "__"), "")),
                    "opening_balance": 0.0,
                    "transactions":    [],
                }
            clients[acct]["transactions"].append({
                "date":        _str(row.get(t_col["date"], "")),
                "description": _str(row.get(t_col["description"], "")),
                "reference":   _str(row.get(t_col.get("reference", "__"), "")),
                "debit":       _to_float(row.get(t_col["debit"], 0)),
                "credit":      _to_float(row.get(t_col["credit"], 0)),
                "balance":     _to_float(row.get(t_col["balance"], 0)),
            })

        return list(clients.values())

    def _read_sheet(self, sheet: str) -> pd.DataFrame:
        return pd.read_excel(self.filepath, sheet_name=sheet, dtype=str).fillna("")

    def _guess_sheet(self, candidates: list[str]) -> str | None:
        names_lower = {s.lower(): s for s in self._xl.sheet_names}
        for c in candidates:
            if c.lower() in names_lower:
                return names_lower[c.lower()]
        return self._xl.sheet_names[0] if self._xl.sheet_names else None


# ── helpers ────────────────────────────────────────────────────────────────────

def _str(val) -> str:
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _to_float(val) -> float:
    try:
        return float(val) if str(val).strip() not in ("", "nan") else 0.0
    except (ValueError, TypeError):
        return 0.0
