# Templyfier v102 - family-name consolidation

- Rows with the same normalised `Item family` name and study stage are consolidated into one family.
- Historical technical group identifiers can no longer split one visible family into several blocks.
- Consolidated families receive one coherent internal identifier and one contiguous position in the question order and Excel output.
- If the same family was assigned to several sections, Templyfier keeps the majority section and gathers every item there.
- Different family names remain separate even when rows are adjacent.
- The v101 safety rule remains: an ordinary cell edit changes one row only; propagation requires explicit **Edit together** selection.

