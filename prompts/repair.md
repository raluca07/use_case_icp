Repair only the supplied failed or suspect pipeline scope. Make the smallest source
change that addresses the cited issue. Return a replacement Python pipeline bundle;
the workflow will calculate and persist the actual diff and reject unchanged output or
changes outside the selected scope. Do not redesign or replace the complete pipeline.
Do not execute it. Preserve clear stage names and follow the response schema exactly.

The context contains `repair_target`. Change only its selected source scope:

- `faulty_node` means only the identified statement may change.
- `boundary` means only the identified function may change.
- `module_fallback` means the captured function could not be mapped to source, so only the identified entry module may change.

Preserve all files, the entry file, declared review boundaries, and source outside that scope exactly. The replacement will be rejected mechanically if it changes anything else.

For `market_demand`, improve the underlying marketing-research method as well as the implementation. Do not merely reduce the Etiq graph, suppress capture, change data types to hide graph growth, or replace weak evidence with unsupported claims. Address repeated processing, low-value sentence-level mechanics, invalid demand inference, and the review findings supplied in context.
