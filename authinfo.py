import os

DEFAULT_NETRC = os.path.expanduser('~/.authinfo')

class AuthInfo(object):
    def __init__(self, user, password):
        self.user = user
        self.password = password

    @staticmethod
    def from_netrc(machine, netrc = DEFAULT_NETRC):
        with open(netrc) as f:
            for line in f:
                split = line.split()
                keys = (k for i, k in enumerate(split) if i % 2 == 0)
                vals = (v for i, v in enumerate(split) if i % 2 == 1)
                info = dict(zip(keys, vals))

                if info['machine'] == machine:
                    return AuthInfo(info['login'], info['password'])
