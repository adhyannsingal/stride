"""Demonstration thresholds only; no walking-safety inference or distance fusion."""


def classify(distance_cm, declared_valid, sensor_status, previous, settings):
    if not declared_valid:
        return "unknown", False, "measurement_invalid"
    if distance_cm is None:
        return "unknown", False, "missing_distance"
    if sensor_status not in (None, "ok", "valid"):
        return "unknown", False, "sensor_error"
    if not settings.sensor_min_cm <= distance_cm <= settings.sensor_max_cm:
        return "unknown", False, "out_of_range"
    if distance_cm <= settings.obstacle_danger_cm:
        return "danger", True, None
    if previous == "danger" and distance_cm <= settings.obstacle_danger_cm + settings.obstacle_hysteresis_cm:
        return "danger", True, None
    if distance_cm <= settings.obstacle_caution_cm:
        return "caution", True, None
    if previous in {"danger", "caution"} and distance_cm <= settings.obstacle_caution_cm + settings.obstacle_hysteresis_cm:
        return "caution", True, None
    return "clear", True, None
