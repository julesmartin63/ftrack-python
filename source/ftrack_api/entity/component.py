# :coding: utf-8
# :copyright: Copyright (c) 2015 ftrack

import ftrack_api.entity.base


class Component(ftrack_api.entity.base.Entity):
    '''Represent a component.'''

    def get_availability(self, locations=None):
        '''Return availability in *locations*.

        If *locations* is None, all known locations will be checked.

        Return a dictionary of {location_id:percentage_availability}

        '''
        return self.session.get_component_availability(
            self, locations=locations
        )


class CreateThumbnailMixin(object):
    '''Mixin to add create_thumbnail method on entity class.'''

    def create_thumbnail(self, path, data=None):
        '''Set entity thumbnail from *path*.

        Creates a thumbnail component using in the ftrack.server location 
        :meth:`Session.create_component 
        <ftrack_api.session.Session.create_component>` The thumbnail component
        will be created using *data* if specified. If no component name is
        given, `thumbnail` will be used.

        The file is expected to be of an appropriate size and valid file
        type.

        .. note::

            A :meth:`Session.commit<ftrack_api.session.Session.commit>` may be
            automatically issued as part of the components registration in the
            location.

        '''
        if data is None:
            data = {}
        if not data.get('name'):
            data['name'] = 'thumbnail'

        thumbnail_component = self.session.create_component(
            path, data, location=self.session._server_location
        )

        self['thumbnail_id'] = thumbnail_component['id']
        self.session.commit()

        return thumbnail_component
