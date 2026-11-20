from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    report_id: int


def make_receipt(report_id):
    return Receipt(f'receipt-{report_id}', report_id)


def decode_receipt(receipt_id, report_id):
    return Receipt(receipt_id, report_id)
