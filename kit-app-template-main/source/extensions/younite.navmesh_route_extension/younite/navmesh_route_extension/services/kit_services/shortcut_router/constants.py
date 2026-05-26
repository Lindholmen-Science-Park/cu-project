"""Tuning constants for shortcut hop cost and elevator vertical filters."""

# Travel-time budget mapped onto Dijkstra "distance" units (cm) so a
# shortcut hop competes with raw walking length on the same scale.
DEFAULT_WALK_CM_PER_SEC = 130.0

# Reject elevator exits that are clearly the wrong vertical move (e.g.
# ride section-A lift down to basement then walk back up past the start
# to a same-tier seat).  Stage units = cm.
ELEVATOR_GOAL_DY_CM = 80.0
# Wrong-way vs **start** (rode opposite to net goal vs player).
ELEVATOR_BACKTRACK_DY_CM = 450.0
# For small |start→end| vertical span: reject exits far below/above *both*
# endpoints (e.g. basement when start and seat are both concourse).
ELEVATOR_SAME_BAND_SPAN_CM = 900.0
ELEVATOR_BASEMENT_DIP_BELOW_LOW_CM = 280.0
# For non-section destinations (POIs, generic positions): "destination
# must be on this floor" threshold used in prefer mode.
ELEVATOR_EXIT_TO_DEST_MAX_CM = 100.0

# Optional margin allowing the lift to beat direct walking by this
# fraction. Default 0.0 → strict shortest.
SHORTCUT_SLACK_FRACTION = 0.0

LOG_PREFIX = "[shortcut_router]"
