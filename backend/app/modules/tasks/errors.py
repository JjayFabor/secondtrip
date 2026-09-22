"""Exceptions understood by the background-job execution boundary."""


class JobCancelled(Exception):
    pass


class PermanentJobError(Exception):
    pass
