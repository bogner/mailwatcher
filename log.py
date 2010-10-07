import sys

LOG_LEVELS = ["error", "debug", "info"]

def set_level(level):
    if level not in LOG_LEVELS:
        raise Exception("unknown level: %s" % level)
    Logger.get_instance().set_level(level)

class Singleton(object):
    instance = None

    @classmethod
    def get_instance(this_class):
        if not this_class.instance:
            this_class.instance = this_class()
        return this_class.instance

class Logger(Singleton):
    def __init__(self):
        self.level = 0

    def set_level(self, level):
        self.level = self.parse_level(level)

    def parse_level(self, level):
        if level in LOG_LEVELS:
            return LOG_LEVELS.index(level)
        return int(level)

    def log(self, level, message):
        if self.parse_level(level) <= self.level:
            sys.stderr.write(message + "\n")

    def __getattr__(self, level):
        return lambda message: self.log(level, message)

for level in LOG_LEVELS:
    globals()[level] = getattr(Logger.get_instance(), level)
