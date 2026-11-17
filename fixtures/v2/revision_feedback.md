The first disposable AppWorld execution did not run because AppWorld disallows importing `decimal`.
Remove that import and use only AppWorld-safe standard modules already permitted by the task environment.

The deterministic evaluator also requires these task semantics exactly:

- An unmatched exact-email lookup is labelled `invoice_skipped_no_exact_venmo_match`.
- The supervisor answer contains exactly the count fragment
  `created=<n>, skipped=<n>, already_processed=<n>`.
- Each inbox thread represents one source message. Process only the newest incoming message from someone other
  than the supervisor, so a reply or another matching-subject email cannot be processed as a second invoice.
- If either the receipt or exact payment request already exists, create neither a missing counterpart nor a
  confirmation; label/read the thread and count it as already processed.

Revise only `solution.py`, then run a syntax-only check. Do not execute AppWorld and do not access the network.
