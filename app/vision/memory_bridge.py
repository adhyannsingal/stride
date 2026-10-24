"""Opt-in stable-track memory recording, independent of the inference worker."""
import asyncio


class StableMemoryBridge:
    def __init__(self, detector, memory, store, interval=.2):
        self.detector,self.memory,self.store=detector,memory,store
        self.interval=interval
        self.task=None
        self.recorded={}  # At most max_sightings_per_session keys per bounded session.
        self.saved=0
        self.failures=0

    async def start(self):
        if self.task is None or self.task.done():
            self.task=asyncio.create_task(self._run(),name='stride-stable-memory')

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
            self.task=None
        self.recorded.clear()

    async def tick(self):
        # Snapshot retrieval is nonblocking; a busy model simply defers this poll.
        for meta,generation,confirmed in self.detector.memory_candidates():
            if not confirmed: continue
            batch=self.store.latest_detections(meta.session_id)
            if batch is None or batch.frame!=meta: continue
            state=self.store.snapshot(meta.session_id)
            if state.status!='live' or state.generation!=generation: continue
            identity=(generation,meta.source_revision,meta.device_id,meta.boot_id)
            old=self.recorded.get(meta.session_id)
            ledger=old[1] if old and old[0]==identity else {}
            self.recorded[meta.session_id]=(identity,ledger)
            cooldown=self.memory.settings.sighting_cooldown_ms
            ids=tuple(track for track in confirmed
                      if track not in ledger or meta.received_ms-ledger[track]>=cooldown)[:16]
            if not ids: continue
            try:
                outcome=await self.memory.record_sightings(session_id=meta.session_id,batch=batch,track_ids=ids)
                if outcome.error:
                    self.failures+=1
                    continue
                self.saved+=outcome.saved
                for track in ids: ledger[track]=meta.received_ms
                while len(ledger)>self.memory.settings.max_sightings_per_session:
                    del ledger[next(iter(ledger))]
            except Exception:
                # Stale/replaced publications and DB faults must not stop vision.
                self.failures+=1

    async def _run(self):
        while True:
            await self.tick()
            await asyncio.sleep(self.interval)
