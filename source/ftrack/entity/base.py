# :coding: utf-8
# :copyright: Copyright (c) 2014 ftrack

import sys
import abc
import collections
import logging

import ftrack.symbol
import ftrack.attribute


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

    entity_type = 'Entity'
    attributes = None
    primary_key_attributes = None
    default_projections = None

    def __init__(self, session, data=None, reconstructing=False):
        '''Initialise entity.

        *session* is an instance of :class:`ftrack.session.Session` that this
        entity instance is bound to.

        *data* is a mapping of key, value pairs to apply as initial attribute
        values.

        *reconstructing* indicates whether this entity is being reconstructed,
        such as from a query, and therefore should not have any special creation
        logic applied, such as initialising defaults for missing data.

        '''
        super(Entity, self).__init__()
        self.logger = logging.getLogger(
            __name__ + '.' + self.__class__.__name__
        )
        self.session = session

        if data is None:
            data = {}

        self.logger.debug(
            '{0} entity from {1!r}.'
            .format(
                ('Reconstructing' if reconstructing else 'Constructing'),
                data
            )
        )

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
            self.primary_key

    def __repr__(self):
        '''Return representation of instance.'''
        return '<dynamic ftrack {0} object at {1:#0{2}x}>'.format(
            self.__class__.__name__, id(self),
            '18' if sys.maxsize > 2**32 else '10'
        )

    def __hash__(self):
        '''Return hash representing instance.'''
        return hash(self.identity)

    def __eq__(self, other):
        '''Return whether *other* is equal to this instance.

        .. note::

            Equality is determined by both instances having the same identity.
            Values of attributes are not considered.

        '''
        return other.identity == self.identity

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

    @property
    def identity(self):
        '''Return unique identity.'''
        return (
            self.entity_type,
            self.primary_key.values()
        )

    @property
    def primary_key(self):
        '''Return primary key as an ordered mapping of {field: value}.

        To get just the primary key values::

            entity.primary_key.values()

        '''
        primary_key = collections.OrderedDict()
        for name in self.primary_key_attributes:
            value = self[name]
            if value is ftrack.symbol.NOT_SET:
                raise KeyError(
                    'Missing required value for primary key attribute "{0}" on '
                    'entity {1}.'.format(name, self)
                )

            primary_key[str(name)] = str(value)

        return primary_key

    def values(self):
        '''Return list of values.'''
        if self.session.auto_populate:
            self._populate_unset_scalar_attributes()

        return super(Entity, self).values()

    def items(self):
        '''Return list of tuples of (key, value) pairs.

        .. note::

            Will fetch all values from the server if not already fetched or set
            locally.

        '''
        if self.session.auto_populate:
            self._populate_unset_scalar_attributes()

        return super(Entity, self).items()

    def clear(self):
        '''Reset all locally modified attribute values.'''
        for attribute in self:
            del self[attribute]

    def _populate_unset_scalar_attributes(self):
        '''Populate all unset scalar attributes in one query.'''
        projections = []
        for attribute in self.attributes:
            if isinstance(attribute, ftrack.attribute.ScalarAttribute):
                if attribute.get_remote_value(self) is ftrack.symbol.NOT_SET:
                    projections.append(attribute.name)

        if projections:
            self.session.populate([self], ', '.join(projections))
