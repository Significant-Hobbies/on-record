--> Claims may be useful and fully transcript-backed even when the transcript
--> does not identify which participant said them. Keep that uncertainty
--> explicit instead of inventing a person or discarding the evidence.
ALTER TABLE `claims` ADD `attribution_status` text NOT NULL DEFAULT 'verified_speaker';
