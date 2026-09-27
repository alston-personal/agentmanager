"""Winton (文中) accounting export adapter.

This first version is intentionally conservative:
- it does NOT assume a private/unpublished Winton API;
- it emits a tabular interchange payload suitable for the documented
  "轉檔工具 / Excel 匯入" workflow;
- exact customer-specific column mapping remains profile-driven.

Once a real Winton import template is obtained from a customer installation,
add that mapping as a versioned profile instead of changing OCR or canonical data.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Mapping

from .adapter import AccountingAdapter, AdapterResult, FinancialDocument, require_review_free


DEFAULT_COLUMNS = (
    "invoice_number",
    "invoice_date",
    "seller_tax_id",
    "vendor_name",
    "amount_before_tax",
    "tax_amount",
    "total_amount",
)


@dataclass
class WintonProfile:
    profile_id: str = "winton-generic-excel-v1"
    column_map: Mapping[str, str] = field(default_factory=lambda: {
        "invoice_number": "發票號碼",
        "invoice_date": "發票日期",
        "seller_tax_id": "銷售人統編",
        "vendor_name": "廠商名稱",
        "amount_before_tax": "未稅金額",
        "tax_amount": "稅額",
        "total_amount": "總額",
    })
    delimiter: str = ","


class WintonExcelAdapter(AccountingAdapter):
    adapter_id = "accounting.adapter.winton"

    def __init__(self, profile: WintonProfile | None = None) -> None:
        self.profile = profile or WintonProfile()

    def can_export(self, document: FinancialDocument) -> bool:
        return not document.review_required and bool(document.fields.get("invoice_number"))

    def export(self, document: FinancialDocument) -> AdapterResult:
        return self.export_many([document], filename=f"winton-import-{document.document_id or 'document'}.csv")

    def export_many(
        self,
        documents: list[FinancialDocument],
        *,
        filename: str = "winton-import-batch.csv",
    ) -> AdapterResult:
        if not documents:
            raise ValueError("no financial documents supplied")
        for document in documents:
            require_review_free(document)
            if not document.fields.get("invoice_number"):
                raise ValueError(f"invoice number required for {document.document_id}")

        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=self.profile.delimiter)
        keys = [key for key in DEFAULT_COLUMNS if key in self.profile.column_map]
        writer.writerow([self.profile.column_map[key] for key in keys])
        for document in documents:
            fields = dict(document.fields)
            writer.writerow([fields.get(key, "") for key in keys])

        data = "\ufeff" + output.getvalue()
        return AdapterResult(
            adapter_id=self.adapter_id,
            payload=data.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            filename=filename,
            warnings=(
                "generic Winton interchange profile; verify against the customer's actual import template",
            ),
            requires_manual_import=True,
        )
