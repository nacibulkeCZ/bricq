"""Single source of truth for hardware wiring and the ServoBus abstraction.

Modes (see modes/) import LEGS and ServoBus from here. Add a new leg's channels
once wired — all downstream code picks it up without changes.

The real `AdafruitServoBus` imports only when adafruit-circuitpython-servokit is
installed (the Pi). On a dev machine the import fails silently and `default_bus()`
returns a `FakeServoBus` — safe to run routes without hardware."""


LEGS = {
    'front-left':  {'knee': 13, 'thigh': 15},
    'front-right': {'knee': 2,  'thigh': 0},
    'back-left':   {'knee': 9,  'thigh': 11},
    'back-right':  {'knee': 6,  'thigh': 4},
}

# Left-side servos face the opposite direction from the right, so the same
# commanded body angle needs an inverted servo command on the left.
LEG_SIGNS = {
    'front-left':  -1,
    'back-left':   -1,
    'front-right': +1,
    'back-right':  +1,
}

# Whole-body crouch that holds the robot stably on four feet. Tuned live in
# `bricq stand`. Walk-style modes should oscillate around this pose, not zero.
STAND_POSE = {'thigh': 62, 'knee': 60}

# Per-channel calibration offset in degrees, applied inside ServoBus.set_angle.
# Compensates for however the servo horn landed when you screwed it in: a
# commanded 0° reaches the same physical joint position across all 8 servos.
# Tune live in `bricq calibrate`.
SERVO_TRIMS = {0: 0, 2: 0, 4: 0, 6: 0, 9: 0, 11: 0, 13: 0, 15: 0}

ANGLE_RANGE = (-90, 90)
PULSE_WIDTH_RANGE = (500, 2500)


class ServoBus:
    def set_angle(self, channel, angle):
        raise NotImplementedError

    def release(self, channel):
        raise NotImplementedError


def _trimmed(channel, angle):
    """Apply per-channel trim and clamp to the servo's commandable range."""
    lo, hi = ANGLE_RANGE
    return max(lo, min(hi, angle + SERVO_TRIMS.get(channel, 0)))


class FakeServoBus(ServoBus):
    def __init__(self):
        self.calls = []
        self.positions = {}

    def set_angle(self, channel, angle):
        trimmed = _trimmed(channel, angle)
        self.calls.append(('set', channel, trimmed))
        self.positions[channel] = trimmed

    def release(self, channel):
        self.calls.append(('release', channel))
        self.positions[channel] = None


try:
    from adafruit_servokit import ServoKit  # type: ignore

    class AdafruitServoBus(ServoBus):
        def __init__(self):
            self._kit = ServoKit(channels=16)
            for channel in _wired_channels():
                self._kit.servo[channel].set_pulse_width_range(*PULSE_WIDTH_RANGE)
                self._kit.servo[channel].angle = None

        def set_angle(self, channel, angle):
            self._kit.servo[channel].angle = 90 + _trimmed(channel, angle)

        def release(self, channel):
            self._kit.servo[channel].angle = None
except ImportError:
    AdafruitServoBus = None


def _wired_channels():
    return {ch for leg in LEGS.values() for ch in leg.values() if isinstance(ch, int)}


def default_bus():
    if AdafruitServoBus is None:
        return FakeServoBus()
    return AdafruitServoBus()


def resolve_leg(name):
    if name not in LEGS:
        raise ValueError('Unknown leg: ' + name + '. Available: ' + ', '.join(LEGS))
    channels = LEGS[name]
    if not all(isinstance(ch, int) for ch in channels.values()):
        raise ValueError('Leg ' + name + ' is not wired yet.')
    return dict(channels)
