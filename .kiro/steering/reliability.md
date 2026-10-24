---
inclusion: always
---
# Reliability rules

1. Bound work. Keep only the newest pending image and at most one in-flight browser upload. Expire stale output; do not relax freshness to conceal a slow model.
2. Preserve identity. Session, device, boot, sequence, frame, receipt, source revision and vision generation determine whether a result is current. Reject duplicate/regressing inputs and obsolete publications.
3. Preserve user control. Confirm advances exactly one checkpoint; Repeat never advances. Pause retains progress. Stop cancels local activity immediately and reports any unconfirmed server operation.
4. Keep navigation authoritative on the backend. Check route IDs, navigation ownership and expected revisions. Recover state after conflicts. Never replay a lost confirmation as a new action.
5. Prioritize feedback: danger, fault, route, observation, informational audio. Bound and deduplicate speech, recheck expiry and validity while queued and speaking, and invalidate callbacks before cancellation.
6. Treat missing, invalid and stale sensor data as unknown. Caution/danger/unknown holds must not be overridden by old clear readings. Recovery returns blocked routes to paused and requires explicit resume.
7. Haptic commands are identified, bounded, short-lived and acknowledged. Stop/cancel preempt turns; reboot/link-loss handling must not revive old commands. Local ESP32 alerting does not depend on HTTP or inference.
8. Browser camera use requires explicit interaction, consent and a dedicated single-producer development session. Viewer/glasses modes do not open browser media. Do not claim server producer ownership exists without an implemented API.
9. Historical sightings retain their timestamps and source. They never become a current detection merely because memory was queried again.
10. Test software with labeled fixtures. Distinguish automated assertions from actual webcam, model, phone, audio, motor and route acceptance.
