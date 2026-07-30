Repair only the supplied source scope. Make the smallest change that addresses the
cited review issue without redesigning the pipeline.

The context contains the evidence package seen by this isolated branch, the review
findings, the exact repair target, and `selected_source`. Return the complete
replacement text for `selected_source` only. Do not return a file bundle and do not
change source outside that scope. Do not execute the pipeline.

This is a frozen-corpus experiment. Do not change request URLs, search queries,
request counts, source endpoints, or network-call construction. Improve source
admission, filtering, extraction, validation, or inference using the recorded
documents. A replacement that requests unrecorded network evidence is invalid.

For `market_demand`, correct the evidence or inference problem itself. Do not hide
Etiq capture, suppress graph nodes, or replace weak evidence with unsupported claims.
Follow the response schema exactly.
