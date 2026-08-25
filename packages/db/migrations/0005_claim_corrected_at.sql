--> When a claim was retracted. The ledger is append-only and corrections are
--> part of the record: a reader should be able to see that a claim was
--> withdrawn and when, not just find it missing.
ALTER TABLE `claims` ADD `corrected_at` integer;
