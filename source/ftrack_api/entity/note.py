# :coding: utf-8
# :copyright: Copyright (c) 2015 ftrack

import ftrack_api.entity.base


class Note(ftrack_api.entity.base.Entity):
    '''Represent a note.'''

    def create_reply(
        self, text, author
    ):
        '''Create a reply with *text* and *author*.

        .. note::

            This is a helper method. To create replies manually use the
            standard :meth:`Session.create` method.

        '''
        reply = self.session.create(
            'Note', {
                'author': author,
                'text': text,
                'parent_id': self['parent_id'],
                'parent_type': self['parent_type'],
                'in_reply_to': self
            }
        )

        self['replies'].append(reply)

        return reply


class CreateNoteMixin(object):
    '''Mixin to add create_note method on entity class.'''

    def create_note(self, text, author, recipients=None, category=None):
        '''Create note with *text*, *author*.

        Note category can be set by including *category* and *recipients*
        can be specified as a list of user or group instances.

        '''
        if not recipients:
            recipients = []

        category_id = None
        if category:
            category_id = category['id']

        data = {
            'text': text,
            'author': author,
            'category_id': category_id,
            'parent_id': self['id'],
            'parent_type': self.entity_type
        }

        note = self.session.create('Note', data)

        self['notes'].append(note)

        for resource in recipients:
            recipient = self.session.create('Recipient', {
                'note_id': note['id'],
                'resource_id': resource['id']
            })

            note['recipients'].append(recipient)

        return note
