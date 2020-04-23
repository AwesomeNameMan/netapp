# Copyright (c) 2018 NetApp
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

''' unit tests for module_utils netapp.py '''
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import os.path
import pytest
import tempfile

from ansible.module_utils.ansible_release import __version__ as ansible_version
from ansible.module_utils import basic
from ansible.module_utils._text import to_bytes
from ansible_collections.netapp.ontap.plugins.module_utils.netapp import COLLECTION_VERSION
from ansible_collections.netapp.ontap.tests.unit.compat.mock import patch, Mock

import ansible_collections.netapp.ontap.plugins.module_utils.netapp as netapp_utils

if not netapp_utils.has_netapp_lib():
    pytestmark = pytest.mark.skip("skipping as missing required netapp_lib")

def set_module_args(args):
    """prepare arguments so that they will be picked up during module creation"""
    args = json.dumps({'ANSIBLE_MODULE_ARGS': args})
    basic._ANSIBLE_ARGS = to_bytes(args)  # pylint: disable=protected-access

SRR = {
    # common responses
    'is_rest': (200, {}, None),
    'is_zapi': (400, {}, "Unreachable"),
    'empty_good': ({}, None),
    'end_of_sequence': (None, "Unexpected call to send_request"),
    'generic_error': (None, "Expected error"),
}

class MockONTAPConnection(object):
    ''' mock a server connection to ONTAP host '''

    def __init__(self, kind=None, parm1=None):
        ''' save arguments '''
        self.type = kind
        self.parm1 = parm1
        self.xml_in = None
        self.xml_out = None

    def invoke_successfully(self, xml, enable_tunneling):  # pylint: disable=unused-argument
        ''' mock invoke_successfully returning xml data '''
        self.xml_in = xml
        if self.type == 'vserver':
            xml = self.build_vserver_info(self.parm1)
        self.xml_out = xml
        return xml

    @staticmethod
    def build_vserver_info(vserver):
        ''' build xml data for vserser-info '''
        xml = netapp_utils.zapi.NaElement('xml')
        attributes = netapp_utils.zapi.NaElement('attributes-list')
        attributes.add_node_with_children('vserver-info',
                                          **{'vserver-name': vserver})
        xml.add_child_elem(attributes)
        return xml


def test_ems_log_event_version():
    ''' validate Ansible version is correctly read '''
    source = 'unittest'
    server = MockONTAPConnection()
    netapp_utils.ems_log_event(source, server)
    xml = server.xml_in
    version = xml.get_child_content('app-version')
    if version == ansible_version:
        assert version == ansible_version
    else:
        assert version == COLLECTION_VERSION
    print("Ansible version: %s" % ansible_version)


def test_get_cserver():
    ''' validate cluster vserser name is correctly retrieved '''
    svm_name = 'svm1'
    server = MockONTAPConnection('vserver', svm_name)
    cserver = netapp_utils.get_cserver(server)
    assert cserver == svm_name


def mock_args():
    return {
        'hostname': 'test',
        'username': 'test_user',
        'password': 'test_pass!'
    }


def create_restapi_object(args):
    argument_spec = netapp_utils.na_ontap_host_argument_spec()
    set_module_args(args)
    module = basic.AnsibleModule(argument_spec)
    restApi = netapp_utils.OntapRestAPI(module)
    return restApi


def test_write_to_file():
    ''' check error and debug logs can be written to disk '''
    restApi = create_restapi_object(mock_args())
    # logging an error also add a debug record
    restApi.log_error(404, '404 error')
    print(restApi.errors)
    print(restApi.debug_logs)
    # logging a debug record only
    restApi.log_debug(501, '501 error')
    print(restApi.errors)
    print(restApi.debug_logs)
    
    try:
        tempdir = tempfile.TemporaryDirectory()
        filepath = os.path.join(tempdir.name, 'log.txt')
    except AttributeError:
        # python 2.7 does not support tempfile.TemporaryDirectory
        # we're taking a small chance that there is a race condition
        filepath = '/tmp/deleteme354.txt'
    restApi.write_debug_log_to_file(filepath=filepath, append=False)
    with open(filepath, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 4
        assert lines[0].strip() == 'Debug: 404'
        assert lines[2].strip() == 'Debug: 501'
    
    # Idempotent, as append is False
    restApi.write_debug_log_to_file(filepath=filepath, append=False)
    with open(filepath, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 4
        assert lines[0].strip() == 'Debug: 404'
        assert lines[2].strip() == 'Debug: 501'
    
    # Duplication, as append is True
    restApi.write_debug_log_to_file(filepath=filepath, append=True)
    with open(filepath, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 8
        assert lines[0].strip() == 'Debug: 404'
        assert lines[2].strip() == 'Debug: 501'
        assert lines[4].strip() == 'Debug: 404'
        assert lines[6].strip() == 'Debug: 501'

    restApi.write_errors_to_file(filepath=filepath, append=False)
    with open(filepath, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 1
        assert lines[0].strip() == 'Error: 404 error'
    
    # Idempotent, as append is False
    restApi.write_errors_to_file(filepath=filepath, append=False)
    with open(filepath, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 1
        assert lines[0].strip() == 'Error: 404 error'
    
    # Duplication, as append is True
    restApi.write_errors_to_file(filepath=filepath, append=True)
    with open(filepath, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 2
        assert lines[0].strip() == 'Error: 404 error'
        assert lines[1].strip() == 'Error: 404 error'

    
@patch('ansible_collections.netapp.ontap.plugins.module_utils.netapp.OntapRestAPI.send_request')
def test_is_rest_true(mock_request):
    ''' is_rest is expected to return True '''
    mock_request.side_effect = [
        SRR['is_rest'],
    ]
    restApi = create_restapi_object(mock_args())
    is_rest = restApi.is_rest()
    print(restApi.errors)
    print(restApi.debug_logs)
    assert is_rest


@patch('ansible_collections.netapp.ontap.plugins.module_utils.netapp.OntapRestAPI.send_request')
def test_is_rest_false(mock_request):
    ''' is_rest is expected to return False '''
    mock_request.side_effect = [
        SRR['is_zapi'],
    ]
    restApi = create_restapi_object(mock_args())
    is_rest = restApi.is_rest()
    print(restApi.errors)
    print(restApi.debug_logs)
    assert not is_rest
    assert restApi.errors[0] == SRR['is_zapi'][2]
    assert restApi.debug_logs[0][0] == SRR['is_zapi'][0]    # status_code
    assert restApi.debug_logs[0][1] == SRR['is_zapi'][2]    # error