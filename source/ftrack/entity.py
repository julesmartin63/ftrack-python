# :coding: utf-8
# :copyright: Copyright (c) 2014 ftrack

import sys
import abc
import uuid
import collections
import logging

import ftrack.symbol
import ftrack.attribute
import ftrack.inspection


def class_factory(schema):
    '''Create entity class from *schema*.'''
    class_name = schema['title']
    class_bases = schema.get('bases', list())
    if not class_bases:
        class_bases = [Entity]

    class_namespace = dict()

    # Build attributes for class.
    attributes = ftrack.attribute.Attributes()
    for name, fragment in schema.get('properties', {}).items():

        default = fragment.get('default', ftrack.symbol.NOT_SET)
        if default == '{uid}':
            default = lambda instance: str(uuid.uuid4())

        data_type = fragment.get('type', ftrack.symbol.NOT_SET)

        if data_type is not ftrack.symbol.NOT_SET:
            if data_type in ('string', 'boolean', 'integer', 'float'):
                attribute = ftrack.attribute.ScalarAttribute(
                    name, data_type=data_type, default_value=default
                )
                attributes.add(attribute)

    class_namespace['schema'] = schema
    class_namespace['attributes'] = attributes

    cls = type(
        class_name,
        tuple(class_bases),
        class_namespace
    )

    return cls


class DynamicEntityTypeMetaclass(abc.ABCMeta):
    '''Custom metaclass to customise representation of dynamic classes.

    .. note::

        Derive from same metaclass as derived bases to avoid conflicts.

    '''
    def __repr__(self):
        '''Return representation of class.'''
        return '<dynamic ftrack class \'{0}\'>'.format(self.__name__)


class Entity(collections.MutableMapping):
    '''Base class for all entities.'''

    __metaclass__ = DynamicEntityTypeMetaclass

    schema = None
    attributes = None

    def __init__(self, session, data=None, reconstructing=False):
        '''Initialise entity.'''
        super(Entity, self).__init__()
        self.logger = logging.getLogger(
            __name__ + '.' + self.__class__.__name__
        )
        self.session = session

        if data is None:
            data = {}

        if not reconstructing:
            # Mark as newly created for later commit.
            # Done here so that entity has correct state, otherwise would
            # receive a state of "modified" following setting of attribute
            # values from *data*.
            self.session.set_state(self, 'created')

            # Data represents locally set values.
            for key, value in data.items():
                attribute = self.__class__.attributes.get(key)
                if attribute is None:
                    self.logger.debug(
                        'Cannot populate {0!r} attribute as no such attribute '
                        'found on entity {1!r}.'.format(key, self)
                    )
                    continue

                attribute.set_local_value(self, value)

            # Set defaults for any unset local attributes.
            for attribute in self.__class__.attributes:
                if not attribute.name in data:
                    default_value = attribute.default_value
                    if callable(default_value):
                        default_value = default_value(self)

                    attribute.set_local_value(self, default_value)

        else:
            # Data represents remote values.
            for key, value in data.items():
                attribute = self.__class__.attributes.get(key)
                if attribute is None:
                    self.logger.debug(
                        'Cannot populate {0!r} attribute as no such attribute '
                        'found on entity {1!r}.'.format(key, self)
                    )
                    continue

                attribute.set_remote_value(self, value)

        # Assert that primary key is set. Suspend auto populate temporarily to
        # avoid infinite recursion if primary key values are not present.
        with self.session.auto_populating(False):
            ftrack.inspection.primary_key(self)

    def __repr__(self):
        '''Return representation of instance.'''
        return '<dynamic ftrack {0} object at {1:#0{2}x}>'.format(
            self.__class__.__name__, id(self),
            '18' if sys.maxsize > 2**32 else '10'
        )

    def __getitem__(self, key):
        '''Return attribute value for *key*.'''
        attribute = self.__class__.attributes.get(key)
        if attribute is None:
            raise KeyError(key)

        return attribute.get_value(self)

    def __setitem__(self, key, value):
        '''Set attribute *value* for *key*.'''
        attribute = self.__class__.attributes.get(key)
        if attribute is None:
            raise KeyError(key)

        attribute.set_local_value(self, value)

    def __delitem__(self, key):
        '''Clear attribute value for *key*.

        .. note::

            Will not remove the attribute, but instead clear any local value
            and revert to the last known server value.

        '''
        attribute = self.__class__.attributes.get(key)
        attribute.set_local_value(self, ftrack.symbol.NOT_SET)

    def __iter__(self):
        '''Iterate over all attributes keys.'''
        for attribute in self.__class__.attributes:
            yield attribute.name

    def __len__(self):
        '''Return count of attributes.'''
        return len(self.__class__.attributes)

    def values(self):
        '''Return list of values.'''
        # Optimisation: Populate all missing attributes in one query.
        if self.session.auto_populate:
            self._populate_unset_remote_values()

        return super(Entity, self).values()

    def items(self):
        '''Return list of tuples of (key, value) pairs.

        .. note::

            Will fetch all values from the server if not already fetched or set
            locally.

        '''
        # Optimisation: Populate all missing attributes in one query.
        if self.session.auto_populate:
            self._populate_unset_remote_values()

        return super(Entity, self).items()

    def _populate_unset_remote_values(self):
        '''Populate all unset remote values in one query.'''
        projections = []
        for attribute in self.attributes:
            if attribute.get_remote_value(self) is ftrack.symbol.NOT_SET:
                projections.append(attribute.name)

        if projections:
            self.session.populate([self], ','.join(projections))
