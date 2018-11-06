# :coding: utf-8
# :copyright: Copyright (c) 2016 ftrack

from builtins import object


class LazyLogMessage(object):
    '''A log message that can be evaluated lazily for improved performance.

    Example::

        # Formatting of string will not occur unless debug logging enabled.
        logger.debug(LazyLogMessage(
            'Hello {0}', 'world'
        ))

    '''

    def __init__(self, message, *args, **kwargs):
        '''Initialise with *message* format string and arguments.'''
        self.message = message
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        '''Return string representation.'''
        return self.message.format(*self.args, **self.kwargs)

