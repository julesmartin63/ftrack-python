# :coding: utf-8
# :copyright: Copyright (c) 2015 ftrack

import ftrack_api


def test_update_status(session, new_job):
    '''Test update status on *new_job*'''
    assert new_job['status'] == 'queued'

    new_job['status'] = 'running'
    session.commit()

    new_session = ftrack_api.Session()
    job = new_session.get('Job', new_job['id'])

    assert job['status'] == 'running'


def test_create_job_using_faulty_type(session, user):
    '''Test creating job with faulty type.'''
    job = session.create('Job', {
        'type': 'api_job',
        'user': user,
        'type': 'not-allowed-type'
    })

    session.commit()

    assert job['type'] == 'api_job'
