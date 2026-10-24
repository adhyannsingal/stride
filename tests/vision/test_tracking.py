from app.vision.model import Detection
from app.vision.tracking import Tracker


def test_track_ids_stability_change_cooldown_and_lost_track_reset():
    tracker = Tracker()
    left = [Detection('chair',.9,(0,.1,.3,.5))]
    a,event = tracker.update(left,10000)
    assert event is None
    b,event = tracker.update(left,10200)
    assert a[0]['track_id']==b[0]['track_id'] and event
    for now in [10400,10600,10800]:
        assert tracker.update(left,now)[1] is None
    tracker.update([],11000)
    new,event = tracker.update(left,11200)
    assert new[0]['track_id'] != a[0]['track_id'] and event is None
    assert tracker.update(left,11400)[1] is None  # per-position cooldown survives ID loss
    assert tracker.update(left,12200)[1] is None
    assert tracker.update(left,13000)[1] is None
    assert tracker.update(left,13400)[1] is not None
