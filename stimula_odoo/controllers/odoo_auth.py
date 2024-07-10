"""
This script class provides an Odoo specific implementation of the Auth class.

Author: Romke Jonker
Email: romke@rnadesign.net
"""
from stimula.service.auth import Auth

from odoo.modules.registry import Registry
from odoo.service import security


class OdooAuth(Auth):
    # set the secret key during instantiation
    def __init__(self, secret_key):
        super().__init__(secret_key)

    def _validate_submitted_credentials(self, database, username, password):
        registry = Registry(database)

        wsgienv = {}
        uid = registry['res.users'].authenticate(database, username, password, wsgienv)

        # verify odoo credentials
        security.check(database, uid, password)

        return uid

    def _validate_token_credentials(self, database, uid, password):
        # verify odoo credentials
        security.check(database, uid, password)

        # verify we can connect to the db
        Registry(database).check_signaling()

        # return database, uid for the connection and cursor objects
        return database, uid
