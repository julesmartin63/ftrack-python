# :coding: utf-8
# :copyright: Copyright (c) 2014 ftrack

import sys
import traceback


class Error(Exception):
    '''ftrack specific error.'''

    default_message = 'Unspecified error occurred.'

    def __init__(self, message=None, details=None, **kw):
        '''Initialise exception with *message*.

        If *message* is None, the class 'default_message' will be used.

        '''
        if message is None:
            message = self.default_message

        self.message = message
        self.details = details
        self.traceback = traceback.format_exc()

    def __str__(self):
        '''Return string representation.'''
        keys = {}
        for key, value in self.__dict__.iteritems():
            if isinstance(value, unicode):
                value = value.encode(sys.getfilesystemencoding())
            keys[key] = value

        return str(self.message.format(**keys))


class AuthenticationError(Error):
    '''Raise when an authentication error occurs.'''

    default_message = 'Authentication error.'


class ServerError(Error):
    '''Raise when the server reports an error.'''

    default_message = 'Server reported error processing request.'


class NotFoundError(Error):
    '''Raise when something that should exist is not found.'''

    default_message = 'Not found.'


class NotUniqueError(Error):
    '''Raise when unique value required and duplicate detected.'''

    default_message = 'Non-unique value detected.'


class EntityTypeError(Error):
    '''Raise when an entity type error occurs.'''

    default_message = 'Entity type error.'


class UnrecognisedEntityTypeError(EntityTypeError):
    '''Raise when an unrecognised entity type detected.'''

    default_message = 'Entity type "{entity_type}" not recognised.'

    def __init__(self, entity_type, **kw):
        '''Initialise with *entity_type* that is unrecognised.'''
        self.entity_type = entity_type
        super(UnrecognisedEntityTypeError, self).__init__(**kw)


class InvalidStateError(Error):
    '''Raise when an invalid state detected.'''

    default_message = 'Invalid state.'


class InvalidStateTransitionError(InvalidStateError):
    '''Raise when an invalid state transition detected.'''

    default_message = (
        'Invalid transition from {current_state!r} to {target_state!r} state '
        'for entity {entity!r}'
    )

    def __init__(self, current_state, target_state, entity, **kw):
        '''Initialise error.'''
        self.current_state = current_state
        self.target_state = target_state
        self.entity = entity
        super(InvalidStateTransitionError, self).__init__(**kw)


class AttributeError(Error):
    '''Raise when an error related to an attribute occurs.'''

    default_message = 'Attribute error.'


class ImmutableAttributeError(AttributeError):
    '''Raise when modification of immutable attribute attempted.'''

    default_message = (
        'Cannot modify value of immutable {attribute.name!r} attribute.'
    )

    def __init__(self, attribute, **kw):
        '''Initialise error.'''
        self.attribute = attribute
        super(ImmutableAttributeError, self).__init__(**kw)


class CollectionError(Error):
    '''Raise when an error related to collections occurs.'''

    default_message = 'Collection error.'

    def __init__(self, collection, **kw):
        '''Initialise error.'''
        self.collection = collection
        super(CollectionError, self).__init__(**kw)


class ImmutableCollectionError(CollectionError):
    '''Raise when modification of immutable collection attempted.'''

    default_message = (
        'Cannot modify value of immutable collection {collection!r}.'
    )


class DuplicateItemInCollectionError(CollectionError):
    '''Raise when duplicate item in collection detected.'''

    default_message = (
        'Item {item!r} already exists in collection {collection!r}.'
    )

    def __init__(self, item, collection, **kw):
        '''Initialise error.'''
        self.item = item
        super(DuplicateItemInCollectionError, self).__init__(collection, **kw)


class ParseError(Error):
    '''Raise when a parsing error occurs.'''

    default_message = 'Failed to parse.'


class EventHubError(Error):
    '''Raise when issues related to event hub occur.'''

    default_message = 'Event hub error occurred.'


class EventHubConnectionError(EventHubError):
    '''Raise when event hub encounters connection problem.'''

    default_message = 'Event hub is not connected.'


class EventHubPacketError(EventHubError):
    '''Raise when event hub encounters an issue with a packet.'''

    default_message = 'Invalid packet.'


class AccessorError(Error):
    '''Base for errors associated with accessors.'''

    defaultMessage = 'Unspecified accessor error'


class AccessorOperationFailedError(AccessorError):
    '''Base for failed operations on accessors.'''

    defaultMessage = 'Operation {operation} failed: {details}'

    def __init__(self, operation='', resource_identifier=None, **kw):
        self.operation = operation
        self.resource_identifier = resource_identifier
        super(AccessorOperationFailedError, self).__init__(**kw)


class AccessorUnsupportedOperationError(AccessorOperationFailedError):
    '''Raise when operation is unsupported.'''

    defaultMessage = 'Operation {operation} unsupported.'


class AccessorPermissionDeniedError(AccessorOperationFailedError):
    '''Raise when permission denied.'''

    defaultMessage = ('Cannot {operation} {resource_identifier}. '
                      'Permission denied.')


class AccessorResourceIdentifierError(AccessorError):
    '''Raise when a error related to a resource_identifier occurs.'''

    defaultMessage = 'Resource identifier is invalid: {resource_identifier}.'

    def __init__(self, resource_identifier, **kw):
        self.resource_identifier = resource_identifier
        super(AccessorResourceIdentifierError, self).__init__(**kw)


class AccessorFilesystemPathError(AccessorResourceIdentifierError):
    '''Raise when a error related to an accessor filesystem path occurs.'''

    defaultMessage = ('Could not determine filesystem path from resource '
                      'identifier: {resource_identifier}.')


class AccessorResourceError(AccessorError):
    '''Base for errors associated with specific resource.'''

    defaultMessage = 'Unspecified resource error: {resource_identifier}'

    def __init__(self, resource_identifier, **kw):
        self.resource_identifier = resource_identifier
        super(AccessorResourceError, self).__init__(**kw)


class AccessorResourceNotFoundError(AccessorResourceError):
    '''Raise when a required resource is not found.'''

    defaultMessage = 'Resource not found: {resource_identifier}'


class AccessorParentResourceNotFoundError(AccessorResourceError):
    '''Raise when a parent resource (such as directory) is not found.'''

    defaultMessage = 'Parent resource is missing: {resource_identifier}'


class AccessorResourceInvalidError(AccessorResourceError):
    '''Raise when a resource is not the right type.'''

    defaultMessage = 'Resource invalid: {resource_identifier}'


class AccessorContainerNotEmptyError(AccessorResourceError):
    '''Raise when container is not empty.'''

    defaultMessage = 'Container is not empty: {resource_identifier}'
