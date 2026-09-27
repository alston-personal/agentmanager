# Financial Intake Plugin

This capability deliberately does **not** compete with ERP/accounting suites.

Its role is to sit in front of systems such as 文中資訊, 鼎新, 正航, Excel or a
custom accounting API:

```
paper / camera / PDF / email
        ↓
document.financial-intake
        ↓
classify → extract → validate → deduplicate → review only exceptions
        ↓
financial-document.normalized/v1
        ↓
accounting adapter
        ├─ Winton
        ├─ Excel / CSV
        ├─ generic API
        └─ future ERP plugins
```

## Product boundary

Financial Intake owns capture, OCR, document understanding, validation, evidence
and normalized output. It does **not** own general ledger, tax filing, payroll,
inventory, ERP master data or statutory accounting behavior.

That boundary is intentional: users keep their existing system of record.

## Winton first adapter

Public Winton materials document a "轉檔工具" and Excel-based import workflows.
The initial adapter therefore targets a **profile-driven interchange file**, not
an undocumented/private API.

The generic profile is only a contract skeleton. Before production use for a
specific customer, obtain one real Winton import template/export sample and add a
versioned mapping profile. Do not hard-code customer column layouts in OCR code.

## Adoption metric

Do not optimize only OCR accuracy. The primary product metric is:

**manual re-keying eliminated per document**

Secondary metrics:
- exception/review rate
- time from capture to ERP-ready payload
- duplicate prevention rate
- adapter import success rate
- unsafe auto-post rate (target: 0)
