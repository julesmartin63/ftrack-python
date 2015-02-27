# :coding: utf-8
# :copyright: Copyright (c) 2014 ftrack

import json
import logging
import collections
import datetime
import os
import getpass
import functools

import pkg_resources
import requests
import requests.auth
import arrow

import ftrack.exception
import ftrack.entity.base
import ftrack.cache
import ftrack.symbol
import ftrack.query
import ftrack.attribute
import ftrack.collection
import ftrack.event.hub
import ftrack.event.base
import ftrack.plugin
import ftrack.inspection


class SessionAuthentication(requests.auth.AuthBase):
    '''Attach ftrack session authentication information to requests.'''

    def __init__(self, api_key, api_user):
        '''Initialise with *api_key* and *api_user*.'''
        self.api_key = api_key
        self.api_user = api_user
        super(SessionAuthentication, self).__init__()

    def __call__(self, request):
        '''Modify *request* to have appropriate headers.'''
        request.headers.update({
            'ftrack-api-key': self.api_key,
            'ftrack-user': self.api_user
        })
        return request


class Session(object):
    '''An isolated session for interaction with an ftrack server.'''

    def __init__(
        self, server_url=None, api_key=None, api_user=None, auto_populate=True,
        plugin_paths=None
    ):
        '''Initialise session.

        *server_url* should be the URL of the ftrack server to connect to
        including any port number. If not specified attempt to look up from
        :envvar:`FTRACK_SERVER`.

        *api_key* should be the API key to use for authentication whilst
        *api_user* should be the username of the user in ftrack to record
        operations against. If not specified, *api_key* should be retrieved
        from :envvar:`FTRACK_API_KEY` and *api_user* from
        :envvar:`FTRACK_API_USER`.

        If *auto_populate* is True (the default), then accessing entity
        attributes will cause them to be automatically fetched from the server
        if they are not already. This flag can be changed on the session
        directly at any time.

        *plugin_paths* should be a list of paths to search for plugins. If not
        specified, default to looking up :envvar:`FTRACK_EVENT_PLUGIN_PATH`.

        '''
        super(Session, self).__init__()
        self.logger = logging.getLogger(
            __name__ + '.' + self.__class__.__name__
        )

        if server_url is None:
            server_url = os.environ.get('FTRACK_SERVER')

        if not server_url:
            raise TypeError(
                'Required "server_url" not specified. Pass as argument or set '
                'in environment variable FTRACK_SERVER.'
            )

        self._server_url = server_url

        if api_key is None:
            api_key = os.environ.get(
                'FTRACK_API_KEY',
                # Backwards compatibility
                os.environ.get('FTRACK_APIKEY')
            )

        if not api_key:
            raise TypeError(
                'Required "api_key" not specified. Pass as argument or set in '
                'environment variable FTRACK_API_KEY.'
            )

        self._api_key = api_key

        if api_user is None:
            api_user = os.environ.get('FTRACK_API_USER')
            if not api_user:
                try:
                    api_user = getpass.getuser()
                except Exception:
                    pass

        if not api_user:
            raise TypeError(
                'Required "api_user" not specified. Pass as argument, set in '
                'environment variable FTRACK_API_USER or one of the standard '
                'environment variables used by Python\'s getpass module.'
            )

        self._api_user = api_user

        self._batches = {
            'write': []
        }

        # TODO: Make cache configurable.
        self._key_maker = ftrack.cache.EntityKeyMaker()
        self._cache = ftrack.cache.MemoryCache()

        self._states = dict(
            created=collections.OrderedDict(),
            modified=collections.OrderedDict(),
            deleted=collections.OrderedDict()
        )

        self._request = requests.Session()
        self._request.auth = SessionAuthentication(
            self._api_key, self._api_user
        )

        # Construct event hub and load plugins.
        self._event_hub = ftrack.event.hub.EventHub(self._server_url)
        self._event_hub.connect()

        self._plugin_paths = plugin_paths
        if self._plugin_paths is None:
            try:
                default_plugin_path = pkg_resources.resource_filename(
                    pkg_resources.Requirement.parse('ftrack-python-api'),
                    'ftrack_default_plugins'
                )
            except pkg_resources.DistributionNotFound:
                default_plugin_path = ''

            self._plugin_paths = os.environ.get(
                'FTRACK_EVENT_PLUGIN_PATH',
                default_plugin_path
            ).split(os.pathsep)

        self._discover_plugins()

        # TODO: Make schemas read-only and non-mutable (or at least without
        # rebuilding types)?
        self.schemas = self._fetch_schemas()
        self.types = self._build_entity_type_classes(self.schemas)

        self.auto_populate = auto_populate

    @property
    def server_url(self):
        '''Return server ulr used for session.'''
        return self._server_url

    @property
    def api_user(self):
        '''Return username used for session.'''
        return self._api_user

    @property
    def api_key(self):
        '''Return API key used for session.'''
        return self._api_key

    @property
    def event_hub(self):
        '''Return event hub.'''
        return self._event_hub

    def reset(self):
        '''Reset session clearing all locally stored data.'''
        if self._states['created']:
            self.logger.warning(
                'Resetting session with pending creations not persisted.'
            )

        if self._states['modified']:
            self.logger.warning(
                'Resetting session with pending modifications not persisted.'
            )

        if self._states['deleted']:
            self.logger.warning(
                'Resetting session with pending deletions not persisted.'
            )

        self._states['created'].clear()
        self._states['modified'].clear()
        self._states['deleted'].clear()
        self._request.close()

    def auto_populating(self, auto_populate):
        '''Temporarily set auto populate to *auto_populate*.

        The current setting will be restored automatically when done.

        Example::

            with session.auto_populating(False):
                print entity['name']

        '''
        return AutoPopulatingContext(self, auto_populate)

    @property
    def created(self):
        '''Return list of newly created entities.'''
        return self._states['created'].values()

    @property
    def modified(self):
        '''Return list of locally modified entities.'''
        return self._states['modified'].values()

    @property
    def deleted(self):
        '''Return list of deleted entities.'''
        return self._states['deleted'].values()

    def set_state(self, entity, state):
        '''Set *entity* *state*.

        Transition from current state to new state.

        Raise :exc:`ftrack.exception.InvalidStateError` if new state is invalid.

        .. note::

            Transitioning from 'created' or 'deleted' to 'modified' is not an
            error, but will not change state.

        '''
        identity = id(entity)
        current_state = self.get_state(entity)

        if current_state == state:
            return

        if current_state in ('created', 'deleted'):
            if state == 'modified':
                # Not an error, but no point marking as modified.
                return

        if current_state == 'deleted':
            raise ftrack.exception.InvalidStateTransitionError(
                current_state, state, entity
            )

        if current_state == 'modified' and state != 'deleted':
            raise ftrack.exception.InvalidStateTransitionError(
                current_state, state, entity
            )

        if current_state:
            del self._states[current_state][identity]

        if state:
            self._states[state][identity] = entity

    def get_state(self, entity):
        '''Return entity *state*.'''
        identity = id(entity)
        for state, entities in self._states.iteritems():
            if identity in entities:
                return state

        return None

    def create(self, entity_type, data=None):
        '''Create and return an entity of *entity_type* with initial *data*.

        If specified, *data* should be a dictionary of key, value pairs that
        should be used to populate attributes on the entity.

        '''
        entity = self._create(entity_type, data, reconstructing=False)
        entity = self.merge(entity)
        return entity

    def _create(self, entity_type, data, reconstructing):
        '''Create and return an entity of *entity_type* with initial *data*.

        If *reconstructing* is True then will merge into any existing entity.

        '''
        try:
            EntityTypeClass = self.types[entity_type]
        except KeyError:
            raise ftrack.exception.UnrecognisedEntityTypeError(entity_type)

        return EntityTypeClass(self, data=data, reconstructing=reconstructing)

    def ensure(self, entity_type, data):
        '''Ensure entity of *entity_type* with *data* exists.'''

    def delete(self, entity):
        '''Mark *entity* for deletion.'''
        self.set_state(entity, 'deleted')

    def get(self, entity_type, entity_key):
        '''Return entity of *entity_type* with unique *entity_key*.

        If no matching entity found, return None.

        '''
        primary_key_definition = self.types[entity_type].primary_key_attributes
        if len(primary_key_definition) > 1:
            # TODO: Handle composite primary key using a syntax of
            # (pka, pkb) in ((v1a,v1b), (v2a, v2b))
            raise ValueError('Composite primary keys not supported.')

        primary_key_definition = primary_key_definition[0]
        if not isinstance(entity_key, basestring):
            entity_key = entity_key[0]

        expression = '{0} where {1} is {2}'.format(
            entity_type, primary_key_definition, entity_key
        )

        results = self.query(expression).all()
        if results:
            return results[0]
        else:
            return None

    def query(self, expression):
        '''Query against remote data according to *expression*.

        *expression* is not executed directly. Instead return an
        :class:`ftrack.query.QueryResult` instance that will execute remote
        call on access.

        '''
        # Add in sensible projections if none specified. Note that this is
        # done here rather than on the server to allow local modification of the
        # schema setting to include commonly used custom attributes for example.
        # TODO: Use a proper parser perhaps?
        if not expression.startswith('select'):
            entity_type = expression.split(' ', 1)[0]
            EntityTypeClass = self.types[entity_type]
            projections = EntityTypeClass.default_projections

            expression = 'select {0} from {1}'.format(
                ', '.join(projections),
                expression
            )

        query_result = ftrack.query.QueryResult(self, expression)
        return query_result

    def _query(self, expression):
        '''Execute *query*.'''
        # TODO: Actually support batching several queries together.
        # TODO: Should batches have unique ids to match them up later.
        batch = [{
            'action': 'query',
            'expression': expression
        }]

        # TODO: When should this execute? How to handle background=True?
        results = self._call(batch)

        # Merge entities into local cache and return merged entities.
        data = []
        for entity in results[0]['data']:
            data.append(self.merge(entity))

        return data

    def merge(self, entity, _seen=None):
        '''Merge *entity* into session returning merged entity.

        Merge is recursive so any references to other entities will also be
        merged and *entity* may be modified in place.

        '''
        merged_entity = entity

        if _seen is None:
            _seen = {}

        with self.auto_populating(False):
            # Check for existing instance of entity in cache.
            entity_key = self._key_maker.key(entity)
            try:
                existing_entity = self._cache.get(entity_key)

            except KeyError:
                # Record new instance in cache.
                self._cache.set(entity_key, entity)

            else:
                if entity is not existing_entity:
                    # Merge set attributes from entity to cache.
                    for attribute in entity.attributes:
                        value = attribute.get_remote_value(entity)
                        if value is not ftrack.symbol.NOT_SET:
                            existing_attribute = existing_entity.attributes.get(
                                attribute.name
                            )
                            existing_attribute.set_remote_value(
                                existing_entity, value
                            )

                    # Set returned entity to be existing cached instance.
                    merged_entity = existing_entity

            # Recursively merge entity references that were present in source
            # entity if not already done.
            if entity_key not in _seen:
                _seen[entity_key] = True

                for attribute in entity.attributes:
                    source_value = attribute.get_remote_value(entity)
                    if source_value is not ftrack.symbol.NOT_SET:
                        value = attribute.get_remote_value(merged_entity)

                        if isinstance(value, ftrack.entity.base.Entity):
                            attribute.set_remote_value(
                                merged_entity, self.merge(value, _seen=_seen)
                            )

                        elif isinstance(value, ftrack.collection.Collection):
                            # Temporarily make collection mutable so that
                            # entities within it can be merged.
                            mutable = value.mutable
                            value.mutable = True
                            try:
                                for index, entry in enumerate(value):
                                    value[index] = self.merge(
                                        entry, _seen=_seen
                                    )
                            finally:
                                value.mutable = mutable

                        # TODO: Handle DictionaryAttributeCollection.

        return merged_entity

    def populate(self, entities, projections, background=False):
        '''Populate *entities* with attributes specified by *projections*.

        if *background* is True make request without blocking and populate
        entities when result received.

        Any locally set values included in the *projections* will not be
        overwritten with the retrieved remote value. If this 'synchronise'
        behaviour is required, first clear the relevant values on the entity by
        setting them to :attr:`ftrack.symbol.NOT_SET`. Deleting the key will
        have the same effect::

            >>> print(user['username'])
            martin
            >>> del user['username']
            >>> print(user['username'])
            Symbol(NOT_SET)

        .. note::

            Entities that have been created and not yet persisted will be
            skipped as they have no remote values to fetch.

        '''
        if not isinstance(entities, (list, tuple, ftrack.query.QueryResult)):
            entities = [entities]

        # TODO: How to handle a mixed collection of different entity types
        # Should probably fail, but need to consider handling hierarchies such
        # as User and Group both deriving from Resource. Actually, could just
        # proceed and ignore projections that are not present in entity type.

        entities_to_process = []

        for entity in entities:
            if self.get_state(entity) == 'created':
                # Created entities that are not yet persisted have no remote
                # values. Don't raise an error here as it is reasonable to
                # iterate over an entities properties and see that some of them
                # are NOT_SET.
                continue

            entities_to_process.append(entity)

        if entities_to_process:
            # TODO: Mark attributes as 'fetching'?
            reference_entity = entities_to_process[0]
            entity_type = reference_entity.entity_type
            query = 'select {0} from {1}'.format(projections, entity_type)

            primary_key_definition = reference_entity.primary_key_attributes
            if len(primary_key_definition) > 1:
                # TODO: Handle composite primary key using a syntax of
                # (pka, pkb) in ((v1a,v1b), (v2a, v2b))
                raise ValueError('Composite primary keys not supported.')

            primary_key = primary_key_definition[0]

            entity_keys = [
                ftrack.inspection.primary_key(entity).values()[0]
                for entity in entities_to_process
            ]

            if len(entity_keys) > 1:
                query = '{0} where {1} in ({2})'.format(
                    query, primary_key, ','.join(map(str, entity_keys))
                )
            else:
                query = '{0} where {1} is {2}'.format(
                    query, primary_key, str(entity_keys[0])
                )

            self.logger.debug('Query: {0!r}'.format(query))
            result = self.query(query)

            # Fetch all results now. Doing so will cause them to populate the
            # relevant entities in the cache.
            result.all()

            # TODO: Should we check that all requested attributes were
            # actually populated? If some weren't would we mark that to avoid
            # repeated calls or perhaps raise an error?

    # TODO: Make atomic.
    def commit(self):
        '''Commit all local changes to the server.'''
        with self.auto_populating(False):

            # Add all deletions in order.
            for entity in self.deleted:
                self._batches['write'].append({
                    'action': 'delete',
                    'entity_type': entity.entity_type,
                    'entity_key': ftrack.inspection.primary_key(entity).values()
                })

            # Add all creations in order.
            for entity in self.created:
                self._batches['write'].append({
                    'action': 'create',
                    'entity_type': entity.entity_type,
                    'entity_data': entity
                })

            # Add all modifications.
            for entity in self.modified:
                self._batches['write'].append({
                    'action': 'update',
                    'entity_type': entity.entity_type,
                    'entity_key': ftrack.inspection.primary_key(entity).values(),
                    'entity_data': entity
                })

        batch = self._batches['write']
        if batch:
            try:
                result = self._call(batch)

            finally:
                # Always clear write batches.
                del self._batches['write'][:]

            # Process result.
            for entry in result:

                if entry['action'] in ('create', 'update'):
                    # Merge returned entities into local cache.
                    self.merge(entry['data'])

                elif entry['action'] == 'delete':
                    # TODO: Expunge entity from cache.
                    pass

            # If successful commit then update states.
            for entity in self.created:
                for attribute in entity.attributes:
                    attribute.set_local_value(entity, ftrack.symbol.NOT_SET)

            for entity in self.modified:
                for attribute in entity.attributes:
                    attribute.set_local_value(entity, ftrack.symbol.NOT_SET)

            self._states['created'].clear()
            self._states['modified'].clear()
            self._states['deleted'].clear()

    def _discover_plugins(self):
        '''Find and load plugins in search paths.

        Each discovered module should implement a register function that
        accepts this session as first argument. Typically the function should
        register appropriate event listeners against the session's event hub.

            def register(session):
                session.event_hub.subscribe(
                    'topic=ftrack.session.construct_entity_type',
                    construct_entity_type
                )

        '''
        ftrack.plugin.discover(self._plugin_paths, [self])

    def _fetch_schemas(self):
        '''Return schemas fetched from server.'''
        result = self._call([{'action': 'query_schemas'}])
        return result[0]

    def _build_entity_type_classes(self, schemas):
        '''Build default entity type classes.'''
        classes = {}

        for schema in schemas:
            results = self.event_hub.publish(
                ftrack.event.base.Event(
                    topic='ftrack.session.construct-entity-type',
                    data=dict(
                        schema=schema,
                        schemas=schemas
                    )
                ),
                synchronous=True
            )

            results = [result for result in results if result is not None]

            if not results:
                raise ValueError(
                    'Expected entity type to represent schema "{0}" but '
                    'received 0 entity types. Ensure '
                    'FTRACK_EVENT_PLUGIN_PATH has been set to point to '
                    'resource/plugin.'.format(
                        schema['id']
                    )
                )

            elif len(results) > 1:
                raise ValueError(
                    'Expected single entity type to represent schema "{0}" but '
                    'received {1} entity types instead.'
                    .format(schema['id'], len(results))
                )

            entity_type_class = results[0]
            classes[entity_type_class.entity_type] = entity_type_class

        return classes

    def _call(self, data):
        '''Make request to server with *data*.'''
        url = self._server_url + '/api'
        headers = {
            'content-type': 'application/json'
        }
        data = self.encode(data, entity_attribute_strategy='modified_only')

        self.logger.debug(
            'Calling server {0} with {1}'.format(url, data)
        )

        response = self._request.post(
            url,
            headers=headers,
            data=data
        )

        self.logger.debug(
            'Call took: {0}'.format(response.elapsed.total_seconds())
        )

        if response.status_code != 200:
            message = (
                'Unanticipated server error occurred. '
                'Please contact support@ftrack.com'
            )

            # TODO: Would be good if the server returned structured errors
            # rather than HTML for error codes so that extraction /
            # reinterpreting is not necessary.
            if response.status_code == 402:
                message = (
                    'Server reported a license error. Please check your server '
                    'license is valid and try again.'
                )

            elif 'Python API is disabled' in response.text:
                message = (
                    'Python API is disabled on the server. Please ask your '
                    'system administrator to enable it.'
                )

            elif response.status_code == 500:
                message = response.text

            raise ftrack.exception.ServerError(message)

        else:
            result = self.decode(response.text)

            if 'exception' in result:
                # Handle exceptions.
                raise ftrack.exception.ServerError(result['content'])

        return result

    def encode(self, data, entity_attribute_strategy='set_only'):
        '''Return *data* encoded as JSON formatted string.

        *entity_attribute_strategy* specifies how entity attributes should be
        handled. The following strategies are available:

        * *all* - Encode all attributes, loading any that are currently NOT_SET.
        * *set_only* - Encode only attributes that are currently set without
          loading any from the remote.
        * *modified_only* - Encode only attributes that have been modified
          locally.

        '''
        entity_attribute_strategies = ('all', 'set_only', 'modified_only')
        if entity_attribute_strategy not in entity_attribute_strategies:
            raise ValueError(
                'Unsupported entity_attribute_strategy "{0}". Must be one of '
                '{1}'.format(
                    entity_attribute_strategy,
                    ', '.join(entity_attribute_strategies)
                )
            )

        return json.dumps(
            data,
            sort_keys=True,
            default=functools.partial(
                self._encode,
                entity_attribute_strategy=entity_attribute_strategy
            )
        )

    def _encode(self, item, entity_attribute_strategy='set_only'):
        '''Return JSON encodable version of *item*.

        *entity_attribute_strategy* specifies how entity attributes should be
        handled. See :meth:`Session.encode` for available strategies.

        '''
        if isinstance(item, (arrow.Arrow, datetime.datetime, datetime.date)):
            return {
                '__type__': 'datetime',
                'value': item.isoformat()
            }

        if isinstance(item, ftrack.entity.base.Entity):
            data = self._entity_reference(item)

            auto_populate = False
            if entity_attribute_strategy == 'all':
                auto_populate = True

            with self.auto_populating(auto_populate):

                for attribute in item.attributes:
                    value = ftrack.symbol.NOT_SET

                    if entity_attribute_strategy in ('all', 'set_only'):
                        # Note: Auto-populate setting ensures correct behaviour
                        # when attribute has not been set.
                        value = attribute.get_value(item)

                    elif entity_attribute_strategy == 'modified_only':
                        if attribute.is_modified(item):
                            value = attribute.get_local_value(item)

                    if value is not ftrack.symbol.NOT_SET:
                        if isinstance(
                            attribute, ftrack.attribute.ReferenceAttribute
                        ):
                            if isinstance(value, ftrack.entity.base.Entity):
                                value = self._entity_reference(value)

                        data[attribute.name] = value

            return data

        if isinstance(item, ftrack.collection.Collection):
            data = []
            for entity in item:
                data.append(self._entity_reference(entity))

            return data

        raise TypeError('{0!r} is not JSON serializable'.format(item))

    def _entity_reference(self, entity):
        '''Return reference to *entity*.

        Return a mapping containing the __entity_type__ of the entity along with
        the key, value pairs that make up it's primary key.

        '''
        reference = {
            '__entity_type__': entity.entity_type
        }
        with self.auto_populating(False):
            reference.update(ftrack.inspection.primary_key(entity))

        return reference

    def decode(self, string):
        '''Return decoded JSON *string* as Python object.'''
        return json.loads(string, object_hook=self._decode)

    def _decode(self, item):
        '''Return *item* transformed into appropriate representation.'''
        if isinstance(item, collections.Mapping):
            if '__type__' in item:
                if item['__type__'] == 'datetime':
                    item = arrow.get(item['value'])

            elif '__entity_type__' in item:
                item = self._create(
                    item['__entity_type__'], item, reconstructing=True
                )

        return item


class AutoPopulatingContext(object):
    '''Context manager for temporary change of session auto_populate value.'''

    def __init__(self, session, auto_populate):
        '''Initialise context.'''
        super(AutoPopulatingContext, self).__init__()
        self._session = session
        self._auto_populate = auto_populate
        self._current_auto_populate = None

    def __enter__(self):
        '''Enter context switching to desired auto populate setting.'''
        self._current_auto_populate = self._session.auto_populate
        self._session.auto_populate = self._auto_populate

    def __exit__(self, exception_type, exception_value, traceback):
        '''Exit context resetting auto populate to original setting.'''
        self._session.auto_populate = self._current_auto_populate
