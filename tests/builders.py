"""Hand-built traces: pay ann@x.com 5 on Venmo, then settle Splitwise expense 77 with that payment.

gold:           login, pay ann (txn 201), settle 77 with 201.
persistent:     login, pay bob (txn 101, wrong), settle 77 with 101, refund 101, pay ann (txn 201).
                Expense 77 still points at the refunded payment: stale.
nonpersistent:  login, pay bob (txn 101, wrong), settle 77 with 101. No repair.
clean:          persistent plus re-settling 77 with 201. Matches gold.
"""
from rdr.trace import Call, Trace, Write

INSTRUCTION = "Pay ann@x.com 5 on Venmo and mark Splitwise expense 77 as settled with that payment."
EXP77_BASE = {"settled": False, "payment_ref": None}


def _login():
    return Call(0, "venmo", "login", {"username": "me"}, {"access_token": "tok-abc"})


def _pay(index, receiver, txn_id):
    row = {"receiver": receiver, "amount": 5, "status": "completed"}
    return Call(index, "venmo", "send_money", {"receiver": receiver, "amount": 5},
                {"transaction_id": txn_id}, [Write(f"venmo.transactions#{txn_id}", None, row)])


def _settle(index, before, ref):
    return Call(index, "splitwise", "settle_expense", {"expense_id": 77, "payment_ref": ref}, {"ok": True},
                [Write("splitwise.expenses#77", before, {"settled": True, "payment_ref": ref})])


def _refund(index, txn_id, receiver):
    before = {"receiver": receiver, "amount": 5, "status": "completed"}
    after = {"receiver": receiver, "amount": 5, "status": "refunded"}
    return Call(index, "venmo", "refund", {"transaction_id": txn_id}, {"status": "refunded"},
                [Write(f"venmo.transactions#{txn_id}", before, after)])


def gold_trace():
    return Trace("t1", INSTRUCTION, "Paid and settled.",
                 [_login(), _pay(1, "ann@x.com", 201), _settle(2, EXP77_BASE, 201)])


def persistent_trace():
    return Trace("t1", INSTRUCTION, "Paid and settled.",
                 [_login(), _pay(1, "bob@x.com", 101), _settle(2, EXP77_BASE, 101),
                  _refund(3, 101, "bob@x.com"), _pay(4, "ann@x.com", 201)])


def nonpersistent_trace():
    return Trace("t1", INSTRUCTION, "Paid and settled.",
                 [_login(), _pay(1, "bob@x.com", 101), _settle(2, EXP77_BASE, 101)])


def clean_trace():
    trace = persistent_trace()
    trace.calls.append(_settle(5, {"settled": True, "payment_ref": 101}, 201))
    return trace
