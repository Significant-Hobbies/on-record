--> Segment text and cue maps move to R2. The column stays: dropping it needs a
--> table rebuild, and claims.segment_id references segments, so D1 rolls the
--> whole migration back on the foreign key check. An emptied column costs
--> nothing, and the point was never the schema — it was the ~400MB of
--> transcript text that 2,600 episodes would otherwise put in D1.
UPDATE `segments` SET `text` = '', `cue_map` = NULL;
