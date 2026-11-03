"""Single source of truth for hardware wiring and the ServoBus abstraction.

Modes (see modes/) import LEGS and ServoBus from here. Add a new leg's channels
once wired — all downstream code picks it up without changes.

The real `AdafruitServoBus` imports only when adafruit-circuitpython-servokit is
installed (the Pi). On a dev machine the import fails silently and `default_bus()`
returns a `FakeServoBus` — safe to run routes without hardware."""


LEGS = {
    'front-left':  {'knee': None, 'thigh': None},
    'front-right': {'knee': 0, 'thigh': 2},
    'back-left':   {'knee': None, 'thigh': None},
    'back-right':  {'knee': None, 'thigh': None},
}

ANGLE_RANGE = (-90, 90)
PULSE_WIDTH_RANGE = (500, 2500)


class ServoBus:
    def set_angle(self, channel, angle):
        raise NotImplementedError

    def release(self, channel):
        raise NotImplementedError


class FakeServoBus(ServoBus):
    def __init__(self):
        self.calls = []
        self.positions = {}

    def set_angle(self, channel, angle):
        self.calls.append(('set', channel, angle))
        self.positions[channel] = angle

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
            self._kit.servo[channel].angle = 90 + angle

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
