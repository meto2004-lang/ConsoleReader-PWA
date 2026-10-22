"""محركات وحساسات وهمية تُعيد قراءات قابلة للضبط."""


class Motor:
    def __init__(self, *args, **kwargs):
        self.stopped = 0

    def stop(self):
        self.stopped += 1


class ColorSensor:
    def __init__(self, *args, **kwargs):
        self.reflection_value = 90

    def color(self):
        return None

    def reflection(self):
        return self.reflection_value

    def ambient(self):
        return 0

    def hsv(self):
        return (0, 0, 0)
